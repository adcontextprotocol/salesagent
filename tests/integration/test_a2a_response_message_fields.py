"""Integration tests for A2A response message field validation.

This test suite prevents AttributeError bugs when A2A handlers try to access
fields that don't exist on response objects (like response.message when the
response type doesn't have a message attribute).

Key principle: Test the ACTUAL dict construction that happens in _handle_*_skill
methods, not just the response object structure.

Regression prevention: https://github.com/adcontextprotocol/salesagent/pull/337
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from tests.helpers.a2a_response_validator import assert_valid_skill_response

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.mark.integration
class TestA2AMessageFieldValidation:
    """Test that all A2A skill handlers properly construct message fields.

    These tests catch AttributeError bugs when handlers try to access
    response.message on response types that don't have that field.
    """

    @pytest.fixture
    def handler(self):
        """Create A2A request handler."""
        return AdCPRequestHandler()

    @pytest.fixture
    def mock_auth_context(self, sample_tenant, sample_principal):
        """Mock authentication context for all tests."""
        from src.a2a_server import adcp_a2a_server

        def _mock_context(handler):
            # Set up request context with proper headers for tenant resolution
            # This will allow _create_tool_context_from_a2a to resolve the tenant from headers
            # Use ContextVars instead of threading.local()
            adcp_a2a_server._request_headers.set(
                {
                    "x-adcp-tenant": sample_tenant["tenant_id"],
                    "authorization": f"Bearer {sample_principal['access_token']}",
                }
            )

            handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

            # Only mock get_principal_from_token - let real tenant lookups happen
            # since sample_tenant fixture created the tenant in the database
            return patch(
                "src.core.auth_utils.get_principal_from_token",
                return_value=sample_principal["principal_id"],
            )

        return _mock_context

    @pytest.mark.asyncio
    async def test_create_media_buy_message_field_exists(
        self, handler, mock_auth_context, sample_tenant, sample_principal, sample_products
    ):
        """Test create_media_buy returns a valid message field.

        Prevents: 'CreateMediaBuyResponse' object has no attribute 'message'
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
                        "product_id": sample_products[0],  # AdCP spec: product_id (singular), not products (array)
                        "budget": 10000.0,  # AdCP spec: budget is a number in packages, not an object
                        "pricing_option_id": "cpm_usd_fixed",
                    }
                ],
                # Note: NO top-level budget field per AdCP v2.2.0 spec
                "start_time": start_date.isoformat(),
                "end_time": end_date.isoformat(),
            }

            # Call the handler method directly - this is where the bug occurred
            result = await handler._handle_create_media_buy_skill(params, sample_principal["access_token"])

            # ✅ CRITICAL: Use comprehensive validator to check all fields
            assert_valid_skill_response(result, "create_media_buy")

    @pytest.mark.asyncio
    async def test_sync_creatives_message_field_exists(self, handler, mock_auth_context, sample_principal):
        """Test sync_creatives returns a valid message field.

        SyncCreativesResponse also doesn't have a .message field, uses __str__
        """
        with mock_auth_context(handler):
            params = {
                "creatives": [
                    {
                        "creative_id": "creative_test_001",  # Changed from buyer_ref to creative_id per adcp library
                        "format_id": "display_300x250",
                        "name": "Test Creative",
                        "assets": {"main_image": {"asset_type": "image", "url": "https://example.com/image.jpg"}},
                    }
                ],
                "validation_mode": "strict",
            }

            # Call handler directly
            result = await handler._handle_sync_creatives_skill(params, sample_principal["access_token"])

            # ✅ Use validator
            assert_valid_skill_response(result, "sync_creatives")

    @pytest.mark.asyncio
    async def test_get_products_spec_compliance(self, handler, mock_auth_context, sample_principal):
        """Test get_products returns spec-compliant A2A response.

        Per AdCP spec and PR #238, DataPart.data must NOT contain protocol fields.
        """
        with mock_auth_context(handler):
            params = {"brand_manifest": {"name": "Test product search"}, "brief": "Looking for display ads"}

            result = await handler._handle_get_products_skill(params, sample_principal["access_token"])

            # ✅ Use comprehensive validator to check spec compliance
            assert_valid_skill_response(result, "get_products")

    @pytest.mark.asyncio
    async def test_list_creatives_spec_compliance(self, handler, mock_auth_context, sample_principal):
        """Test list_creatives returns spec-compliant A2A response.

        Per AdCP spec and PR #238, DataPart.data must NOT contain protocol fields.
        """
        with mock_auth_context(handler):
            params = {
                "buyer_ref": "test_creative",
                "page": 1,
                "limit": 10,
            }

            result = await handler._handle_list_creatives_skill(params, sample_principal["access_token"])

            # ✅ Use comprehensive validator to check spec compliance
            assert_valid_skill_response(result, "list_creatives")

    @pytest.mark.asyncio
    async def test_list_creative_formats_spec_compliance(self, handler, mock_auth_context, sample_principal):
        """Test list_creative_formats returns spec-compliant A2A response.

        Per AdCP spec and PR #238, DataPart.data must NOT contain protocol fields.
        """
        with mock_auth_context(handler):
            params = {}

            result = await handler._handle_list_creative_formats_skill(params, sample_principal["access_token"])

            # ✅ Use comprehensive validator to check spec compliance
            assert_valid_skill_response(result, "list_creative_formats")


