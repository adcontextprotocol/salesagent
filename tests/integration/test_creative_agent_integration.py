"""Integration tests using real creative agent.

These tests require the creative agent service to be running:
  docker-compose up creative-agent

The creative agent is available at http://localhost:8095 (or CREATIVE_AGENT_PORT).

These tests verify the FULL integration path:
  sync_creatives → CreativeAgentRegistry → MCP → Creative Agent → preview_creative

Unlike test_creative_validation_failures.py which mocks the creative agent,
these tests use the actual creative agent implementation.
"""

import os
from datetime import UTC, datetime

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import Creative as DBCreative
from src.core.database.models import Principal
from src.core.main import _sync_creatives_impl
from src.core.schemas import Creative as SchemaCreative
from src.core.schemas import SyncCreativesRequest
from tests.utils.database_helpers import create_tenant_with_timestamps

# Get creative agent URL from environment (docker-compose sets this)
CREATIVE_AGENT_URL = os.getenv("CREATIVE_AGENT_URL", "http://localhost:8095")


@pytest.mark.integration
@pytest.mark.requires_db
@pytest.mark.requires_creative_agent
class TestCreativeAgentIntegration:
    """Integration tests with real creative agent.

    NOTE: These tests require creative agent to be running.
    Start with: docker-compose up creative-agent
    """

    @pytest.fixture(autouse=True)
    def setup_test_data(self, integration_db):
        """Create test tenant and principal."""
        with get_db_session() as session:
            # Create test tenant
            tenant = create_tenant_with_timestamps(
                tenant_id="creative_agent_test",
                name="Creative Agent Test Tenant",
                subdomain="creative-agent-test",
                is_active=True,
                ad_server="mock",
                authorized_emails=[],
                authorized_domains=[],
            )
            session.add(tenant)

            # Create test principal
            principal = Principal(
                tenant_id="creative_agent_test",
                principal_id="test_advertiser",
                name="Test Advertiser",
                access_token="test-token-456",
                platform_mappings={"mock": {"id": "test_advertiser"}},
            )
            session.add(principal)

            session.commit()

    @pytest.mark.skip_ci  # TODO: Needs MCP/A2A client setup for proper auth context
    def test_valid_creative_with_real_agent(self, integration_db):
        """Test that valid creatives work with real creative agent.

        This tests the FULL path: sync_creatives → MCP → creative agent → preview

        NOTE: This test needs to be called through MCP/A2A client (not _impl directly)
        to have proper auth context. The mocked tests in test_creative_validation_failures.py
        verify the core rejection logic works correctly.
        """
        # Create sync request with valid creative data
        # NOTE: These values depend on what formats the creative agent supports
        now = datetime.now(UTC)
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_valid_creative",
                    name="Test Display Creative",
                    content_uri="https://example.com/ad-300x250.jpg",
                    principal_id="test_advertiser",
                    created_at=now,
                    updated_at=now,
                    agent_url=CREATIVE_AGENT_URL,
                    format_id="display_300x250",  # Standard IAB format
                    assets=[
                        {
                            "type": "image",
                            "url": "https://example.com/ad-300x250.jpg",
                        }
                    ],
                    click_url="https://example.com/click",
                )
            ]
        )

        # Execute - this will call the REAL creative agent
        response = _sync_creatives_impl(
            creatives=[c.model_dump() for c in request.creatives],
            patch=request.patch,
            assignments=request.assignments,
            delete_missing=request.delete_missing,
            dry_run=request.dry_run,
            validation_mode=request.validation_mode,
        )

        # Verify: Creative accepted and preview URL populated
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.creative_id == "test_valid_creative"
        assert result.action == "created", f"Expected created, got {result.action}. Errors: {result.errors}"
        assert len(result.errors) == 0

        # Verify: Creative stored in database with preview URL
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_valid_creative").first()
            assert creative is not None
            assert "url" in creative.data, "Preview URL should be populated from creative agent"

    @pytest.mark.skip_ci  # TODO: Needs MCP/A2A client setup for proper auth context
    def test_invalid_creative_rejected_by_agent(self, integration_db):
        """Test that invalid creatives are rejected by real creative agent.

        This tests validation failures that come FROM the creative agent.
        """
        # Create sync request with INVALID creative data (missing required assets)
        now = datetime.now(UTC)
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_invalid_creative",
                    name="Test Invalid Creative",
                    content_uri="https://example.com/placeholder.jpg",
                    principal_id="test_advertiser",
                    created_at=now,
                    updated_at=now,
                    agent_url=CREATIVE_AGENT_URL,
                    format_id="display_300x250",
                    assets=[],  # Empty assets - should fail validation
                )
            ]
        )

        # Execute - creative agent should reject this
        response = _sync_creatives_impl(
            creatives=[c.model_dump() for c in request.creatives],
            patch=request.patch,
            assignments=request.assignments,
            delete_missing=request.delete_missing,
            dry_run=request.dry_run,
            validation_mode=request.validation_mode,
        )

        # Verify: Creative rejected
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.creative_id == "test_invalid_creative"
        assert result.action == "failed"
        assert len(result.errors) > 0

        # Verify: Creative NOT stored in database
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_invalid_creative").first()
            assert creative is None

    @pytest.mark.skip_ci  # Manual test: stop creative agent before running
    def test_creative_agent_unavailable(self, integration_db):
        """Test behavior when creative agent is unavailable.

        This is a MANUAL test - stop the creative agent before running:
          docker-compose stop creative-agent

        Then run this test to verify network error handling.
        """
        now = datetime.now(UTC)
        request = SyncCreativesRequest(
            creatives=[
                SchemaCreative(
                    creative_id="test_agent_down",
                    name="Test Agent Down Creative",
                    content_uri="https://example.com/ad.jpg",
                    principal_id="test_advertiser",
                    created_at=now,
                    updated_at=now,
                    agent_url=CREATIVE_AGENT_URL,
                    format_id="display_300x250",
                    assets=[{"type": "image", "url": "https://example.com/ad.jpg"}],
                )
            ]
        )

        # Execute - should fail with network error
        response = _sync_creatives_impl(
            creatives=[c.model_dump() for c in request.creatives],
            patch=request.patch,
            assignments=request.assignments,
            delete_missing=request.delete_missing,
            dry_run=request.dry_run,
            validation_mode=request.validation_mode,
        )

        # Verify: Creative rejected with retry recommendation
        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action == "failed"
        assert any("Retry recommended" in err for err in result.errors)

        # Verify: Creative NOT stored
        with get_db_session() as session:
            creative = session.query(DBCreative).filter_by(creative_id="test_agent_down").first()
            assert creative is None


