"""Add authorized properties table

Revision ID: 023_add_authorized_properties
Revises: 022_add_signals_agent_config
Create Date: 2025-01-20 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "023_add_authorized_properties"
down_revision = "6e19576203a0"
branch_labels = None
depends_on = None


def upgrade():
    # Check if tables already exist to make migration idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create authorized_properties table if it doesn't exist
    if "authorized_properties" not in existing_tables:
        op.create_table(
            "authorized_properties",
            sa.Column("property_id", sa.String(100), nullable=False),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("property_type", sa.String(20), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("identifiers", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
            sa.Column("tags", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
            sa.Column("publisher_domain", sa.String(255), nullable=False),
            sa.Column("verification_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("verification_checked_at", sa.DateTime(), nullable=True),
            sa.Column("verification_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
            sa.PrimaryKeyConstraint("property_id", "tenant_id"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
            sa.CheckConstraint(
                "property_type IN ('website', 'mobile_app', 'ctv_app', 'dooh', 'podcast', 'radio', 'streaming_audio')",
                name="ck_property_type",
            ),
            sa.CheckConstraint(
                "verification_status IN ('pending', 'verified', 'failed')", name="ck_verification_status"
            ),
        )
        print("✅ Created authorized_properties table")
    else:
        print("ℹ️  authorized_properties table already exists, skipping")

    # Create property_tags table if it doesn't exist
    if "property_tags" not in existing_tables:
        op.create_table(
            "property_tags",
            sa.Column("tag_id", sa.String(50), nullable=False),
            sa.Column("tenant_id", sa.String(50), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
            sa.PrimaryKeyConstraint("tag_id", "tenant_id"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        )
        print("✅ Created property_tags table")
    else:
        print("ℹ️  property_tags table already exists, skipping")

    # Create indices if they don't exist
    existing_indexes = (
        [idx["name"] for idx in inspector.get_indexes("authorized_properties")]
        if "authorized_properties" in existing_tables
        else []
    )

    if "idx_authorized_properties_tenant" not in existing_indexes:
        op.create_index("idx_authorized_properties_tenant", "authorized_properties", ["tenant_id"])
        print("✅ Created idx_authorized_properties_tenant index")

    if "idx_authorized_properties_domain" not in existing_indexes:
        op.create_index("idx_authorized_properties_domain", "authorized_properties", ["publisher_domain"])
        print("✅ Created idx_authorized_properties_domain index")

    if "idx_authorized_properties_type" not in existing_indexes:
        op.create_index("idx_authorized_properties_type", "authorized_properties", ["property_type"])
        print("✅ Created idx_authorized_properties_type index")

    if "idx_authorized_properties_verification" not in existing_indexes:
        op.create_index("idx_authorized_properties_verification", "authorized_properties", ["verification_status"])
        print("✅ Created idx_authorized_properties_verification index")

    existing_tag_indexes = (
        [idx["name"] for idx in inspector.get_indexes("property_tags")] if "property_tags" in existing_tables else []
    )

    if "idx_property_tags_tenant" not in existing_tag_indexes:
        op.create_index("idx_property_tags_tenant", "property_tags", ["tenant_id"])
        print("✅ Created idx_property_tags_tenant index")


def downgrade():
    # Check if tables exist before dropping to make downgrade idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Drop property_tags indices and table if they exist
    if "property_tags" in existing_tables:
        existing_tag_indexes = [idx["name"] for idx in inspector.get_indexes("property_tags")]
        if "idx_property_tags_tenant" in existing_tag_indexes:
            op.drop_index("idx_property_tags_tenant")
        op.drop_table("property_tags")
        print("✅ Dropped property_tags table and indices")

    # Drop authorized_properties indices and table if they exist
    if "authorized_properties" in existing_tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("authorized_properties")]

        if "idx_authorized_properties_verification" in existing_indexes:
            op.drop_index("idx_authorized_properties_verification")
        if "idx_authorized_properties_type" in existing_indexes:
            op.drop_index("idx_authorized_properties_type")
        if "idx_authorized_properties_domain" in existing_indexes:
            op.drop_index("idx_authorized_properties_domain")
        if "idx_authorized_properties_tenant" in existing_indexes:
            op.drop_index("idx_authorized_properties_tenant")

        op.drop_table("authorized_properties")
        print("✅ Dropped authorized_properties table and indices")
