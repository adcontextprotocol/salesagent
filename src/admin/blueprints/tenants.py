"""Tenant management blueprint for admin UI.

⚠️ ROUTING NOTICE: This file contains the ACTUAL handler for tenant settings!
- URL: /admin/tenant/{id}/settings
- Function: settings()
- DO NOT confuse with src/admin/blueprints/settings.py which handles superadmin settings
"""

import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import and_

from src.admin.utils import get_tenant_config_from_db, require_auth, require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Principal, Product, Tenant, User
from src.core.validation import sanitize_form_data, validate_form_data

logger = logging.getLogger(__name__)

# Create Blueprint
tenants_bp = Blueprint("tenants", __name__, url_prefix="/tenant")


@tenants_bp.route("/<tenant_id>")
@require_tenant_access()
def dashboard(tenant_id):
    """Show tenant dashboard."""
    try:
        with get_db_session() as db_session:
            # Get tenant info
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Get stats
            active_campaigns = db_session.query(MediaBuy).filter_by(tenant_id=tenant_id, status="active").count()

            total_spend = (
                db_session.query(MediaBuy)
                .filter_by(tenant_id=tenant_id)
                .filter(MediaBuy.status.in_(["active", "completed"]))
                .all()
            )
            total_spend_amount = float(sum(buy.budget or 0 for buy in total_spend))

            principals_count = db_session.query(Principal).filter_by(tenant_id=tenant_id).count()

            products_count = db_session.query(Product).filter_by(tenant_id=tenant_id).count()

            # Get recent media buys - use outerjoin to handle missing principals
            recent_buys = (
                db_session.query(MediaBuy, Principal)
                .outerjoin(
                    Principal,
                    and_(MediaBuy.principal_id == Principal.principal_id, MediaBuy.tenant_id == Principal.tenant_id),
                )
                .filter(MediaBuy.tenant_id == tenant_id)
                .order_by(MediaBuy.created_at.desc())
                .limit(10)
                .all()
            )

            # Get tenant config for features
            config = get_tenant_config_from_db(tenant_id)
            features = config.get("features", {})

            # Get recent revenue data for chart
            from datetime import timedelta

            today = datetime.now(UTC).date()
            revenue_data = []

            for i in range(30):
                date = today - timedelta(days=29 - i)
                # Calculate revenue for this date
                daily_buys = (
                    db_session.query(MediaBuy)
                    .filter_by(tenant_id=tenant_id)
                    .filter(MediaBuy.start_date <= date)
                    .filter(MediaBuy.end_date >= date)
                    .filter(MediaBuy.status.in_(["active", "completed"]))
                    .all()
                )

                daily_revenue = 0
                for buy in daily_buys:
                    if buy.start_date and buy.end_date:
                        days_in_flight = (buy.end_date - buy.start_date).days + 1
                        if days_in_flight > 0:
                            daily_revenue += float(buy.budget or 0) / days_in_flight

                revenue_data.append({"date": date.isoformat(), "revenue": round(daily_revenue, 2)})

            # Calculate revenue change (comparing last 7 days to previous 7 days)
            last_week_revenue = sum(d["revenue"] for d in revenue_data[-7:])
            previous_week_revenue = sum(d["revenue"] for d in revenue_data[-14:-7]) if len(revenue_data) >= 14 else 0
            revenue_change = (
                ((last_week_revenue - previous_week_revenue) / previous_week_revenue * 100)
                if previous_week_revenue > 0
                else 0
            )

            # Calculate pending buys
            pending_buys = db_session.query(MediaBuy).filter_by(tenant_id=tenant_id, status="pending").count()

            # Calculate tasks metrics from the Task table
            from src.core.database.models import Task

            open_tasks = db_session.query(Task).filter_by(tenant_id=tenant_id, status="pending").count()

            # Calculate overdue tasks (tasks past their due date)
            overdue_tasks = (
                db_session.query(Task)
                .filter(Task.tenant_id == tenant_id, Task.status == "pending", Task.due_date < datetime.now(UTC))
                .count()
            )

            # Calculate advertiser metrics
            active_advertisers = db_session.query(Principal).filter_by(tenant_id=tenant_id).count()

            # Calculate metrics for the template
            metrics = {
                "total_revenue": total_spend_amount,
                "active_buys": active_campaigns,
                "pending_buys": pending_buys,
                "pending_approvals": 0,  # Could be calculated from tasks if needed
                "conversion_rate": 0.0,  # Could be calculated from actual data
                "revenue_change": round(revenue_change, 1),
                "revenue_change_abs": round(abs(revenue_change), 1),  # Absolute value for display
                "open_tasks": open_tasks,
                "overdue_tasks": overdue_tasks,
                "active_advertisers": active_advertisers,
                "total_advertisers": active_advertisers,  # Same for now, could differentiate active vs total
            }

            # Prepare chart data for template
            chart_labels = [d["date"] for d in revenue_data]
            chart_data = [d["revenue"] for d in revenue_data]

            # Transform recent_buys tuples to list of MediaBuy objects with extra properties
            recent_media_buys_list = []
            for media_buy, _principal in recent_buys:
                # TODO: Calculate actual spend from delivery data when available
                media_buy.spend = 0

                # TODO: Calculate relative time properly with timezone handling
                media_buy.created_at_relative = (
                    media_buy.created_at.strftime("%Y-%m-%d") if media_buy.created_at else "Unknown"
                )

                recent_media_buys_list.append(media_buy)

            return render_template(
                "tenant_dashboard.html",
                tenant=tenant,
                tenant_id=tenant_id,
                active_campaigns=active_campaigns,
                total_spend=total_spend_amount,
                principals_count=principals_count,
                products_count=products_count,
                recent_buys=recent_buys,
                recent_media_buys=recent_media_buys_list,  # Pass transformed list
                features=features,
                revenue_data=json.dumps(revenue_data),
                chart_labels=chart_labels,
                chart_data=chart_data,
                metrics=metrics,
            )

    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        logger.error(f"Error loading tenant dashboard: {e}\nFull traceback:\n{error_detail}")
        # Show more specific error in development/debugging
        if os.environ.get("DEBUG_ERRORS") == "true":
            flash(f"Error loading dashboard: {str(e)}", "error")
        else:
            flash("Error loading dashboard", "error")
        return redirect(url_for("core.index"))