@pytest.mark.skip_ci  # Manual test: requires creative agent running
class TestCreativeAgentFormats:
    """Tests for creative agent format discovery.

    These verify that we can list and use formats from the real creative agent.
    """

    def test_list_formats_from_agent(self):
        """Test that we can fetch formats from creative agent via MCP."""
        from src.core.creative_agent_registry import CreativeAgentRegistry

        registry = CreativeAgentRegistry()

        # This should call the creative agent's list_formats MCP tool
        import asyncio

        formats = asyncio.run(registry.list_formats_from_agent(CREATIVE_AGENT_URL))

        assert len(formats) > 0, "Creative agent should return at least one format"
        assert all(hasattr(f, "format_id") for f in formats), "All formats should have format_id"

    def test_preview_creative_with_valid_format(self):
        """Test preview_creative MCP call with valid format."""
        from src.core.creative_agent_registry import CreativeAgentRegistry

        registry = CreativeAgentRegistry()

        # Create valid creative manifest
        manifest = {
            "creative_id": "test_preview",
            "assets": {
                "image_url": "https://example.com/ad-300x250.jpg",
                "click_url": "https://example.com/click",
            },
        }

        # Call preview_creative via MCP
        import asyncio

        result = asyncio.run(
            registry.preview_creative(
                agent_url=CREATIVE_AGENT_URL, format_id="display_300x250", creative_manifest=manifest
            )
        )

        assert result is not None
        assert "previews" in result, "preview_creative should return previews array"
        assert len(result["previews"]) > 0
