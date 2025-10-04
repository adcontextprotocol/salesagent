"""Add format_performance_metrics table for dynamic pricing

Revision ID: 574ecf3d98c7
Revises: 32f2fa9c903f
Create Date: 2025-10-02 17:40:58.656120

Caches GAM reporting data by country + creative format (AdCP PR #79).
Simpler than product-level: GAM naturally reports by COUNTRY_CODE + CREATIVE_SIZE.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "574ecf3d98c7"
down_revision: str | Sequence[str] | None = "32f2fa9c903f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add format_performance_metrics table for caching historical reporting data.

    Stores GAM reporting data by country + creative format (e.g., US + 300x250).
    Much simpler than product-level since GAM naturally reports these dimensions.
    Populated by scheduled job that queries GAM ReportService with COUNTRY_CODE + CREATIVE_SIZE dimensions.
    """
    op.create_table(
        "format_performance_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=True),  # ISO-3166-1 alpha-3, NULL = all countries
        sa.Column("creative_size", sa.String(length=20), nullable=False),  # "300x250", "728x90", etc.
        # Time period for these metrics
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        # Volume metrics from GAM reporting (COUNTRY_CODE + CREATIVE_SIZE dimensions)
        sa.Column("total_impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_revenue_micros", sa.BigInteger(), nullable=False, server_default="0"),
        # Calculated pricing metrics (in USD)
        sa.Column("average_cpm", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("median_cpm", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("p75_cpm", sa.DECIMAL(precision=10, scale=2), nullable=True),  # 75th percentile
        sa.Column("p90_cpm", sa.DECIMAL(precision=10, scale=2), nullable=True),  # 90th percentile
        # Metadata
        sa.Column(
            "line_item_count", sa.Integer(), nullable=False, server_default="0"
        ),  # Number of line items in aggregate
        sa.Column("last_updated", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "country_code", "creative_size", "period_start", "period_end", name="uq_format_perf_metrics"
        ),
    )

    # Indexes for common queries
    op.create_index("idx_format_perf_tenant", "format_performance_metrics", ["tenant_id"])
    op.create_index("idx_format_perf_country_size", "format_performance_metrics", ["country_code", "creative_size"])
    op.create_index("idx_format_perf_period", "format_performance_metrics", ["period_start", "period_end"])


def downgrade() -> None:
    """Remove format_performance_metrics table."""
    op.drop_index("idx_format_perf_period", table_name="format_performance_metrics")
    op.drop_index("idx_format_perf_country_size", table_name="format_performance_metrics")
    op.drop_index("idx_format_perf_tenant", table_name="format_performance_metrics")
    op.drop_table("format_performance_metrics")
