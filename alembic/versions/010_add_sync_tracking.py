"""Add sync tracking table

Revision ID: 010_add_sync_tracking
Revises: 009_fix_inventory_type_length
Create Date: 2025-01-08 08:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "010_add_sync_tracking"
down_revision = "009_fix_inventory_type_length"
branch_labels = None
depends_on = None


def upgrade():
    """Add sync_jobs table for tracking inventory sync operations."""
    op.create_table(
        "sync_jobs",
        sa.Column("sync_id", sa.String(50), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("adapter_type", sa.String(50), nullable=False),
        sa.Column("sync_type", sa.String(20), nullable=False),  # inventory, targeting, full
        sa.Column("status", sa.String(20), nullable=False),  # pending, running, completed, failed
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),  # JSON with counts, details
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=False),  # user, cron, system
        sa.Column("triggered_by_id", sa.String(255), nullable=True),  # user email or system identifier
        sa.PrimaryKeyConstraint("sync_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
    )

    # Create indexes for common queries
    op.create_index("idx_sync_jobs_tenant", "sync_jobs", ["tenant_id"])
    op.create_index("idx_sync_jobs_status", "sync_jobs", ["status"])
    op.create_index("idx_sync_jobs_started", "sync_jobs", ["started_at"])


def downgrade():
    """Remove sync_jobs table."""
    op.drop_index("idx_sync_jobs_started", table_name="sync_jobs")
    op.drop_index("idx_sync_jobs_status", table_name="sync_jobs")
    op.drop_index("idx_sync_jobs_tenant", table_name="sync_jobs")
    op.drop_table("sync_jobs")
