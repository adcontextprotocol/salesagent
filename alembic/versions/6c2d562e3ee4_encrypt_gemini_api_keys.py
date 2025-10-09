"""encrypt_gemini_api_keys

Revision ID: 6c2d562e3ee4
Revises: add_creative_reviews
Create Date: 2025-10-08 22:05:21.075960

This migration encrypts all existing plaintext Gemini API keys in the tenants table.
Uses Fernet symmetric encryption with key from ENCRYPTION_KEY environment variable.

IMPORTANT: This migration is idempotent - it detects already-encrypted keys and skips them.
"""

import logging
import os
from collections.abc import Sequence

from sqlalchemy.sql import text

from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "6c2d562e3ee4"
down_revision: str | Sequence[str] | None = "add_creative_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def is_encrypted(value: str) -> bool:
    """Check if a value appears to be encrypted.

    Fernet tokens are base64-encoded and typically start with 'gAAAAA'.
    This is a heuristic check - if we can't tell, we'll try to encrypt it.
    """
    if not value:
        return False

    # Fernet tokens have specific characteristics:
    # - Base64 encoded
    # - Start with version byte (usually 0x80 = 'gA' in base64)
    # - Minimum length of ~80 characters
    if len(value) >= 80 and value.startswith("gA"):
        return True

    return False


def upgrade() -> None:
    """Encrypt all plaintext Gemini API keys."""
    from cryptography.fernet import Fernet

    # Get encryption key
    encryption_key = os.environ.get("ENCRYPTION_KEY")
    if not encryption_key:
        logger.warning(
            "ENCRYPTION_KEY not set - skipping encryption of Gemini API keys. "
            "Set ENCRYPTION_KEY environment variable and re-run migration."
        )
        return

    try:
        fernet = Fernet(encryption_key.encode())
    except Exception as e:
        logger.error(f"Invalid ENCRYPTION_KEY: {e}")
        raise ValueError(f"Invalid ENCRYPTION_KEY: {e}")

    connection = op.get_bind()

    # Get all tenants with Gemini API keys
    result = connection.execute(text("SELECT tenant_id, gemini_api_key FROM tenants WHERE gemini_api_key IS NOT NULL"))

    encrypted_count = 0
    skipped_count = 0

    for row in result:
        tenant_id = row[0]
        current_key = row[1]

        # Skip if already encrypted
        if is_encrypted(current_key):
            logger.info(f"Tenant {tenant_id}: API key already encrypted, skipping")
            skipped_count += 1
            continue

        # Encrypt the key
        try:
            encrypted_key = fernet.encrypt(current_key.encode()).decode()

            # Update the database
            connection.execute(
                text("UPDATE tenants SET gemini_api_key = :encrypted_key WHERE tenant_id = :tenant_id"),
                {"encrypted_key": encrypted_key, "tenant_id": tenant_id},
            )

            logger.info(f"Tenant {tenant_id}: Encrypted Gemini API key")
            encrypted_count += 1

        except Exception as e:
            logger.error(f"Tenant {tenant_id}: Failed to encrypt API key: {e}")
            raise

    logger.info(f"Migration complete: {encrypted_count} keys encrypted, {skipped_count} already encrypted")
    print("\nEncryption summary:")
    print(f"  - Keys encrypted: {encrypted_count}")
    print(f"  - Already encrypted (skipped): {skipped_count}")


def downgrade() -> None:
    """Decrypt all encrypted Gemini API keys back to plaintext.

    WARNING: This will store API keys in plaintext!
    Only use this for rollback purposes.
    """
    from cryptography.fernet import Fernet, InvalidToken

    # Get encryption key
    encryption_key = os.environ.get("ENCRYPTION_KEY")
    if not encryption_key:
        logger.warning(
            "ENCRYPTION_KEY not set - cannot decrypt Gemini API keys. "
            "Set ENCRYPTION_KEY environment variable and re-run migration."
        )
        return

    try:
        fernet = Fernet(encryption_key.encode())
    except Exception as e:
        logger.error(f"Invalid ENCRYPTION_KEY: {e}")
        raise ValueError(f"Invalid ENCRYPTION_KEY: {e}")

    connection = op.get_bind()

    # Get all tenants with Gemini API keys
    result = connection.execute(text("SELECT tenant_id, gemini_api_key FROM tenants WHERE gemini_api_key IS NOT NULL"))

    decrypted_count = 0
    skipped_count = 0

    for row in result:
        tenant_id = row[0]
        current_key = row[1]

        # Skip if not encrypted (already plaintext)
        if not is_encrypted(current_key):
            logger.info(f"Tenant {tenant_id}: API key already plaintext, skipping")
            skipped_count += 1
            continue

        # Decrypt the key
        try:
            decrypted_key = fernet.decrypt(current_key.encode()).decode()

            # Update the database
            connection.execute(
                text("UPDATE tenants SET gemini_api_key = :decrypted_key WHERE tenant_id = :tenant_id"),
                {"decrypted_key": decrypted_key, "tenant_id": tenant_id},
            )

            logger.info(f"Tenant {tenant_id}: Decrypted Gemini API key")
            decrypted_count += 1

        except InvalidToken:
            logger.error(f"Tenant {tenant_id}: Invalid encrypted data or wrong encryption key")
            raise ValueError(f"Tenant {tenant_id}: Cannot decrypt with current ENCRYPTION_KEY")
        except Exception as e:
            logger.error(f"Tenant {tenant_id}: Failed to decrypt API key: {e}")
            raise

    logger.info(f"Rollback complete: {decrypted_count} keys decrypted, {skipped_count} already plaintext")
    print("\nDecryption summary:")
    print(f"  - Keys decrypted: {decrypted_count}")
    print(f"  - Already plaintext (skipped): {skipped_count}")