@tenants_bp.route("/<tenant_id>/settings")
@tenants_bp.route("/<tenant_id>/settings/<section>")
@require_tenant_access()
def tenant_settings(tenant_id, section=None):
    """Show tenant settings page.

    ⚠️ IMPORTANT: This is the ACTUAL handler for /admin/tenant/{id}/settings URLs.
    Function renamed from settings() to tenant_settings() for clarity.

    This function handles the main tenant settings UI including:
    - Adapter selection and configuration
    - GAM OAuth status
    - Template rendering with active_adapter variable
    """
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Get adapter config
            adapter_config_obj = tenant.adapter_config

            # Get active adapter - this was missing!
            active_adapter = None
            if tenant.ad_server:
                active_adapter = tenant.ad_server
            elif adapter_config_obj and adapter_config_obj.adapter_type:
                active_adapter = adapter_config_obj.adapter_type

            # Get OAuth status for GAM
            oauth_configured = False
            if adapter_config_obj and adapter_config_obj.adapter_type == "google_ad_manager":
                oauth_configured = bool(adapter_config_obj.gam_refresh_token)

            # Get advertiser data for the advertisers section
            from src.core.database.models import Principal

            principals = db_session.query(Principal).filter_by(tenant_id=tenant_id).all()
            advertiser_count = len(principals)
            active_advertisers = len(principals)  # For now, assume all are active

            # Get additional variables that the template expects
            last_sync_time = None  # Could be enhanced to track actual sync times

            # Convert adapter_config to dict format for template compatibility
            adapter_config_dict = {}
            if adapter_config_obj:
                adapter_config_dict = {
                    "network_code": adapter_config_obj.gam_network_code or "",
                    "refresh_token": adapter_config_obj.gam_refresh_token or "",
                    "trafficker_id": adapter_config_obj.gam_trafficker_id or "",
                    "application_name": getattr(adapter_config_obj, "gam_application_name", "") or "",
                }

            return render_template(
                "tenant_settings.html",
                tenant=tenant,
                tenant_id=tenant_id,
                section=section or "general",
                active_adapter=active_adapter,
                adapter_config=adapter_config_dict,  # Use dict format
                oauth_configured=oauth_configured,
                last_sync_time=last_sync_time,
                principals=principals,
                advertiser_count=advertiser_count,
                active_advertisers=active_advertisers,
            )

    except Exception as e:
        logger.error(f"Error loading tenant settings: {e}", exc_info=True)
        flash("Error loading settings", "error")
        return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/update", methods=["POST"])
