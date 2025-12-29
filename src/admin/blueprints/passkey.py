"""Passkey authentication blueprint.

Provides WebAuthn endpoints for passkey registration and authentication.
"""

import logging

from flask import Blueprint, jsonify, request, session
from sqlalchemy import select

from src.admin.utils import require_tenant_access
from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant, User
from src.services.passkey_service import (
    create_authentication_options,
    create_registration_options,
    delete_passkey,
    get_user_passkeys,
    user_has_passkeys,
    verify_and_save_registration,
    verify_authentication,
)

logger = logging.getLogger(__name__)

passkey_bp = Blueprint("passkey", __name__, url_prefix="/auth/passkey")


@passkey_bp.route("/register/options", methods=["POST"])
@require_tenant_access()
def registration_options(tenant_id: str):
    """Get WebAuthn registration options for the current user.

    Requires authenticated session.
    """
    email = session.get("user")
    if not email:
        return jsonify({"error": "Not authenticated"}), 401

    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        user = db_session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        options = create_registration_options(user, tenant)

        # Store challenge in session for verification
        session["passkey_registration_challenge"] = options["_challenge"]

        # Remove internal fields before sending to client
        del options["_challenge"]

        return jsonify(options)


@passkey_bp.route("/register/verify", methods=["POST"])
@require_tenant_access()
def verify_registration(tenant_id: str):
    """Verify WebAuthn registration and save the credential.

    Expects JSON body with:
    - credential: The WebAuthn credential response from navigator.credentials.create()
    - name: Optional human-readable name for the passkey
    """
    email = session.get("user")
    if not email:
        return jsonify({"error": "Not authenticated"}), 401

    challenge = session.pop("passkey_registration_challenge", None)
    if not challenge:
        return jsonify({"error": "No registration in progress"}), 400

    data = request.get_json()
    if not data or "credential" not in data:
        return jsonify({"error": "Missing credential"}), 400

    passkey_name = data.get("name", "Passkey")

    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        user = db_session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant_id)).first()
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
            return jsonify(
                {
                    "success": True,
                    "passkey": {
                        "id": passkey.id,
                        "name": passkey.name,
                        "created_at": passkey.created_at.isoformat() if passkey.created_at else None,
                    },
                }
            )
        except ValueError as e:
            logger.error(f"Passkey registration failed: {e}")
            return jsonify({"error": str(e)}), 400


@passkey_bp.route("/login/options", methods=["POST"])
def authentication_options():
    """Get WebAuthn authentication options for a user.

    Expects JSON body with:
    - email: The user's email address
    - tenant_id: The tenant ID
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    email = data.get("email", "").lower()
    tenant_id = data.get("tenant_id")

    if not email or not tenant_id:
        return jsonify({"error": "Email and tenant_id are required"}), 400

    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        options = create_authentication_options(email, tenant)

        if not options:
            return jsonify({"error": "No passkeys registered for this user"}), 404

        # Store challenge and user_id in session for verification
        session["passkey_auth_challenge"] = options["_challenge"]
        session["passkey_auth_user_id"] = options["_user_id"]
        session["passkey_auth_tenant_id"] = tenant_id

        # Remove internal fields before sending to client
        del options["_challenge"]
        del options["_user_id"]

        return jsonify(options)


@passkey_bp.route("/login/verify", methods=["POST"])
def verify_login():
    """Verify WebAuthn authentication and create session.

    Expects JSON body with:
    - credential: The WebAuthn credential response from navigator.credentials.get()
    """
    challenge = session.pop("passkey_auth_challenge", None)
    user_id = session.pop("passkey_auth_user_id", None)
    tenant_id = session.pop("passkey_auth_tenant_id", None)

    if not challenge or not user_id or not tenant_id:
        return jsonify({"error": "No authentication in progress"}), 400

    data = request.get_json()
    if not data or "credential" not in data:
        return jsonify({"error": "Missing credential"}), 400

    with get_db_session() as db_session:
        tenant = db_session.scalars(select(Tenant).filter_by(tenant_id=tenant_id)).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        try:
            user = verify_authentication(
                tenant=tenant,
                credential_response=data["credential"],
                challenge=challenge,
                user_id=user_id,
            )

            # Create session
            session["user"] = user.email
            session["user_name"] = user.name or user.email
            session["tenant_id"] = tenant_id
            session["authenticated"] = True
            session["auth_method"] = "passkey"

            return jsonify(
                {
                    "success": True,
                    "user": {
                        "email": user.email,
                        "name": user.name,
                    },
                    "redirect": f"/tenant/{tenant_id}",
                }
            )
        except ValueError as e:
            logger.error(f"Passkey authentication failed: {e}")
            return jsonify({"error": str(e)}), 401


@passkey_bp.route("/check", methods=["POST"])
def check_passkeys():
    """Check if a user has registered passkeys.

    Expects JSON body with:
    - email: The user's email address
    - tenant_id: The tenant ID

    Returns:
    - has_passkeys: boolean
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    email = data.get("email", "").lower()
    tenant_id = data.get("tenant_id")

    if not email or not tenant_id:
        return jsonify({"error": "Email and tenant_id are required"}), 400

    has_passkeys = user_has_passkeys(email, tenant_id)
    return jsonify({"has_passkeys": has_passkeys})


@passkey_bp.route("/list", methods=["GET"])
@require_tenant_access()
def list_passkeys(tenant_id: str):
    """List all passkeys for the current user."""
    email = session.get("user")
    if not email:
        return jsonify({"error": "Not authenticated"}), 401

    with get_db_session() as db_session:
        user = db_session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        passkeys = get_user_passkeys(user.user_id, tenant_id)
        return jsonify({"passkeys": passkeys})


@passkey_bp.route("/<int:passkey_id>", methods=["DELETE"])
@require_tenant_access()
def remove_passkey(tenant_id: str, passkey_id: int):
    """Delete a passkey."""
    email = session.get("user")
    if not email:
        return jsonify({"error": "Not authenticated"}), 401

    with get_db_session() as db_session:
        user = db_session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        if delete_passkey(passkey_id, user.user_id, tenant_id):
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Passkey not found"}), 404
