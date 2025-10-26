"""User management blueprint for admin UI."""

import logging
from datetime import UTC, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from src.admin.utils import require_tenant_access  # type: ignore[attr-defined]
from src.admin.utils.audit_decorator import log_admin_action
from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant, User

logger = logging.getLogger(__name__)

# Create Blueprint
users_bp = Blueprint("users", __name__, url_prefix="/tenant/<tenant_id>/users")


@users_bp.route("")
@require_tenant_access()
def list_users(tenant_id):
    """List users for a tenant."""
    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            flash("Tenant not found", "error")
            return redirect(url_for("core.index"))

        stmt = select(User).filter_by(tenant_id=tenant_id).order_by(User.email)
        users = db_session.scalars(stmt).all()

        users_list = []
        for user in users:
            users_list.append(
                {
                    "user_id": user.user_id,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                }
            )

        return render_template(
            "tenant_users.html",
            tenant=tenant,
            tenant_id=tenant_id,
            users=users_list,
        )


@users_bp.route("/add", methods=["POST"])
@require_tenant_access()
@log_admin_action(
    "add_user", extract_details=lambda r, **kw: {"email": request.form.get("email"), "role": request.form.get("role")}
)
def add_user(tenant_id):
    """Add a new user to the tenant."""
    try:
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "viewer")

        if not email:
            flash("Email is required", "error")
            return redirect(url_for("users.list_users", tenant_id=tenant_id))

        # Validate email format
        import re

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email format", "error")
            return redirect(url_for("users.list_users", tenant_id=tenant_id))

        with get_db_session() as db_session:
            # Check if user already exists
            existing = db_session.scalars(select(User).filter_by(tenant_id=tenant_id, email=email)).first()
            if existing:
                flash(f"User {email} already exists", "error")
                return redirect(url_for("users.list_users", tenant_id=tenant_id))

            # Create new user
            import uuid

            user = User(
                tenant_id=tenant_id,
                user_id=f"user_{uuid.uuid4().hex[:8]}",
                email=email,
                role=role,
                is_active=True,
                created_at=datetime.now(UTC),
            )

            db_session.add(user)
            db_session.commit()

            flash(f"User {email} added successfully", "success")

    except Exception as e:
        logger.error(f"Error adding user: {e}", exc_info=True)
        flash(f"Error adding user: {str(e)}", "error")

    return redirect(url_for("users.list_users", tenant_id=tenant_id))


@users_bp.route("/<user_id>/toggle", methods=["POST"])
@log_admin_action("toggle_user")
@require_tenant_access()
def toggle_user(tenant_id, user_id):
    """Toggle user active status."""
    try:
        with get_db_session() as db_session:
            user = db_session.scalars(select(User).filter_by(tenant_id=tenant_id, user_id=user_id)).first()
            if not user:
                flash("User not found", "error")
                return redirect(url_for("users.list_users", tenant_id=tenant_id))

            user.is_active = not user.is_active
            db_session.commit()

            status = "activated" if user.is_active else "deactivated"
            flash(f"User {user.email} {status}", "success")

    except Exception as e:
        logger.error(f"Error toggling user: {e}", exc_info=True)
        flash(f"Error toggling user: {str(e)}", "error")

    return redirect(url_for("users.list_users", tenant_id=tenant_id))


@users_bp.route("/<user_id>/update_role", methods=["POST"])
@log_admin_action("update_role")
@require_tenant_access()
def update_role(tenant_id, user_id):
    """Update user role."""
    try:
        new_role = request.form.get("role")
        if not new_role or new_role not in ["admin", "manager", "viewer"]:
            flash("Invalid role", "error")
            return redirect(url_for("users.list_users", tenant_id=tenant_id))

        with get_db_session() as db_session:
            user = db_session.scalars(select(User).filter_by(tenant_id=tenant_id, user_id=user_id)).first()
            if not user:
                flash("User not found", "error")
                return redirect(url_for("users.list_users", tenant_id=tenant_id))

            user.role = new_role
            db_session.commit()

            flash(f"User {user.email} role updated to {new_role}", "success")

    except Exception as e:
        logger.error(f"Error updating user role: {e}", exc_info=True)
        flash(f"Error updating role: {str(e)}", "error")

    return redirect(url_for("users.list_users", tenant_id=tenant_id))
