"""Operations management blueprint."""

import logging

from flask import Blueprint, jsonify
from sqlalchemy import select

from src.admin.utils import require_auth, require_tenant_access

logger = logging.getLogger(__name__)

# Create blueprint
operations_bp = Blueprint("operations", __name__)


@operations_bp.route("/targeting", methods=["GET"])
@require_tenant_access()
def targeting(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


# @operations_bp.route("/inventory", methods=["GET"])
# @require_tenant_access()
# def inventory(tenant_id, **kwargs):
#     """TODO: Extract implementation from admin_ui.py."""
#     # Placeholder implementation - DISABLED: Conflicts with inventory_bp.inventory_browser route
#     return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/orders", methods=["GET"])
@require_tenant_access()
def orders(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501


@operations_bp.route("/reporting", methods=["GET"])
@require_auth()
def reporting(tenant_id):
    """Display GAM reporting dashboard."""
    # Import needed for this function
    from flask import render_template, session

    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    # Verify tenant access
    if session.get("role") != "super_admin" and session.get("tenant_id") != tenant_id:
        return "Access denied", 403

    with get_db_session() as db_session:
        tenant_obj = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()

        if not tenant_obj:
            return "Tenant not found", 404

        # Convert to dict for template compatibility
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "ad_server": tenant_obj.ad_server,
            "subdomain": tenant_obj.subdomain,
            "is_active": tenant_obj.is_active,
        }

        # Check if tenant is using Google Ad Manager
        if tenant_obj.ad_server != "google_ad_manager":
            return (
                render_template(
                    "error.html",
                    error_title="GAM Reporting Not Available",
                    error_message=f"This tenant is currently using {tenant_obj.ad_server or 'no ad server'}. GAM Reporting is only available for tenants using Google Ad Manager.",
                    back_url=f"/tenant/{tenant_id}",
                ),
                400,
            )

        return render_template("gam_reporting.html", tenant=tenant)


@operations_bp.route("/workflows", methods=["GET"])
@require_tenant_access()
def workflows(tenant_id, **kwargs):
    """List all workflows and pending approvals."""
    from flask import render_template

    from src.core.database.database_session import get_db_session
    from src.core.database.models import Context, MediaBuy, Tenant, WorkflowStep
    from src.core.database.models import Principal as ModelPrincipal

    with get_db_session() as db:
        # Get tenant
        tenant = db.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return "Tenant not found", 404

        # Get all workflow steps that need attention
        pending_steps = (
            db.query(WorkflowStep)
            .join(Context, WorkflowStep.context_id == Context.context_id)
            .filter(Context.tenant_id == tenant_id, WorkflowStep.status == "pending_approval")
            .order_by(WorkflowStep.created_at.desc())
            .all()
        )

        # Get media buys for context
        media_buys = db.query(MediaBuy).filter_by(tenant_id=tenant_id).order_by(MediaBuy.created_at.desc()).all()

        # Build summary stats
        summary = {
            "active_buys": len([mb for mb in media_buys if mb.status == "active"]),
            "pending_tasks": len(pending_steps),
            "completed_today": 0,  # TODO: Calculate from workflow history
            "total_spend": sum(mb.budget or 0 for mb in media_buys if mb.status == "active"),
        }

        # Format workflow steps for display
        workflows_list = []
        for step in pending_steps:
            context = db.scalars(select(Context).filter_by(context_id=step.context_id)).first()
            principal = None
            if context and context.principal_id:
                principal = db.scalars(
                    select(ModelPrincipal).filter_by(principal_id=context.principal_id, tenant_id=tenant_id)
                ).first()

            workflows_list.append(
                {
                    "step_id": step.step_id,
                    "workflow_id": step.workflow_id,
                    "step_name": step.step_name,
                    "status": step.status,
                    "created_at": step.created_at,
                    "principal_name": principal.name if principal else "Unknown",
                    "request_data": step.request_data,
                }
            )

        return render_template(
            "workflows.html",
            tenant=tenant,
            tenant_id=tenant_id,
            summary=summary,
            workflows=workflows_list,
            media_buys=media_buys,
            tasks=[],  # Deprecated - using workflow_steps now
            audit_logs=[],  # Will be populated if needed
        )


@operations_bp.route("/media-buy/<media_buy_id>", methods=["GET"])
@require_tenant_access()
def media_buy_detail(tenant_id, media_buy_id):
    """View media buy details."""
    from flask import render_template

    from src.core.database.database_session import get_db_session
    from src.core.database.models import MediaBuy, Principal

    try:
        with get_db_session() as db_session:
            media_buy = db_session.scalars(
                select(MediaBuy).filter_by(tenant_id=tenant_id, media_buy_id=media_buy_id)
            ).first()

            if not media_buy:
                return "Media buy not found", 404

            # Get principal info
            principal = None
            if media_buy.principal_id:
                stmt = select(Principal).filter_by(tenant_id=tenant_id, principal_id=media_buy.principal_id)
            principal = db_session.scalars(stmt).first()

            return render_template(
                "media_buy_detail.html", tenant_id=tenant_id, media_buy=media_buy, principal=principal
            )
    except Exception as e:
        logger.error(f"Error viewing media buy: {e}", exc_info=True)
        return "Error loading media buy", 500


@operations_bp.route("/media-buy/<media_buy_id>/approve", methods=["GET"])
@require_tenant_access()
def media_buy_media_buy_id_approve(tenant_id, **kwargs):
    """TODO: Extract implementation from admin_ui.py."""
    # Placeholder implementation
    return jsonify({"error": "Not yet implemented"}), 501
