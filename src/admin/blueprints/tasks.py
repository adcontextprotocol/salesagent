"""Tasks management blueprint for admin UI."""

import logging
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Task

logger = logging.getLogger(__name__)

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tenant/<tenant_id>/tasks")


@tasks_bp.route("/")
@require_tenant_access()
def list_tasks(tenant_id):
    """List all tasks for a tenant."""
    try:
        with get_db_session() as db_session:
            # Get all tasks for this tenant
            tasks = db_session.query(Task).filter_by(tenant_id=tenant_id).order_by(Task.created_at.desc()).all()

            # Separate by status
            pending_tasks = [t for t in tasks if t.status == "pending"]
            completed_tasks = [t for t in tasks if t.status == "completed"]

            return render_template(
                "tasks.html",
                tenant_id=tenant_id,
                pending_tasks=pending_tasks,
                completed_tasks=completed_tasks,
                total_tasks=len(tasks),
            )

    except Exception as e:
        logger.error(f"Error listing tasks: {e}", exc_info=True)
        flash("Error loading tasks", "error")
        return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))


@tasks_bp.route("/<task_id>")
@require_tenant_access()
def view_task(tenant_id, task_id):
    """View task details."""
    try:
        with get_db_session() as db_session:
            task = db_session.query(Task).filter_by(tenant_id=tenant_id, task_id=task_id).first()

            if not task:
                flash("Task not found", "error")
                return redirect(url_for("tasks.list_tasks", tenant_id=tenant_id))

            # Get related media buy if exists
            media_buy = None
            if task.media_buy_id:
                media_buy = (
                    db_session.query(MediaBuy).filter_by(tenant_id=tenant_id, media_buy_id=task.media_buy_id).first()
                )

            # Get principal info if exists
            principal = None
            # Note: Task model doesn't have principal_id field
            # Would need to get from media_buy if needed

            return render_template(
                "task_detail.html", tenant_id=tenant_id, task=task, media_buy=media_buy, principal=principal
            )

    except Exception as e:
        logger.error(f"Error viewing task: {e}", exc_info=True)
        flash("Error loading task", "error")
        return redirect(url_for("tasks.list_tasks", tenant_id=tenant_id))


@tasks_bp.route("/<task_id>/approve", methods=["GET", "POST"])
@require_tenant_access()
def approve_task(tenant_id, task_id):
    """Approve or reject a task."""
    try:
        with get_db_session() as db_session:
            task = db_session.query(Task).filter_by(tenant_id=tenant_id, task_id=task_id).first()

            if not task:
                flash("Task not found", "error")
                return redirect(url_for("tasks.list_tasks", tenant_id=tenant_id))

            if task.status != "pending":
                flash("Task is not pending approval", "warning")
                return redirect(url_for("tasks.view_task", tenant_id=tenant_id, task_id=task_id))

            if request.method == "POST":
                action = request.form.get("action")
                notes = request.form.get("notes", "")

                if action == "approve":
                    task.status = "completed"
                    task.resolution = "approved"
                    task.resolution_notes = notes
                    task.resolved_by = request.session.get("user", {}).get("email", "admin")
                    task.resolved_at = datetime.now(UTC)
                    flash("Task approved successfully", "success")

                    # Log approval
                    from src.core.audit_logger import get_audit_logger

                    audit_logger = get_audit_logger("Admin", tenant_id)
                    audit_logger.log_operation(
                        operation="approve_task",
                        principal_name=task.resolved_by,
                        principal_id=task.resolved_by,
                        adapter_id="admin",
                        success=True,
                        details={
                            "task_id": task_id,
                            "task_type": task.task_type,
                            "resolution": "approved",
                            "notes": notes,
                        },
                    )

                elif action == "reject":
                    task.status = "completed"
                    task.resolution = "rejected"
                    task.resolution_notes = notes
                    task.resolved_by = request.session.get("user", {}).get("email", "admin")
                    task.resolved_at = datetime.now(UTC)
                    flash("Task rejected", "info")

                    # Log rejection
                    from src.core.audit_logger import get_audit_logger

                    audit_logger = get_audit_logger("Admin", tenant_id)
                    audit_logger.log_operation(
                        operation="reject_task",
                        principal_name=task.resolved_by,
                        principal_id=task.resolved_by,
                        adapter_id="admin",
                        success=True,
                        details={
                            "task_id": task_id,
                            "task_type": task.task_type,
                            "resolution": "rejected",
                            "notes": notes,
                        },
                    )

                db_session.commit()

                # If this was a media buy approval, update the media buy status
                if task.task_type == "manual_approval" and task.media_buy_id and action == "approve":
                    media_buy = (
                        db_session.query(MediaBuy)
                        .filter_by(tenant_id=tenant_id, media_buy_id=task.media_buy_id)
                        .first()
                    )
                    if media_buy and media_buy.status == "pending":
                        media_buy.status = "active"
                        db_session.commit()
                        flash("Media buy activated", "success")

                return redirect(url_for("tasks.list_tasks", tenant_id=tenant_id))

            # GET request - show approval form
            # Get related objects for context
            media_buy = None
            if task.media_buy_id:
                media_buy = (
                    db_session.query(MediaBuy).filter_by(tenant_id=tenant_id, media_buy_id=task.media_buy_id).first()
                )

            principal = None
            # Note: Task model doesn't have principal_id field
            # Would need to get from media_buy if needed

            return render_template(
                "task_approve.html", tenant_id=tenant_id, task=task, media_buy=media_buy, principal=principal
            )

    except Exception as e:
        logger.error(f"Error processing task approval: {e}", exc_info=True)
        flash("Error processing task", "error")
        return redirect(url_for("tasks.list_tasks", tenant_id=tenant_id))


@tasks_bp.route("/api/pending")
@require_tenant_access()
def api_pending_tasks(tenant_id):
    """API endpoint to get pending tasks count."""
    try:
        with get_db_session() as db_session:
            pending_count = db_session.query(Task).filter_by(tenant_id=tenant_id, status="pending").count()

            return jsonify({"count": pending_count})

    except Exception as e:
        logger.error(f"Error getting pending tasks: {e}", exc_info=True)
        return jsonify({"error": "Failed to get pending tasks"}), 500
