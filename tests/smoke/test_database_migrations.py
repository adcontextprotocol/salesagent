"""Tests for database migrations - ensure migrations work correctly."""

from pathlib import Path

import pytest


class TestMigrationVersioning:
    """Test migration version tracking."""

    @pytest.mark.smoke
    def test_migrations_directory_exists(self):
        """Test that migrations directory and files exist."""
        migrations_dir = Path("alembic")
        assert migrations_dir.exists(), "Migrations directory does not exist"

        # Check for alembic.ini
        alembic_ini = Path("alembic.ini")
        assert alembic_ini.exists(), "alembic.ini not found"

        # Check for versions directory
        versions_dir = migrations_dir / "versions"
        assert versions_dir.exists(), "Migrations versions directory does not exist"

        # Check that at least one migration exists
        migration_files = list(versions_dir.glob("*.py"))
        assert len(migration_files) > 0, "No migration files found"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "smoke"])
