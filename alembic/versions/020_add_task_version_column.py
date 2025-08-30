"""Add version column for optimistic locking on tasks

Revision ID: 020_add_task_version_column
Revises: 019_add_performance_indexes
Create Date: 2025-08-30

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "020_add_task_version_column"
down_revision = "019_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade():
    """Add version column to tasks table for optimistic locking."""

    # Add version column with default value of 1
    op.add_column("tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # Add index on version column for performance
    op.create_index("idx_tasks_version", "tasks", ["version"], postgresql_using="btree")


def downgrade():
    """Remove version column from tasks table."""
    op.drop_index("idx_tasks_version", table_name="tasks")
    op.drop_column("tasks", "version")
