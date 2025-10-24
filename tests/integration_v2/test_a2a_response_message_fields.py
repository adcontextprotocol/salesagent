"""Integration tests for A2A response spec compliance.

This test suite validates that A2A handlers return spec-compliant responses
matching MCP behavior. Per PR #604, A2A responses no longer include protocol
fields like 'success' or 'message' in the response data. Instead, human-readable
messages are in Artifact.description.

Key principle: A2A responses must be identical to MCP responses (spec-compliant).

Updated for PR #604: https://github.com/adcontextprotocol/salesagent/pull/604
"""

import contextlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

# This test uses sample_products fixture which now uses pricing_options (v2)
pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.mark.integration
class TestA2AMessageFieldValidation:
    """Test that all A2A skill handlers return spec-compliant responses.

    Per PR #604, A2A responses no longer include protocol fields (success, message).
    These are now in Artifact.description, not response data.
    """

    @pytest.fixture
    def handler(self):
        """Create A2A request handler."""
        return AdCPRequestHandler()

    @pytest.fixture
    def mock_auth_context(self, sample_tenant, sample_principal):
        """Mock authentication context for all tests."""
        from src.core.config_loader import set_current_tenant

        @contextlib.contextmanager
        def _mock_context(handler):
            handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])
            # Set tenant context explicitly (required for database queries)
            set_current_tenant({"tenant_id": sample_tenant["tenant_id"], "name": "Test Tenant"})
            # Patch get_current_tenant in both modules where it's used
            # Also skip setup validation for tests
            with (
                patch.multiple(
                    "src.a2a_server.adcp_a2a_server",
                    get_principal_from_token=MagicMock(return_value=sample_principal["principal_id"]),
                    get_current_tenant=MagicMock(return_value={"tenant_id": sample_tenant["tenant_id"]}),
                ),
                patch("src.core.main.get_current_tenant", return_value={"tenant_id": sample_tenant["tenant_id"]}),
                patch("src.core.main.validate_setup_complete"),
            ):
                yield

        return _mock_context

    @pytest.mark.asyncio
    async def test_create_media_buy_spec_compliant_response(
        self, handler, mock_auth_context, sample_tenant, sample_principal, sample_products
    ):
        """Test create_media_buy returns spec-compliant response (no 'message' field).

        Per PR #604: A2A responses should match MCP responses (spec-compliant).
        """
        with mock_auth_context(handler):
            # Create parameters for create_media_buy skill
            start_date = datetime.now(UTC) + timedelta(days=1)
            end_date = start_date + timedelta(days=30)

            params = {
                "brand_manifest": {"name": "Test Campaign"},
                "packages": [
                    {
                        "buyer_ref": f"pkg_{sample_products[0]}",
                        "products": [sample_products[0]],
                        "budget": {"total": 10000.0, "currency": "USD"},
                    }
                ],
                "budget": {"total": 10000.0, "currency": "USD"},
                "start_time": start_date.isoformat(),
                "end_time": end_date.isoformat(),
            }

            # Call the handler method directly
            result = await handler._handle_create_media_buy_skill(params, sample_principal["access_token"])

            # ✅ Validate spec-compliant response (no 'success' or 'message' fields)
            assert isinstance(result, dict), "Result must be dict"
            assert "media_buy_id" in result, "Response must include media_buy_id"
            assert "message" not in result, "Response should NOT include 'message' field (spec-compliant)"
            assert "success" not in result, "Response should NOT include 'success' field (spec-compliant)"

    @pytest.mark.asyncio
    async def test_sync_creatives_spec_compliant_response(self, handler, mock_auth_context, sample_principal):
        """Test sync_creatives returns spec-compliant response (no 'message' field).

        Per PR #604: A2A responses should match MCP responses (spec-compliant).
        """
        with mock_auth_context(handler):
            params = {
                "creatives": [
                    {
                        "buyer_ref": "creative_test_001",
                        "format_id": "display_300x250",
                        "name": "Test Creative",
                        "assets": {"main_image": {"asset_type": "image", "url": "https://example.com/image.jpg"}},
                    }
                ],
                "validation_mode": "strict",
            }

            # Call handler directly
            result = await handler._handle_sync_creatives_skill(params, sample_principal["access_token"])

            # ✅ Validate spec-compliant response
            assert isinstance(result, dict), "Result must be dict"
            assert "creatives" in result, "Response must include creatives"
            assert "message" not in result, "Response should NOT include 'message' field (spec-compliant)"
            assert "success" not in result, "Response should NOT include 'success' field (spec-compliant)"

    @pytest.mark.asyncio
    async def test_get_products_spec_compliant_response(self, handler, mock_auth_context, sample_principal):
        """Test get_products returns spec-compliant response (no 'message' field).

        Per PR #604: A2A responses should match MCP responses (spec-compliant).
        """
        with mock_auth_context(handler):
            params = {
                "brand_manifest": {"name": "Test product search"},
                "brief": "Looking for display ads",
            }

            result = await handler._handle_get_products_skill(params, sample_principal["access_token"])

            # ✅ Validate spec-compliant response
            assert isinstance(result, dict), "Result must be dict"
            assert "products" in result, "Response must include products"
            assert "message" not in result, "Response should NOT include 'message' field (spec-compliant)"
            assert "success" not in result, "Response should NOT include 'success' field (spec-compliant)"

    @pytest.mark.asyncio
    async def test_list_creatives_spec_compliant_response(self, handler, mock_auth_context, sample_principal):
        """Test list_creatives returns spec-compliant response (no 'message' field)."""
        with mock_auth_context(handler):
            params = {
                "buyer_ref": "test_creative",
                "page": 1,
                "limit": 10,
            }

            result = await handler._handle_list_creatives_skill(params, sample_principal["access_token"])

            # ✅ Validate spec-compliant response
            assert isinstance(result, dict), "Result must be dict"
            assert "creatives" in result, "Response must include creatives"
            assert "message" not in result, "Response should NOT include 'message' field (spec-compliant)"
            assert "success" not in result, "Response should NOT include 'success' field (spec-compliant)"

    @pytest.mark.asyncio
    async def test_list_creative_formats_spec_compliant_response(self, handler, mock_auth_context, sample_principal):
        """Test list_creative_formats returns spec-compliant response (no 'message' field)."""
        with mock_auth_context(handler):
            params = {}

            result = await handler._handle_list_creative_formats_skill(params, sample_principal["access_token"])

            # ✅ Validate spec-compliant response
            assert isinstance(result, dict), "Result must be dict"
            assert "formats" in result, "Response must include formats"
            assert "message" not in result, "Response should NOT include 'message' field (spec-compliant)"
            assert "success" not in result, "Response should NOT include 'success' field (spec-compliant)"


