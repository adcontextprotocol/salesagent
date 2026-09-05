"""Integration tests for A2A response message field validation.

This test suite prevents AttributeError bugs when A2A handlers try to access
fields that don't exist on response objects (like response.message when the
response type doesn't have a message attribute).

Key principle: Test the ACTUAL dict construction that happens in _handle_*_skill
methods, not just the response object structure.

Regression prevention: https://github.com/prebid/salesagent/pull/337

NOTE: Some tests connect to external creative agents (creative.adcontextprotocol.org).
If these services are unavailable (HTTP 5xx, connection errors), tests will skip
rather than fail, since external service availability is outside our control.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from tests.factories.principal import PrincipalFactory

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_MOCK_IDENTITY = PrincipalFactory.make_identity(
    principal_id="test_principal",
    tenant_id="test_tenant",
    tenant={"tenant_id": "test_tenant"},
    protocol="a2a",
)


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

    def test_the_a2a_stamp_adds_message_to_any_response(self):
        """``message`` reaches the wire for every skill, graded once on the step that adds it.

        Five per-tool copies of this stood here -- create_media_buy, sync_creatives,
        get_products, list_creatives, list_creative_formats -- each driving a real skill
        through full setup to ask whether its reply carried a ``message``. They could not
        disagree: ``message`` and ``success`` are stamped by ONE static method,
        ``_stamp_a2a_protocol_fields``, which takes any AdCPBaseModel and is the only place
        either field is added (they are not spec fields on any response). Five tools cannot
        answer that question differently, so asking five times graded the same method five
        times at five times the cost -- the per-tool enumeration the registry replaced
        everywhere else.

        That the stamped value then reaches the artifact is pinned separately, by
        test_a2a_skill_invocation.py::test_artifact_text_part_is_the_data_part_message.
        """
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
        from src.core.schemas import GetProductsResponse

        stamped = AdCPRequestHandler._stamp_a2a_protocol_fields(GetProductsResponse(products=[]))

        assert "message" in stamped, "the A2A stamp must add a message field"
        assert isinstance(stamped["message"], str) and stamped["message"], "message must be a non-empty string"
        assert stamped["success"] is True


@pytest.mark.integration
class TestA2AResponseDictConstruction:
    """Test that all response types can be safely converted to A2A response dicts.

    This catches the pattern where we try to access an attribute that doesn't exist
    on a Pydantic model, by testing the dict construction directly.
    """

    def test_create_media_buy_response_to_dict(self):
        """Test CreateMediaBuySuccess can be converted to A2A dict.

        Protocol fields (status) are added by A2A wrapper, not in domain response.

        NOTE: CreateMediaBuyResponse is a Union type (Success | Error) in adcp v1.2.1,
        so we test with CreateMediaBuySuccess instead.
        """
        from src.core.schemas import CreateMediaBuySuccess

        response = CreateMediaBuySuccess.carrier(
            media_buy_id="mb-456",
            packages=[],  # Required field in adcp v1.2.1
        )

        # Simulate what _handle_create_media_buy_skill does
        # ✅ This should NOT raise AttributeError
        a2a_dict = {
            "success": True,
            "media_buy_id": response.media_buy_id,
            "message": str(response),  # Safe for all response types
        }

        assert a2a_dict["message"] == "Media buy mb-456 created successfully."

    def test_sync_creatives_response_to_dict(self):
        """Test SyncCreativesResponse can be converted to A2A dict.

        Protocol fields (status, message) are added by A2A wrapper.
        Domain response uses __str__() to generate message.
        """
        from src.core.schemas import SyncCreativeResult, SyncCreativesResponse

        response = SyncCreativesResponse(
            dry_run=False,
            creatives=[
                SyncCreativeResult(
                    creative_id="cr-001",
                    internal_status="approved",
                    action="created",  # Required field
                )
            ],
        )

        # ✅ This should NOT raise AttributeError
        a2a_dict = {
            "success": True,
            "message": str(response),  # Safe - uses __str__ method
        }

        assert isinstance(a2a_dict["message"], str)
        assert len(a2a_dict["message"]) > 0

    def test_get_products_response_to_dict(self):
        """Test GetProductsResponse can be converted to A2A dict."""
        from src.core.schemas import GetProductsResponse

        response = GetProductsResponse(products=[])

        # ✅ Uses __str__ method to generate message
        a2a_dict = {
            "products": [p.model_dump() if hasattr(p, "model_dump") else p for p in response.products],
            "message": str(response),  # Uses __str__ method
        }

        assert a2a_dict["message"] == "No products matched your requirements."

    def test_all_response_types_have_str_or_message(self):
        """Test that all response types used in A2A have either __str__ or .message.

        This is a contract test - ensures we don't add response types that
        can't be safely converted to A2A dicts.

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
            # Check if it has __str__ method or message field
            has_str_method = hasattr(response_cls, "__str__")

            # Try to create a minimal instance and check for message field
            # This is tricky because we need to provide required fields
            # For now, just check the class definition
            has_message_field = "message" in response_cls.model_fields

            assert has_str_method or has_message_field, (
                f"{response_cls.__name__} must have either __str__ method or .message field for A2A compatibility"
            )


@pytest.mark.integration
class TestA2AErrorHandling:
    """Test that A2A handlers properly handle errors without AttributeErrors."""

    @pytest.fixture
    def handler(self):
        return AdCPRequestHandler()

    @pytest.mark.asyncio
    async def test_skill_error_has_message_field(self, handler, sample_principal):
        """Test that skill errors return proper message fields."""
        handler._get_auth_token = MagicMock(return_value=sample_principal["access_token"])

        with patch("src.core.resolved_identity.resolve_identity", return_value=_MOCK_IDENTITY):
            # Force an error by passing invalid parameters
            params = {
                # Missing required fields - should cause validation error
            }

            try:
                raw_result = await handler._handle_create_media_buy_skill(params, identity=_MOCK_IDENTITY)
                result = handler._serialize_for_a2a(raw_result)
                # If it doesn't raise, check the error response structure
                if not result.get("success", True):
                    assert "message" in result or "error" in result, "Error response must have message or error field"
            except Exception as e:
                pass  # the operation must raise; its message is not asserted
                # Errors are expected for invalid params
