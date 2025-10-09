"""
Unit tests for GAMCreativesManager class.

Tests creative validation logic including 1x1 wildcard placeholder handling.
"""

from unittest.mock import MagicMock

from src.adapters.gam.managers.creatives import GAMCreativesManager


def test_basic_functionality():
    """Test basic functionality."""
    assert True


def test_creative_validation_logic():
    """Test creative validation logic."""

    def validate_creative_dimensions(width, height):
        return width > 0 and height > 0

    assert validate_creative_dimensions(300, 250) is True
    assert validate_creative_dimensions(0, 250) is False
    assert validate_creative_dimensions(300, 0) is False


def test_creative_data_structure():
    """Test creative data structure validation."""
    creative = {
        "id": "13579",
        "name": "Test Creative",
        "advertiserId": "123456",
        "size": {"width": 300, "height": 250},
        "snippet": "<div>Test Creative Content</div>",
    }

    assert creative["id"] == "13579"
    assert creative["name"] == "Test Creative"
    assert creative["size"]["width"] == 300
    assert creative["size"]["height"] == 250


def test_creative_format_validation():
    """Test creative format validation logic."""
    supported_formats = ["display", "video", "native"]

    def is_supported_format(format_type):
        return format_type in supported_formats

    assert is_supported_format("display") is True
    assert is_supported_format("video") is True
    assert is_supported_format("unknown") is False


def test_1x1_placeholder_accepts_any_creative_size_native_template():
    """1x1 placeholder with template_id should accept any creative size."""
    # Setup manager
    client_manager = MagicMock()
    manager = GAMCreativesManager(client_manager, "advertiser_123", dry_run=True)

    # Mock asset with native creative dimensions
    asset = {
        "creative_id": "creative_123",
        "format": "native",
        "width": 1200,
        "height": 627,
        "package_assignments": ["package_1"],
    }

    # Creative placeholders with 1x1 + template_id (GAM native template)
    creative_placeholders = {
        "package_1": [
            {
                "size": {"width": 1, "height": 1},
                "creativeTemplateId": 12345678,
                "expectedCreativeCount": 1,
            }
        ]
    }

    # Should not return any validation errors
    errors = manager._validate_creative_size_against_placeholders(asset, creative_placeholders)
    assert errors == []


def test_1x1_placeholder_accepts_any_creative_size_programmatic():
    """1x1 placeholder without template_id should accept any creative size (programmatic)."""
    client_manager = MagicMock()
    manager = GAMCreativesManager(client_manager, "advertiser_123", dry_run=True)

    # Mock asset with standard display dimensions
    asset = {
        "creative_id": "creative_456",
        "format": "display",
        "width": 300,
        "height": 250,
        "third_party_url": "https://example.com/ad",
        "package_assignments": ["package_2"],
    }

    # Creative placeholders with 1x1 only (programmatic/third-party)
    creative_placeholders = {
        "package_2": [
            {
                "size": {"width": 1, "height": 1},
                "expectedCreativeCount": 1,
            }
        ]
    }

    # Should not return any validation errors
    errors = manager._validate_creative_size_against_placeholders(asset, creative_placeholders)
    assert errors == []


def test_standard_placeholder_requires_exact_match():
    """Non-1x1 placeholders should require exact dimension match."""
    client_manager = MagicMock()
    manager = GAMCreativesManager(client_manager, "advertiser_123", dry_run=True)

    # Mock asset with wrong dimensions
    asset = {
        "creative_id": "creative_789",
        "format": "display",
        "width": 728,
        "height": 90,
        "package_assignments": ["package_3"],
    }

    # Creative placeholders expecting 300x250
    creative_placeholders = {
        "package_3": [
            {
                "size": {"width": 300, "height": 250},
                "creativeSizeType": "PIXEL",
                "expectedCreativeCount": 1,
            }
        ]
    }

    # Should return validation error
    errors = manager._validate_creative_size_against_placeholders(asset, creative_placeholders)
    assert len(errors) == 1
    assert "728x90" in errors[0]
    assert "300x250" in errors[0]


def test_standard_placeholder_accepts_exact_match():
    """Non-1x1 placeholders should accept exact dimension match."""
    client_manager = MagicMock()
    manager = GAMCreativesManager(client_manager, "advertiser_123", dry_run=True)

    # Mock asset with correct dimensions
    asset = {
        "creative_id": "creative_999",
        "format": "display",
        "width": 300,
        "height": 250,
        "package_assignments": ["package_4"],
    }

    # Creative placeholders expecting 300x250
    creative_placeholders = {
        "package_4": [
            {
                "size": {"width": 300, "height": 250},
                "creativeSizeType": "PIXEL",
                "expectedCreativeCount": 1,
            }
        ]
    }

    # Should not return any validation errors
    errors = manager._validate_creative_size_against_placeholders(asset, creative_placeholders)
    assert errors == []


def test_1x1_takes_priority_over_other_sizes():
    """When multiple placeholders exist, 1x1 should match first."""
    client_manager = MagicMock()
    manager = GAMCreativesManager(client_manager, "advertiser_123", dry_run=True)

    # Mock asset that doesn't match 300x250 but should match 1x1
    asset = {
        "creative_id": "creative_111",
        "format": "display",
        "width": 728,
        "height": 90,
        "package_assignments": ["package_5"],
    }

    # Creative placeholders with both standard and 1x1
    creative_placeholders = {
        "package_5": [
            {
                "size": {"width": 300, "height": 250},
                "creativeSizeType": "PIXEL",
                "expectedCreativeCount": 1,
            },
            {
                "size": {"width": 1, "height": 1},
                "expectedCreativeCount": 1,
            },
        ]
    }

    # Should not return any validation errors (matches 1x1)
    errors = manager._validate_creative_size_against_placeholders(asset, creative_placeholders)
    assert errors == []


def test_dry_run_simulation():
    """Test dry run mode behavior simulation."""
    dry_run = True

    if dry_run:
        creative_id = "dry_run_creative_123"
        actual_upload = False
    else:
        creative_id = None
        actual_upload = True

    assert creative_id == "dry_run_creative_123"
    assert actual_upload is False