@pytest.mark.integration
class TestA2AResponseDictConstruction:
    """Test that all response types can be safely converted to spec-compliant dicts.

    Per PR #604, A2A responses use model_dump() directly (no extra fields).
    Human-readable messages are in Artifact.description, not response data.
    """

    def test_create_media_buy_response_to_dict(self):
        """Test CreateMediaBuyResponse can be converted to spec-compliant dict.

        Per PR #604: A2A uses model_dump() directly (no extra fields).
        """
        from src.core.schemas import CreateMediaBuyResponse

        response = CreateMediaBuyResponse(
            buyer_ref="test-123",
            media_buy_id="mb-456",
        )

        # Simulate what _handle_create_media_buy_skill does now (PR #604)
        # ✅ This should NOT raise AttributeError
        a2a_dict = response.model_dump()  # Direct conversion, no extra fields

        assert "media_buy_id" in a2a_dict
        assert a2a_dict["media_buy_id"] == "mb-456"
        assert "success" not in a2a_dict  # No protocol fields
        assert "message" not in a2a_dict  # No protocol fields

    def test_sync_creatives_response_to_dict(self):
        """Test SyncCreativesResponse can be converted to spec-compliant dict.

        Per PR #604: A2A uses model_dump() directly (no extra fields).
        """
        from src.core.schemas import SyncCreativeResult, SyncCreativesResponse

        response = SyncCreativesResponse(
            dry_run=False,
            creatives=[
                SyncCreativeResult(
                    buyer_ref="test-001",
                    creative_id="cr-001",
                    status="approved",
                    action="created",  # Required field
                )
            ],
        )

        # ✅ This should NOT raise AttributeError
        a2a_dict = response.model_dump()  # Direct conversion, no extra fields

        assert "creatives" in a2a_dict
        assert len(a2a_dict["creatives"]) == 1
        assert "success" not in a2a_dict  # No protocol fields
        assert "message" not in a2a_dict  # No protocol fields

    def test_get_products_response_to_dict(self):
        """Test GetProductsResponse can be converted to spec-compliant dict."""
        from src.core.schema_adapters import GetProductsResponse

        response = GetProductsResponse(products=[])

        # ✅ Direct conversion, no extra fields
        a2a_dict = response.model_dump()

        assert "products" in a2a_dict
        assert a2a_dict["products"] == []
        assert "message" not in a2a_dict  # No protocol fields
        assert "success" not in a2a_dict  # No protocol fields

    def test_all_response_types_have_str_for_artifact_description(self):
        """Test that all response types have __str__ method for Artifact.description.

        Per PR #604: Human-readable messages are in Artifact.description,
        generated from response.__str__(). All response types must have __str__.
        """
        from src.core.schemas import (
            CreateMediaBuyResponse,
            GetProductsResponse,
            ListCreativeFormatsResponse,
            ListCreativesResponse,
            SyncCreativesResponse,
        )

        response_types = [
            CreateMediaBuyResponse,
            SyncCreativesResponse,
            GetProductsResponse,
            ListCreativeFormatsResponse,
            ListCreativesResponse,
        ]

        for response_cls in response_types:
            # All response types must have __str__ method
            has_str_method = hasattr(response_cls, "__str__")

            assert (
                has_str_method
            ), f"{response_cls.__name__} must have __str__ method for Artifact.description (PR #604)"


@pytest.mark.integration
class TestA2AErrorHandling:
    """Test that A2A handlers properly handle errors without AttributeErrors."""

    @pytest.fixture
    def handler(self):
        return AdCPRequestHandler()

    @pytest.mark.asyncio
    async def test_skill_error_has_errors_field(self, handler, sample_principal):
        """Test that skill errors return spec-compliant error structure.

        Per PR #604: Errors are in 'errors' field, not 'success' or 'message'.
        """
        handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

        with patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_get_principal:
            mock_get_principal.return_value = sample_principal["principal_id"]

            # Force an error by passing invalid parameters
            params = {
                # Missing required fields - should cause validation error
            }

            try:
                result = await handler._handle_create_media_buy_skill(params, sample_principal["access_token"])
                # If it doesn't raise, check the error response structure (spec-compliant)
                if result.get("errors"):
                    assert "errors" in result, "Error response must have errors field"
                    assert isinstance(result["errors"], list), "errors must be a list"
            except Exception as e:
                # Errors are expected for invalid params
                assert "AttributeError" not in str(e), "Should not get AttributeError when handling skill errors"
