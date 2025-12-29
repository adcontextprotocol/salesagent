"""Setup blueprint for first-time tenant configuration.

Handles the bootstrap flow when no users exist for a tenant.
"""

import logging
import uuid
from datetime import UTC, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, select

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant, User
from src.services.passkey_service import (
    create_registration_options,
    verify_and_save_registration,
)

logger = logging.getLogger(__name__)

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")


def tenant_needs_setup(tenant_id: str) -> bool:
    """Check if a tenant has no users and needs initial setup."""
    with get_db_session() as db_session:
        stmt = select(func.count()).select_from(User).filter_by(tenant_id=tenant_id)
        user_count = db_session.execute(stmt).scalar() or 0
        return user_count == 0


def get_tenant_for_setup(tenant_id: str) -> Tenant | None:
    """Get tenant if it exists and needs setup."""
    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return None
        if not tenant_needs_setup(tenant_id):
            return None
        return tenant


@setup_bp.route("/<tenant_id>")
def setup_page(tenant_id: str):
    """Show the initial setup page for a tenant.

    This page is only accessible when the tenant has no users.
    """
    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            flash("Tenant not found", "error")
            return redirect(url_for("auth.login"))

        if not tenant_needs_setup(tenant_id):
            # Tenant already has users, redirect to login
            return redirect(url_for("auth.login"))

        return render_template(
            "setup.html",
            tenant=tenant,
            tenant_id=tenant_id,
        )


@setup_bp.route("/<tenant_id>/register", methods=["POST"])
def register_first_user(tenant_id: str):
    """Register the first user for a tenant.

    This creates the user and initiates passkey registration.
    Expects JSON body with:
    - email: The admin's email address
    - name: The admin's name (optional)
    """
    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        if not tenant_needs_setup(tenant_id):
            return jsonify({"error": "Tenant already has users"}), 400

        data = request.get_json()
        if not data or not data.get("email"):
            return jsonify({"error": "Email is required"}), 400

        email = data["email"].lower().strip()
        name = data.get("name", email.split("@")[0].title())

        # Validate email format
        import re

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"error": "Invalid email format"}), 400

        # Create the first user as admin
        user = User(
            user_id=f"user_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            email=email,
            name=name,
            role="admin",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Store in session for passkey registration
        session["setup_user_id"] = user.user_id
        session["setup_user_email"] = user.email
        session["setup_tenant_id"] = tenant_id

        # Generate passkey registration options
        options = create_registration_options(user, tenant)

        # Store challenge for verification
        session["passkey_registration_challenge"] = options["_challenge"]
        del options["_challenge"]

        logger.info(f"Created first admin user {email} for tenant {tenant_id}")

        return jsonify(
            {
                "success": True,
                "user": {
                    "user_id": user.user_id,
                    "email": user.email,
                    "name": user.name,
                },
                "passkey_options": options,
            }
        )


@setup_bp.route("/<tenant_id>/verify-passkey", methods=["POST"])
def verify_setup_passkey(tenant_id: str):
    """Verify passkey registration during setup.

    Expects JSON body with:
    - credential: The WebAuthn credential response
    - name: Optional name for the passkey
    """
    user_id = session.get("setup_user_id")
    user_email = session.get("setup_user_email")
    setup_tenant_id = session.get("setup_tenant_id")
    challenge = session.get("passkey_registration_challenge")

    if not all([user_id, user_email, setup_tenant_id, challenge]):
        return jsonify({"error": "No setup in progress"}), 400

    if setup_tenant_id != tenant_id:
        return jsonify({"error": "Tenant mismatch"}), 400

    data = request.get_json()
    if not data or "credential" not in data:
        return jsonify({"error": "Missing credential"}), 400

    passkey_name = data.get("name", "Initial Setup Key")

    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        user = db_session.scalars(select(User).filter_by(user_id=user_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        try:
            passkey = verify_and_save_registration(
                user=user,
                tenant=tenant,
                credential_response=data["credential"],
                challenge=challenge,
                passkey_name=passkey_name,
            )

            # Clear setup session data
            session.pop("setup_user_id", None)
            session.pop("setup_user_email", None)
            session.pop("setup_tenant_id", None)
            session.pop("passkey_registration_challenge", None)

            # Create authenticated session
            session["user"] = user.email
            session["user_name"] = user.name
            session["tenant_id"] = tenant_id
            session["authenticated"] = True
            session["auth_method"] = "passkey"

            logger.info(f"Setup completed for tenant {tenant_id} with user {user.email}")

            return jsonify(
                {
                    "success": True,
                    "redirect": url_for("tenants.dashboard", tenant_id=tenant_id),
                }
            )

        except ValueError as e:
            logger.error(f"Setup passkey verification failed: {e}")
            # Clean up the user if passkey registration failed
            db_session.delete(user)
            db_session.commit()
            return jsonify({"error": str(e)}), 400


@setup_bp.route("/<tenant_id>/skip-passkey", methods=["POST"])
def skip_passkey_setup(tenant_id: str):
    """Skip passkey setup and use test mode instead.

    Only available when ADCP_AUTH_TEST_MODE=true.
    Creates the user without a passkey.
    """
    import os

    if os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() != "true":
        return jsonify({"error": "Passkey is required"}), 400

    user_id = session.get("setup_user_id")
    user_email = session.get("setup_user_email")
    setup_tenant_id = session.get("setup_tenant_id")

    if not all([user_id, user_email, setup_tenant_id]):
        return jsonify({"error": "No setup in progress"}), 400

    if setup_tenant_id != tenant_id:
        return jsonify({"error": "Tenant mismatch"}), 400

    # Clear setup session data
    session.pop("setup_user_id", None)
    session.pop("setup_user_email", None)
    session.pop("setup_tenant_id", None)
    session.pop("passkey_registration_challenge", None)

    # Create authenticated session (test mode)
    session["user"] = user_email
    session["tenant_id"] = tenant_id
    session["authenticated"] = True
    session["auth_method"] = "test"

    logger.info(f"Setup completed (test mode) for tenant {tenant_id} with user {user_email}")

    return jsonify(
        {
            "success": True,
            "redirect": url_for("tenants.dashboard", tenant_id=tenant_id),
        }
    )
