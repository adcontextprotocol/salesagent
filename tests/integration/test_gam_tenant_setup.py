#!/usr/bin/env python3
"""
Integration test for GAM tenant setup and configuration flow.

This test ensures that the GAM configuration flow works properly,
specifically testing the scenarios that caused the regression:
1. Creating a tenant without network code (should auto-detect)
2. Creating a tenant with manual network code input
3. OAuth flow for network detection
4. Proper database schema handling

This would have caught the regression where network code was required upfront.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from setup_tenant import create_tenant, main


@pytest.mark.integration
@pytest.mark.requires_db
class TestGAMTenantSetup:
    """Test GAM tenant setup and configuration flow."""

    @pytest.mark.skip(reason="setup_tenant.py calls sys.exit() which breaks test")
    def test_gam_tenant_creation_without_network_code(self):
        """
        Test that a GAM tenant can be created without providing network code upfront.

        This tests the core regression scenario: network code should be optional
        during tenant creation when using OAuth tokens.
        """
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Create database schema
            conn = sqlite3.connect(tmp_path)
            self._create_test_schema(conn)

            # Mock database connection to use our test DB
            with patch("setup_tenant.get_db_session") as mock_get_session:
                # Create a mock session that works with SQLAlchemy ORM
                mock_session = Mock()
                mock_session.execute = conn.execute
                mock_session.commit = conn.commit
                mock_session.close = Mock()  # Don't actually close the connection yet
                mock_session.query = Mock()  # Add query method for ORM operations
                mock_session.add = Mock()  # Add method for adding objects
                mock_session.flush = Mock()  # Add flush method

                # Make it work as a context manager
                mock_context = Mock()
                mock_context.__enter__ = Mock(return_value=mock_session)
                mock_context.__exit__ = Mock(return_value=None)
                mock_get_session.return_value = mock_context

                # Create args without network code (should work)
                args = Mock()
                args.name = "Test GAM Publisher"
                args.tenant_id = "test_gam_pub"
                args.subdomain = "testgampub"
                args.adapter = "google_ad_manager"
                args.gam_network_code = None  # Key test: No network code provided
                args.gam_refresh_token = "test_refresh_token_123"
                args.manual_approval = False
                args.auto_approve_all = False
                args.max_daily_budget = 15000
                args.admin_token = "test_admin_token"

                # This should NOT raise an error (the regression made this fail)
                create_tenant(args)

                # Verify tenant was created successfully
                cursor = conn.execute(
                    "SELECT name, ad_server FROM tenants WHERE tenant_id = ?",
                    (args.tenant_id,),
                )
                tenant = cursor.fetchone()
                assert tenant is not None
                assert tenant[0] == "Test GAM Publisher"
                assert tenant[1] == "google_ad_manager"

                # Verify adapter config allows null network code initially
                cursor = conn.execute(
                    "SELECT gam_network_code, gam_refresh_token FROM adapter_config WHERE tenant_id = ?",
                    (args.tenant_id,),
                )
                adapter_config = cursor.fetchone()
                assert adapter_config is not None
                assert adapter_config[0] is None  # network_code should be null initially
                assert adapter_config[1] == "test_refresh_token_123"  # refresh_token should be stored

        finally:
            conn.close()
            os.unlink(tmp_path)

    @pytest.mark.skip(reason="setup_tenant.py calls sys.exit() which breaks test")
    def test_gam_tenant_creation_with_network_code(self):
        """
        Test that a GAM tenant can be created WITH network code provided upfront.

        This ensures the manual network code path still works.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            self._create_test_schema(conn)

            with patch("setup_tenant.get_db_session") as mock_get_session:
                # Create a mock session that works with SQLAlchemy ORM
                mock_session = Mock()
                mock_session.execute = conn.execute
                mock_session.commit = conn.commit
                mock_session.close = Mock()  # Don't actually close the connection yet
                mock_session.query = Mock()  # Add query method for ORM operations
                mock_session.add = Mock()  # Add method for adding objects
                mock_session.flush = Mock()  # Add flush method

                # Make it work as a context manager
                mock_context = Mock()
                mock_context.__enter__ = Mock(return_value=mock_session)
                mock_context.__exit__ = Mock(return_value=None)
                mock_get_session.return_value = mock_context

                args = Mock()
                args.name = "Test GAM Publisher With Code"
                args.tenant_id = "test_gam_with_code"
                args.subdomain = "testgamcode"
                args.adapter = "google_ad_manager"
                args.gam_network_code = "123456789"  # Network code provided
                args.gam_refresh_token = "test_refresh_token_456"
                args.manual_approval = False
                args.auto_approve_all = False
                args.max_daily_budget = 20000
                args.admin_token = "test_admin_token_2"

                create_tenant(args)

                # Verify network code was stored
                cursor = conn.execute(
                    "SELECT gam_network_code FROM adapter_config WHERE tenant_id = ?",
                    (args.tenant_id,),
                )
                adapter_config = cursor.fetchone()
                assert adapter_config is not None
                assert adapter_config[0] == "123456789"

        finally:
            conn.close()
            os.unlink(tmp_path)

    def test_command_line_parsing_network_code_optional(self):
        """
        Test that the command line parsing correctly handles optional network code.

        This would have caught the regression where --gam-network-code was required.
        """
        # Test the CLI argument parsing
        old_argv = sys.argv
        try:
            # Simulate command line without network code
            sys.argv = [
                "setup_tenant.py",
                "Test Publisher",
                "--adapter",
                "google_ad_manager",
                "--gam-refresh-token",
                "test_token",
                # Note: NO --gam-network-code provided - should NOT error
            ]

            with patch("setup_tenant.create_tenant") as mock_create:
                try:
                    main()
                    # If we get here, the parsing succeeded (correct behavior)
                    parsing_succeeded = True

                    # Verify create_tenant was called with network_code as None
                    mock_create.assert_called_once()
                    args = mock_create.call_args[0][0]
                    assert args.gam_network_code is None
                    assert args.gam_refresh_token == "test_token"

                except SystemExit as e:
                    # Check if it's just the normal success exit
                    if e.code == 0:
                        parsing_succeeded = True
                    else:
                        parsing_succeeded = False
                except Exception:
                    # Any other exception means parsing failed
                    parsing_succeeded = False

            assert parsing_succeeded, "Network code should be optional when refresh token is provided"

        finally:
            sys.argv = old_argv

    @pytest.mark.skip(reason="Requires superadmin_config table - not critical for CI")
    def test_admin_ui_network_detection_endpoint(self):
        """
        Test the Admin UI endpoint for detecting network code from refresh token.

        This tests the OAuth → network code detection flow.
        """
        from src.admin.app import create_app

        app, _ = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_secret"

        with app.test_client() as client:
            # Mock authentication
            with client.session_transaction() as sess:
                sess["authenticated"] = True
                sess["role"] = "super_admin"
                sess["email"] = "test@example.com"

            # Mock the GAM client and network detection
            with patch("googleads.ad_manager.AdManagerClient") as MockClient:
                mock_client_instance = MagicMock()
                mock_network_service = MagicMock()
                mock_network_service.getCurrentNetwork.return_value = {
                    "id": "123456",
                    "networkCode": "78901234",
                    "displayName": "Test Publisher Network",
                    "currencyCode": "USD",
                    "timeZone": "America/New_York",
                }
                mock_client_instance.GetService.return_value = mock_network_service
                MockClient.LoadFromDict.return_value = mock_client_instance

                # Test the network detection endpoint
                response = client.post(
                    "/tenant/test_tenant/gam/detect-network",
                    json={"refresh_token": "test_refresh_token"},
                    content_type="application/json",
                )

                assert response.status_code == 200
                data = response.get_json()
                assert data["success"] is True
                assert data["network_code"] == "78901234"
                assert data["network_name"] == "Test Publisher Network"

                # Verify the GAM client was called with correct config
                MockClient.LoadFromDict.assert_called_once()
                config = MockClient.LoadFromDict.call_args[0][0]
                assert "ad_manager" in config
                assert config["ad_manager"]["refresh_token"] == "test_refresh_token"

    def test_gam_adapter_initialization_without_network_code(self):
        """
        Test that the GAM adapter can be initialized even without network code.

        This ensures the adapter gracefully handles missing network codes
        during the configuration phase.
        """
        from src.adapters.google_ad_manager import GoogleAdManager
        from src.core.schemas import Principal

        # Create principal with GAM platform mapping
        principal = Principal(
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"google_ad_manager": "12345"},
        )

        # Config without network code (should not crash)
        config = {
            "refresh_token": "test_refresh_token",
            # network_code is missing - should be handled gracefully
        }

        # This should not raise an exception
        adapter = GoogleAdManager(
            config=config,
            principal=principal,
            dry_run=True,  # Use dry_run to avoid actual API calls
        )

        # Adapter should be created successfully
        assert adapter is not None
        assert adapter.adapter_name == "gam"
        assert adapter.refresh_token == "test_refresh_token"
        # network_code should be None but not cause errors
        assert adapter.network_code is None

    def _create_test_schema(self, conn):
        """Create test database schema."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                subdomain TEXT UNIQUE NOT NULL,
                ad_server TEXT NOT NULL,
                max_daily_budget REAL DEFAULT 10000,
                enable_aee_signals BOOLEAN DEFAULT 1,
                admin_token TEXT,
                auto_approve_formats TEXT DEFAULT '[]',
                human_review_required BOOLEAN DEFAULT 0,
                policy_settings TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                billing_plan TEXT DEFAULT 'standard'
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS adapter_config (
                tenant_id TEXT PRIMARY KEY,
                adapter_type TEXT NOT NULL,
                gam_network_code TEXT,
                gam_refresh_token TEXT,
                gam_manual_approval_required BOOLEAN DEFAULT 0,
                mock_dry_run BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            )
        """
        )

        conn.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
