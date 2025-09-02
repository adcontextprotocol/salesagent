"""Super Admin API for tenant management - Using direct SQL queries."""

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime
from functools import wraps

from flask import Blueprint, jsonify, request

from src.core.database.database_session import get_db_session
from src.core.database.models import (
    AdapterConfig,
    AuditLog,
    MediaBuy,
    Principal,
    Product,
    SuperadminConfig,
    Task,
    Tenant,
    User,
)

logger = logging.getLogger(__name__)

# Create Blueprint
superadmin_api = Blueprint("superadmin_api", __name__, url_prefix="/api/v1/superadmin")


def require_superadmin_api_key(f):
    """Decorator to require super admin API key for access."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-Superadmin-API-Key")

        if not api_key:
            return jsonify({"error": "Missing API key"}), 401

        # Get the stored API key from database
        with get_db_session() as db_session:
            config = db_session.query(SuperadminConfig).filter_by(config_key="superadmin_api_key").first()

            if not config or not config.config_value:
                logger.error("Superadmin API key not configured in database")
                return jsonify({"error": "API not configured"}), 503

            if api_key != config.config_value:
                logger.warning(f"Invalid superadmin API key attempted: {api_key[:8]}...")
                return jsonify({"error": "Invalid API key"}), 401

            return f(*args, **kwargs)

    return decorated_function


@superadmin_api.route("/health", methods=["GET"])
@require_superadmin_api_key
def health_check():
    """Health check endpoint for the super admin API."""
    return jsonify({"status": "healthy", "timestamp": datetime.now(UTC).isoformat()})


@superadmin_api.route("/tenants", methods=["GET"])
@require_superadmin_api_key
def list_tenants():
    """List all tenants."""
    from sqlalchemy import func

    from src.core.database.models import AdapterConfig

    with get_db_session() as db_session:
        try:
            # Query with left join and group by
            tenants_query = (
                db_session.query(
                    Tenant.tenant_id,
                    Tenant.name,
                    Tenant.subdomain,
                    Tenant.is_active,
                    Tenant.billing_plan,
                    Tenant.ad_server,
                    Tenant.created_at,
                    func.count(AdapterConfig.tenant_id).label("has_adapter"),
                )
                .outerjoin(AdapterConfig, Tenant.tenant_id == AdapterConfig.tenant_id)
                .group_by(Tenant.tenant_id)
                .order_by(Tenant.created_at.desc())
            )

            results = []
            for row in tenants_query:
                results.append(
                    {
                        "tenant_id": row.tenant_id,
                        "name": row.name,
                        "subdomain": row.subdomain,
                        "is_active": bool(row.is_active),
                        "billing_plan": row.billing_plan,
                        "ad_server": row.ad_server,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "adapter_configured": bool(row.has_adapter),
                    }
                )

            return jsonify({"tenants": results, "count": len(results)})

        except Exception as e:
            logger.error(f"Error listing tenants: {str(e)}")
            return jsonify({"error": "Failed to list tenants"}), 500


@superadmin_api.route("/tenants", methods=["POST"])
@require_superadmin_api_key
def create_tenant():
    """Create a new tenant."""

    from src.core.database.models import AdapterConfig

    with get_db_session() as db_session:
        try:
            data = request.get_json()

            # Validate required fields
            required_fields = ["name", "subdomain", "ad_server"]
            for field in required_fields:
                if field not in data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400

            # Generate tenant ID
            tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
            admin_token = secrets.token_urlsafe(32)

            # Create tenant
            new_tenant = Tenant(
                tenant_id=tenant_id,
                name=data["name"],
                subdomain=data["subdomain"],
                ad_server=data["ad_server"],
                is_active=data.get("is_active", True),
                billing_plan=data.get("billing_plan", "standard"),
                billing_contact=data.get("billing_contact"),
                max_daily_budget=data.get("max_daily_budget", 10000),
                enable_aee_signals=data.get("enable_aee_signals", True),
                authorized_emails=json.dumps(data.get("authorized_emails", [])),
                authorized_domains=json.dumps(data.get("authorized_domains", [])),
                slack_webhook_url=data.get("slack_webhook_url"),
                slack_audit_webhook_url=data.get("slack_audit_webhook_url"),
                hitl_webhook_url=data.get("hitl_webhook_url"),
                admin_token=admin_token,
                auto_approve_formats=json.dumps(data.get("auto_approve_formats", ["display_300x250"])),
                human_review_required=data.get("human_review_required", True),
                policy_settings=json.dumps(data.get("policy_settings", {})),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(new_tenant)

            # Create adapter config
            adapter_type = data["ad_server"]

            # Insert adapter config with appropriate fields based on type
            if adapter_type == "google_ad_manager":
                new_adapter = AdapterConfig(
                    tenant_id=tenant_id,
                    adapter_type=adapter_type,
                    gam_network_code=data.get("gam_network_code"),
                    gam_refresh_token=data.get("gam_refresh_token"),
                    gam_company_id=data.get("gam_company_id"),
                    gam_trafficker_id=data.get("gam_trafficker_id"),
                    gam_manual_approval_required=data.get("gam_manual_approval_required", False),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            elif adapter_type == "kevel":
                new_adapter = AdapterConfig(
                    tenant_id=tenant_id,
                    adapter_type=adapter_type,
                    kevel_network_id=data.get("kevel_network_id"),
                    kevel_api_key=data.get("kevel_api_key"),
                    kevel_manual_approval_required=data.get("kevel_manual_approval_required", False),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            elif adapter_type == "triton":
                new_adapter = AdapterConfig(
                    tenant_id=tenant_id,
                    adapter_type=adapter_type,
                    triton_station_id=data.get("triton_station_id"),
                    triton_api_key=data.get("triton_api_key"),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            else:  # mock or other
                new_adapter = AdapterConfig(
                    tenant_id=tenant_id,
                    adapter_type=adapter_type,
                    mock_dry_run=data.get("mock_dry_run", False),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )

            db_session.add(new_adapter)

            # Create default principal if requested
            principal_token = None
            if data.get("create_default_principal", True):
                principal_id = f"principal_{uuid.uuid4().hex[:8]}"
                principal_token = secrets.token_urlsafe(32)

                # Add a default platform mapping based on the adapter type
                default_mappings = {}
                if adapter_type == "google_ad_manager":
                    # For GAM, add a placeholder advertiser ID
                    default_mappings = {"google_ad_manager": {"advertiser_id": "placeholder"}}
                elif adapter_type == "kevel":
                    default_mappings = {"kevel": {"advertiser_id": "placeholder"}}
                elif adapter_type == "triton":
                    default_mappings = {"triton": {"advertiser_id": "placeholder"}}
                else:
                    # For mock and others
                    default_mappings = {"mock": {"advertiser_id": "default"}}

                new_principal = Principal(
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    name=f"{data['name']} Default Principal",
                    platform_mappings=json.dumps(default_mappings),
                    access_token=principal_token,
                    created_at=datetime.now(UTC),
                )
                db_session.add(new_principal)

            db_session.commit()

            result = {
                "tenant_id": tenant_id,
                "name": data["name"],
                "subdomain": data["subdomain"],
                "admin_token": admin_token,
                "admin_ui_url": f"http://{data['subdomain']}.localhost:8001/tenant/{tenant_id}",
            }

            if principal_token:
                result["default_principal_token"] = principal_token

            return jsonify(result), 201

        except Exception as e:
            db_session.rollback()
            if "UNIQUE constraint failed: tenants.subdomain" in str(e):
                return jsonify({"error": "Subdomain already exists"}), 409
            logger.error(f"Error creating tenant: {str(e)}")
            return jsonify({"error": "Failed to create tenant"}), 500


@superadmin_api.route("/tenants/<tenant_id>", methods=["GET"])
@require_superadmin_api_key
def get_tenant(tenant_id):
    """Get details for a specific tenant."""
    with get_db_session() as db_session:
        try:
            # Get tenant details
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()

            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            result = {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "subdomain": tenant.subdomain,
                "is_active": bool(tenant.is_active),
                "billing_plan": tenant.billing_plan,
                "billing_contact": tenant.billing_contact,
                "ad_server": tenant.ad_server,
                "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
                "settings": {
                    "max_daily_budget": tenant.max_daily_budget,
                    "enable_aee_signals": bool(tenant.enable_aee_signals),
                    "authorized_emails": tenant.authorized_emails if tenant.authorized_emails else [],
                    "authorized_domains": tenant.authorized_domains if tenant.authorized_domains else [],
                    "slack_webhook_url": tenant.slack_webhook_url,
                    "slack_audit_webhook_url": tenant.slack_audit_webhook_url,
                    "hitl_webhook_url": tenant.hitl_webhook_url,
                    "auto_approve_formats": (tenant.auto_approve_formats if tenant.auto_approve_formats else []),
                    "human_review_required": bool(tenant.human_review_required),
                    "policy_settings": tenant.policy_settings if tenant.policy_settings else {},
                },
            }

            # Get adapter config
            adapter = db_session.query(AdapterConfig).filter_by(tenant_id=tenant_id).first()
            if adapter:
                adapter_data = {
                    "adapter_type": adapter.adapter_type,
                    "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
                }

                if adapter.adapter_type == "google_ad_manager":
                    adapter_data.update(
                        {
                            "gam_network_code": adapter.gam_network_code,
                            "has_refresh_token": bool(adapter.gam_refresh_token),
                            "gam_company_id": adapter.gam_company_id,
                            "gam_trafficker_id": adapter.gam_trafficker_id,
                            "gam_manual_approval_required": bool(adapter.gam_manual_approval_required),
                        }
                    )
                elif adapter.adapter_type == "kevel":
                    adapter_data.update(
                        {
                            "kevel_network_id": adapter.kevel_network_id,
                            "has_api_key": bool(adapter.kevel_api_key),
                            "kevel_manual_approval_required": bool(adapter.kevel_manual_approval_required),
                        }
                    )
                elif adapter.adapter_type == "triton":
                    adapter_data.update(
                        {"triton_station_id": adapter.triton_station_id, "has_api_key": bool(adapter.triton_api_key)}
                    )
                elif adapter.adapter_type == "mock":
                    adapter_data.update({"mock_dry_run": bool(adapter.mock_dry_run)})

                result["adapter_config"] = adapter_data

            # Get principals count
            principals_count = db_session.query(Principal).filter_by(tenant_id=tenant_id).count()
            result["principals_count"] = principals_count

            return jsonify(result)

        except Exception as e:
            logger.error(f"Error getting tenant {tenant_id}: {str(e)}")
            return jsonify({"error": "Failed to get tenant"}), 500


@superadmin_api.route("/tenants/<tenant_id>", methods=["PUT"])
@require_superadmin_api_key
def update_tenant(tenant_id):
    """Update a tenant."""
    with get_db_session() as db_session:
        try:
            # Check if tenant exists
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            data = request.get_json()

            # Update fields based on provided data
            if "name" in data:
                tenant.name = data["name"]
            if "is_active" in data:
                tenant.is_active = data["is_active"]
            if "billing_plan" in data:
                tenant.billing_plan = data["billing_plan"]
            if "billing_contact" in data:
                tenant.billing_contact = data["billing_contact"]
            if "max_daily_budget" in data:
                tenant.max_daily_budget = data["max_daily_budget"]
            if "enable_aee_signals" in data:
                tenant.enable_aee_signals = data["enable_aee_signals"]
            if "authorized_emails" in data:
                tenant.authorized_emails = json.dumps(data["authorized_emails"])
            if "authorized_domains" in data:
                tenant.authorized_domains = json.dumps(data["authorized_domains"])
            if "slack_webhook_url" in data:
                tenant.slack_webhook_url = data["slack_webhook_url"]
            if "slack_audit_webhook_url" in data:
                tenant.slack_audit_webhook_url = data["slack_audit_webhook_url"]
            if "hitl_webhook_url" in data:
                tenant.hitl_webhook_url = data["hitl_webhook_url"]
            if "auto_approve_formats" in data:
                tenant.auto_approve_formats = json.dumps(data["auto_approve_formats"])
            if "human_review_required" in data:
                tenant.human_review_required = data["human_review_required"]
            if "policy_settings" in data:
                tenant.policy_settings = json.dumps(data["policy_settings"])

            # Always update the updated_at timestamp
            tenant.updated_at = datetime.now(UTC)

            # Update adapter config if provided
            if "adapter_config" in data:
                adapter_data = data["adapter_config"]

                # Get current adapter
                adapter = db_session.query(AdapterConfig).filter_by(tenant_id=tenant_id).first()

                if adapter:
                    if adapter.adapter_type == "google_ad_manager":
                        if "gam_network_code" in adapter_data:
                            adapter.gam_network_code = adapter_data["gam_network_code"]
                        if "gam_refresh_token" in adapter_data:
                            adapter.gam_refresh_token = adapter_data["gam_refresh_token"]
                        if "gam_company_id" in adapter_data:
                            adapter.gam_company_id = adapter_data["gam_company_id"]
                        if "gam_trafficker_id" in adapter_data:
                            adapter.gam_trafficker_id = adapter_data["gam_trafficker_id"]
                        if "gam_manual_approval_required" in adapter_data:
                            adapter.gam_manual_approval_required = adapter_data["gam_manual_approval_required"]

                    elif adapter.adapter_type == "kevel":
                        if "kevel_network_id" in adapter_data:
                            adapter.kevel_network_id = adapter_data["kevel_network_id"]
                        if "kevel_api_key" in adapter_data:
                            adapter.kevel_api_key = adapter_data["kevel_api_key"]
                        if "kevel_manual_approval_required" in adapter_data:
                            adapter.kevel_manual_approval_required = adapter_data["kevel_manual_approval_required"]

                    elif adapter.adapter_type == "triton":
                        if "triton_station_id" in adapter_data:
                            adapter.triton_station_id = adapter_data["triton_station_id"]
                        if "triton_api_key" in adapter_data:
                            adapter.triton_api_key = adapter_data["triton_api_key"]

                    elif adapter.adapter_type == "mock":
                        if "mock_dry_run" in adapter_data:
                            adapter.mock_dry_run = adapter_data["mock_dry_run"]

                    adapter.updated_at = datetime.now(UTC)

            db_session.commit()

            return jsonify(
                {
                    "tenant_id": tenant_id,
                    "name": tenant.name,
                    "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
                }
            )

        except Exception as e:
            db_session.rollback()
            logger.error(f"Error updating tenant {tenant_id}: {str(e)}")
            return jsonify({"error": f"Failed to update tenant: {str(e)}"}), 500


@superadmin_api.route("/tenants/<tenant_id>", methods=["DELETE"])
@require_superadmin_api_key
def delete_tenant(tenant_id):
    """Delete a tenant (soft delete by default)."""
    with get_db_session() as db_session:
        try:
            # Check if tenant exists
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404

            # Soft delete by default
            hard_delete = request.args.get("hard_delete", "false").lower() == "true"

            # Check request body for hard_delete flag (not query params)
            data = request.get_json(force=True, silent=True) or {}
            hard_delete = data.get("hard_delete", False)

            if hard_delete:
                # Delete related records first due to foreign key constraints
                db_session.query(AdapterConfig).filter_by(tenant_id=tenant_id).delete()
                db_session.query(Principal).filter_by(tenant_id=tenant_id).delete()
                db_session.query(Product).filter_by(tenant_id=tenant_id).delete()
                db_session.query(MediaBuy).filter_by(tenant_id=tenant_id).delete()
                db_session.query(Task).filter_by(tenant_id=tenant_id).delete()
                db_session.query(AuditLog).filter_by(tenant_id=tenant_id).delete()
                db_session.query(User).filter_by(tenant_id=tenant_id).delete()

                # Finally delete the tenant
                db_session.delete(tenant)
                message = "Tenant and all related data permanently deleted"
            else:
                # Just mark as inactive
                tenant.is_active = False
                tenant.updated_at = datetime.now(UTC)
                message = "Tenant deactivated successfully"

            db_session.commit()

            return jsonify({"message": message, "tenant_id": tenant_id})

        except Exception as e:
            db_session.rollback()
            logger.error(f"Error deleting tenant {tenant_id}: {str(e)}")
            return jsonify({"error": f"Failed to delete tenant: {str(e)}"}), 500


@superadmin_api.route("/init-api-key", methods=["POST"])
def initialize_api_key():
    """Initialize the super admin API key (can only be done once)."""

    with get_db_session() as db_session:
        try:
            # Check if API key already exists
            existing_config = db_session.query(SuperadminConfig).filter_by(config_key="superadmin_api_key").first()

            if existing_config:
                return jsonify({"error": "API key already initialized"}), 409

            # Generate new API key
            api_key = f"sk-{secrets.token_urlsafe(32)}"

            # Store in database
            new_config = SuperadminConfig(
                config_key="superadmin_api_key",
                config_value=api_key,
                description="Super admin API key for tenant management",
                updated_at=datetime.now(UTC),
                updated_by="system",
            )
            db_session.add(new_config)
            db_session.commit()

            return (
                jsonify(
                    {
                        "message": "Super admin API key initialized",
                        "api_key": api_key,
                        "warning": "Save this key securely. It cannot be retrieved again.",
                    }
                ),
                201,
            )

        except Exception as e:
            db_session.rollback()
            logger.error(f"Error initializing API key: {str(e)}")
            return jsonify({"error": "Failed to initialize API key"}), 500
