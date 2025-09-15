"""Handle partial schemas and make migrations more robust

Revision ID: 015_handle_partial_schemas
Revises: 014_add_context_persistence
Create Date: 2025-08-17 14:30:00.000000

This migration handles cases where tables might have been partially created
by init_db() or previous failed migrations, making the migration process
more robust and idempotent.
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic
revision = "017_handle_partial_schemas"
down_revision = "016_add_json_validation"
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists in the database."""
    conn = op.get_bind()
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(index_name, table_name):
    """Check if an index exists on a table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def safe_create_table(table_name, *columns, **kwargs):
    """Create a table only if it doesn't exist."""
    if not table_exists(table_name):
        op.create_table(table_name, *columns, **kwargs)
        return True
    return False


def safe_add_column(table_name, column):
    """Add a column only if it doesn't exist."""
    if table_exists(table_name) and not column_exists(table_name, column.name):
        op.add_column(table_name, column)
        return True
    return False


def safe_create_index(index_name, table_name, columns):
    """Create an index only if it doesn't exist."""
    if table_exists(table_name) and not index_exists(index_name, table_name):
        op.create_index(index_name, table_name, columns)
        return True
    return False


def safe_create_foreign_key(constraint_name, source_table, ref_table, source_cols, ref_cols, **kwargs):
    """Create a foreign key only if both tables exist."""
    if table_exists(source_table) and table_exists(ref_table):
        try:
            op.create_foreign_key(constraint_name, source_table, ref_table, source_cols, ref_cols, **kwargs)
            return True
        except Exception:
            # Foreign key might already exist
            pass
    return False


def upgrade():
    """
    This migration doesn't create new schema - it just ensures that
    indexes and foreign keys from migration 014 exist properly.

    NOTE: Migration 014 already creates the contexts and workflow_steps tables.
    This migration only adds indexes/constraints if they're missing.
    """

    # Ensure indexes exist on contexts table (if table exists)
    if table_exists("contexts"):
        # Add indexes that might be missing
        safe_create_index("idx_contexts_tenant", "contexts", ["tenant_id"])
        safe_create_index("idx_contexts_principal", "contexts", ["principal_id"])
        safe_create_index("idx_contexts_last_activity", "contexts", ["last_activity_at"])

    # Ensure indexes exist on workflow_steps table (if table exists)
    if table_exists("workflow_steps"):
        # Add indexes that might be missing
        safe_create_index("idx_workflow_steps_context", "workflow_steps", ["context_id"])
        safe_create_index("idx_workflow_steps_status", "workflow_steps", ["status"])
        safe_create_index("idx_workflow_steps_owner", "workflow_steps", ["owner"])
        safe_create_index("idx_workflow_steps_assigned", "workflow_steps", ["assigned_to"])
        safe_create_index("idx_workflow_steps_created", "workflow_steps", ["created_at"])

    # Add columns to existing tables if they don't exist
    safe_add_column("media_buys", sa.Column("context_id", sa.String(100), nullable=True))
    safe_create_foreign_key(
        "fk_media_buys_context",
        "media_buys",
        "contexts",
        ["context_id"],
        ["context_id"],
        ondelete="SET NULL",
    )
    safe_create_index("idx_media_buys_context", "media_buys", ["context_id"])

    safe_add_column("tasks", sa.Column("context_id", sa.String(100), nullable=True))
    safe_create_foreign_key(
        "fk_tasks_context",
        "tasks",
        "contexts",
        ["context_id"],
        ["context_id"],
        ondelete="SET NULL",
    )
    safe_create_index("idx_tasks_context", "tasks", ["context_id"])

    # Add task fields if they don't exist
    safe_add_column(
        "tasks",
        sa.Column("human_needed", sa.Boolean, nullable=False, server_default="0"),
    )
    safe_add_column("tasks", sa.Column("message", sa.Text, nullable=True))
    safe_add_column(
        "tasks",
        sa.Column("clarification_needed", sa.Boolean, nullable=False, server_default="0"),
    )
    safe_add_column("tasks", sa.Column("clarification_details", sa.Text, nullable=True))


def downgrade():
    """
    Since this migration is about making things idempotent,
    we don't actually remove anything in downgrade - that would
    be handled by downgrading migration 014.
    """
    pass
