"""Workflow approval and review blueprint for Admin UI."""

import json
import logging
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.orm import attributes

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import Context, WorkflowStep
from src.core.database.models import Principal as ModelPrincipal

logger = logging.getLogger(__name__)

workflows_bp = Blueprint("workflows", __name__)


@workflows_bp.route("/<tenant_id>/workflows")
@require_tenant_access()
def list_workflows(tenant_id, **kwargs):
    """List all workflows and pending approvals."""
    from src.core.database.models import MediaBuy, Tenant

    with get_db_session() as db:
        # Get tenant
        tenant = db.query(Tenant).filter_by(tenant_id=tenant_id).first()
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
            context = db.query(Context).filter_by(context_id=step.context_id).first()
            principal = None
            if context and context.principal_id:
                principal = (
                    db.query(ModelPrincipal).filter_by(principal_id=context.principal_id, tenant_id=tenant_id).first()
                )

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


@workflows_bp.route("/<tenant_id>/workflows/<workflow_id>/steps/<step_id>/review")
@require_tenant_access()
def review_workflow_step(tenant_id, workflow_id, step_id):
    """Show detailed review page for a workflow step requiring approval."""
    with get_db_session() as db:
        # Get the workflow step with context
        step = (
            db.query(WorkflowStep)
            .join(Context, WorkflowStep.context_id == Context.context_id)
            .filter(WorkflowStep.step_id == step_id, Context.tenant_id == tenant_id)
            .first()
        )

        if not step:
            flash("Workflow step not found", "error")
            return redirect(url_for("tenants.tenant_dashboard", tenant_id=tenant_id))

        # Get the context for tenant/principal info
        context = db.query(Context).filter_by(context_id=step.context_id).first()

        # Get principal info
        principal = None
        if context and context.principal_id:
            principal = (
                db.query(ModelPrincipal).filter_by(principal_id=context.principal_id, tenant_id=tenant_id).first()
            )

        # Parse request data
        request_data = step.request_data if step.request_data else {}

        # Format the data for display
        formatted_request = json.dumps(request_data, indent=2)

        return render_template(
            "workflow_review.html",
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            step=step,
            context=context,
            principal=principal,
            request_data=request_data,
            formatted_request=formatted_request,
        )


@workflows_bp.route("/<tenant_id>/workflows/<workflow_id>/steps/<step_id>/approve", methods=["POST"])
@require_tenant_access()
def approve_workflow_step(tenant_id, workflow_id, step_id):
    """Approve a workflow step."""
    try:
        with get_db_session() as db:
            # Get the workflow step
            step = (
                db.query(WorkflowStep)
                .join(Context, WorkflowStep.context_id == Context.context_id)
                .filter(WorkflowStep.step_id == step_id, Context.tenant_id == tenant_id)
                .first()
            )

            if not step:
                return jsonify({"error": "Workflow step not found"}), 404

            # Update status
            step.status = "approved"
            step.updated_at = datetime.now(UTC)

            # Add approval comment with authenticated user
            user_info = session.get("user", {})
            user_email = user_info.get("email", "system") if isinstance(user_info, dict) else str(user_info)

            if not step.comments:
                step.comments = []
            step.comments.append(
                {"user": user_email, "timestamp": datetime.now(UTC).isoformat(), "comment": "Approved via admin UI"}
            )
            attributes.flag_modified(step, "comments")

            db.commit()

            flash("Workflow step approved successfully", "success")
            return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error approving workflow step {step_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@workflows_bp.route("/<tenant_id>/workflows/<workflow_id>/steps/<step_id>/reject", methods=["POST"])
@require_tenant_access()
def reject_workflow_step(tenant_id, workflow_id, step_id):
    """Reject a workflow step with a reason."""
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "No reason provided")

        with get_db_session() as db:
            # Get the workflow step
            step = (
                db.query(WorkflowStep)
                .join(Context, WorkflowStep.context_id == Context.context_id)
                .filter(WorkflowStep.step_id == step_id, Context.tenant_id == tenant_id)
                .first()
            )

            if not step:
                return jsonify({"error": "Workflow step not found"}), 404

            # Update status
            step.status = "rejected"
            step.updated_at = datetime.now(UTC)

            # Add rejection comment with authenticated user
            user_info = session.get("user", {})
            user_email = user_info.get("email", "system") if isinstance(user_info, dict) else str(user_info)

            if not step.comments:
                step.comments = []
            step.comments.append(
                {"user": user_email, "timestamp": datetime.now(UTC).isoformat(), "comment": f"Rejected: {reason}"}
            )
            attributes.flag_modified(step, "comments")

            db.commit()

            flash("Workflow step rejected", "info")
            return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error rejecting workflow step {step_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
