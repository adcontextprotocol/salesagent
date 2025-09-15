"""Add GAM orders and line items tables

Revision ID: 012_add_gam_orders_line_items
Revises: 011_add_superadmin_api_key
Create Date: 2025-01-08

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "012_add_gam_orders_line_items"
down_revision = "011_add_superadmin_api_key"
branch_labels = None
depends_on = None


def upgrade():
    # Create gam_orders table
    op.create_table(
        "gam_orders",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.String(50), nullable=False),  # GAM Order ID
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("advertiser_id", sa.String(50), nullable=True),
        sa.Column("advertiser_name", sa.String(255), nullable=True),
        sa.Column("agency_id", sa.String(50), nullable=True),
        sa.Column("agency_name", sa.String(255), nullable=True),
        sa.Column("trafficker_id", sa.String(50), nullable=True),
        sa.Column("trafficker_name", sa.String(255), nullable=True),
        sa.Column("salesperson_id", sa.String(50), nullable=True),
        sa.Column("salesperson_name", sa.String(255), nullable=True),
        sa.Column(
            "status", sa.String(30), nullable=False
        ),  # DRAFT, PENDING_APPROVAL, APPROVED, PAUSED, CANCELED, DELETED
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("unlimited_end_date", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("total_budget", sa.Float(), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=True),
        sa.Column("external_order_id", sa.String(100), nullable=True),  # PO number
        sa.Column("po_number", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_modified_date", sa.DateTime(), nullable=True),
        sa.Column("is_programmatic", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("applied_labels", sa.JSON(), nullable=True),  # List of label IDs
        sa.Column("effective_applied_labels", sa.JSON(), nullable=True),  # List of label IDs
        sa.Column("custom_field_values", sa.JSON(), nullable=True),
        sa.Column("order_metadata", sa.JSON(), nullable=True),  # Additional GAM fields
        sa.Column("last_synced", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes for orders
    op.create_index("idx_gam_orders_tenant", "gam_orders", ["tenant_id"])
    op.create_index("idx_gam_orders_order_id", "gam_orders", ["order_id"])
    op.create_index("idx_gam_orders_status", "gam_orders", ["status"])
    op.create_index("idx_gam_orders_advertiser", "gam_orders", ["advertiser_id"])
    op.create_index("uq_gam_orders", "gam_orders", ["tenant_id", "order_id"], unique=True)

    # Create gam_line_items table
    op.create_table(
        "gam_line_items",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_item_id", sa.String(50), nullable=False),  # GAM Line Item ID
        sa.Column("order_id", sa.String(50), nullable=False),  # GAM Order ID (not FK since order might not be synced)
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "status", sa.String(30), nullable=False
        ),  # DRAFT, PENDING_APPROVAL, APPROVED, PAUSED, ARCHIVED, CANCELED
        sa.Column("line_item_type", sa.String(30), nullable=False),  # STANDARD, SPONSORSHIP, NETWORK, HOUSE, etc.
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("unlimited_end_date", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("auto_extension_days", sa.Integer(), nullable=True),
        sa.Column("cost_type", sa.String(20), nullable=True),  # CPM, CPC, CPD, CPA
        sa.Column("cost_per_unit", sa.Float(), nullable=True),
        sa.Column("discount_type", sa.String(20), nullable=True),  # PERCENTAGE, ABSOLUTE_VALUE
        sa.Column("discount", sa.Float(), nullable=True),
        sa.Column("contracted_units_bought", sa.BigInteger(), nullable=True),
        sa.Column("delivery_rate_type", sa.String(30), nullable=True),  # EVENLY, FRONTLOADED, AS_FAST_AS_POSSIBLE
        sa.Column("goal_type", sa.String(20), nullable=True),  # LIFETIME, DAILY, NONE
        sa.Column("primary_goal_type", sa.String(20), nullable=True),  # IMPRESSIONS, CLICKS, etc.
        sa.Column("primary_goal_units", sa.BigInteger(), nullable=True),
        sa.Column("impression_limit", sa.BigInteger(), nullable=True),
        sa.Column("click_limit", sa.BigInteger(), nullable=True),
        sa.Column("target_platform", sa.String(20), nullable=True),  # WEB, MOBILE, ANY
        sa.Column("environment_type", sa.String(20), nullable=True),  # BROWSER, VIDEO_PLAYER
        sa.Column("allow_overbook", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("skip_inventory_check", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("reserve_at_creation", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("stats_impressions", sa.BigInteger(), nullable=True),
        sa.Column("stats_clicks", sa.BigInteger(), nullable=True),
        sa.Column("stats_ctr", sa.Float(), nullable=True),
        sa.Column("stats_video_completions", sa.BigInteger(), nullable=True),
        sa.Column("stats_video_starts", sa.BigInteger(), nullable=True),
        sa.Column("stats_viewable_impressions", sa.BigInteger(), nullable=True),
        sa.Column(
            "delivery_indicator_type", sa.String(30), nullable=True
        ),  # UNDER_DELIVERY, EXPECTED_DELIVERY, OVER_DELIVERY, etc.
        sa.Column("delivery_data", sa.JSON(), nullable=True),  # Detailed delivery stats
        sa.Column("targeting", sa.JSON(), nullable=True),  # Full targeting criteria
        sa.Column("creative_placeholders", sa.JSON(), nullable=True),  # Creative sizes and companions
        sa.Column("frequency_caps", sa.JSON(), nullable=True),
        sa.Column("applied_labels", sa.JSON(), nullable=True),
        sa.Column("effective_applied_labels", sa.JSON(), nullable=True),
        sa.Column("custom_field_values", sa.JSON(), nullable=True),
        sa.Column("third_party_measurement_settings", sa.JSON(), nullable=True),
        sa.Column("video_max_duration", sa.BigInteger(), nullable=True),
        sa.Column("line_item_metadata", sa.JSON(), nullable=True),  # Additional GAM fields
        sa.Column("last_modified_date", sa.DateTime(), nullable=True),
        sa.Column("creation_date", sa.DateTime(), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("last_synced", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes for line items
    op.create_index("idx_gam_line_items_tenant", "gam_line_items", ["tenant_id"])
    op.create_index("idx_gam_line_items_line_item_id", "gam_line_items", ["line_item_id"])
    op.create_index("idx_gam_line_items_order_id", "gam_line_items", ["order_id"])
    op.create_index("idx_gam_line_items_status", "gam_line_items", ["status"])
    op.create_index("idx_gam_line_items_type", "gam_line_items", ["line_item_type"])
    op.create_index("uq_gam_line_items", "gam_line_items", ["tenant_id", "line_item_id"], unique=True)


def downgrade():
    # Drop indexes
    op.drop_index("uq_gam_line_items", table_name="gam_line_items")
    op.drop_index("idx_gam_line_items_type", table_name="gam_line_items")
    op.drop_index("idx_gam_line_items_status", table_name="gam_line_items")
    op.drop_index("idx_gam_line_items_order_id", table_name="gam_line_items")
    op.drop_index("idx_gam_line_items_line_item_id", table_name="gam_line_items")
    op.drop_index("idx_gam_line_items_tenant", table_name="gam_line_items")

    op.drop_index("uq_gam_orders", table_name="gam_orders")
    op.drop_index("idx_gam_orders_advertiser", table_name="gam_orders")
    op.drop_index("idx_gam_orders_status", table_name="gam_orders")
    op.drop_index("idx_gam_orders_order_id", table_name="gam_orders")
    op.drop_index("idx_gam_orders_tenant", table_name="gam_orders")

    # Drop tables
    op.drop_table("gam_line_items")
    op.drop_table("gam_orders")
