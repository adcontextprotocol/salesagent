"""Tests for protocol envelope wrapper.

Verifies that the ProtocolEnvelope class correctly wraps domain responses
according to the AdCP v2.4 spec.
"""

from datetime import UTC, datetime

import pytest

from src.core.protocol_envelope import ProtocolEnvelope
from src.core.schemas import CreateMediaBuyResponse, GetProductsResponse


class TestProtocolEnvelope:
    """Test protocol envelope wrapping per AdCP v2.4 spec."""

    def test_wrap_pydantic_model_with_minimal_fields(self):
        """Test wrapping a Pydantic model with only required envelope fields."""
        # Create domain response
        response = GetProductsResponse(products=[])

        # Wrap in protocol envelope
        envelope = ProtocolEnvelope.wrap(payload=response, status="completed", add_timestamp=False)

        # Verify envelope structure
        assert envelope.status == "completed"
        assert "products" in envelope.payload
        assert envelope.payload["products"] == []
        # Note: GetProductsResponse still has adcp_version (will be removed in later task)
        assert envelope.message is not None  # Generated from __str__
        assert envelope.task_id is None
        assert envelope.context_id is None
        assert envelope.timestamp is None

    def test_wrap_pydantic_model_with_all_fields(self):
        """Test wrapping with all optional envelope fields."""
        # Create domain response (no protocol fields - those go in envelope)
        response = CreateMediaBuyResponse(buyer_ref="ref123", media_buy_id="mb_456", packages=[], errors=None)

        # Create push notification config
        push_config = {
            "url": "https://example.com/webhook",
            "authentication": {"schemes": ["HMAC-SHA256"], "credentials": "secret"},
        }

        # Wrap with all fields
        envelope = ProtocolEnvelope.wrap(
            payload=response,
            status="completed",
            message="Media buy created",
            task_id="task_789",
            context_id="ctx_abc",
            push_notification_config=push_config,
            add_timestamp=True,
        )

        # Verify all fields present
        assert envelope.status == "completed"
        assert envelope.message == "Media buy created"
        assert envelope.task_id == "task_789"
        assert envelope.context_id == "ctx_abc"
        assert envelope.push_notification_config == push_config
        assert envelope.timestamp is not None
        assert isinstance(envelope.timestamp, datetime)

        # Verify payload contains domain data (status removed by model_dump)
        assert "buyer_ref" in envelope.payload
        assert envelope.payload["buyer_ref"] == "ref123"

    def test_wrap_dict_payload(self):
        """Test wrapping a dict payload (not a Pydantic model)."""
        payload_dict = {"products": [{"product_id": "p1", "name": "Test Product"}]}

        envelope = ProtocolEnvelope.wrap(
            payload=payload_dict, status="completed", message="Found 1 product", add_timestamp=False
        )

        assert envelope.status == "completed"
        assert envelope.message == "Found 1 product"
        assert envelope.payload == payload_dict

    def test_model_dump_excludes_none_values(self):
        """Test that model_dump excludes None values by default."""
        response = GetProductsResponse(products=[])

        envelope = ProtocolEnvelope.wrap(payload=response, status="completed", add_timestamp=False)

        dumped = envelope.model_dump()

        # None values should be excluded
        assert "task_id" not in dumped
        assert "context_id" not in dumped
        assert "timestamp" not in dumped
        assert "push_notification_config" not in dumped

        # Required and present values should be included
        assert "status" in dumped
        assert "payload" in dumped
        assert "message" in dumped  # Generated from __str__

    def test_status_values_from_spec(self):
        """Test all valid status values per AdCP spec."""
        valid_statuses = [
            "submitted",
            "working",
            "completed",
            "failed",
            "input-required",
            "canceled",
            "rejected",
            "auth-required",
        ]

        for status in valid_statuses:
            envelope = ProtocolEnvelope.wrap(payload={}, status=status, add_timestamp=False)
            assert envelope.status == status

    def test_invalid_status_raises_validation_error(self):
        """Test that invalid status values raise validation errors."""
        with pytest.raises(ValueError):
            ProtocolEnvelope.wrap(payload={}, status="invalid_status", add_timestamp=False)

    def test_payload_excludes_internal_fields(self):
        """Test that payload excludes internal fields via model_dump."""
        response = CreateMediaBuyResponse(
            buyer_ref="ref123",
            media_buy_id="mb_456",
            workflow_step_id="ws_789",  # Internal field
            packages=[],
            errors=None,
        )

        envelope = ProtocolEnvelope.wrap(payload=response, status="completed", add_timestamp=False)

        # Internal fields should be excluded from payload
        assert "workflow_step_id" not in envelope.payload
        assert "buyer_ref" in envelope.payload

    def test_message_generation_from_payload_str(self):
        """Test that message is auto-generated from payload.__str__ if not provided."""
        response = CreateMediaBuyResponse(buyer_ref="ref123", media_buy_id="mb_456", packages=[], errors=None)

        envelope = ProtocolEnvelope.wrap(payload=response, status="completed", add_timestamp=False)

        # Message should be generated from response.__str__
        assert envelope.message is not None
        assert "mb_456" in envelope.message
        assert "created successfully" in envelope.message.lower()

    def test_timestamp_format(self):
        """Test that timestamp is ISO 8601 UTC datetime."""
        envelope = ProtocolEnvelope.wrap(payload={}, status="completed", add_timestamp=True)

        assert envelope.timestamp is not None
        assert envelope.timestamp.tzinfo == UTC

        # Verify serialization to ISO 8601
        dumped = envelope.model_dump(mode="json")  # Use mode="json" for proper serialization
        assert "timestamp" in dumped
        timestamp_str = dumped["timestamp"]
        # Should be parseable as ISO 8601
        assert isinstance(timestamp_str, str)
        parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)

    def test_async_operation_with_task_id(self):
        """Test envelope for async operation (submitted status with task_id)."""
        response = CreateMediaBuyResponse(buyer_ref="ref123", packages=[], errors=None)

        envelope = ProtocolEnvelope.wrap(
            payload=response, status="submitted", task_id="task_async_123", message="Processing media buy creation"
        )

        assert envelope.status == "submitted"
        assert envelope.task_id == "task_async_123"
        assert "payload" in envelope.model_dump()

    def test_error_response_with_failures(self):
        """Test envelope for failed operation."""
        from src.core.schemas import Error

        response = CreateMediaBuyResponse(
            buyer_ref="ref123",
            errors=[Error(code="INVALID_BUDGET", message="Budget too low", severity="error")],
            packages=[],
        )

        envelope = ProtocolEnvelope.wrap(payload=response, status="failed", message="Media buy creation failed")

        assert envelope.status == "failed"
        assert envelope.message == "Media buy creation failed"
        assert "errors" in envelope.payload
        assert len(envelope.payload["errors"]) == 1
