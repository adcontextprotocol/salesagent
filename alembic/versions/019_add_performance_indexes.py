"""Add performance indexes

Revision ID: 019_add_performance_indexes
Revises: 018_add_missing_updated_at
Create Date: 2025-08-30

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "019_add_performance_indexes"
down_revision = "018_add_missing_updated_at"
branch_labels = None
depends_on = None


def upgrade():
    """Add database indexes for performance optimization."""

    # Index for audit_logs queries by tenant and timestamp
    op.create_index(
        "idx_audit_logs_tenant_timestamp", "audit_logs", ["tenant_id", "timestamp"], postgresql_using="btree"
    )

    # Index for tasks queries by tenant and status
    op.create_index("idx_tasks_tenant_status", "tasks", ["tenant_id", "status"], postgresql_using="btree")

    # Index for tasks queries by due_date for overdue checks
    op.create_index(
        "idx_tasks_due_date", "tasks", ["due_date"], postgresql_using="btree", postgresql_where="status = 'pending'"
    )

    # Index for media_buys queries by tenant and status
    op.create_index("idx_media_buys_tenant_status", "media_buys", ["tenant_id", "status"], postgresql_using="btree")

    # Index for media_buys date range queries
    op.create_index(
        "idx_media_buys_dates", "media_buys", ["flight_start_date", "flight_end_date"], postgresql_using="btree"
    )

    # Index for principals queries by tenant
    op.create_index("idx_principals_tenant", "principals", ["tenant_id"], postgresql_using="btree")

    # Index for products queries by tenant
    op.create_index("idx_products_tenant", "products", ["tenant_id"], postgresql_using="btree")


def downgrade():
    """Remove performance indexes."""
    op.drop_index("idx_audit_logs_tenant_timestamp", table_name="audit_logs")
    op.drop_index("idx_tasks_tenant_status", table_name="tasks")
    op.drop_index("idx_tasks_due_date", table_name="tasks")
    op.drop_index("idx_media_buys_tenant_status", table_name="media_buys")
    op.drop_index("idx_media_buys_dates", table_name="media_buys")
    op.drop_index("idx_principals_tenant", table_name="principals")
    op.drop_index("idx_products_tenant", table_name="products")
