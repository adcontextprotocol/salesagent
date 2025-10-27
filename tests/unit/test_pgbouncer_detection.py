"""Test PgBouncer detection and configuration."""

import os
from unittest.mock import MagicMock, patch


class TestPgBouncerDetection:
    """Test PgBouncer detection logic."""

    def test_pgbouncer_detected_by_port(self):
        """Test that PgBouncer is detected when port 6543 is in connection string."""
        from src.core.database.database_session import reset_engine

        # Reset engine to clear any existing connections
        reset_engine()

        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost:6543/test"}),
            patch("src.core.database.database_session.create_engine") as mock_create_engine,
        ):
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine

            from src.core.database.database_session import get_engine

            engine = get_engine()

            # Verify create_engine was called
            assert mock_create_engine.called
            call_kwargs = mock_create_engine.call_args[1]

            # Verify PgBouncer-optimized settings
            assert call_kwargs["pool_size"] == 2  # Small pool for PgBouncer
            assert call_kwargs["max_overflow"] == 5  # Limited overflow
            assert call_kwargs["pool_pre_ping"] is False  # Disabled for PgBouncer
            assert call_kwargs["pool_recycle"] == 300  # 5 minutes

    def test_pgbouncer_detected_by_env_var(self):
        """Test that PgBouncer is detected when USE_PGBOUNCER=true."""
        from src.core.database.database_session import reset_engine

        reset_engine()

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
                    "USE_PGBOUNCER": "true",
                },
            ),
            patch("src.core.database.database_session.create_engine") as mock_create_engine,
        ):
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine

            from src.core.database.database_session import get_engine

            engine = get_engine()

            # Verify PgBouncer-optimized settings
            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs["pool_size"] == 2
            assert call_kwargs["pool_pre_ping"] is False

    def test_direct_postgres_without_pgbouncer(self):
        """Test that direct PostgreSQL settings are used without PgBouncer."""
        from src.core.database.database_session import reset_engine

        reset_engine()

        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost:5432/test"}),
            patch("src.core.database.database_session.create_engine") as mock_create_engine,
        ):
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine

            from src.core.database.database_session import get_engine

            engine = get_engine()

            # Verify direct PostgreSQL settings
            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs["pool_size"] == 10  # Larger pool for direct connection
            assert call_kwargs["max_overflow"] == 20
            assert call_kwargs["pool_pre_ping"] is True  # Enabled for direct connection
            assert call_kwargs["pool_recycle"] == 3600  # 1 hour

    def test_connection_string_with_port_6543(self):
        """Test that port 6543 in connection string triggers PgBouncer mode."""
        from src.core.database.database_session import reset_engine

        reset_engine()

        # Test various connection string formats
        pgbouncer_urls = [
            "postgresql://user:pass@host.internal:6543/db",
            "postgres://user:pass@localhost:6543/testdb",
            "postgresql://user@host:6543/db?sslmode=require",
        ]

        for url in pgbouncer_urls:
            reset_engine()
            with (
                patch.dict(os.environ, {"DATABASE_URL": url}),
                patch("src.core.database.database_session.create_engine") as mock_create_engine,
            ):
                mock_engine = MagicMock()
                mock_create_engine.return_value = mock_engine

                from src.core.database.database_session import get_engine

                engine = get_engine()

                call_kwargs = mock_create_engine.call_args[1]
                assert call_kwargs["pool_size"] == 2, f"Failed for URL: {url}"
                assert call_kwargs["pool_pre_ping"] is False, f"Failed for URL: {url}"

    def test_use_pgbouncer_env_var_case_insensitive(self):
        """Test that USE_PGBOUNCER environment variable is case-insensitive."""
        from src.core.database.database_session import reset_engine

        for value in ["true", "True", "TRUE", "TrUe"]:
            reset_engine()
            with (
                patch.dict(
                    os.environ,
                    {
                        "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
                        "USE_PGBOUNCER": value,
                    },
                ),
                patch("src.core.database.database_session.create_engine") as mock_create_engine,
            ):
                mock_engine = MagicMock()
                mock_create_engine.return_value = mock_engine

                from src.core.database.database_session import get_engine

                engine = get_engine()

                call_kwargs = mock_create_engine.call_args[1]
                assert call_kwargs["pool_size"] == 2, f"Failed for USE_PGBOUNCER={value}"

    def test_pgbouncer_false_uses_direct_connection(self):
        """Test that USE_PGBOUNCER=false uses direct PostgreSQL settings."""
        from src.core.database.database_session import reset_engine

        reset_engine()

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
                    "USE_PGBOUNCER": "false",
                },
            ),
            patch("src.core.database.database_session.create_engine") as mock_create_engine,
        ):
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine

            from src.core.database.database_session import get_engine

            engine = get_engine()

            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs["pool_size"] == 10  # Direct PostgreSQL settings
            assert call_kwargs["pool_pre_ping"] is True
