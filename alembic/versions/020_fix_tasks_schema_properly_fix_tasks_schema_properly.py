"""fix_tasks_schema_properly

Revision ID: 020_fix_tasks_schema_properly
Revises: 13a4e417ebb5
Create Date: 2025-08-31 16:58:53.407080

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.engine import reflection

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_fix_tasks_schema_properly"
down_revision: str | Sequence[str] | None = "13a4e417ebb5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ensure workflow tables exist and handle schema inconsistencies.

    This migration was previously empty but is critical for production stability.
    It ensures workflow_steps and object_workflow_mapping tables exist, which are
    referenced by the application code but may be missing in production.
    """
    # Get database connection
    connection = op.get_bind()
    inspector = reflection.Inspector.from_engine(connection)
    existing_tables = inspector.get_table_names()

    # Ensure workflow_steps table exists (may be missing in production)
    if "workflow_steps" not in existing_tables:
        print("Creating missing workflow_steps table...")
        op.create_table(
            "workflow_steps",
            sa.Column("step_id", sa.String(100), primary_key=True),
            sa.Column("context_id", sa.String(100), nullable=False),
            sa.Column("step_type", sa.String(50), nullable=False),
            sa.Column("tool_name", sa.String(100), nullable=True),
            sa.Column("request_data", sa.JSON, nullable=True),
            sa.Column("response_data", sa.JSON, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("owner", sa.String(20), nullable=False),
            sa.Column("assigned_to", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime, nullable=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("transaction_details", sa.JSON, nullable=True),
            sa.Column("comments", sa.JSON, nullable=False, server_default="[]"),
        )

        # Add indexes for workflow_steps
        op.create_index("idx_workflow_steps_context", "workflow_steps", ["context_id"])
        op.create_index("idx_workflow_steps_status", "workflow_steps", ["status"])
        op.create_index("idx_workflow_steps_owner", "workflow_steps", ["owner"])
        op.create_index("idx_workflow_steps_assigned", "workflow_steps", ["assigned_to"])
        op.create_index("idx_workflow_steps_created", "workflow_steps", ["created_at"])

        # Add foreign key constraint if contexts table exists
        if "contexts" in existing_tables:
            try:
                op.create_foreign_key(
                    "fk_workflow_steps_context",
                    "workflow_steps",
                    "contexts",
                    ["context_id"],
                    ["context_id"],
                    ondelete="CASCADE",
                )
            except Exception as e:
                print(f"Warning: Could not add foreign key constraint: {e}")
    else:
        print("workflow_steps table already exists")

    # Ensure object_workflow_mapping table exists (may be missing in production)
    if "object_workflow_mapping" not in existing_tables:
        print("Creating missing object_workflow_mapping table...")
        op.create_table(
            "object_workflow_mapping",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("object_type", sa.String(50), nullable=False),
            sa.Column("object_id", sa.String(100), nullable=False),
            sa.Column("step_id", sa.String(100), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )

        # Add indexes for object_workflow_mapping
        op.create_index("idx_object_workflow_type_id", "object_workflow_mapping", ["object_type", "object_id"])
        op.create_index("idx_object_workflow_step", "object_workflow_mapping", ["step_id"])
        op.create_index("idx_object_workflow_created", "object_workflow_mapping", ["created_at"])

        # Add foreign key constraint to workflow_steps (created above or existing)
        try:
            op.create_foreign_key(
                "fk_object_workflow_step",
                "object_workflow_mapping",
                "workflow_steps",
                ["step_id"],
                ["step_id"],
                ondelete="CASCADE",
            )
        except Exception as e:
            print(f"Warning: Could not add foreign key constraint: {e}")
    else:
        print("object_workflow_mapping table already exists")

    print("Migration 020 completed: Workflow tables ensured to exist")


def downgrade() -> None:
    """Downgrade schema by removing workflow tables if they were created."""
    # Drop tables in reverse order due to foreign key constraints
    try:
        op.drop_table("object_workflow_mapping")
        print("Dropped object_workflow_mapping table")
    except Exception as e:
        print(f"Could not drop object_workflow_mapping table: {e}")

    try:
        op.drop_table("workflow_steps")
        print("Dropped workflow_steps table")
    except Exception as e:
        print(f"Could not drop workflow_steps table: {e}")

    print("Migration 020 downgrade completed")
