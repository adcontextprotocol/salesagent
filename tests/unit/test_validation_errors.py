"""Unit tests for validation error handling in create_media_buy."""

import pytest
from pydantic import ValidationError

from src.core.schemas import BrandManifest, CreateMediaBuyRequest
from src.core.validation_helpers import format_validation_error


def test_brand_manifest_target_audience_must_be_string():
    """Test that target_audience in BrandManifest must be a string, not object."""
    # This should raise ValidationError per AdCP spec
    with pytest.raises(ValidationError) as exc_info:
        BrandManifest(
            name="Test Brand",
            target_audience={"demographics": ["spiritual seekers"], "interests": ["unexplained phenomena"]},
        )

    # Check that the error is about string_type
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "string_type"
    assert errors[0]["loc"] == ("target_audience",)


def test_brand_manifest_target_audience_string_works():
    """Test that target_audience as string works correctly per AdCP spec."""
    manifest = BrandManifest(
        name="Test Brand",
        target_audience="spiritual seekers interested in unexplained phenomena",
    )

    assert manifest.target_audience == "spiritual seekers interested in unexplained phenomena"


def test_create_media_buy_request_invalid_brand_manifest():
    """Test that CreateMediaBuyRequest validates brand_manifest structure."""
    # Invalid: brand_manifest with nested object for target_audience
    with pytest.raises(ValidationError) as exc_info:
        CreateMediaBuyRequest(
            buyer_ref="test_ref",
            brand_manifest={
                "name": "Test Brand",
                "target_audience": {"demographics": ["spiritual seekers"], "interests": ["unexplained phenomena"]},
            },
        )

    # Should have validation errors
    errors = exc_info.value.errors()
    assert len(errors) >= 1
    # At least one error should be about target_audience being wrong type
    assert any("target_audience" in str(error["loc"]) and "string_type" in error["type"] for error in errors)


def test_validation_error_formatting():
    """Test that our validation error formatting provides helpful messages."""
    # Test the format_validation_error helper function
    try:
        raise ValidationError.from_exception_data(
            "CreateMediaBuyRequest",
            [
                {
                    "type": "string_type",
                    "loc": ("brand_manifest", "BrandManifest", "target_audience"),
                    "msg": "Input should be a valid string",
                    "input": {"demographics": ["test"], "interests": ["test"]},
                }
            ],
        )
    except ValidationError as e:
        # Use the shared helper function
        error_msg = format_validation_error(e, context="test request")

        # Check that we got a helpful error message
        assert "Invalid test request:" in error_msg
        assert "brand_manifest.BrandManifest.target_audience" in error_msg
        assert "Expected string, got object" in error_msg
        assert "AdCP spec requires this field to be a simple string" in error_msg
        assert "https://adcontextprotocol.org/schemas/v1/" in error_msg


def test_validation_error_formatting_missing_field():
    """Test formatting for missing required fields."""
    try:
        raise ValidationError.from_exception_data(
            "CreateMediaBuyRequest",
            [
                {
                    "type": "missing",
                    "loc": ("buyer_ref",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )
    except ValidationError as e:
        error_msg = format_validation_error(e)

        assert "buyer_ref: Required field is missing" in error_msg
        assert "Invalid request:" in error_msg


def test_validation_error_formatting_extra_field():
    """Test formatting for extra forbidden fields."""
    try:
        raise ValidationError.from_exception_data(
            "CreateMediaBuyRequest",
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("unknown_field",),
                    "msg": "Extra inputs are not permitted",
                    "input": "some_value",
                }
            ],
        )
    except ValidationError as e:
        error_msg = format_validation_error(e)

        assert "unknown_field: Extra field not allowed by AdCP spec" in error_msg
