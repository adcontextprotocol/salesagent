"""Add AdCP v2.4 protocol fields

Revision ID: 13a4e417ebb5
Revises: 018_add_missing_updated_at
Create Date: 2025-01-07 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "13a4e417ebb5"
down_revision = "e81e275c9b29"  # Follow from the latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Make migration idempotent - check if columns exist before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("media_buys")]
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("media_buys")]

    # Add buyer_ref column if it doesn't exist
    if "buyer_ref" not in existing_columns:
        op.add_column("media_buys", sa.Column("buyer_ref", sa.String(100), nullable=True))

    # Add currency column if it doesn't exist
    if "currency" not in existing_columns:
        op.add_column("media_buys", sa.Column("currency", sa.String(3), nullable=False, server_default="USD"))

    # Add datetime columns if they don't exist
    if "start_time" not in existing_columns:
        op.add_column("media_buys", sa.Column("start_time", sa.DateTime, nullable=True))

    if "end_time" not in existing_columns:
        op.add_column("media_buys", sa.Column("end_time", sa.DateTime, nullable=True))

    # Populate datetime fields only if they're null and source dates exist
    # Use database-agnostic approach with proper casting
    dialect = conn.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE media_buys
            SET start_time = (start_date || ' 00:00:00')::timestamp,
                end_time = (end_date || ' 23:59:59')::timestamp
            WHERE (start_time IS NULL OR end_time IS NULL)
              AND start_date IS NOT NULL
              AND end_date IS NOT NULL
        """
        )
    else:  # SQLite
        op.execute(
            """
            UPDATE media_buys
            SET start_time = datetime(start_date || ' 00:00:00'),
                end_time = datetime(end_date || ' 23:59:59')
            WHERE (start_time IS NULL OR end_time IS NULL)
              AND start_date IS NOT NULL
              AND end_date IS NOT NULL
        """
        )

    # Only create index if it doesn't exist
    if "ix_media_buys_buyer_ref" not in existing_indexes:
        op.create_index("ix_media_buys_buyer_ref", "media_buys", ["buyer_ref"])


def downgrade():
    # Make downgrade idempotent too
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("media_buys")]
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("media_buys")]

    # Remove index if it exists
    if "ix_media_buys_buyer_ref" in existing_indexes:
        op.drop_index("ix_media_buys_buyer_ref", table_name="media_buys")

    # Remove columns if they exist
    if "buyer_ref" in existing_columns:
        op.drop_column("media_buys", "buyer_ref")

    if "currency" in existing_columns:
        op.drop_column("media_buys", "currency")

    if "start_time" in existing_columns:
        op.drop_column("media_buys", "start_time")

    if "end_time" in existing_columns:
        op.drop_column("media_buys", "end_time")
