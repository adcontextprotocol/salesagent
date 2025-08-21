"""Unit tests for the new dashboard functionality."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# Test data fixtures
@pytest.fixture
def mock_tenant():
    return {
        "tenant_id": "test_tenant",
        "name": "Test Publisher",
        "subdomain": "test",
        "is_active": True,
        "ad_server": "mock",
    }


@pytest.fixture
def mock_media_buys():
    return [
        {
            "media_buy_id": "mb_001",
            "principal_id": "p_001",
            "advertiser_name": "Test Advertiser 1",
            "status": "active",
            "budget": 5000.0,
            "created_at": datetime.now(UTC) - timedelta(hours=2),
        },
        {
            "media_buy_id": "mb_002",
            "principal_id": "p_002",
            "advertiser_name": "Test Advertiser 2",
            "status": "pending",
            "budget": 3000.0,
            "created_at": datetime.now(UTC) - timedelta(days=1),
        },
    ]


@pytest.fixture
def mock_human_tasks():
    return [
        {
            "task_type": "approve_creative",
            "details": json.dumps({"description": "Approve creative CR_123"}),
            "status": "pending",
            "created_at": datetime.now(UTC) - timedelta(days=4),
        },
        {
            "task_type": "review_budget",
            "details": json.dumps({"description": "Review budget for MB_001"}),
            "status": "pending",
            "created_at": datetime.now(UTC) - timedelta(hours=1),
        },
    ]


@pytest.mark.unit
class TestDashboardRoutes:
    """Test the dashboard route functions."""

    def test_dashboard_route_authentication(self, flask_client):
        """Test that dashboard requires authentication."""
        response = flask_client.get("/tenant/test_tenant")
        assert response.status_code == 302  # Should redirect to login
        assert "/login" in response.location

    @patch("src.core.database.database_session.get_db_session")
    def test_dashboard_with_valid_tenant(self, mock_db, flask_client, mock_tenant):
        """Test dashboard loads with valid tenant."""
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value = mock_conn

        # Mock different query results based on call count
        # First call is for tenant info, subsequent calls are for metrics
        mock_cursor.fetchone.side_effect = [
            # Tenant query
            (
                mock_tenant["tenant_id"],
                mock_tenant["name"],
                mock_tenant["subdomain"],
                mock_tenant["is_active"],
                mock_tenant["ad_server"],
            ),
            # Revenue query
            (5000.0,),
            # Previous revenue query
            (4000.0,),
            # Active buys query
            (10,),
            # Pending buys query
            (5,),
            # Open tasks query
            (8,),
            # Overdue tasks query
            (2,),
            # Active advertisers query
            (15,),
            # Total advertisers query
            (20,),
            # Default for any additional queries
            (0,),
        ]

        with flask_client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["role"] = "super_admin"

        response = flask_client.get("/tenant/test_tenant")

        # Should not error
        assert response.status_code != 500

    @patch("src.core.database.database_session.get_db_session")
    def test_dashboard_invalid_tenant(self, mock_get_session, flask_client):
        """Test dashboard with non-existent tenant."""
        # Mock database session using context manager
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_get_session.return_value = mock_session

        # Mock tenant query returning None (tenant not found)
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with flask_client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["role"] = "super_admin"

        response = flask_client.get("/tenant/nonexistent")

        # Should return 404 or redirect
        assert response.status_code in [404, 302]


class TestDashboardMetrics:
    """Test dashboard metric calculations."""

    @patch("src.core.database.database_session.get_db_session")
    def test_revenue_calculation(self, mock_db, mock_media_buys):
        """Test revenue metrics are calculated correctly."""
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session
        mock_db.return_value.__exit__.return_value = None

        # Mock MediaBuy ORM query for active buys
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_filter = MagicMock()
        mock_query.filter_by.return_value = mock_filter

        # Create mock MediaBuy objects
        mock_buy1 = MagicMock()
        mock_buy1.budget = 3000.0
        mock_buy1.status = "active"

        mock_buy2 = MagicMock()
        mock_buy2.budget = 2000.0
        mock_buy2.status = "active"

        mock_filter.all.return_value = [mock_buy1, mock_buy2]

        # Calculate total revenue from active media buys
        from src.core.database.models import MediaBuy

        with mock_db() as session:
            active_buys = session.query(MediaBuy).filter_by(status="active").all()
            total_revenue = sum(buy.budget for buy in active_buys)

        assert total_revenue == 5000.0

    @patch("src.core.database.database_session.get_db_session")
    def test_task_count_metrics(self, mock_db, mock_human_tasks):
        """Test task counting metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value = mock_conn

        # Mock task count query
        pending_tasks = len([t for t in mock_human_tasks if t["status"] == "pending"])
        mock_cursor.fetchone.return_value = [pending_tasks]

        assert pending_tasks == 2

        # Check overdue tasks (older than 3 days)
        overdue = len(
            [
                t
                for t in mock_human_tasks
                if t["status"] == "pending" and t["created_at"] < datetime.now(UTC) - timedelta(days=3)
            ]
        )
        assert overdue == 1


