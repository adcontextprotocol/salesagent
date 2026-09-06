#!/usr/bin/env python3
"""
Unit test for error handling in media buy approval when adapter returns CreateMediaBuyError.

This tests the fix for the bug where trying to approve a media buy would crash with:
"'CreateMediaBuyError' object has no attribute 'media_buy_id'"
"""

from src.core.schemas import CreateMediaBuyError, CreateMediaBuySuccess, Error


class TestApprovalErrorHandling:
    """Test error handling when adapter creation fails during approval."""

    def test_create_media_buy_error_has_errors_field_not_media_buy_id(self):
        """Verify CreateMediaBuyError structure - has 'errors' but not 'media_buy_id'."""
        # This test documents the schema structure that caused the bug
        error_response = CreateMediaBuyError(errors=[Error(code="VALIDATION_ERROR")])

        # CreateMediaBuyError has 'errors' field
        assert hasattr(error_response, "errors")
        assert len(error_response.errors) == 1
        # `message` is derived from CODE_TABLE by the code alone (ADR-010), so a
        # caller-supplied string is discarded rather than echoed back.
        assert error_response.errors[0].message == Error(code="VALIDATION_ERROR").message
        assert error_response.errors[0].message

        # CreateMediaBuyError does NOT have 'media_buy_id' field
        assert not hasattr(error_response, "media_buy_id")

    def test_create_media_buy_success_has_media_buy_id(self):
        """Verify CreateMediaBuySuccess has media_buy_id field."""
        success_response = CreateMediaBuySuccess.carrier(
            media_buy_id="mb_123",
            packages=[],
        )

        # CreateMediaBuySuccess has 'media_buy_id' field
        assert hasattr(success_response, "media_buy_id")
        assert success_response.media_buy_id == "mb_123"

    def test_error_response_isinstance_check(self):
        """Test isinstance check correctly identifies error responses."""
        error_response = CreateMediaBuyError(errors=[Error(code="VALIDATION_ERROR", message="Test error")])
        success_response = CreateMediaBuySuccess.carrier(
            media_buy_id="mb_123",
            packages=[],
        )

        # Can distinguish error from success using isinstance
        assert isinstance(error_response, CreateMediaBuyError)
        assert not isinstance(success_response, CreateMediaBuyError)

        assert isinstance(success_response, CreateMediaBuySuccess)
        assert not isinstance(error_response, CreateMediaBuySuccess)
