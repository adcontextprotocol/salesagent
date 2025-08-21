"""Basic smoke tests that don't require running servers."""

from pathlib import Path

import pytest


class TestCriticalImports:
    """Test that critical modules can be imported."""

    @pytest.mark.smoke
    def test_main_module_imports(self):
        """Test that main.py can be imported."""
        import main

        assert hasattr(main, "mcp")

    @pytest.mark.smoke
    def test_schemas_import(self):
        """Test that schemas module imports correctly."""
        import schemas

        assert hasattr(schemas, "MediaBuyRequest")
        assert hasattr(schemas, "Product")

    @pytest.mark.smoke
    def test_database_module_imports(self):
        """Test that database modules import."""
        import database_session
        import models

        assert hasattr(database_session, "get_db_session")
        assert hasattr(models, "MediaBuy")

    @pytest.mark.smoke
    def test_adapter_imports(self):
        """Test that adapters can be imported."""
        from adapters.base import AdServerAdapter
        from adapters.mock_ad_server import MockAdServer

        assert issubclass(MockAdServer, AdServerAdapter)


class TestDatabaseSchema:
    """Test database schema is correct."""

    @pytest.mark.smoke
    def test_models_have_required_fields(self):
        """Test that models have required fields."""
        from models import MediaBuy, Principal, Product, Tenant

        # Test MediaBuy has critical fields
        assert hasattr(MediaBuy, "media_buy_id")
        assert hasattr(MediaBuy, "tenant_id")
        assert hasattr(MediaBuy, "status")
        assert hasattr(MediaBuy, "budget")

        # Test Tenant has critical fields
        assert hasattr(Tenant, "tenant_id")
        assert hasattr(Tenant, "name")

        # Test Principal has auth fields
        assert hasattr(Principal, "principal_id")
        assert hasattr(Principal, "access_token")

        # Test Product has required fields
        assert hasattr(Product, "product_id")
        assert hasattr(Product, "name")


class TestConfiguration:
    """Test configuration can be loaded."""

    @pytest.mark.smoke
    def test_config_loader_works(self):
        """Test that config loader can be imported and used."""
        from config_loader import load_config

        # Should not raise an error
        config = load_config()
        assert config is not None


class TestCriticalPaths:
    """Test critical code paths work."""

    @pytest.mark.smoke
    def test_principal_auth_logic(self):
        """Test principal authentication logic exists."""
        from main import get_principal_from_token

        # Function should exist and be callable
        assert callable(get_principal_from_token)

    @pytest.mark.smoke
    def test_adapter_factory_pattern(self):
        """Test adapter factory pattern works."""
        from adapters.mock_ad_server import MockAdServer
        from schemas import Principal

        # Create a test principal
        principal = Principal(principal_id="test", name="Test", adapter_mappings={})

        # Should be able to create adapter
        adapter = MockAdServer(principal=principal, dry_run=False)
        assert adapter is not None

    @pytest.mark.smoke
    def test_audit_logger_exists(self):
        """Test audit logger can be imported."""
        from audit_logger import get_audit_logger

        logger = get_audit_logger()
        assert logger is not None
        assert hasattr(logger, "log_operation")


class TestProjectStructure:
    """Test project structure is correct."""

    @pytest.mark.smoke
    def test_critical_files_exist(self):
        """Test that critical files exist."""
        base_dir = Path("/Users/brianokelley/Developer/salesagent/.conductor/kigali")

        critical_files = [
            "main.py",
            "schemas.py",
            "models.py",
            "database_session.py",
            "config_loader.py",
            "audit_logger.py",
            "adapters/base.py",
            "adapters/mock_ad_server.py",
            "pytest.ini",
            ".pre-commit-config.yaml",
        ]

        for file_path in critical_files:
            full_path = base_dir / file_path
            assert full_path.exists(), f"Critical file missing: {file_path}"

    @pytest.mark.smoke
    def test_migrations_directory_exists(self):
        """Test that migrations directory exists."""
        migrations_dir = Path("/Users/brianokelley/Developer/salesagent/.conductor/kigali/migrations")
        assert migrations_dir.exists(), "Migrations directory missing"

        versions_dir = migrations_dir / "versions"
        assert versions_dir.exists(), "Migration versions directory missing"


class TestNoSkippedTests:
    """Ensure no tests are being skipped."""

    @pytest.mark.smoke
    def test_no_skip_decorators(self):
        """Test that no test files contain skip decorators."""
        import subprocess

        # Build the pattern in parts to avoid matching ourselves
        skip_pattern = "@pytest" + ".mark" + ".skip"
        result = subprocess.run(
            ["grep", "-r", skip_pattern, "tests/"],
            cwd="/Users/brianokelley/Developer/salesagent/.conductor/kigali",
            capture_output=True,
            text=True,
        )

        # Filter out legitimate uses
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            bad_lines = [
                line
                for line in lines
                if line
                and "pytest.skip(" not in line  # Allow runtime skips
                and "skip_pattern" not in line  # Exclude this test file
                and "test_no_skip" not in line  # Exclude this test
            ]
            assert len(bad_lines) == 0, f"Found skip decorators:\n{chr(10).join(bad_lines[:5])}"


class TestCodeQuality:
    """Test code quality standards."""

    @pytest.mark.smoke
    def test_no_hardcoded_credentials(self):
        """Test that no hardcoded credentials exist in code."""
        import subprocess

        # Check for common credential patterns
        patterns = [
            "password.*=.*[\"'][^\"']*[\"']",
            "secret.*=.*[\"'][^\"']*[\"']",
            "api_key.*=.*[\"'][^\"']*[\"']",
            "token.*=.*[\"']test_token",  # Exclude test tokens
        ]

        for pattern in patterns[:3]:  # Skip test token check
            result = subprocess.run(
                ["grep", "-r", "-E", pattern, "--include=*.py", "."],
                cwd="/Users/brianokelley/Developer/salesagent/.conductor/kigali",
                capture_output=True,
                text=True,
            )

            # Filter out test files and comments
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                non_test_lines = [line for line in lines if line and "test" not in line.lower() and "#" not in line]
                assert len(non_test_lines) == 0, f"Found hardcoded credentials:\n{chr(10).join(non_test_lines[:5])}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "smoke"])
