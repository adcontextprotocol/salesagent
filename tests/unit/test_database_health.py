"""Unit tests for database health check core logic."""

from unittest.mock import Mock, patch

from src.core.database.health_check import (
    check_database_health,
    print_health_report,
)


class TestDatabaseHealthLogic:
    """Test core database health check logic with minimal mocking."""

    @patch("src.core.database.health_check.get_db_session")
    def test_database_connection_failure_handling(self, mock_get_db):
        """Test health check handles database connection failures gracefully."""
        mock_get_db.side_effect = Exception("Database connection failed")

        health = check_database_health()

        assert health["status"] == "error"
        assert "Database connection failed" in health["schema_issues"][0]

    def test_print_health_report_formats_correctly(self, capsys):
        """Test that health report prints correctly formatted output."""
        healthy_report = {
            "status": "healthy",
            "missing_tables": [],
            "extra_tables": [],
            "schema_issues": [],
            "migration_status": "020_fix_tasks_schema_properly",
            "recommendations": [],
        }

        print_health_report(healthy_report)
        captured = capsys.readouterr()

        assert "✅ Database Health Status: HEALTHY" in captured.out
        assert "020_fix_tasks_schema_properly" in captured.out

        # Test unhealthy report formatting
        unhealthy_report = {
            "status": "unhealthy",
            "missing_tables": ["workflow_steps"],
            "extra_tables": ["deprecated_table"],
            "schema_issues": ["Critical table missing"],
            "migration_status": "020_fix_tasks_schema_properly",
            "recommendations": ["Run database migrations"],
        }

        print_health_report(unhealthy_report)
        captured = capsys.readouterr()

        assert "❌ Database Health Status: UNHEALTHY" in captured.out
        assert "workflow_steps" in captured.out
        assert "deprecated_table" in captured.out
        assert "Critical table missing" in captured.out
        assert "Run database migrations" in captured.out

    @patch("src.core.database.health_check.get_db_session")
    def test_health_check_basic_structure(self, mock_get_db):
        """Test that health check returns proper structure even with minimal database."""
        # Setup minimal mock that doesn't crash
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = ["tenants", "alembic_version"]
            mock_session.execute.return_value.scalar.return_value = "some_version"

            health = check_database_health()

            # Verify return structure
            expected_keys = [
                "status",
                "missing_tables",
                "extra_tables",
                "schema_issues",
                "migration_status",
                "recommendations",
            ]
            for key in expected_keys:
                assert key in health

            assert isinstance(health["missing_tables"], list)
            assert isinstance(health["schema_issues"], list)
            assert isinstance(health["recommendations"], list)
