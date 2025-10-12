"""
Tests for response factory functions.

These tests ensure the factory functions prevent validation errors by requiring
all mandatory fields and providing clear error messages when they're missing.
"""

import pytest

from src.core.response_factory import (
    create_media_buy_approval_response,
    create_media_buy_error_response,
    create_media_buy_response,
)
from src.core.schemas import CreateMediaBuyResponse


class TestCreateMediaBuyResponse:
    """Test create_media_buy_response factory function."""

    def test_minimal_required_fields(self):
        """Test creating response with only required fields."""
        response = create_media_buy_response(buyer_ref="test_ref", status="completed")

        assert isinstance(response, CreateMediaBuyResponse)
        assert response.buyer_ref == "test_ref"
        assert response.status == "completed"
        assert response.adcp_version == "2.3.0"

    def test_all_fields_populated(self):
        """Test creating response with all fields."""
        response = create_media_buy_response(
            buyer_ref="test_ref",
            status="completed",
            media_buy_id="mb_123",
            task_id="task_456",
            packages=[{"package_id": "pkg_1"}],
            workflow_step_id="step_789",
        )

        assert response.buyer_ref == "test_ref"
        assert response.status == "completed"
        assert response.media_buy_id == "mb_123"
        assert response.task_id == "task_456"
        assert len(response.packages) == 1
        assert response.workflow_step_id == "step_789"

    def test_missing_buyer_ref_raises_error(self):
        """Test that missing buyer_ref raises clear error."""
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_response(buyer_ref=None, status="completed")

        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_response(buyer_ref="", status="completed")

    def test_missing_status_raises_error(self):
        """Test that missing status raises clear error."""
        with pytest.raises(ValueError, match="status is required"):
            create_media_buy_response(buyer_ref="test_ref", status=None)

        with pytest.raises(ValueError, match="status is required"):
            create_media_buy_response(buyer_ref="test_ref", status="")

    def test_invalid_status_raises_error(self):
        """Test that invalid status value raises error."""
        with pytest.raises(ValueError, match="Invalid status"):
            create_media_buy_response(buyer_ref="test_ref", status="invalid_status")

    def test_valid_statuses(self):
        """Test all valid AdCP status values."""
        valid_statuses = [
            "submitted",
            "working",
            "input-required",
            "completed",
            "failed",
            "canceled",
            "rejected",
            "auth-required",
        ]

        for status in valid_statuses:
            response = create_media_buy_response(buyer_ref="test_ref", status=status)
            assert response.status == status

    def test_default_packages_empty_list(self):
        """Test that packages defaults to empty list, not None."""
        response = create_media_buy_response(buyer_ref="test_ref", status="completed")
        assert response.packages == []
        assert response.packages is not None

    def test_keyword_only_arguments(self):
        """Test that all arguments must be keyword arguments."""
        # This should work
        response = create_media_buy_response(buyer_ref="test_ref", status="completed")
        assert response.buyer_ref == "test_ref"

        # Positional arguments should raise TypeError
        with pytest.raises(TypeError):
            create_media_buy_response("test_ref", "completed")  # type: ignore


class TestCreateMediaBuyErrorResponse:
    """Test create_media_buy_error_response convenience function."""

    def test_creates_error_response(self):
        """Test creating error response with default failed status."""
        response = create_media_buy_error_response(
            buyer_ref="test_ref", error_code="validation_error", error_message="Invalid budget"
        )

        assert response.buyer_ref == "test_ref"
        assert response.status == "failed"
        assert len(response.errors) == 1
        assert response.errors[0].code == "validation_error"
        assert response.errors[0].message == "Invalid budget"

    def test_custom_status(self):
        """Test error response with custom status."""
        response = create_media_buy_error_response(
            buyer_ref="test_ref",
            error_code="auth_error",
            error_message="Not authorized",
            status="rejected",
        )

        assert response.status == "rejected"

    def test_missing_buyer_ref(self):
        """Test that error response also requires buyer_ref."""
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_error_response(buyer_ref=None, error_code="validation_error", error_message="Test")


class TestCreateMediaBuyApprovalResponse:
    """Test create_media_buy_approval_response convenience function."""

    def test_creates_approval_response(self):
        """Test creating approval response with required fields."""
        response = create_media_buy_approval_response(buyer_ref="test_ref", media_buy_id="mb_pending_123")

        assert response.buyer_ref == "test_ref"
        assert response.status == "input-required"
        assert response.media_buy_id == "mb_pending_123"

    def test_with_task_id(self):
        """Test approval response with task tracking."""
        response = create_media_buy_approval_response(
            buyer_ref="test_ref",
            media_buy_id="mb_pending_123",
            task_id="task_456",
            workflow_step_id="step_789",
        )

        assert response.task_id == "task_456"
        assert response.workflow_step_id == "step_789"

    def test_missing_buyer_ref(self):
        """Test that approval response also requires buyer_ref."""
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_approval_response(buyer_ref=None, media_buy_id="mb_123")


class TestResponseValidation:
    """Test that factory-created responses pass Pydantic validation."""

    def test_success_response_serializes(self):
        """Test that success response can be serialized."""
        response = create_media_buy_response(buyer_ref="test_ref", status="completed", media_buy_id="mb_123")

        # Should serialize without errors
        data = response.model_dump()
        assert data["buyer_ref"] == "test_ref"
        assert data["status"] == "completed"

    def test_error_response_serializes(self):
        """Test that error response can be serialized."""
        response = create_media_buy_error_response(
            buyer_ref="test_ref", error_code="test_error", error_message="Test message"
        )

        data = response.model_dump()
        assert data["buyer_ref"] == "test_ref"
        assert len(data["errors"]) == 1

    def test_approval_response_serializes(self):
        """Test that approval response can be serialized."""
        response = create_media_buy_approval_response(buyer_ref="test_ref", media_buy_id="mb_pending")

        data = response.model_dump()
        assert data["buyer_ref"] == "test_ref"
        assert data["status"] == "input-required"


class TestFactoryPreventsRegressions:
    """Test that factory prevents the exact bug we fixed."""

    def test_prevents_missing_buyer_ref_in_approval(self):
        """Test that we can't forget buyer_ref in approval responses."""
        # This was the bug - creating response without buyer_ref
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_approval_response(
                buyer_ref=None,  # Missing!
                media_buy_id="mb_pending_123",
            )

    def test_prevents_missing_buyer_ref_in_error(self):
        """Test that we can't forget buyer_ref in error responses."""
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_error_response(
                buyer_ref=None,  # Missing!
                error_code="validation_error",
                error_message="Test",
            )

    def test_prevents_empty_buyer_ref(self):
        """Test that empty string buyer_ref is also caught."""
        with pytest.raises(ValueError, match="buyer_ref is required"):
            create_media_buy_response(buyer_ref="", status="completed")
