"""Passkey (WebAuthn) authentication service.

Provides WebAuthn credential registration and authentication for passwordless login.
"""

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import func, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant, User, UserPasskey

logger = logging.getLogger(__name__)


def get_rp_id(tenant: Tenant) -> str:
    """Get the Relying Party ID for a tenant.

    The RP ID is typically the domain without port.
    For local development, we use localhost.
    """
    if tenant.virtual_host:
        # Custom domain - extract host without port
        return tenant.virtual_host.split(":")[0]

    # Check for configured domain
    base_domain = os.environ.get("SALES_AGENT_DOMAIN", "")
    if base_domain and tenant.subdomain:
        return f"{tenant.subdomain}.{base_domain}"

    # Fallback for local development
    return os.environ.get("WEBAUTHN_RP_ID", "localhost")


def get_rp_name(tenant: Tenant) -> str:
    """Get the Relying Party name for display."""
    return tenant.name or "AdCP Sales Agent"


def get_expected_origin(tenant: Tenant) -> str:
    """Get the expected origin for WebAuthn verification."""
    rp_id = get_rp_id(tenant)

    # Local development
    if rp_id == "localhost":
        port = os.environ.get("ADMIN_UI_PORT", "8001")
        return f"http://localhost:{port}"

    # Production - always HTTPS
    return f"https://{rp_id}"


def create_registration_options(user: User, tenant: Tenant) -> dict:
    """Generate WebAuthn registration options for a user.

    Args:
        user: The user registering a passkey
        tenant: The tenant context

    Returns:
        Registration options as a dict suitable for JSON response
    """
    rp_id = get_rp_id(tenant)
    rp_name = get_rp_name(tenant)

    # Get existing credentials to exclude (prevent re-registration)
    with get_db_session() as session:
        existing_passkeys = session.scalars(
            select(UserPasskey).filter_by(user_id=user.user_id, tenant_id=tenant.tenant_id)
        ).all()

        exclude_credentials = [PublicKeyCredentialDescriptor(id=pk.credential_id) for pk in existing_passkeys]

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=user.user_id.encode(),
        user_name=user.email,
        user_display_name=user.name or user.email,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    # Convert to dict for JSON serialization
    return {
        "rp": {"id": options.rp.id, "name": options.rp.name},
        "user": {
            "id": bytes_to_base64url(options.user.id),
            "name": options.user.name,
            "displayName": options.user.display_name,
        },
        "challenge": bytes_to_base64url(options.challenge),
        "pubKeyCredParams": [{"type": p.type.value, "alg": p.alg.value} for p in options.pub_key_cred_params],
        "timeout": options.timeout,
        "excludeCredentials": [
            {"type": c.type.value, "id": bytes_to_base64url(c.id)} for c in (options.exclude_credentials or [])
        ],
        "authenticatorSelection": {
            "residentKey": (
                options.authenticator_selection.resident_key.value if options.authenticator_selection else "preferred"
            ),
            "userVerification": (
                options.authenticator_selection.user_verification.value
                if options.authenticator_selection
                else "preferred"
            ),
        },
        "attestation": options.attestation.value if options.attestation else "none",
        # Store challenge for verification
        "_challenge": bytes_to_base64url(options.challenge),
    }


def verify_and_save_registration(
    user: User,
    tenant: Tenant,
    credential_response: dict,
    challenge: str,
    passkey_name: str = "Passkey",
) -> UserPasskey:
    """Verify WebAuthn registration response and save the credential.

    Args:
        user: The user registering the passkey
        tenant: The tenant context
        credential_response: The credential response from the browser
        challenge: The original challenge (base64url encoded)
        passkey_name: Human-readable name for this passkey

    Returns:
        The created UserPasskey record

    Raises:
        ValueError: If verification fails
    """
    rp_id = get_rp_id(tenant)
    expected_origin = get_expected_origin(tenant)

    try:
        verification = verify_registration_response(
            credential=credential_response,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=rp_id,
            expected_origin=expected_origin,
        )
    except Exception as e:
        logger.error(f"WebAuthn registration verification failed: {e}")
        raise ValueError(f"Registration verification failed: {e}") from e

    # Save the credential
    with get_db_session() as session:
        passkey = UserPasskey(
            user_id=user.user_id,
            tenant_id=tenant.tenant_id,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            name=passkey_name,
            created_at=datetime.now(UTC),
        )
        session.add(passkey)
        session.commit()
        session.refresh(passkey)

        logger.info(f"Registered passkey '{passkey_name}' for user {user.email} in tenant {tenant.tenant_id}")
        return passkey


