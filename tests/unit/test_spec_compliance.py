"""Tests for spec compliance after context management improvements."""

import pytest

from src.core.async_patterns import (
    AsyncTask,
    TaskState,
    TaskStatus,
    is_async_operation,
)
from src.core.schemas import (
    CreateMediaBuyResponse,
    Error,
    GetProductsResponse,
    ListCreativeFormatsResponse,
)


class TestResponseSchemas:
    """Test that response schemas are spec-compliant."""

    def test_create_media_buy_response_no_context_id(self):
        """Verify CreateMediaBuyResponse doesn't have context_id."""
        response = CreateMediaBuyResponse(
            media_buy_id="buy_123", buyer_ref="ref_456", status="active", packages=[], message="Created successfully"
        )

        # Verify context_id is not in the schema
        assert not hasattr(response, "context_id")

        # Verify new fields are present
        assert response.status == "active"
        assert response.message == "Created successfully"
        assert response.buyer_ref == "ref_456"

    def test_get_products_response_no_context_id(self):
        """Verify GetProductsResponse doesn't have context_id."""
        response = GetProductsResponse(products=[], message="No products found")

        # Verify context_id is not in the schema
        assert not hasattr(response, "context_id")

        # Verify protocol fields are present
        assert response.message == "No products found"
        assert response.products == []

    def test_list_creative_formats_response_no_context_id(self):
        """Verify ListCreativeFormatsResponse doesn't have context_id."""
        response = ListCreativeFormatsResponse(formats=["display_300x250", "video_16x9"], message="2 formats available")

        # Verify context_id is not in the schema
        assert not hasattr(response, "context_id")

        # Verify fields
        assert len(response.formats) == 2
        assert response.message == "2 formats available"

    def test_error_reporting_in_responses(self):
        """Verify error reporting is protocol-compliant."""
        response = CreateMediaBuyResponse(
            media_buy_id="",
            status="failed",
            message="Creation failed",
            errors=[Error(code="validation_error", message="Invalid budget", details={"budget": -100})],
        )

        assert response.status == "failed"
        assert response.errors is not None
        assert len(response.errors) == 1
        assert response.errors[0].code == "validation_error"


class TestAsyncPatterns:
    """Test async operation patterns."""

    def test_task_state_enum(self):
        """Verify TaskState enum has all A2A states."""
        expected_states = {
            "submitted",
            "working",
            "input_required",
            "completed",
            "canceled",
            "failed",
            "rejected",
            "auth_required",
            "unknown",
        }

        actual_states = {state.value for state in TaskState}

        # All A2A states should be present
        assert expected_states.issubset(actual_states)

        # We added pending_approval as custom state
        assert TaskState.PENDING_APPROVAL.value == "pending_approval"

    def test_async_task_model(self):
        """Test AsyncTask model functionality."""
        task = AsyncTask(
            task_id="task_123", task_type="media_buy_creation", status=TaskStatus(state=TaskState.WORKING), result=None
        )

        assert task.task_id == "task_123"
        assert not task.is_complete()
        assert not task.is_success()
        assert not task.needs_input()

        # Update to completed
        task.status.state = TaskState.COMPLETED
        assert task.is_complete()
        assert task.is_success()

        # Update to pending approval
        task.status.state = TaskState.PENDING_APPROVAL
        assert not task.is_complete()
        assert task.needs_input()

    def test_operation_classification(self):
        """Test classification of operations as sync vs async."""
        # Async operations
        assert is_async_operation("create_media_buy") is True
        assert is_async_operation("update_media_buy") is True
        assert is_async_operation("bulk_upload_creatives") is True

        # Sync operations
        assert is_async_operation("get_products") is False
        assert is_async_operation("list_creative_formats") is False
        assert is_async_operation("check_media_buy_status") is False

        # Default behavior - create/update/delete are async
        assert is_async_operation("create_campaign") is True
        assert is_async_operation("update_settings") is True
        assert is_async_operation("delete_creative") is True
        assert is_async_operation("fetch_data") is False


class TestProtocolCompliance:
    """Test protocol compliance."""

    def test_create_media_buy_async_states(self):
        """Test that create_media_buy response handles async states correctly."""
        # Pending approval state
        response = CreateMediaBuyResponse(
            media_buy_id="pending_123",
            status="pending_manual",
            detail="Requires approval",
            message="Your request has been submitted for review",
        )

        assert response.status == "pending_manual"
        assert response.detail == "Requires approval"
        assert "review" in response.message.lower()

        # Failed state
        response = CreateMediaBuyResponse(
            media_buy_id="",
            status="failed",
            message="Budget validation failed",
            errors=[Error(code="invalid_budget", message="Budget must be positive")],
        )

        assert response.status == "failed"
        assert response.errors is not None
        assert response.media_buy_id == ""  # Empty on failure

        # Success state
        response = CreateMediaBuyResponse(
            media_buy_id="buy_456",
            buyer_ref="ref_789",
            status="active",
            packages=[{"package_id": "pkg_1"}],
            message="Media buy created successfully",
        )

        assert response.status == "active"
        assert response.media_buy_id == "buy_456"
        assert len(response.packages) == 1
        assert response.errors is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
