"""Tests for database health check functionality."""

from unittest.mock import Mock, patch

import pytest

from src.core.database.health_check import (
    check_database_health,
    check_table_exists,
    get_table_info,
    print_health_report,
)


class TestDatabaseHealthCheck:
    """Test database health check functionality."""

    @patch("src.core.database.health_check.get_db_session")
    def test_check_database_health_all_tables_exist(self, mock_get_db):
        """Test health check when all expected tables exist."""
        # Mock database session and inspector
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        # Mock all expected tables exist
        all_expected_tables = [
            "tenants",
            "creative_formats",
            "products",
            "principals",
            "users",
            "media_buys",
            "audit_logs",
            "superadmin_config",
            "adapter_config",
            "gam_inventory",
            "product_inventory_mappings",
            "gam_orders",
            "gam_line_items",
            "sync_jobs",
            "contexts",
            "workflow_steps",
            "object_workflow_mapping",
            "strategies",
            "strategy_states",
        ]

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = all_expected_tables + ["alembic_version"]

            # Mock alembic version check
            mock_session.execute.return_value.scalar.return_value = "020_fix_tasks_schema_properly"

            health = check_database_health()

            assert health["status"] == "healthy"
            assert health["missing_tables"] == []
            assert health["schema_issues"] == []
            assert health["migration_status"] == "020_fix_tasks_schema_properly"

    @patch("src.core.database.health_check.get_db_session")
    def test_check_database_health_missing_workflow_tables(self, mock_get_db):
        """Test health check when workflow tables are missing."""
        # Mock database session and inspector
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        # Mock missing workflow tables
        existing_tables = [
            "tenants",
            "products",
            "audit_logs",
            "alembic_version",
            # Missing: workflow_steps, object_workflow_mapping
        ]

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = existing_tables

            # Mock alembic version check
            mock_session.execute.return_value.scalar.return_value = "020_fix_tasks_schema_properly"

            health = check_database_health()

            assert health["status"] == "unhealthy"
            assert "workflow_steps" in health["missing_tables"]
            assert "object_workflow_mapping" in health["missing_tables"]

            # Should have specific issue messages for critical tables
            workflow_issues = [
                issue for issue in health["schema_issues"] if "workflow_steps" in issue and "dashboard crashes" in issue
            ]
            assert len(workflow_issues) > 0

    @patch("src.core.database.health_check.get_db_session")
    def test_check_database_health_deprecated_tables_exist(self, mock_get_db):
        """Test health check when deprecated tables still exist."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        # Include deprecated tables
        existing_tables = [
            "tenants",
            "audit_logs",
            "workflow_steps",
            "object_workflow_mapping",
            "tasks",
            "human_tasks",  # Deprecated but still present
            "alembic_version",
        ]

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = existing_tables

            # Mock alembic version check
            mock_session.execute.return_value.scalar.return_value = "020_fix_tasks_schema_properly"

            health = check_database_health()

            # Should detect deprecated tables
            deprecated_issues = [
                issue for issue in health["schema_issues"] if "Deprecated table" in issue and "safe to ignore" in issue
            ]
            assert len(deprecated_issues) == 2  # tasks and human_tasks

    @patch("src.core.database.health_check.get_db_session")
    def test_check_database_health_missing_migration_020_recommendations(self, mock_get_db):
        """Test that missing workflow tables trigger specific Migration 020 recommendation."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        # Missing workflow tables
        existing_tables = ["tenants", "audit_logs", "alembic_version"]

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = existing_tables

            mock_session.execute.return_value.scalar.return_value = "020_fix_tasks_schema_properly"

            health = check_database_health()

            # Should recommend checking Migration 020
            migration_020_recs = [
                rec for rec in health["recommendations"] if "Migration 020" in rec and "may have failed" in rec
            ]
            assert len(migration_020_recs) > 0

    @patch("src.core.database.health_check.get_db_session")
    def test_check_database_health_database_error(self, mock_get_db):
        """Test health check when database connection fails."""
        mock_get_db.side_effect = Exception("Database connection failed")

        health = check_database_health()

        assert health["status"] == "error"
        assert "Database connection failed" in health["schema_issues"][0]

    @patch("src.core.database.health_check.get_db_session")
    def test_check_table_exists_positive(self, mock_get_db):
        """Test check_table_exists returns True for existing table."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = ["audit_logs", "tenants"]

            result = check_table_exists("audit_logs")
            assert result is True

    @patch("src.core.database.health_check.get_db_session")
    def test_check_table_exists_negative(self, mock_get_db):
        """Test check_table_exists returns False for missing table."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = ["tenants"]

            result = check_table_exists("workflow_steps")
            assert result is False

    @patch("src.core.database.health_check.get_db_session")
    def test_get_table_info_existing_table(self, mock_get_db):
        """Test get_table_info for existing table."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = ["audit_logs"]
            mock_inspector.get_columns.return_value = [{"name": "log_id"}, {"name": "operation"}]
            mock_inspector.get_indexes.return_value = [{"name": "idx_audit_logs_tenant"}]
            mock_inspector.get_foreign_keys.return_value = [{"name": "fk_audit_tenant"}]

            info = get_table_info("audit_logs")

            assert info["exists"] is True
            assert "log_id" in info["columns"]
            assert "operation" in info["columns"]
            assert "idx_audit_logs_tenant" in info["indexes"]
            assert "fk_audit_tenant" in info["foreign_keys"]

    @patch("src.core.database.health_check.get_db_session")
    def test_get_table_info_missing_table(self, mock_get_db):
        """Test get_table_info for missing table."""
        mock_session = Mock()
        mock_engine = Mock()
        mock_inspector = Mock()

        mock_get_db.return_value.__enter__.return_value = mock_session
        mock_session.get_bind.return_value = mock_engine

        with patch("src.core.database.health_check.reflection.Inspector") as mock_inspector_class:
            mock_inspector_class.from_engine.return_value = mock_inspector
            mock_inspector.get_table_names.return_value = []

            info = get_table_info("nonexistent_table")

            assert info["exists"] is False

    def test_print_health_report_healthy(self, capsys):
        """Test print_health_report for healthy status."""
        report = {
            "status": "healthy",
            "missing_tables": [],
            "extra_tables": [],
            "schema_issues": [],
            "migration_status": "020_fix_tasks_schema_properly",
            "recommendations": [],
        }

        print_health_report(report)

        captured = capsys.readouterr()
        assert "✅ Database Health Status: HEALTHY" in captured.out
        assert "020_fix_tasks_schema_properly" in captured.out

    def test_print_health_report_unhealthy(self, capsys):
        """Test print_health_report for unhealthy status."""
        report = {
            "status": "unhealthy",
            "missing_tables": ["workflow_steps"],
            "extra_tables": ["old_table"],
            "schema_issues": ["Critical table 'workflow_steps' is missing"],
            "migration_status": "020_fix_tasks_schema_properly",
            "recommendations": ["Run migrations to create missing tables"],
        }

        print_health_report(report)

        captured = capsys.readouterr()
        assert "❌ Database Health Status: UNHEALTHY" in captured.out
        assert "Missing Tables" in captured.out
        assert "workflow_steps" in captured.out
        assert "Unexpected Tables" in captured.out
        assert "old_table" in captured.out
        assert "Schema Issues" in captured.out
        assert "Critical table" in captured.out
        assert "Recommendations" in captured.out
        assert "Run migrations" in captured.out


class TestDatabaseHealthIntegration:
    """Integration tests for database health check with real database."""

    @pytest.mark.requires_db
    def test_real_database_health_check(self):
        """Test health check against real test database."""
        health = check_database_health()

        # Should return valid health report structure
        assert isinstance(health, dict)
        assert "status" in health
        assert "missing_tables" in health
        assert "schema_issues" in health
        assert health["status"] in ["healthy", "unhealthy", "error"]

    @pytest.mark.requires_db
    def test_real_table_existence_checks(self):
        """Test table existence checks against real database."""
        # These tables should always exist in test database
        assert check_table_exists("tenants") is True
        assert check_table_exists("audit_logs") is True

        # This table definitely should not exist
        assert check_table_exists("definitely_nonexistent_table_12345") is False

    @pytest.mark.requires_db
    def test_real_table_info_audit_logs(self):
        """Test getting real table info for audit_logs."""
        info = get_table_info("audit_logs")

        assert info["exists"] is True
        assert "log_id" in info["columns"]
        assert "tenant_id" in info["columns"]
        assert "operation" in info["columns"]