@require_tenant_access()
def update(tenant_id):
    """Update tenant settings."""
    try:
        # Sanitize form data
        form_data = sanitize_form_data(request.form.to_dict())

        # Validate form data
        is_valid, errors = validate_form_data(form_data, ["name", "subdomain"])
        if not is_valid:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("tenants.settings", tenant_id=tenant_id))

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Update tenant
            tenant.name = form_data.get("name", tenant.name)
            tenant.subdomain = form_data.get("subdomain", tenant.subdomain)
            tenant.billing_plan = form_data.get("billing_plan", tenant.billing_plan)
            tenant.updated_at = datetime.now(UTC)

            db_session.commit()
            flash("Tenant settings updated successfully", "success")

    except Exception as e:
        logger.error(f"Error updating tenant: {e}", exc_info=True)
        flash("Error updating tenant", "error")

    return redirect(url_for("tenants.settings", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/update_slack", methods=["POST"])
@require_tenant_access()
def update_slack(tenant_id):
    """Update tenant Slack settings."""
    try:
        # Sanitize form data
        form_data = sanitize_form_data(request.form.to_dict())
        webhook_url = form_data.get("slack_webhook_url", "").strip()

        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Update Slack webhook
            tenant.slack_webhook_url = webhook_url if webhook_url else None
            tenant.updated_at = datetime.now(UTC)

            db_session.commit()
            flash("Slack settings updated successfully", "success")

    except Exception as e:
        logger.error(f"Error updating Slack settings: {e}", exc_info=True)
        flash("Error updating Slack settings", "error")

    return redirect(url_for("tenants.settings", tenant_id=tenant_id, section="slack"))


@tenants_bp.route("/<tenant_id>/test_slack", methods=["POST"])
@require_tenant_access()
def test_slack(tenant_id):
    """Test Slack webhook."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                return jsonify({"success": False, "error": "Tenant not found"}), 404

            if not tenant.slack_webhook_url:
                return jsonify({"success": False, "error": "No Slack webhook configured"}), 400

            # Send test message
            import requests

            response = requests.post(
                tenant.slack_webhook_url,
                json={
                    "text": f"🎉 Test message from AdCP Sales Agent for {tenant.name}",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Test Notification*\nThis is a test message from the AdCP Sales Agent for *{tenant.name}*.",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"Sent at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                                }
                            ],
                        },
                    ],
                },
                timeout=5,
            )

            if response.status_code == 200:
                return jsonify({"success": True, "message": "Test message sent successfully"})
            else:
                return (
                    jsonify(
                        {"success": False, "error": f"Slack returned status {response.status_code}: {response.text}"}
                    ),
                    400,
                )

    except requests.exceptions.RequestException as e:
        logger.error(f"Error testing Slack webhook: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error testing Slack: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Internal server error"}), 500


@tenants_bp.route("/<tenant_id>/update", methods=["POST"])
@require_auth()
def update_tenant(tenant_id):
    """Update tenant configuration."""
    # Check access based on role
    if session.get("role") == "viewer":
        return "Access denied. Viewers cannot update configuration.", 403

    # Check if user is trying to update another tenant
    if session.get("role") in ["admin", "manager", "tenant_admin"] and session.get("tenant_id") != tenant_id:
        return "Access denied. You can only update your own tenant.", 403

    with get_db_session() as db_session:
        try:
            # Get form data for individual fields
            max_daily_budget = request.form.get("max_daily_budget", type=int)
            enable_aee_signals = request.form.get("enable_aee_signals") == "true"
            human_review_required = request.form.get("human_review_required") == "true"

            # Find and update tenant
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if tenant:
                tenant.max_daily_budget = max_daily_budget
                tenant.enable_aee_signals = enable_aee_signals
                tenant.human_review_required = human_review_required
                tenant.updated_at = datetime.now().isoformat()

                db_session.commit()
                flash("Configuration updated successfully", "success")
            else:
                flash("Tenant not found", "error")

            return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))
        except Exception as e:
            flash(f"Error updating configuration: {str(e)}", "error")
            return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/users")
@require_tenant_access()
def list_users(tenant_id):
    """List users for a tenant."""
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            users = (
                db_session.query(User).filter_by(tenant_id=tenant_id).order_by(User.is_admin.desc(), User.email).all()
            )

            return render_template(
                "users.html",
                tenant=tenant,
                tenant_id=tenant_id,
                users=users,
            )

    except Exception as e:
        logger.error(f"Error loading users: {e}", exc_info=True)
        flash("Error loading users", "error")
        return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/users/add", methods=["POST"])
@require_tenant_access()
def add_user(tenant_id):
    """Add a new user to tenant."""
    try:
        # Sanitize form data
        form_data = sanitize_form_data(request.form.to_dict())

        # Validate form data
        is_valid, errors = validate_form_data(form_data, ["email", "name"])
        if not is_valid:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("tenants.list_users", tenant_id=tenant_id))

        with get_db_session() as db_session:
            # Check if user already exists
            existing = db_session.query(User).filter_by(tenant_id=tenant_id, email=form_data["email"].lower()).first()
            if existing:
                flash("User already exists", "error")
                return redirect(url_for("tenants.list_users", tenant_id=tenant_id))

            # Create new user
            user = User(
                user_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                email=form_data["email"].lower(),
                name=form_data["name"],
                is_admin=form_data.get("is_admin") == "on",
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(user)
            db_session.commit()

            flash(f"User {user.email} added successfully", "success")

    except Exception as e:
        logger.error(f"Error adding user: {e}", exc_info=True)
        flash("Error adding user", "error")

    return redirect(url_for("tenants.list_users", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/users/<user_id>/toggle", methods=["POST"])
@require_tenant_access()
def toggle_user(tenant_id, user_id):
    """Toggle user active status."""
    try:
        with get_db_session() as db_session:
            user = db_session.query(User).filter_by(tenant_id=tenant_id, user_id=user_id).first()
            if not user:
                flash("User not found", "error")
                return redirect(url_for("tenants.list_users", tenant_id=tenant_id))

            user.is_active = not user.is_active
            user.updated_at = datetime.now(UTC)
            db_session.commit()

            status = "activated" if user.is_active else "deactivated"
            flash(f"User {user.email} {status}", "success")

    except Exception as e:
        logger.error(f"Error toggling user: {e}", exc_info=True)
        flash("Error updating user", "error")

    return redirect(url_for("tenants.list_users", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/users/<user_id>/update_role", methods=["POST"])
@require_tenant_access()
def update_user_role(tenant_id, user_id):
    """Update user admin role."""
    try:
        with get_db_session() as db_session:
            user = db_session.query(User).filter_by(tenant_id=tenant_id, user_id=user_id).first()
            if not user:
                flash("User not found", "error")
                return redirect(url_for("tenants.list_users", tenant_id=tenant_id))

            user.is_admin = request.form.get("is_admin") == "on"
            user.updated_at = datetime.now(UTC)
            db_session.commit()

            role = "admin" if user.is_admin else "user"
            flash(f"User {user.email} updated to {role}", "success")

    except Exception as e:
        logger.error(f"Error updating user role: {e}", exc_info=True)
        flash("Error updating user", "error")

    return redirect(url_for("tenants.list_users", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/principals/create", methods=["GET", "POST"])
@require_tenant_access()
def create_principal(tenant_id):
    """Create a new principal (advertiser) for the tenant."""
    if request.method == "POST":
        try:
            # Sanitize form data
            form_data = sanitize_form_data(request.form.to_dict())

            # Validate form data
            is_valid, errors = validate_form_data(form_data, ["name"])
            if not is_valid:
                for error in errors:
                    flash(error, "error")
                    return redirect(url_for("tenants.create_principal", tenant_id=tenant_id))

            with get_db_session() as db_session:
                # Create principal
                principal_id = f"principal_{uuid.uuid4().hex[:8]}"
                access_token = secrets.token_urlsafe(32)

                # Build platform mappings based on adapter
                platform_mappings = {}

                # Get tenant to check adapter type
                tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
                if tenant and tenant.adapter_config:
                    adapter_config_obj = tenant.adapter_config

                    if adapter_config_obj.adapter_type == "google_ad_manager":
                        # Get GAM advertiser ID from form
                        gam_advertiser_id = form_data.get("gam_advertiser_id", "").strip()
                        if gam_advertiser_id:
                            platform_mappings["google_ad_manager"] = {
                                "advertiser_id": gam_advertiser_id,
                                "advertiser_name": form_data.get("gam_advertiser_name", ""),
                            }
                        else:
                            # GAM but no advertiser ID provided, use default
                            platform_mappings["google_ad_manager"] = {
                                "advertiser_id": f"gam_{principal_id[:8]}",
                                "advertiser_name": form_data["name"],
                            }
                    elif adapter_config_obj.adapter_type == "mock":
                        # For mock adapter, create a default mapping
                        platform_mappings["mock"] = {
                            "advertiser_id": f"mock_adv_{principal_id[:8]}",
                            "advertiser_name": form_data["name"],
                        }
                    else:
                        # For other adapters, create a basic mapping
                        platform_mappings[adapter_config_obj.adapter_type] = {
                            "advertiser_id": f"{adapter_config_obj.adapter_type}_{principal_id[:8]}",
                            "advertiser_name": form_data["name"],
                        }
                else:
                    # Default to mock if no adapter configured
                    platform_mappings["mock"] = {
                        "advertiser_id": f"mock_adv_{principal_id[:8]}",
                        "advertiser_name": form_data["name"],
                    }

                principal = Principal(
                    principal_id=principal_id,
                    tenant_id=tenant_id,
                    name=form_data["name"],
                    access_token=access_token,
                    platform_mappings=json.dumps(platform_mappings),  # Always provide JSON, even if empty dict
                    created_at=datetime.now(UTC),
                )
                db_session.add(principal)
                db_session.commit()

                flash(f"Advertiser '{principal.name}' created successfully", "success")
                return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))

        except Exception as e:
            logger.error(f"Error creating principal: {e}", exc_info=True)
            flash("Error creating advertiser", "error")
            return redirect(url_for("tenants.create_principal", tenant_id=tenant_id))

    # GET request - show form
    try:
        with get_db_session() as db_session:
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            if not tenant:
                flash("Tenant not found", "error")
                return redirect(url_for("core.index"))

            # Check if GAM is enabled
            gam_enabled = False
            if tenant.adapter_config:
                gam_enabled = tenant.adapter_config.adapter_type == "google_ad_manager"

            return render_template(
                "create_principal.html",
                tenant=tenant,
                tenant_id=tenant_id,
                gam_enabled=gam_enabled,
            )

    except Exception as e:
        logger.error(f"Error loading create principal form: {e}", exc_info=True)
        flash("Error loading form", "error")
        return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@tenants_bp.route("/<tenant_id>/principal/<principal_id>/update_mappings", methods=["POST"])
@require_tenant_access()
def update_principal_mappings(tenant_id, principal_id):
    """Update principal platform mappings."""
    try:
        # Sanitize form data
        form_data = sanitize_form_data(request.form.to_dict())

        with get_db_session() as db_session:
            principal = db_session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=principal_id).first()
            if not principal:
                return jsonify({"error": "Principal not found"}), 404

            # Parse existing mappings
            platform_mappings = json.loads(principal.platform_mappings) if principal.platform_mappings else {}

            # Update mappings based on form data
            for key, value in form_data.items():
                if key.startswith("mapping_"):
                    parts = key.split("_", 2)
                    if len(parts) == 3:
                        platform = parts[1]
                        field = parts[2]
                        if platform not in platform_mappings:
                            platform_mappings[platform] = {}
                        platform_mappings[platform][field] = value

            # Save updated mappings
            principal.platform_mappings = json.dumps(platform_mappings)
            principal.updated_at = datetime.now(UTC)
            db_session.commit()

            return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error updating principal mappings: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@tenants_bp.route("/<tenant_id>/principals/<principal_id>/delete", methods=["DELETE"])
@require_tenant_access()
def delete_principal(tenant_id, principal_id):
    """Delete a principal/advertiser."""
    try:
        with get_db_session() as db_session:
            # Find the principal
            principal = db_session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=principal_id).first()

            if not principal:
                return jsonify({"error": "Principal not found"}), 404

            # Check if principal has active media buys
            from src.core.database.models import MediaBuy

            active_buys = (
                db_session.query(MediaBuy)
                .filter_by(tenant_id=tenant_id, principal_id=principal_id)
                .filter(MediaBuy.status.in_(["active", "pending"]))
                .count()
            )

            if active_buys > 0:
                return jsonify({"error": f"Cannot delete principal with {active_buys} active media buys"}), 400

            # Delete the principal
            db_session.delete(principal)
            db_session.commit()

            return jsonify({"success": True, "message": f"Principal {principal.name} deleted successfully"})

    except Exception as e:
        logger.error(f"Error deleting principal {principal_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
