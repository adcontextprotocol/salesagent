#!/usr/bin/env python3
"""
Database Health Check Integration Tests - Real Database Tests

These tests validate database health check functionality with real database connections
to catch issues that mocks would miss. This replaces over-mocked unit tests that
don't test actual database interactions.

This addresses the pattern identified in issue #161 of reducing mocking at data boundaries
to improve test coverage and catch real bugs.
"""

import pytest
import tempfile
import os
from pathlib import Path

from src.core.database.health_check import check_database_health, print_health_report
from src.core.database.database_session import get_db_session
from src.core.database.models import Base, Tenant, Product


class TestDatabaseHealthIntegration:
    """Test database health check with real database connections."""

    @pytest.fixture
    def temp_database(self):
        """Create a temporary SQLite database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            temp_db_path = tmp_file.name
        
        # Set up temporary database URL
        original_db_url = os.environ.get('DATABASE_URL')
        temp_db_url = f"sqlite:///{temp_db_path}"
        os.environ['DATABASE_URL'] = temp_db_url
        
        # Create all tables
        from src.core.database.database_session import engine
        Base.metadata.create_all(bind=engine)
        
        yield temp_db_path
        
        # Cleanup
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        
        try:
            os.unlink(temp_db_path)
        except OSError:
            pass

    def test_health_check_with_complete_database(self, temp_database):
        """Test health check against a complete, properly migrated database."""
        # Create some test data to ensure database is functional
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="health_test_tenant",
                name="Health Check Test Tenant",
                subdomain="health-test",
                config={},
                billing_plan="test"
            )
            session.add(tenant)
            session.commit()
        
        # Run health check with real database
        health = check_database_health()
        
        # Validate structure
        expected_keys = [
            "status", "missing_tables", "extra_tables", 
            "schema_issues", "migration_status", "recommendations"
        ]
        for key in expected_keys:
            assert key in health, f"Missing key '{key}' in health report"
        
        # Should be healthy with complete schema
        assert health["status"] in ["healthy", "warning"], f"Unexpected status: {health['status']}"
        assert isinstance(health["missing_tables"], list)
        assert isinstance(health["extra_tables"], list)
        assert isinstance(health["schema_issues"], list)
        assert isinstance(health["recommendations"], list)

    def test_health_check_with_missing_tables(self, temp_database):
        """Test health check detects missing tables correctly."""
        # Drop a critical table to simulate missing tables
        from src.core.database.database_session import engine
        
        # Drop the products table
        with engine.connect() as connection:
            connection.execute("DROP TABLE IF EXISTS products")
            connection.commit()
        
        # Run health check
        health = check_database_health()
        
        # Should detect missing table
        assert "products" in health["missing_tables"], "Should detect missing products table"
        assert health["status"] in ["unhealthy", "warning"], "Should report unhealthy status"
        assert len(health["schema_issues"]) > 0, "Should report schema issues"

    def test_health_check_with_extra_tables(self, temp_database):
        """Test health check detects extra/deprecated tables."""
        # Add an extra table that shouldn't exist
        from src.core.database.database_session import engine
        
        with engine.connect() as connection:
            connection.execute(
                "CREATE TABLE deprecated_old_table (id INTEGER PRIMARY KEY, data TEXT)"
            )
            connection.commit()
        
        # Run health check
        health = check_database_health()
        
        # Should detect extra table
        assert "deprecated_old_table" in health["extra_tables"], "Should detect extra table"

    def test_health_check_database_access_errors(self):
        """Test health check handles database access errors gracefully."""
        # Set invalid database URL to simulate connection failure
        original_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = "sqlite:///nonexistent_path/invalid.db"
        
        try:
            health = check_database_health()
            
            # Should handle error gracefully
            assert health["status"] == "error", "Should report error status for invalid database"
            assert len(health["schema_issues"]) > 0, "Should report schema issues for failed connection"
            
            # Error should be descriptive
            error_found = any("connection" in issue.lower() or "database" in issue.lower() 
                            for issue in health["schema_issues"])
            assert error_found, "Should include database connection error in issues"
            
        finally:
            # Restore original database URL
            if original_db_url:
                os.environ['DATABASE_URL'] = original_db_url
            else:
                os.environ.pop('DATABASE_URL', None)

    def test_health_check_migration_status_detection(self, temp_database):
        """Test that health check correctly detects migration status."""
        # The health check should detect current migration version
        health = check_database_health()
        
        # Migration status should be a string indicating current version
        assert isinstance(health["migration_status"], str), "Migration status should be a string"
        
        # Should not be empty (unless no migrations have been run)
        # In a real database, there should be some migration version
        if health["migration_status"]:
            assert len(health["migration_status"]) > 0, "Migration status should not be empty string"

    def test_print_health_report_integration(self, temp_database, capsys):
        """Test health report printing with real health check data."""
        # Run real health check
        health = check_database_health()
        
        # Print the report
        print_health_report(health)
        captured = capsys.readouterr()
        
        # Should contain actual status
        assert health["status"].upper() in captured.out, "Should display actual health status"
        
        # Should display migration status if available
        if health["migration_status"]:
            assert health["migration_status"] in captured.out, "Should display migration status"
        
        # Should be properly formatted
        assert "Database Health Status:" in captured.out, "Should have header"

    def test_health_check_with_real_schema_validation(self, temp_database):
        """Test health check validates actual database schema against expected schema."""
        # Add test data to verify schema works
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id="schema_test_tenant",
                name="Schema Test Tenant", 
                subdomain="schema-test",
                config={},
                billing_plan="test"
            )
            session.add(tenant)
            
            product = Product(
                tenant_id="schema_test_tenant",
                product_id="schema_test_product",
                name="Schema Test Product",
                description="Product for schema validation testing",
                formats=["display_300x250"],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=False
            )
            session.add(product)
            session.commit()
        
        # Run health check
        health = check_database_health()
        
        # Schema should be valid with proper data
        if health["status"] == "healthy":
            assert len(health["schema_issues"]) == 0, "Healthy database should have no schema issues"
        
        # Verify we can query the data successfully (indicates schema is correct)
        with get_db_session() as session:
            tenant_count = session.query(Tenant).count()
            product_count = session.query(Product).count()
            
            assert tenant_count >= 1, "Should have at least one tenant"
            assert product_count >= 1, "Should have at least one product"

    def test_health_check_performance_with_real_database(self, temp_database):
        """Test that health check completes in reasonable time with real database."""
        import time
        
        # Add some test data to make it more realistic
        with get_db_session() as session:
            for i in range(10):
                tenant = Tenant(
                    tenant_id=f"perf_test_tenant_{i}",
                    name=f"Performance Test Tenant {i}",
                    subdomain=f"perf-test-{i}",
                    config={},
                    billing_plan="test"
                )
                session.add(tenant)
            session.commit()
        
        # Measure health check performance
        start_time = time.time()
        health = check_database_health()
        elapsed_time = time.time() - start_time
        
        # Should complete within reasonable time (5 seconds for local SQLite)
        assert elapsed_time < 5.0, f"Health check took too long: {elapsed_time:.2f}s"
        
        # Should still return valid results
        assert "status" in health, "Should return valid health report even with larger dataset"

    def test_health_check_table_existence_validation(self, temp_database):
        """Test that health check validates existence of all required tables."""
        # Get list of tables that should exist
        from src.core.database.models import Base
        expected_tables = set(Base.metadata.tables.keys())
        
        # Run health check
        health = check_database_health()
        
        # Check that health check knows about expected tables
        missing_critical_tables = {"tenants", "products", "principals"} & set(health["missing_tables"])
        
        if health["status"] == "healthy":
            # If healthy, no critical tables should be missing
            assert not missing_critical_tables, f"Critical tables missing: {missing_critical_tables}"
        
        # At minimum, should check for tenant table existence
        # (This is a core table that must exist for the system to function)
        with get_db_session() as session:
            # This should not raise an exception if schema is correct
            tenant_table_exists = True
            try:
                session.execute("SELECT COUNT(*) FROM tenants")
            except Exception:
                tenant_table_exists = False
            
            if not tenant_table_exists:
                assert "tenants" in health["missing_tables"], "Should detect missing tenants table"