"""Add context persistence for A2A protocol support

Revision ID: 014_add_context_persistence
Revises: 013_principal_advertiser_mapping
Create Date: 2025-01-11

Context table represents overall workflows/conversations.
Workflow_steps table tracks individual steps/tasks as a work queue.
Conversation_history in contexts is for clarifications and refinements.

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "014_add_context_persistence"
down_revision = "013_principal_advertiser_mapping"
branch_labels = None
depends_on = None


def upgrade():
    # Create context table for persistent conversation state (simplified)
    # Context just tracks conversations - workflow_steps is the actual work queue
    op.create_table(
        "contexts",
        sa.Column("context_id", sa.String(100), primary_key=True),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("principal_id", sa.String(100), nullable=False),
        # Simple conversation tracking
        sa.Column(
            "conversation_history", sa.JSON, nullable=False, server_default="[]"
        ),  # Clarifications and refinements only
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "last_activity_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Foreign key constraints
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "principal_id"],
            ["principals.tenant_id", "principals.principal_id"],
            ondelete="CASCADE",
        ),
    )

    # Create minimal indexes
    op.create_index("idx_contexts_tenant", "contexts", ["tenant_id"])
    op.create_index("idx_contexts_principal", "contexts", ["principal_id"])
    op.create_index("idx_contexts_last_activity", "contexts", ["last_activity_at"])

    # Create workflow_steps table as a proper work queue
    op.create_table(
        "workflow_steps",
        sa.Column("step_id", sa.String(100), primary_key=True),
        sa.Column("context_id", sa.String(100), nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),  # tool_call, approval, notification, etc.
        sa.Column("tool_name", sa.String(100), nullable=True),  # MCP tool name if applicable
        sa.Column("request_data", sa.JSON, nullable=True),  # Original request JSON
        sa.Column("response_data", sa.JSON, nullable=True),  # Response/result JSON
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),  # pending, in_progress, completed, failed, requires_approval
        sa.Column("owner", sa.String(20), nullable=False),  # principal, publisher, system
        sa.Column("assigned_to", sa.String(255), nullable=True),  # Specific user/system if assigned
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("transaction_details", sa.JSON, nullable=True),  # Actual API calls made to GAM, etc.
        sa.ForeignKeyConstraint(["context_id"], ["contexts.context_id"], ondelete="CASCADE"),
    )

    op.create_index("idx_workflow_steps_context", "workflow_steps", ["context_id"])
    op.create_index("idx_workflow_steps_status", "workflow_steps", ["status"])
    op.create_index("idx_workflow_steps_owner", "workflow_steps", ["owner"])
    op.create_index("idx_workflow_steps_assigned", "workflow_steps", ["assigned_to"])
    op.create_index("idx_workflow_steps_created", "workflow_steps", ["created_at"])

    # Add context_id to media_buys table to link media buys with their creation context
    op.add_column("media_buys", sa.Column("context_id", sa.String(100), nullable=True))
    try:
        # SQLite doesn't support adding foreign keys with ALTER TABLE
        op.create_foreign_key(
            "fk_media_buys_context",
            "media_buys",
            "contexts",
            ["context_id"],
            ["context_id"],
            ondelete="SET NULL",
        )
    except NotImplementedError:
        pass  # SQLite doesn't support ALTER TABLE ADD CONSTRAINT
    op.create_index("idx_media_buys_context", "media_buys", ["context_id"])

    # Add context_id to tasks table for direct context linkage
    op.add_column("tasks", sa.Column("context_id", sa.String(100), nullable=True))
    try:
        # SQLite doesn't support adding foreign keys with ALTER TABLE
        op.create_foreign_key(
            "fk_tasks_context",
            "tasks",
            "contexts",
            ["context_id"],
            ["context_id"],
            ondelete="SET NULL",
        )
    except NotImplementedError:
        pass  # SQLite doesn't support ALTER TABLE ADD CONSTRAINT
    op.create_index("idx_tasks_context", "tasks", ["context_id"])

    # Add fields to tasks table for better integration
    op.add_column(
        "tasks",
        sa.Column("human_needed", sa.Boolean, nullable=False, server_default="0"),
    )
    op.add_column("tasks", sa.Column("message", sa.Text, nullable=True))
    op.add_column(
        "tasks",
        sa.Column("clarification_needed", sa.Boolean, nullable=False, server_default="0"),
    )
    op.add_column("tasks", sa.Column("clarification_details", sa.Text, nullable=True))


def downgrade():
    # Remove task columns
    op.drop_column("tasks", "clarification_details")
    op.drop_column("tasks", "clarification_needed")
    op.drop_column("tasks", "message")
    op.drop_column("tasks", "human_needed")

    # Remove context linkages
    op.drop_index("idx_tasks_context", "tasks")
    op.drop_constraint("fk_tasks_context", "tasks", type_="foreignkey")
    op.drop_column("tasks", "context_id")

    op.drop_index("idx_media_buys_context", "media_buys")
    op.drop_constraint("fk_media_buys_context", "media_buys", type_="foreignkey")
    op.drop_column("media_buys", "context_id")

    # Drop workflow_steps table
    op.drop_index("idx_workflow_steps_created", "workflow_steps")
    op.drop_index("idx_workflow_steps_assigned", "workflow_steps")
    op.drop_index("idx_workflow_steps_owner", "workflow_steps")
    op.drop_index("idx_workflow_steps_status", "workflow_steps")
    op.drop_index("idx_workflow_steps_context", "workflow_steps")
    op.drop_table("workflow_steps")

    # Drop contexts table
    op.drop_index("idx_contexts_last_activity", "contexts")
    op.drop_index("idx_contexts_principal", "contexts")
    op.drop_index("idx_contexts_tenant", "contexts")
    op.drop_table("contexts")
