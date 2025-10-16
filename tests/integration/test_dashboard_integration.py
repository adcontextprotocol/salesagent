"""Integration tests for dashboard with real database."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.core.database.database_session import DatabaseConfig

pytestmark = pytest.mark.integration


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
@pytest.mark.requires_db
def test_db(integration_db):
    """Create a test database with sample data."""
    # Tables are already created by integration_db fixture
    # No need to call init_db() which expects existing tables

    from sqlalchemy import text

    from src.core.database.database_session import get_engine

    engine = get_engine()
    conn = engine.connect()

    # Get placeholder for SQL queries
    ph = get_placeholder()

    # First, clean up any existing test data
    try:
        # Tasks table removed - no need to delete
        conn.execute(text("DELETE FROM media_buys WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM products WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM principals WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM tenants WHERE tenant_id = 'test_dashboard'"))
        conn.commit()
    except:
        pass  # Ignore errors if tables don't exist yet

    # Use INSERT OR IGNORE for SQLite compatibility
    if DatabaseConfig.get_db_config()["type"] == "sqlite":
        conn.execute(
            text(
                """
            INSERT OR IGNORE INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
            VALUES (:tenant_id, :name, :subdomain, :is_active, :ad_server, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "name": "Test Dashboard Tenant",
                "subdomain": "test-dashboard",
                "is_active": True,
                "ad_server": "mock",
            },
        )
    else:
        conn.execute(
            text(
                """
            INSERT INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
            VALUES (:tenant_id, :name, :subdomain, :is_active, :ad_server, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "name": "Test Dashboard Tenant",
                "subdomain": "test-dashboard",
                "is_active": True,
                "ad_server": "mock",
            },
        )

    # Commit the tenant first to ensure it exists
    conn.commit()

    # Insert test principals
    if DatabaseConfig.get_db_config()["type"] == "sqlite":
        conn.execute(
            text(
                """
            INSERT OR IGNORE INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES (:tenant_id, :principal_id, :name, :access_token, :platform_mappings)
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "principal_id": "principal_1",
                "name": "Test Advertiser 1",
                "access_token": "token_1",
                "platform_mappings": "{}",
            },
        )

        conn.execute(
            text(
                """
            INSERT OR IGNORE INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES (:tenant_id, :principal_id, :name, :access_token, :platform_mappings)
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "principal_id": "principal_2",
                "name": "Test Advertiser 2",
                "access_token": "token_2",
                "platform_mappings": "{}",
            },
        )
    else:
        conn.execute(
            text(
                """
            INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES (:tenant_id, :principal_id, :name, :access_token, :platform_mappings)
            ON CONFLICT (tenant_id, principal_id) DO NOTHING
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "principal_id": "principal_1",
                "name": "Test Advertiser 1",
                "access_token": "token_1",
                "platform_mappings": "{}",
            },
        )

        conn.execute(
            text(
                """
            INSERT INTO principals (tenant_id, principal_id, name, access_token, platform_mappings)
            VALUES (:tenant_id, :principal_id, :name, :access_token, :platform_mappings)
            ON CONFLICT (tenant_id, principal_id) DO NOTHING
        """
            ),
            {
                "tenant_id": "test_dashboard",
                "principal_id": "principal_2",
                "name": "Test Advertiser 2",
                "access_token": "token_2",
                "platform_mappings": "{}",
            },
        )

    # Insert test media buys with different statuses and dates
    now = datetime.now(UTC)

    # Active buy from 5 days ago
    conn.execute(
        text(
            """
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES (:media_buy_id, :tenant_id, :principal_id, :order_name, :advertiser_name,
                  :budget, :start_date, :end_date, :status, :created_at, :raw_request)
    """
        ),
        {
            "media_buy_id": "mb_test_001",
            "tenant_id": "test_dashboard",
            "principal_id": "principal_1",
            "order_name": "Test Order 1",
            "advertiser_name": "Test Advertiser 1",
            "budget": 5000.0,
            "start_date": (now - timedelta(days=5)).date(),
            "end_date": (now + timedelta(days=25)).date(),
            "status": "active",
            "created_at": now - timedelta(days=5),
            "raw_request": json.dumps({}),
        },
    )

    # Pending buy from today
    conn.execute(
        text(
            """
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES (:media_buy_id, :tenant_id, :principal_id, :order_name, :advertiser_name,
                  :budget, :start_date, :end_date, :status, :created_at, :raw_request)
    """
        ),
        {
            "media_buy_id": "mb_test_002",
            "tenant_id": "test_dashboard",
            "principal_id": "principal_2",
            "order_name": "Test Order 2",
            "advertiser_name": "Test Advertiser 2",
            "budget": 3000.0,
            "start_date": now.date(),
            "end_date": (now + timedelta(days=30)).date(),
            "status": "pending",
            "created_at": now,
            "raw_request": json.dumps({}),
        },
    )

    # Completed buy from 45 days ago (for revenue change calculation)
    conn.execute(
        text(
            """
        INSERT INTO media_buys (
            media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
            budget, start_date, end_date, status, created_at, raw_request
        ) VALUES (:media_buy_id, :tenant_id, :principal_id, :order_name, :advertiser_name,
                  :budget, :start_date, :end_date, :status, :created_at, :raw_request)
    """
        ),
        {
            "media_buy_id": "mb_test_003",
            "tenant_id": "test_dashboard",
            "principal_id": "principal_1",
            "order_name": "Test Order 3",
            "advertiser_name": "Test Advertiser 1",
            "budget": 2000.0,
            "start_date": (now - timedelta(days=75)).date(),
            "end_date": (now - timedelta(days=45)).date(),
            "status": "completed",
            "created_at": now - timedelta(days=45),
            "raw_request": json.dumps({}),
        },
    )

    # Skip inserting tasks - table removed in favor of workflow_steps
    # The dashboard doesn't use tasks anymore

    # Skip second task insert - tasks table removed

    # Insert test products with required fields
    conn.execute(
        text(
            """
        INSERT INTO products (product_id, tenant_id, name, formats, targeting_template, delivery_type, is_fixed_price)
        VALUES (:product_id, :tenant_id, :name, :formats, :targeting_template, :delivery_type, :is_fixed_price)
    """
        ),
        {
            "product_id": "prod_001",
            "tenant_id": "test_dashboard",
            "name": "Test Product 1",
            "formats": '["display_300x250"]',
            "targeting_template": "{}",
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        },
    )

    conn.execute(
        text(
            """
        INSERT INTO products (product_id, tenant_id, name, formats, targeting_template, delivery_type, is_fixed_price)
        VALUES (:product_id, :tenant_id, :name, :formats, :targeting_template, :delivery_type, :is_fixed_price)
    """
        ),
        {
            "product_id": "prod_002",
            "tenant_id": "test_dashboard",
            "name": "Test Product 2",
            "formats": '["video_16x9"]',
            "targeting_template": "{}",
            "delivery_type": "guaranteed",
            "is_fixed_price": True,
        },
    )

    conn.commit()

    yield conn

    # Cleanup
    try:
        # Tasks table removed - no need to delete
        conn.execute(text("DELETE FROM media_buys WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM products WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM principals WHERE tenant_id = 'test_dashboard'"))
        conn.execute(text("DELETE FROM tenants WHERE tenant_id = 'test_dashboard'"))
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
        from sqlalchemy import text

        interval_30 = get_interval_syntax(30)
        # Query for 30-day revenue
        cursor = test_db.execute(
            text(
                f"""
            SELECT COALESCE(SUM(budget), 0) as total_revenue
            FROM media_buys
            WHERE tenant_id = :tenant_id
            AND status IN ('active', 'completed')
            AND created_at >= {interval_30}
        """
            ),
            {"tenant_id": "test_dashboard"},
        )

        total_revenue = cursor.fetchone()[0]

        # Should include active buy (5000) but not pending (3000) or old completed (2000)
        assert total_revenue == 5000.0

    @pytest.mark.requires_db
    def test_revenue_change_calculation(self, test_db):
        """Test revenue change vs previous period."""
        from sqlalchemy import text

        interval_30 = get_interval_syntax(30)
        interval_60 = get_interval_syntax(60)

        # Current period (last 30 days)
        cursor = test_db.execute(
            text(
                f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = :tenant_id
            AND status IN ('active', 'completed')
            AND created_at >= {interval_30}
        """
            ),
            {"tenant_id": "test_dashboard"},
        )
        current = cursor.fetchone()[0]

        # Previous period (30-60 days ago)
        cursor = test_db.execute(
            text(
                f"""
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = :tenant_id
            AND status IN ('active', 'completed')
            AND created_at >= {interval_60}
            AND created_at < {interval_30}
        """
            ),
            {"tenant_id": "test_dashboard"},
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
        from sqlalchemy import text

        # Active buys
        cursor = test_db.execute(
            text(
                """
            SELECT COUNT(*) FROM media_buys
            WHERE tenant_id = :tenant_id AND status = 'active'
        """
            ),
            {"tenant_id": "test_dashboard"},
        )
        active = cursor.fetchone()[0]
        assert active == 1

        # Pending buys
        cursor = test_db.execute(
            text(
                """
            SELECT COUNT(*) FROM media_buys
            WHERE tenant_id = :tenant_id AND status = 'pending'
        """
            ),
            {"tenant_id": "test_dashboard"},
        )
        pending = cursor.fetchone()[0]
        assert pending == 1

    @pytest.mark.requires_db
    def test_advertiser_metrics(self, test_db):
        """Test advertiser counting."""
        from sqlalchemy import text

        # Total advertisers
        cursor = test_db.execute(
            text(
                """
            SELECT COUNT(*) FROM principals WHERE tenant_id = :tenant_id
        """
            ),
            {"tenant_id": "test_dashboard"},
        )
        total = cursor.fetchone()[0]
        assert total == 2

        # Active advertisers (with activity in last 30 days)
        interval_30 = get_interval_syntax(30)
        cursor = test_db.execute(
            text(
                f"""
            SELECT COUNT(DISTINCT principal_id)
            FROM media_buys
            WHERE tenant_id = :tenant_id
            AND created_at >= {interval_30}
        """
            ),
            {"tenant_id": "test_dashboard"},
        )
        active = cursor.fetchone()[0]
        assert active == 2  # Both have recent activity


class TestDashboardDataRetrieval:
    """Test retrieving and formatting dashboard data."""

    @pytest.mark.requires_db
    def test_recent_media_buys(self, test_db):
        """Test fetching recent media buys."""
        from sqlalchemy import text

        cursor = test_db.execute(
            text(
                """
            SELECT
                mb.media_buy_id,
                mb.principal_id,
                mb.advertiser_name,
                mb.status,
                mb.budget,
                mb.created_at
            FROM media_buys mb
            WHERE mb.tenant_id = :tenant_id
            ORDER BY mb.created_at DESC
            LIMIT 10
        """
            ),
            {"tenant_id": "test_dashboard"},
        )

        buys = cursor.fetchall()
        assert len(buys) == 3

        # Most recent should be mb_test_002 (pending)
        most_recent = buys[0]
        assert most_recent[0] == "mb_test_002"
        assert most_recent[3] == "pending"
        assert most_recent[4] == 3000.0

    @pytest.mark.requires_db
    def test_revenue_by_advertiser_chart(self, test_db):
        """Test data for revenue chart."""
        from sqlalchemy import text

        interval_7 = get_interval_syntax(7)
        cursor = test_db.execute(
            text(
                f"""
            SELECT
                mb.advertiser_name,
                SUM(mb.budget) as revenue
            FROM media_buys mb
            WHERE mb.tenant_id = :tenant_id
            AND mb.created_at >= {interval_7}
            AND mb.status IN ('active', 'completed')
            GROUP BY mb.advertiser_name
            ORDER BY revenue DESC
            LIMIT 10
        """
            ),
            {"tenant_id": "test_dashboard"},
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
        from sqlalchemy import text

        db_config = DatabaseConfig.get_db_config()

        # Create empty tenant
        if db_config["type"] == "sqlite":
            test_db.execute(
                text(
                    """
                INSERT OR IGNORE INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
                VALUES (:tenant_id, :name, :subdomain, :is_active, :ad_server, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
                ),
                {
                    "tenant_id": "empty_tenant",
                    "name": "Empty Tenant",
                    "subdomain": "empty",
                    "is_active": True,
                    "ad_server": "mock",
                },
            )
        else:
            test_db.execute(
                text(
                    """
                INSERT INTO tenants (tenant_id, name, subdomain, is_active, ad_server, created_at, updated_at)
                VALUES (:tenant_id, :name, :subdomain, :is_active, :ad_server, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id) DO NOTHING
            """
                ),
                {
                    "tenant_id": "empty_tenant",
                    "name": "Empty Tenant",
                    "subdomain": "empty",
                    "is_active": True,
                    "ad_server": "mock",
                },
            )
        test_db.commit()

        # All metrics should return 0 or empty
        cursor = test_db.execute(
            text(
                """
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = :tenant_id
        """
            ),
            {"tenant_id": "empty_tenant"},
        )

        assert cursor.fetchone()[0] == 0

        # Cleanup
        test_db.execute(text("DELETE FROM tenants WHERE tenant_id = 'empty_tenant'"))
        test_db.commit()

    @pytest.mark.requires_db
    def test_null_budget_handling(self, test_db):
        """Test handling of NULL budget values."""
        from sqlalchemy import text

        # Insert media buy with NULL budget
        test_db.execute(
            text(
                """
            INSERT INTO media_buys (
                media_buy_id, tenant_id, principal_id, order_name, advertiser_name,
                budget, start_date, end_date, status, raw_request
            ) VALUES (:media_buy_id, :tenant_id, :principal_id, :order_name, :advertiser_name,
                      :budget, :start_date, :end_date, :status, :raw_request)
            """
            ),
            {
                "media_buy_id": "mb_null",
                "tenant_id": "test_dashboard",
                "principal_id": "principal_1",
                "order_name": "Null Budget",
                "advertiser_name": "Test",
                "budget": None,
                "start_date": datetime.now().date(),
                "end_date": datetime.now().date(),
                "status": "active",
                "raw_request": json.dumps({}),
            },
        )
        test_db.commit()

        # Query should handle NULL gracefully
        cursor = test_db.execute(
            text(
                """
            SELECT COALESCE(SUM(budget), 0)
            FROM media_buys
            WHERE tenant_id = :tenant_id AND media_buy_id = :media_buy_id
        """
            ),
            {"tenant_id": "test_dashboard", "media_buy_id": "mb_null"},
        )

        assert cursor.fetchone()[0] == 0

        # Cleanup
        test_db.execute(text("DELETE FROM media_buys WHERE media_buy_id = 'mb_null'"))
        test_db.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "requires_db"])