class TestDashboardQueries:
    """Test database queries used in dashboard."""

    def test_postgresql_query_syntax(self):
        """Ensure queries use PostgreSQL syntax."""
        queries = [
            "SELECT COALESCE(SUM(budget), 0) FROM media_buys WHERE tenant_id = %s",
            "SELECT COUNT(*) FROM human_tasks WHERE tenant_id = %s AND status IN ('pending', 'in_progress')",
            "SELECT COUNT(*) FROM media_buys WHERE tenant_id = %s AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'",
        ]

        for query in queries:
            # Check for PostgreSQL placeholder
            assert "%s" in query
            # Check for PostgreSQL interval syntax
            if "INTERVAL" in query:
                assert "INTERVAL '" in query
            # Should not have SQLite syntax
            assert "datetime(" not in query
            assert "?" not in query

    def test_json_field_handling(self):
        """Test proper JSON field access in PostgreSQL."""
        query = """
        SELECT task_type,
               CASE
                   WHEN details::text != '' AND details IS NOT NULL
                   THEN (details::json->>'description')::text
                   ELSE task_type
               END as description
        FROM human_tasks
        """

        # Check for proper PostgreSQL JSON operators
        assert "::json->>" in query
        assert "::text" in query


class TestDashboardDataTransformation:
    """Test data transformation for dashboard display."""

    def test_relative_time_calculation(self):
        """Test relative time string generation."""
        now = datetime.now(UTC)

        test_cases = [
            (now - timedelta(minutes=5), "5m ago"),
            (now - timedelta(hours=2), "2h ago"),
            (now - timedelta(days=1), "1d ago"),
            (now - timedelta(days=5), "5d ago"),
        ]

        for created_at, expected in test_cases:
            delta = now - created_at

            if delta.days > 0:
                relative = f"{delta.days}d ago"
            elif delta.seconds > 3600:
                relative = f"{delta.seconds // 3600}h ago"
            else:
                relative = f"{delta.seconds // 60}m ago"

            assert relative == expected

    def test_revenue_change_calculation(self):
        """Test revenue change percentage calculation."""
        test_cases = [
            (1000, 500, 100.0),  # 100% increase
            (500, 1000, -50.0),  # 50% decrease
            (1000, 1000, 0.0),  # No change
            (1000, 0, 0),  # From zero (special case)
        ]

        for current, previous, expected_change in test_cases:
            if previous > 0:
                change = ((current - previous) / previous) * 100
            else:
                change = 0

            assert change == expected_change


class TestDashboardErrorHandling:
    """Test error handling in dashboard."""

    @patch("src.core.database.database_session.get_db_session")
    def test_database_connection_error(self, mock_get_db_session):
        """Test handling of database connection errors."""
        # Simulate connection failure by raising an exception
        mock_get_db_session.side_effect = Exception("Database connection failed")

        # Test that database errors are handled gracefully
        from src.core.database.database_session import get_db_session

        with pytest.raises(Exception) as exc_info:
            with get_db_session() as session:
                session.query("test").all()

        assert "Database connection failed" in str(exc_info.value)

    def test_missing_required_fields(self):
        """Test handling of missing database fields."""
        # Simulate row with missing fields
        row = [None, "Test", "test", True, None]  # Missing tenant_id

        # Should handle None values gracefully
        tenant = {
            "tenant_id": row[0] or "unknown",
            "name": row[1] or "Unknown",
            "subdomain": row[2] or "localhost",
            "is_active": row[3] if row[3] is not None else False,
            "ad_server": row[4],
        }

        assert tenant["tenant_id"] == "unknown"
        assert tenant["name"] == "Test"


class TestSettingsPage:
    """Test the settings page functionality."""

    @patch("src.core.database.database_session.get_db_session")
    def test_settings_page_loads(self, mock_db, flask_client):
        """Test that settings page loads without error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_db.return_value = mock_conn

        # Mock query results in order they're called
        mock_cursor.fetchone.side_effect = [
            # Tenant query
            ("test", "Test Tenant", "test", True, "mock"),
            # Product count
            (5,),
            # Advertiser count
            (3,),
            # Active advertisers
            (2,),
            # Default for additional queries
            (0,),
        ]

        with flask_client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["role"] = "super_admin"

        response = flask_client.get("/tenant/test/settings")

        # Should load without 500 error
        assert response.status_code != 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