@pytest.mark.integration
class TestA2AResponseDictConstruction:
    """Test that all response types can be safely converted to spec-compliant responses.

    Per AdCP spec and PR #238:
    - DataPart contains pure AdCP payload (response.model_dump())
    - TextPart contains human message (str(response))
    - NO protocol fields (success, message) in DataPart.data
    """

    def test_create_media_buy_response_to_spec_compliant_dict(self):
        """Test CreateMediaBuySuccess converts to spec-compliant response.

        Per AdCP spec:
        - DataPart contains ONLY AdCP response fields
        - TextPart contains human-readable message
        - NO success/message fields in data
        """
        from src.core.schemas import CreateMediaBuySuccess

        response = CreateMediaBuySuccess(
            buyer_ref="test-123",
            media_buy_id="mb-456",
            packages=[],  # Required field in adcp v1.2.1
        )

        # ✅ CORRECT - Pure AdCP payload for DataPart
        data_part = response.model_dump()
        assert "success" not in data_part, "Protocol fields violate AdCP spec"
        assert "message" not in data_part, "Protocol fields violate AdCP spec"
        assert "media_buy_id" in data_part, "AdCP field should be present"

        # ✅ CORRECT - Human message for TextPart
        text_part = str(response)
        assert text_part == "Media buy mb-456 created successfully."
        assert isinstance(text_part, str)

    def test_sync_creatives_response_to_spec_compliant_dict(self):
        """Test SyncCreativesResponse converts to spec-compliant response.

        Per AdCP spec:
        - DataPart contains ONLY AdCP response fields
        - TextPart contains human-readable message from __str__()
        - NO success/message fields in data
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

        # ✅ CORRECT - Pure AdCP payload for DataPart
        data_part = response.model_dump()
        assert "success" not in data_part, "Protocol fields violate AdCP spec"
        assert "message" not in data_part, "Protocol fields violate AdCP spec"
        assert "creatives" in data_part, "AdCP field should be present"

        # ✅ CORRECT - Human message for TextPart
        text_part = str(response)
        assert isinstance(text_part, str)
        assert len(text_part) > 0

    def test_get_products_response_to_spec_compliant_dict(self):
        """Test GetProductsResponse converts to spec-compliant response.

        Per AdCP spec:
        - DataPart contains ONLY AdCP response fields
        - TextPart contains human-readable message from __str__()
        - NO success/message fields in data
        """
        from src.core.schema_adapters import GetProductsResponse

        response = GetProductsResponse(products=[])

        # ✅ CORRECT - Pure AdCP payload for DataPart
        data_part = response.model_dump()
        assert "success" not in data_part, "Protocol fields violate AdCP spec"
        assert "message" not in data_part, "Protocol fields violate AdCP spec"
        assert "products" in data_part, "AdCP field should be present"

        # ✅ CORRECT - Human message for TextPart
        text_part = str(response)
        assert text_part == "No products matched your requirements."
        assert isinstance(text_part, str)

    def test_all_response_types_have_str_method(self):
        """Test that all response types used in A2A have __str__() methods.

        Per AdCP spec and PR #238:
        - Response types provide human messages via __str__() method
        - These messages go in TextPart, separate from DataPart (AdCP payload)
        - NO .message field in response data (protocol field)

        This is a contract test - ensures we don't add response types that
        can't provide human-readable messages for TextPart.

        NOTE: In adcp v1.2.1, some response types are Union types (Success | Error).
        We test both Success and Error variants separately.
        """
        from src.core.schemas import (
            CreateMediaBuyError,
            CreateMediaBuySuccess,
            GetProductsResponse,
            ListCreativeFormatsResponse,
            ListCreativesResponse,
            SyncCreativesResponse,
        )

        response_types = [
            CreateMediaBuySuccess,  # Test Success variant
            CreateMediaBuyError,  # Test Error variant
            SyncCreativesResponse,
            GetProductsResponse,
            ListCreativeFormatsResponse,
            ListCreativesResponse,
        ]

        for response_cls in response_types:
            # All response types MUST have __str__() method for TextPart
            has_str_method = hasattr(response_cls, "__str__")

            assert has_str_method, (
                f"{response_cls.__name__} must have __str__() method for A2A TextPart compliance. "
                f"Human messages come from str(response), not response.message field."
            )


@pytest.mark.integration
class TestA2AErrorHandling:
    """Test that A2A handlers properly handle errors without AttributeErrors."""

    @pytest.fixture
    def handler(self):
        return AdCPRequestHandler()

    @pytest.mark.asyncio
    async def test_skill_error_handling_spec_compliance(self, handler, sample_principal):
        """Test that skill errors use proper exception handling (not protocol fields).

        Per AdCP spec and PR #238:
        - Errors should raise ServerError exceptions
        - NOT return dicts with success/message fields
        - A2A framework converts exceptions to Task.status.state = failed
        """
        handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

        with patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_get_principal:
            mock_get_principal.return_value = sample_principal["principal_id"]

            # Force an error by passing invalid parameters
            params = {
                # Missing required fields - should cause ServerError to be raised
            }

            # ✅ CORRECT - Errors should raise exceptions, not return error dicts
            with pytest.raises(Exception) as exc_info:
                await handler._handle_create_media_buy_skill(params, sample_principal["access_token"])

            # Verify we don't get AttributeError (original bug this test was catching)
            assert "AttributeError" not in str(
                exc_info.value
            ), "Should not get AttributeError when handling skill errors"
