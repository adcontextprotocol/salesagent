"""Integration tests for dashboard with real database."""

import pytest
from datetime import datetime, timedelta, timezone
import json
from db_config import get_db_connection, DatabaseConfig
from database import init_db


def get_placeholder():
    """Get the appropriate SQL placeholder for the current database type."""
    db_config = DatabaseConfig.get_db_config()
    return "?" if db_config["type"] == "sqlite" else "%s"


def get_interval_syntax(days):
    """Get the appropriate interval syntax for the current database type."""
    db_config = DatabaseConfig.get_db_config()
    if db_config["type"] == "sqlite":
        return f"datetime('now', '-{days} days')"
    else:
        return f"CURRENT_TIMESTAMP - INTERVAL '{days} days'"


@pytest.fixture
def test_db():
    """Create a test database with sample data."""
    # Initialize test database - handle if tables already exist
    try:
        init_db()
    except Exception as e:
        # If tables already exist from another test, that's OK
        if "already exists" not in str(e):
            raise

    conn = get_db_connection()

    # Get placeholder for SQL queries
    ph = get_placeholder()

    # First, clean up any existing test data
    try:
        # Tasks table removed - no need to delete
        conn.execute("DELETE FROM media_buys WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM products WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM principals WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM tenants WHERE tenant_id = 'test_dashboard'")
        conn.commit()
    except:
        pass  # Ignore errors if tables don't exist yet

    # Use INSERT OR IGNORE for SQLite compatibility
    if DatabaseConfig.get_db_config()["type"] == "sqlite":
        conn.execute(
            f"""
            INSERT OR IGNORE INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
            ("test_dashboard", "Test Dashboard Tenant", "test-dashboard", True, "mock"),
        )
    else:
        conn.execute(
            f"""
            INSERT INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """,
            ("test_dashboard", "Test Dashboard Tenant", "test-dashboard", True, "mock"),
        )

    # Commit the tenant first to ensure it exists
    conn.commit()

    # Insert test principals
    if DatabaseConfig.get_db_config()["type"] == "sqlite":
        conn.execute(
            f"""
            INSERT OR IGNORE INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        """,
            ("test_dashboard", "principal_1", "Test Advertiser 1", "token_1", "{}"),
        )

        conn.execute(
            f"""
            INSERT OR IGNORE INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        """,
            ("test_dashboard", "principal_2", "Test Advertiser 2", "token_2", "{}"),
        )
    else:
        conn.execute(
            f"""
            INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            ON CONFLICT (tenant_id, principal_id) DO NOTHING
        """,
            ("test_dashboard", "principal_1", "Test Advertiser 1", "token_1", "{}"),
        )

        conn.execute(
            f"""
            INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            ON CONFLICT (tenant_id, principal_id) DO NOTHING
        """,
            ("test_dashboard", "principal_2", "Test Advertiser 2", "token_2", "{}"),
        )

    # Insert test media buys with different statuses and dates
    now = datetime.now(timezone.utc)

    # Active buy from 5 days ago
    conn.execute(
        f"""
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    """,
        (
            "mb_test_001",
            "test_dashboard",
            "principal_1",
            "Test Order 1",
            "Test Advertiser 1",
            5000.0,
            (now - timedelta(days=5)).date(),
            (now + timedelta(days=25)).date(),
            "active",
            now - timedelta(days=5),
            json.dumps({}),
        ),
    )

    # Pending buy from today
    conn.execute(
        f"""
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    """,
        (
            "mb_test_002",
            "test_dashboard",
            "principal_2",
            "Test Order 2",
            "Test Advertiser 2",
            3000.0,
            now.date(),
            (now + timedelta(days=30)).date(),
            "pending",
            now,
            json.dumps({}),
        ),
    )

    # Completed buy from 45 days ago (for revenue change calculation)
    conn.execute(
        f"""
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    """,
        (
            "mb_test_003",
            "test_dashboard",
            "principal_1",
            "Test Order 3",
            "Test Advertiser 1",
            2000.0,
            (now - timedelta(days=75)).date(),
            (now - timedelta(days=45)).date(),
            "completed",
            now - timedelta(days=45),
            json.dumps({}),
        ),
    )

    # Skip inserting tasks - table removed in favor of workflow_steps
    # The dashboard doesn't use tasks anymore

    # Skip second task insert - tasks table removed

    # Insert test products with required fields
    conn.execute(
        f"""
        INSERT INTO products (product_id, tenant_id, name, formats, targeting_template, delivery_type, is_fixed_price)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    """,
        (
            "prod_001",
            "test_dashboard",
            "Test Product 1",
            '["display_300x250"]',
            "{}",
            "guaranteed",
            True,
        ),
    )

    conn.execute(
        f"""
        INSERT INTO products (product_id, tenant_id, name, formats, targeting_template, delivery_type, is_fixed_price)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
    """,
        (
            "prod_002",
            "test_dashboard",
            "Test Product 2",
            '["video_16x9"]',
            "{}",
            "guaranteed",
            True,
        ),
    )

    conn.commit()

    yield conn

    # Cleanup
    try:
        # Tasks table removed - no need to delete
        conn.execute("DELETE FROM media_buys WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM products WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM principals WHERE tenant_id = 'test_dashboard'")
        conn.execute("DELETE FROM tenants WHERE tenant_id = 'test_dashboard'")
        conn.commit()
    except Exception as e:
        print(f"Cleanup error: {e}")
    finally:
        conn.close()


class TestDashboardMetricsIntegration:
    """Test dashboard metrics with real database."""

    @pytest.mark.requires_db
    def test_revenue_metrics(self, test_db):
        """Test revenue calculation from database."""
        ph = get_placeholder()
        interval_30 = get_interval_syntax(30)
        # Query for 30-day revenue
        cursor = test_db.execute(
            f"""
            SELECT COALESCE(SUM(budget), 0) as total_revenue
            FROM media_buys
            WHERE tenant_id = {ph}
            AND status IN ('active', 'completed')
            AND created_at >= {interval_30}
        """,
            ("test_dashboard",),
        )

        total_revenue = cursor.fetchone()[0]

        # Should include active buy (5000) but not pending (3000) or old completed (2000)
        assert total_revenue == 5000.0

    @pytest.mark.requires_db
    def test_revenue_change_calculation(self, test_db):
        """Test revenue change vs previous period."""
        ph = get_placeholder()
        interval_30 = get_interval_syntax(30)
        interval_60 = get_interval_syntax(60)

        # Current period (last 30 days)
        cursor = test_db.execute(
            f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = {ph}
            AND status IN ('active', 'completed')
            AND created_at >= {interval_30}
        """,
            ("test_dashboard",),
        )
        current = cursor.fetchone()[0]

        # Previous period (30-60 days ago)
        cursor = test_db.execute(
            f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = {ph}
            AND status IN ('active', 'completed')
            AND created_at >= {interval_60}
            AND created_at < {interval_30}
        """,
            ("test_dashboard",),
        )
        previous = cursor.fetchone()[0]

        # Current should be 5000, previous should be 2000
        assert current == 5000.0
        assert previous == 2000.0

        # Calculate change
        change = ((current - previous) / previous) * 100 if previous > 0 else 0
        assert change == 150.0  # 150% increase

    @pytest.mark.requires_db
    def test_media_buy_counts(self, test_db):
        """Test counting active and pending media buys."""
        ph = get_placeholder()
        # Active buys
        cursor = test_db.execute(
            f"""
            SELECT COUNT(*) FROM media_buys
            WHERE tenant_id = {ph} AND status = 'active'
        """,
            ("test_dashboard",),
        )
        active = cursor.fetchone()[0]
        assert active == 1

        # Pending buys
        cursor = test_db.execute(
            f"""
            SELECT COUNT(*) FROM media_buys
            WHERE tenant_id = {ph} AND status = 'pending'
        """,
            ("test_dashboard",),
        )
        pending = cursor.fetchone()[0]
        assert pending == 1

    @pytest.mark.requires_db
    def test_task_metrics(self, test_db):
        """Test task counting and overdue detection."""
        ph = get_placeholder()
        # Open tasks - using tasks table not human_tasks
        cursor = test_db.execute(
            f"""
            SELECT COUNT(*) FROM tasks
            WHERE tenant_id = {ph} AND status IN ('pending', 'in_progress')
        """,
            ("test_dashboard",),
        )
        open_tasks = cursor.fetchone()[0]
        assert open_tasks == 2

        # Overdue tasks (older than 3 days)
        interval_3 = get_interval_syntax(3)
        cursor = test_db.execute(
            f"""
            SELECT COUNT(*) FROM tasks
            WHERE tenant_id = {ph}
            AND status IN ('pending', 'in_progress')
            AND created_at < {interval_3}
        """,
            ("test_dashboard",),
        )
        overdue = cursor.fetchone()[0]
        assert overdue == 1  # Only task_002 is overdue

    @pytest.mark.requires_db
    def test_advertiser_metrics(self, test_db):
        """Test advertiser counting."""
        ph = get_placeholder()
        # Total advertisers
        cursor = test_db.execute(
            f"""
            SELECT COUNT(*) FROM principals WHERE tenant_id = {ph}
        """,
            ("test_dashboard",),
        )
        total = cursor.fetchone()[0]
        assert total == 2

        # Active advertisers (with activity in last 30 days)
        interval_30 = get_interval_syntax(30)
        cursor = test_db.execute(
            f"""
            SELECT COUNT(DISTINCT principal_id)
            FROM media_buys
            WHERE tenant_id = {ph}
            AND created_at >= {interval_30}
        """,
            ("test_dashboard",),
        )
        active = cursor.fetchone()[0]
        assert active == 2  # Both have recent activity


class TestDashboardDataRetrieval:
    """Test retrieving and formatting dashboard data."""

    @pytest.mark.requires_db
    def test_recent_media_buys(self, test_db):
        """Test fetching recent media buys."""
        ph = get_placeholder()
        cursor = test_db.execute(
            f"""
            SELECT
                mb.media_buy_id,
                mb.principal_id,
                mb.advertiser_name,
                mb.status,
                mb.budget,
                mb.created_at
            FROM media_buys mb
            WHERE mb.tenant_id = {ph}
            ORDER BY mb.created_at DESC
            LIMIT 10
        """,
            ("test_dashboard",),
        )

        buys = cursor.fetchall()
        assert len(buys) == 3

        # Most recent should be mb_test_002 (pending)
        most_recent = buys[0]
        assert most_recent[0] == "mb_test_002"
        assert most_recent[3] == "pending"
        assert most_recent[4] == 3000.0

    @pytest.mark.requires_db
    def test_pending_tasks_retrieval(self, test_db):
        """Test fetching pending tasks with descriptions."""
        ph = get_placeholder()
        db_config = DatabaseConfig.get_db_config()

        if db_config["type"] == "sqlite":
            # SQLite syntax
            cursor = test_db.execute(
                f"""
                SELECT task_type,
                       CASE
                           WHEN metadata != '' AND metadata IS NOT NULL
                           THEN json_extract(metadata, '$.description')
                           ELSE task_type
                       END as description
                FROM tasks
                WHERE tenant_id = {ph} AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 5
            """,
                ("test_dashboard",),
            )
        else:
            # PostgreSQL syntax
            cursor = test_db.execute(
                f"""
                SELECT task_type,
                       CASE
                           WHEN metadata::text != '' AND metadata IS NOT NULL
                           THEN (metadata::json->>'description')::text
                           ELSE task_type
                       END as description
                FROM tasks
                WHERE tenant_id = {ph} AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 5
            """,
                ("test_dashboard",),
            )

        tasks = cursor.fetchall()
        assert len(tasks) == 2

        # Check descriptions were extracted
        for task in tasks:
            assert task[1] is not None
            if task[0] == "approve_creative":
                assert "Approve creative" in task[1]

    @pytest.mark.requires_db
    def test_revenue_by_advertiser_chart(self, test_db):
        """Test data for revenue chart."""
        ph = get_placeholder()
        interval_7 = get_interval_syntax(7)
        cursor = test_db.execute(
            f"""
            SELECT
                mb.advertiser_name,
                SUM(mb.budget) as revenue
            FROM media_buys mb
            WHERE mb.tenant_id = {ph}
            AND mb.created_at >= {interval_7}
            AND mb.status IN ('active', 'completed')
            GROUP BY mb.advertiser_name
            ORDER BY revenue DESC
            LIMIT 10
        """,
            ("test_dashboard",),
        )

        chart_data = cursor.fetchall()

        # Should have Test Advertiser 1 with 5000 budget
        assert len(chart_data) == 1
        assert chart_data[0][0] == "Test Advertiser 1"
        assert chart_data[0][1] == 5000.0


class TestDashboardErrorCases:
    """Test dashboard behavior with edge cases."""

    @pytest.mark.requires_db
    def test_empty_tenant_data(self, test_db):
        """Test dashboard with tenant that has no data."""
        ph = get_placeholder()
        db_config = DatabaseConfig.get_db_config()

        # Create empty tenant
        if db_config["type"] == "sqlite":
            test_db.execute(
                f"""
                INSERT OR IGNORE INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
                ("empty_tenant", "Empty Tenant", "empty", True, "mock"),
            )
        else:
            test_db.execute(
                f"""
                INSERT INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id) DO NOTHING
            """,
                ("empty_tenant", "Empty Tenant", "empty", True, "mock"),
            )
        test_db.commit()

        # All metrics should return 0 or empty
        cursor = test_db.execute(
            f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = {ph}
        """,
            ("empty_tenant",),
        )

        assert cursor.fetchone()[0] == 0

        # Cleanup
        test_db.execute("DELETE FROM tenants WHERE tenant_id = 'empty_tenant'")
        test_db.commit()

    @pytest.mark.requires_db
    def test_null_budget_handling(self, test_db):
        """Test handling of NULL budget values."""
        ph = get_placeholder()
        # Insert media buy with NULL budget
        test_db.execute(
            f"""
            INSERT INTO media_buys (
                media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
                budget, start_date, end_date, status, raw_request
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (
                "mb_null",
                "test_dashboard",
                "principal_1",
                "Null Budget",
                "Test",
                None,
                datetime.now().date(),
                datetime.now().date(),
                "active",
                json.dumps({}),
            ),
        )
        test_db.commit()

        # Query should handle NULL gracefully
        cursor = test_db.execute(
            f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = {ph} AND media_buy_id = {ph}
        """,
            ("test_dashboard", "mb_null"),
        )

        assert cursor.fetchone()[0] == 0

        # Cleanup
        test_db.execute("DELETE FROM media_buys WHERE media_buy_id = 'mb_null'")
        test_db.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "requires_db"])