def create_authentication_options(email: str, tenant: Tenant) -> dict | None:
    """Generate WebAuthn authentication options for a user.

    Args:
        email: The user's email address
        tenant: The tenant context

    Returns:
        Authentication options as a dict, or None if user has no passkeys
    """
    rp_id = get_rp_id(tenant)

    with get_db_session() as session:
        # Find user and their passkeys
        user = session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant.tenant_id)).first()

        if not user:
            logger.warning(f"Authentication attempted for unknown user: {email}")
            return None

        passkeys = session.scalars(
            select(UserPasskey).filter_by(user_id=user.user_id, tenant_id=tenant.tenant_id)
        ).all()

        if not passkeys:
            logger.info(f"User {email} has no registered passkeys")
            return None

        allow_credentials = [PublicKeyCredentialDescriptor(id=pk.credential_id) for pk in passkeys]

    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    return {
        "challenge": bytes_to_base64url(options.challenge),
        "timeout": options.timeout,
        "rpId": options.rp_id,
        "allowCredentials": [
            {"type": c.type.value, "id": bytes_to_base64url(c.id)} for c in (options.allow_credentials or [])
        ],
        "userVerification": options.user_verification.value if options.user_verification else "preferred",
        # Store for verification
        "_challenge": bytes_to_base64url(options.challenge),
        "_user_id": user.user_id,
    }


def verify_authentication(
    tenant: Tenant,
    credential_response: dict,
    challenge: str,
    user_id: str,
) -> User:
    """Verify WebAuthn authentication response.

    Args:
        tenant: The tenant context
        credential_response: The credential response from the browser
        challenge: The original challenge (base64url encoded)
        user_id: The user ID from the authentication options

    Returns:
        The authenticated User

    Raises:
        ValueError: If verification fails
    """
    rp_id = get_rp_id(tenant)
    expected_origin = get_expected_origin(tenant)

    # Get the credential ID from the response
    credential_id = base64url_to_bytes(credential_response.get("id", ""))

    with get_db_session() as session:
        # Find the passkey
        passkey = session.scalars(
            select(UserPasskey).filter_by(credential_id=credential_id, tenant_id=tenant.tenant_id, user_id=user_id)
        ).first()

        if not passkey:
            raise ValueError("Unknown credential")

        # Get the user
        user = session.scalars(select(User).filter_by(user_id=user_id)).first()
        if not user:
            raise ValueError("User not found")

        if not user.is_active:
            raise ValueError("User account is disabled")

        try:
            verification = verify_authentication_response(
                credential=credential_response,
                expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=rp_id,
                expected_origin=expected_origin,
                credential_public_key=passkey.public_key,
                credential_current_sign_count=passkey.sign_count,
            )
        except Exception as e:
            logger.error(f"WebAuthn authentication verification failed: {e}")
            raise ValueError(f"Authentication verification failed: {e}") from e

        # Update sign count to prevent replay attacks
        passkey.sign_count = verification.new_sign_count
        passkey.last_used_at = datetime.now(UTC)

        # Update user last login
        user.last_login = datetime.now(UTC)

        session.commit()

        logger.info(f"User {user.email} authenticated via passkey in tenant {tenant.tenant_id}")
        return user


def get_user_passkeys(user_id: str, tenant_id: str) -> list[dict]:
    """Get all passkeys for a user.

    Args:
        user_id: The user's ID
        tenant_id: The tenant ID

    Returns:
        List of passkey info dicts
    """
    with get_db_session() as session:
        passkeys = session.scalars(select(UserPasskey).filter_by(user_id=user_id, tenant_id=tenant_id)).all()

        return [
            {
                "id": pk.id,
                "name": pk.name,
                "created_at": pk.created_at.isoformat() if pk.created_at else None,
                "last_used_at": pk.last_used_at.isoformat() if pk.last_used_at else None,
            }
            for pk in passkeys
        ]


def delete_passkey(passkey_id: int, user_id: str, tenant_id: str) -> bool:
    """Delete a passkey.

    Args:
        passkey_id: The passkey ID to delete
        user_id: The user's ID (for authorization)
        tenant_id: The tenant ID (for authorization)

    Returns:
        True if deleted, False if not found
    """
    with get_db_session() as session:
        passkey = session.scalars(
            select(UserPasskey).filter_by(id=passkey_id, user_id=user_id, tenant_id=tenant_id)
        ).first()

        if not passkey:
            return False

        session.delete(passkey)
        session.commit()
        logger.info(f"Deleted passkey {passkey_id} for user {user_id}")
        return True


def user_has_passkeys(email: str, tenant_id: str) -> bool:
    """Check if a user has any registered passkeys.

    Args:
        email: The user's email
        tenant_id: The tenant ID

    Returns:
        True if user has at least one passkey
    """
    with get_db_session() as session:
        user = session.scalars(select(User).filter_by(email=email.lower(), tenant_id=tenant_id)).first()

        if not user:
            return False

        stmt = select(func.count()).select_from(UserPasskey).filter_by(user_id=user.user_id, tenant_id=tenant_id)
        count = session.execute(stmt).scalar() or 0

        return count > 0
