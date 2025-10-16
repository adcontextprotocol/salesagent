"""Integration tests for creative validation failure handling.

Tests that creatives are properly rejected when:
1. preview_creative returns empty/None (invalid creative)
2. preview_creative raises exception (network error, agent down)

These tests verify the fixes for creative validation that ensure no invalid
creatives are stored in the database.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import Creative as DBCreative
from src.core.database.models import Principal
from src.core.main import _sync_creatives_impl
from src.core.schemas import Creative as SchemaCreative
from src.core.schemas import SyncCreativesRequest
from tests.utils.database_helpers import create_tenant_with_timestamps


@pytest.mark.integration
@pytest.mark.requires_db
class TestCreativeValidationFailures:
    """Test creative validation failure handling."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, integration_db):
        """Create test tenant and principal."""
        with get_db_session() as session:
            # Create test tenant
            tenant = create_tenant_with_timestamps(
                tenant_id="validation_test",
                name="Validation Test Tenant",
                subdomain="validation-test",
                is_active=True,
                ad_server="mock",
                authorized_emails=[],
                authorized_domains=[],
            )
            session.add(tenant)

            # Create test principal
            principal = Principal(
                tenant_id="validation_test",
                principal_id="test_advertiser",
                name="Test Advertiser",
                access_token="test-token-123",
                platform_mappings={"mock": {"id": "test_advertiser"}},
            )
            session.add(principal)

            session.commit()

    @patch("src.core.main.CreativeAgentRegistry")
    def test_empty_preview_result_rejects_creative(self, mock_registry_class, integration_db):
        """Test that creatives are rejected when preview_creative returns empty result."""
        # Setup: Mock registry to return empty preview
        mock_registry = mock_registry_class.return_value
        mock_registry.get_format = AsyncMock(
            return_value=type("Format", (), {"agent_url": "https://test.agent", "format_id": "test_format"})()
        )
        mock_registry.preview_creative = AsyncMock(return_value={})  # Empty result

        # Create sync request
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_creative_1",
                    agent_url="https://test.agent",
                    format_id="test_format",
                    assets={"image_url": "https://example.com/image.jpg"},
                )
            ]
        )

        # Execute
        response = _sync_creatives_impl(
            tenant_id="validation_test",
            principal_id="test_advertiser",
            creatives=request.creatives,
            operation="create",
        )

        # Verify: Creative rejected
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.creative_id == "test_creative_1"
        assert result.action == "failed"
        assert len(result.errors) == 1
        assert "preview_creative returned no previews" in result.errors[0]

        # Verify: Creative NOT in database
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_creative_1").first()
            assert creative is None, "Creative should not be stored when preview fails"

    @patch("src.core.main.CreativeAgentRegistry")
    def test_preview_none_rejects_creative(self, mock_registry_class, integration_db):
        """Test that creatives are rejected when preview_creative returns None."""
        # Setup: Mock registry to return None
        mock_registry = mock_registry_class.return_value
        mock_registry.get_format = AsyncMock(
            return_value=type("Format", (), {"agent_url": "https://test.agent", "format_id": "test_format"})()
        )
        mock_registry.preview_creative = AsyncMock(return_value=None)

        # Create sync request
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_creative_2",
                    agent_url="https://test.agent",
                    format_id="test_format",
                    assets={"image_url": "https://example.com/image.jpg"},
                )
            ]
        )

        # Execute
        response = _sync_creatives_impl(
            tenant_id="validation_test",
            principal_id="test_advertiser",
            creatives=request.creatives,
            operation="create",
        )

        # Verify: Creative rejected
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action == "failed"
        assert "preview_creative returned no previews" in result.errors[0]

        # Verify: Creative NOT in database
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_creative_2").first()
            assert creative is None

    @patch("src.core.main.CreativeAgentRegistry")
    def test_network_error_rejects_creative_with_retry_message(self, mock_registry_class, integration_db):
        """Test that network errors reject creative with retry recommendation in error message."""
        # Setup: Mock registry to raise exception (simulating network error)
        mock_registry = mock_registry_class.return_value
        mock_registry.get_format = AsyncMock(
            return_value=type("Format", (), {"agent_url": "https://test.agent", "format_id": "test_format"})()
        )
        mock_registry.preview_creative = AsyncMock(side_effect=ConnectionError("Connection refused"))

        # Create sync request
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_creative_3",
                    agent_url="https://test.agent",
                    format_id="test_format",
                    assets={"image_url": "https://example.com/image.jpg"},
                )
            ]
        )

        # Execute
        response = _sync_creatives_impl(
            tenant_id="validation_test",
            principal_id="test_advertiser",
            creatives=request.creatives,
            operation="create",
        )

        # Verify: Creative rejected with retry message
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.creative_id == "test_creative_3"
        assert result.action == "failed"
        assert len(result.errors) == 1
        error_msg = result.errors[0]
        assert "Creative agent unreachable" in error_msg or "validation error" in error_msg
        assert "Retry recommended" in error_msg
        assert "temporarily unavailable" in error_msg

        # Verify: Creative NOT in database
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_creative_3").first()
            assert creative is None, "Creative should not be stored on network error"

    @patch("src.core.main.CreativeAgentRegistry")
    def test_update_with_empty_preview_rejects(self, mock_registry_class, integration_db):
        """Test that creative updates are also rejected when preview fails."""
        # Setup: Create existing creative in database
        with get_db_session() as session:
            creative = DBCreative(
                tenant_id="validation_test",
                creative_id="existing_creative",
                principal_id="test_advertiser",
                name="Existing Creative",
                agent_url="https://test.agent",
                format="test_format",
                status="approved",
                data={"url": "https://example.com/old.jpg"},
            )
            session.add(creative)
            session.commit()

        # Setup: Mock registry to return empty preview for update
        mock_registry = mock_registry_class.return_value
        mock_registry.get_format = AsyncMock(
            return_value=type("Format", (), {"agent_url": "https://test.agent", "format_id": "test_format"})()
        )
        mock_registry.preview_creative = AsyncMock(return_value={})

        # Create update request
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="existing_creative",
                    agent_url="https://test.agent",
                    format_id="test_format",
                    assets={"image_url": "https://example.com/new.jpg"},  # New asset
                )
            ]
        )

        # Execute update
        response = _sync_creatives_impl(
            tenant_id="validation_test",
            principal_id="test_advertiser",
            creatives=request.creatives,
            operation="update",
        )

        # Verify: Update rejected
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action == "failed"
        assert "preview_creative returned no previews" in result.errors[0]

        # Verify: Creative unchanged in database
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="existing_creative").first()
            assert creative is not None
            assert creative.data["url"] == "https://example.com/old.jpg", "Creative should not be updated"

    @patch("src.core.main.CreativeAgentRegistry")
    def test_valid_preview_accepts_creative(self, mock_registry_class, integration_db):
        """Test that creatives WITH valid previews are still accepted (sanity check)."""
        # Setup: Mock registry to return valid preview
        mock_registry = mock_registry_class.return_value
        mock_registry.get_format = AsyncMock(
            return_value=type("Format", (), {"agent_url": "https://test.agent", "format_id": "test_format"})()
        )
        mock_registry.preview_creative = AsyncMock(
            return_value={
                "previews": [
                    {
                        "renders": [
                            {
                                "preview_url": "https://preview.example.com/creative.jpg",
                                "dimensions": {"width": 300, "height": 250},
                            }
                        ]
                    }
                ]
            }
        )

        # Create sync request
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_creative_valid",
                    agent_url="https://test.agent",
                    format_id="test_format",
                    assets={"image_url": "https://example.com/image.jpg"},
                )
            ]
        )

        # Execute
        response = _sync_creatives_impl(
            tenant_id="validation_test",
            principal_id="test_advertiser",
            creatives=request.creatives,
            operation="create",
        )

        # Verify: Creative accepted
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action == "created"
        assert len(result.errors) == 0

        # Verify: Creative IS in database with preview URL
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_creative_valid").first()
            assert creative is not None
            assert creative.data.get("url") == "https://preview.example.com/creative.jpg"
