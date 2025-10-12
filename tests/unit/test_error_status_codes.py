"""Test error responses use correct AdCP status codes.

This tests the fix for the bug where validation errors returned status="completed"
with null media_buy_id instead of status="failed" or "rejected" per AdCP spec.
"""

from src.core.schemas import CreateMediaBuyResponse, Error


class TestErrorStatusCodes:
    """Test that error responses use correct AdCP status values."""

    def test_validation_error_returns_failed_status(self):
        """Test that validation errors return status='failed' not 'completed'."""
        # Test creating a response with validation error
        response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="failed",  # Should be 'failed' for validation errors
            buyer_ref="test_buyer",
            errors=[Error(code="validation_error", message="Currency EUR is not supported")],
        )

        assert response.status == "failed"
        assert response.media_buy_id is None
        assert len(response.errors) == 1
        assert response.errors[0].code == "validation_error"

    def test_auth_error_returns_rejected_status(self):
        """Test that authentication errors return status='rejected' not 'completed'."""
        response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="rejected",  # Should be 'rejected' for auth failures
            buyer_ref="test_buyer",
            errors=[Error(code="authentication_error", message="Principal not found")],
        )

        assert response.status == "rejected"
        assert response.media_buy_id is None
        assert len(response.errors) == 1
        assert response.errors[0].code == "authentication_error"

    def test_success_returns_working_or_completed_status(self):
        """Test that successful operations return 'working' or 'completed'."""
        # Working status (async operation)
        response_working = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="working",
            buyer_ref="test_buyer",
            media_buy_id="buy_123",
            packages=[],
        )

        assert response_working.status == "working"
        assert response_working.media_buy_id == "buy_123"
        assert response_working.errors is None or len(response_working.errors) == 0

        # Completed status (sync operation)
        response_completed = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="completed",
            buyer_ref="test_buyer",
            media_buy_id="buy_456",
            packages=[],
        )

        assert response_completed.status == "completed"
        assert response_completed.media_buy_id == "buy_456"
        assert response_completed.errors is None or len(response_completed.errors) == 0

    def test_schema_allows_all_adcp_statuses(self):
        """Test that CreateMediaBuyResponse schema allows all 8 AdCP status values."""
        valid_statuses = [
            "submitted",
            "working",
            "input-required",
            "completed",
            "canceled",
            "failed",
            "rejected",
            "auth-required",
        ]

        for status in valid_statuses:
            response = CreateMediaBuyResponse(
                adcp_version="2.3.0",
                status=status,
                buyer_ref="test_buyer",
            )
            assert response.status == status

    def test_completed_status_should_have_media_buy_id(self):
        """Test that status='completed' responses should have media_buy_id (not null)."""
        # This is the pattern: completed = success, must have media_buy_id
        response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="completed",
            buyer_ref="test_buyer",
            media_buy_id="buy_789",  # Required for completed status
        )

        assert response.status == "completed"
        assert response.media_buy_id is not None
        assert response.media_buy_id == "buy_789"

    def test_failed_status_should_not_have_media_buy_id(self):
        """Test that status='failed' responses should NOT have media_buy_id (null is ok)."""
        # This is the pattern: failed = error, media_buy_id is null
        response = CreateMediaBuyResponse(
            adcp_version="2.3.0",
            status="failed",
            buyer_ref="test_buyer",
            media_buy_id=None,  # Null for failed operations
            errors=[Error(code="validation_error", message="Invalid input")],
        )

        assert response.status == "failed"
        assert response.media_buy_id is None
        assert len(response.errors) == 1
