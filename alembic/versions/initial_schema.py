"""Initial schema creation

Revision ID: initial_schema
Revises:
Create Date: 2025-07-31 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial schema."""
    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subdomain", sa.String(100), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.Column("billing_plan", sa.String(50), nullable=True, default="standard"),
        sa.Column("billing_contact", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("subdomain"),
    )

    # Create creative_formats table
    op.create_table(
        "creative_formats",
        sa.Column("format_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("max_file_size_kb", sa.Integer(), nullable=True),
        sa.Column("specs", sa.JSON(), nullable=False),
        sa.Column("is_standard", sa.Boolean(), nullable=True, default=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("format_id"),
    )

    # Create products table
    op.create_table(
        "products",
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("formats", sa.JSON(), nullable=False),
        sa.Column("targeting_template", sa.JSON(), nullable=False),
        sa.Column("delivery_type", sa.String(50), nullable=False),
        sa.Column("is_fixed_price", sa.Boolean(), nullable=False),
        sa.Column("cpm", sa.Float(), nullable=True),
        sa.Column("price_guidance", sa.Text(), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=True, default=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("countries", sa.JSON(), nullable=True),
        sa.Column("implementation_config", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("tenant_id", "product_id"),
    )

    # Create principals table
    op.create_table(
        "principals",
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("principal_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform_mappings", sa.JSON(), nullable=False),
        sa.Column("access_token", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("tenant_id", "principal_id"),
        sa.UniqueConstraint("access_token"),
    )

    # Create users table
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )

    # Create media_buys table
    op.create_table(
        "media_buys",
        sa.Column("media_buy_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("principal_id", sa.String(100), nullable=False),
        sa.Column("order_name", sa.String(255), nullable=False),
        sa.Column("advertiser_name", sa.String(255), nullable=False),
        sa.Column("campaign_objective", sa.Text(), nullable=True),
        sa.Column("kpi_goal", sa.Text(), nullable=True),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("raw_request", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["tenant_id", "principal_id"], ["principals.tenant_id", "principals.principal_id"]),
        sa.PrimaryKeyConstraint("media_buy_id"),
    )

    # Create tasks table
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("media_buy_id", sa.String(100), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("task_id"),
    )

    # Create media_packages table
    op.create_table(
        "media_packages",
        sa.Column("media_buy_id", sa.String(100), nullable=False),
        sa.Column("package_id", sa.String(100), nullable=False),
        sa.Column("package_config", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"]),
        sa.PrimaryKeyConstraint("media_buy_id", "package_id"),
    )

    # Create creatives table
    op.create_table(
        "creatives",
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("principal_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("format", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("group_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["tenant_id", "principal_id"], ["principals.tenant_id", "principals.principal_id"]),
        sa.PrimaryKeyConstraint("creative_id"),
    )

    # Create creative_associations table
    op.create_table(
        "creative_associations",
        sa.Column("media_buy_id", sa.String(100), nullable=False),
        sa.Column("package_id", sa.String(100), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["creative_id"], ["creatives.creative_id"]),
        sa.ForeignKeyConstraint(
            ["media_buy_id", "package_id"], ["media_packages.media_buy_id", "media_packages.package_id"]
        ),
        sa.PrimaryKeyConstraint("media_buy_id", "package_id", "creative_id"),
    )

    # Create human_tasks table
    op.create_table(
        "human_tasks",
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("media_buy_id", sa.String(100), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("operation", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("context_data", sa.JSON(), nullable=True),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.String(255), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["media_buy_id"], ["media_buys.media_buy_id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("task_id"),
    )

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("log_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True, server_default=sa.func.current_timestamp()),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("principal_name", sa.String(255), nullable=True),
        sa.Column("principal_id", sa.String(100), nullable=True),
        sa.Column("adapter_id", sa.String(50), nullable=True),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=True, default=False),
        sa.Column("violation_type", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("log_id"),
    )

    # Create indexes
    op.create_index("idx_audit_logs_tenant_timestamp", "audit_logs", ["tenant_id", "timestamp"])
    op.create_index("idx_audit_logs_principal", "audit_logs", ["tenant_id", "principal_id"])
    op.create_index("idx_media_buys_tenant_principal", "media_buys", ["tenant_id", "principal_id"])
    op.create_index("idx_tasks_media_buy", "tasks", ["media_buy_id"])
    op.create_index("idx_human_tasks_status", "human_tasks", ["tenant_id", "status"])
    op.create_index("idx_creatives_tenant_principal", "creatives", ["tenant_id", "principal_id"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index("idx_creatives_tenant_principal")
    op.drop_index("idx_human_tasks_status")
    op.drop_index("idx_tasks_media_buy")
    op.drop_index("idx_media_buys_tenant_principal")
    op.drop_index("idx_audit_logs_principal")
    op.drop_index("idx_audit_logs_tenant_timestamp")

    op.drop_table("audit_logs")
    op.drop_table("human_tasks")
    op.drop_table("creative_associations")
    op.drop_table("creatives")
    op.drop_table("media_packages")
    op.drop_table("tasks")
    op.drop_table("media_buys")
    op.drop_table("users")
    op.drop_table("principals")
    op.drop_table("products")
    op.drop_table("creative_formats")
    op.drop_table("tenants")
