"""Add creative_reviews table for AI review analytics.

Revision ID: add_creative_reviews
Revises: 62514cfb8658
Create Date: 2025-10-08 16:00:00.000000

This migration creates the creative_reviews table to store AI and human
review decisions separately from the creative data JSONB column.

Benefits:
- Better queryability for analytics
- Supports multiple reviews per creative over time
- Enables AI learning and improvement tracking
- Tracks human override behavior

The migration also includes data migration logic to copy existing ai_review
data from creatives.data JSONB column into the new table.
"""


import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_creative_reviews"
down_revision = "62514cfb8658"
branch_labels = None
depends_on = None


def upgrade():
    """Add creative_reviews table and migrate existing data."""
    # Create creative_reviews table
    op.create_table(
        "creative_reviews",
        sa.Column("review_id", sa.String(100), nullable=False),
        sa.Column("creative_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(50), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("review_type", sa.String(20), nullable=False),
        sa.Column("reviewer_email", sa.String(255), nullable=True),
        sa.Column("ai_decision", sa.String(20), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("policy_triggered", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        # Use JSONB for PostgreSQL (no SQLite support)
        sa.Column("recommendations", JSONB, nullable=True),
        sa.Column("human_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("final_decision", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("review_id"),
        sa.ForeignKeyConstraint(["creative_id"], ["creatives.creative_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
    )

    # Create indexes for better query performance
    op.create_index("ix_creative_reviews_creative_id", "creative_reviews", ["creative_id"])
    op.create_index("ix_creative_reviews_tenant_id", "creative_reviews", ["tenant_id"])
    op.create_index("ix_creative_reviews_reviewed_at", "creative_reviews", ["reviewed_at"])
    op.create_index("ix_creative_reviews_review_type", "creative_reviews", ["review_type"])
    op.create_index("ix_creative_reviews_final_decision", "creative_reviews", ["final_decision"])

    # Migrate existing ai_review data from creatives.data JSONB column
    connection = op.get_bind()

    # PostgreSQL-only: Use JSONB operators
    migrate_query = text(
        """
        INSERT INTO creative_reviews (
            review_id,
            creative_id,
            tenant_id,
            reviewed_at,
            review_type,
            ai_decision,
            confidence_score,
            policy_triggered,
            reason,
            human_override,
            final_decision
        )
        SELECT
            gen_random_uuid()::text,
            creative_id,
            tenant_id,
            COALESCE(
                (data->>'ai_review'->'reviewed_at')::timestamp,
                updated_at,
                created_at,
                now()
            ),
            'ai',
            data->'ai_review'->>'decision',
            CASE
                WHEN data->'ai_review'->>'confidence' = 'high' THEN 0.9
                WHEN data->'ai_review'->>'confidence' = 'low' THEN 0.3
                ELSE 0.6
            END,
            NULL,
            data->'ai_review'->>'reason',
            false,
            COALESCE(data->'ai_review'->>'decision', status)
        FROM creatives
        WHERE data IS NOT NULL
            AND data::jsonb ? 'ai_review'
            AND data->'ai_review' IS NOT NULL
            AND data->'ai_review' != 'null'::jsonb;
        """
    )

    try:
        result = connection.execute(migrate_query)
        migrated_count = result.rowcount
        print(f"Migrated {migrated_count} existing AI reviews to creative_reviews table")
    except Exception as e:
        print(f"Warning: Data migration encountered an error (table may be empty): {e}")


def downgrade():
    """Remove creative_reviews table.

    WARNING: This will delete all review history data!
    The ai_review data in creatives.data JSONB column is preserved.
    """
    # Drop indexes first
    op.drop_index("ix_creative_reviews_final_decision", table_name="creative_reviews")
    op.drop_index("ix_creative_reviews_review_type", table_name="creative_reviews")
    op.drop_index("ix_creative_reviews_reviewed_at", table_name="creative_reviews")
    op.drop_index("ix_creative_reviews_tenant_id", table_name="creative_reviews")
    op.drop_index("ix_creative_reviews_creative_id", table_name="creative_reviews")

    # Drop table
    op.drop_table("creative_reviews")
