"""allow_users_multi_tenant_access

Revision ID: aff9ca8baa9c
Revises: a7acdcb7b3d3
Create Date: 2025-10-06 09:34:13.246331

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aff9ca8baa9c"
down_revision: str | Sequence[str] | None = "a7acdcb7b3d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to allow users to belong to multiple tenants.

    Changes:
    - Remove global unique constraint on users.email
    - Add composite unique constraint (tenant_id, email)
    """
    import logging

    from sqlalchemy import inspect

    logger = logging.getLogger(__name__)
    connection = op.get_bind()
    inspector = inspect(connection)

    # Check current constraints on users table
    existing_constraints = [c["name"] for c in inspector.get_unique_constraints("users")]
    logger.info(f"Existing unique constraints on users table: {existing_constraints}")

    with op.batch_alter_table("users", schema=None) as batch_op:
        # Drop the existing email unique constraint if it exists
        constraint_dropped = False

        if connection.dialect.name == "postgresql":
            # PostgreSQL auto-generates: users_email_key
            if "users_email_key" in existing_constraints:
                batch_op.drop_constraint("users_email_key", type_="unique")
                constraint_dropped = True
                logger.info("Dropped PostgreSQL constraint: users_email_key")
        else:
            # SQLite may use different names
            for constraint_name in ["uq_users_email", "users_email_key"]:
                if constraint_name in existing_constraints:
                    batch_op.drop_constraint(constraint_name, type_="unique")
                    constraint_dropped = True
                    logger.info(f"Dropped SQLite constraint: {constraint_name}")
                    break

        if not constraint_dropped:
            logger.warning(
                "No email unique constraint found to drop. "
                "This may indicate the migration was already applied or the constraint has a different name."
            )

        # Add composite unique constraint for tenant_id + email
        if "uq_users_tenant_email" not in existing_constraints:
            batch_op.create_unique_constraint("uq_users_tenant_email", ["tenant_id", "email"])
            logger.info("Created composite unique constraint: uq_users_tenant_email")
        else:
            logger.info("Composite constraint uq_users_tenant_email already exists, skipping")


def downgrade() -> None:
    """Downgrade schema to restore global email uniqueness.

    WARNING: This will fail if there are duplicate emails across tenants.
    """
    import logging

    from sqlalchemy import text

    logger = logging.getLogger(__name__)
    connection = op.get_bind()

    # Check for duplicate emails across tenants before attempting downgrade
    result = connection.execute(
        text(
            """
        SELECT email, COUNT(DISTINCT tenant_id) as tenant_count
        FROM users
        GROUP BY email
        HAVING COUNT(DISTINCT tenant_id) > 1
    """
        )
    )

    duplicates = result.fetchall()
    if duplicates:
        duplicate_emails = [row[0] for row in duplicates[:5]]  # Show first 5
        raise ValueError(
            f"Cannot downgrade: {len(duplicates)} email(s) exist in multiple tenants. "
            f"Examples: {', '.join(duplicate_emails)}. "
            "You must manually resolve these duplicate emails before downgrading. "
            "Either delete duplicate user records or change their email addresses."
        )

    # Safe to proceed with downgrade
    logger.info("No duplicate emails found across tenants, proceeding with downgrade")

    with op.batch_alter_table("users", schema=None) as batch_op:
        # Remove composite unique constraint
        batch_op.drop_constraint("uq_users_tenant_email", type_="unique")

        # Restore global email unique constraint
        batch_op.create_unique_constraint("users_email_key", ["email"])

    logger.info("Successfully restored global email uniqueness constraint")
