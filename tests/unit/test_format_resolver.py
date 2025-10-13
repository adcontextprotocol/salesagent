"""Unit tests for format resolver with custom formats and product overrides."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.format_resolver import (
    _get_product_format_override,
    _get_tenant_custom_format,
    get_format,
    list_available_formats,
)
from src.core.schemas import Format


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("src.core.format_resolver.get_db_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - now uses CreativeAgentRegistry")
@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_get_format_from_standard_registry():
    """Test getting standard format from FORMAT_REGISTRY."""
    format_obj = get_format("display_300x250")

    assert format_obj.format_id == "display_300x250"
    assert format_obj.type == "display"
    assert format_obj.requirements["width"] == 300
    assert format_obj.requirements["height"] == 250


def test_get_format_unknown_raises_error():
    """Test that unknown format raises ValueError."""
    with pytest.raises(ValueError, match="Unknown format_id 'unknown_format'"):
        get_format("unknown_format")


def test_get_format_with_tenant_id_in_error(mock_db_session):
    """Test error message includes tenant_id when provided."""
    # Mock no tenant custom format found
    mock_db_session.execute.return_value.fetchone.return_value = None

    with pytest.raises(ValueError, match="for tenant tenant_123"):
        get_format("unknown_format", tenant_id="tenant_123")


def test_get_tenant_custom_format(mock_db_session):
    """Test getting tenant-specific custom format from database."""
    # Mock database row
    mock_db_session.execute.return_value.fetchone.return_value = (
        "custom_video_640x380",  # format_id
        "Custom Video Player",  # name
        "video",  # type
        "Custom aspect ratio video",  # description
        640,  # width
        380,  # height
        30,  # duration_seconds
        10240,  # max_file_size_kb
        json.dumps({"codecs": ["h264"]}),  # specs
        False,  # is_standard
        json.dumps(
            {  # platform_config
                "gam": {
                    "creative_placeholder": {
                        "width": 640,
                        "height": 380,
                        "creative_size_type": "PIXEL",
                    },
                    "environment_type": "VIDEO_PLAYER",
                }
            }
        ),
    )

    format_obj = _get_tenant_custom_format("tenant_123", "custom_video_640x380")

    assert format_obj is not None
    assert format_obj.format_id == "custom_video_640x380"
    assert format_obj.type == "video"
    assert format_obj.requirements["width"] == 640
    assert format_obj.requirements["height"] == 380
    assert format_obj.requirements["duration_max"] == 30
    assert format_obj.requirements["codecs"] == ["h264"]
    assert format_obj.platform_config["gam"]["creative_placeholder"]["width"] == 640


def test_get_tenant_custom_format_not_found(mock_db_session):
    """Test that None is returned when custom format not found."""
    mock_db_session.execute.return_value.fetchone.return_value = None

    format_obj = _get_tenant_custom_format("tenant_123", "nonexistent_format")

    assert format_obj is None


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_get_product_format_override(mock_db_session):
    """Test getting product-level format override."""
    # Mock product with format override
    impl_config = {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {
                        "creative_placeholder": {
                            "width": 1,
                            "height": 1,
                            "creative_template_id": 12345678,
                        }
                    }
                }
            }
        }
    }
    # First call: get product impl_config
    # Second call: get tenant custom format (returns None)
    mock_db_session.execute.return_value.fetchone.side_effect = [
        (json.dumps(impl_config),),  # Product impl_config
        None,  # No tenant custom format, will use FORMAT_REGISTRY
    ]

    format_obj = _get_product_format_override("tenant_123", "product_456", "display_300x250")

    assert format_obj is not None
    assert format_obj.format_id == "display_300x250"
    # Base format dimensions preserved
    assert format_obj.requirements["width"] == 300
    assert format_obj.requirements["height"] == 250
    # But platform_config overridden
    assert format_obj.platform_config["gam"]["creative_placeholder"]["width"] == 1
    assert format_obj.platform_config["gam"]["creative_placeholder"]["height"] == 1
    assert format_obj.platform_config["gam"]["creative_placeholder"]["creative_template_id"] == 12345678


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_get_product_format_override_not_configured(mock_db_session):
    """Test that None is returned when product has no override for format."""
    impl_config = {"format_overrides": {}}
    mock_db_session.execute.return_value.fetchone.return_value = (json.dumps(impl_config),)

    format_obj = _get_product_format_override("tenant_123", "product_456", "display_300x250")

    assert format_obj is None


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_get_product_format_override_no_impl_config(mock_db_session):
    """Test that None is returned when product has no implementation_config."""
    mock_db_session.execute.return_value.fetchone.return_value = (None,)

    format_obj = _get_product_format_override("tenant_123", "product_456", "display_300x250")

    assert format_obj is None


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_get_format_priority_product_override(mock_db_session):
    """Test format resolution priority: product override takes precedence."""
    # Mock product override
    impl_config = {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {
                        "creative_placeholder": {
                            "width": 1,
                            "height": 1,
                            "creative_template_id": 99999,
                        }
                    }
                }
            }
        }
    }
    mock_db_session.execute.return_value.fetchone.side_effect = [
        (json.dumps(impl_config),),  # Product impl_config
        None,  # No tenant custom format
    ]

    format_obj = get_format("display_300x250", tenant_id="tenant_123", product_id="product_456")

    # Should use product override
    assert format_obj.platform_config["gam"]["creative_placeholder"]["creative_template_id"] == 99999


def test_get_format_priority_tenant_custom(mock_db_session):
    """Test format resolution priority: tenant custom used when no product override."""
    # Mock no product override (first call) and tenant custom format (second call)
    mock_results = [
        (None,),  # No product override
        (  # Tenant custom format
            "custom_display_300x250",
            "Custom Display",
            "display",
            "Custom version",
            300,
            250,
            None,
            None,
            json.dumps({}),
            False,
            json.dumps({"gam": {"environment_type": "CUSTOM"}}),
        ),
    ]
    mock_db_session.execute.return_value.fetchone.side_effect = mock_results

    format_obj = get_format("custom_display_300x250", tenant_id="tenant_123", product_id="product_456")

    # Should use tenant custom format
    assert format_obj.platform_config["gam"]["environment_type"] == "CUSTOM"


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_list_available_formats_standard_only(mock_db_session):
    """Test listing formats with no tenant (standard only)."""
    formats = list_available_formats()

    # Should include all standard formats
    assert len(formats) > 0
    assert any(f.format_id == "display_300x250" for f in formats)
    assert any(f.format_id == "video_1280x720" for f in formats)


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_list_available_formats_with_tenant(mock_db_session):
    """Test listing formats includes tenant custom formats."""
    # Mock tenant custom format
    mock_db_session.execute.return_value.fetchall.return_value = [
        (
            "custom_format",
            "Custom Format",
            "display",
            "Custom",
            100,
            100,
            None,
            None,
            json.dumps({}),
            False,
            None,
        )
    ]

    formats = list_available_formats(tenant_id="tenant_123")

    # Should include standard + custom
    assert len(formats) > len(FORMAT_REGISTRY)
    assert any(f.format_id == "custom_format" for f in formats)


def test_get_format_with_gam_creative_template_id():
    """Test format with GAM creative_template_id in platform_config."""
    # Create a custom format with creative_template_id
    custom_format = Format(
        format_id="gam_native_template",
        name="GAM Native Template",
        type="native",
        is_standard=False,
        requirements={},
        platform_config={
            "gam": {
                "creative_placeholder": {
                    "width": 1,
                    "height": 1,
                    "creative_template_id": 12345678,
                }
            }
        },
    )

    # Verify platform_config structure
    assert "creative_template_id" in custom_format.platform_config["gam"]["creative_placeholder"]
    assert custom_format.platform_config["gam"]["creative_placeholder"]["creative_template_id"] == 12345678
    assert custom_format.platform_config["gam"]["creative_placeholder"]["width"] == 1
    assert custom_format.platform_config["gam"]["creative_placeholder"]["height"] == 1


@pytest.mark.skip(reason="FORMAT_REGISTRY removed - dynamic discovery via CreativeAgentRegistry")
def test_product_override_merges_platform_config(mock_db_session):
    """Test that product override merges platform_config deeply."""
    # Product override adds GAM config to format that has Kevel config
    impl_config = {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {"creative_placeholder": {"width": 1, "height": 1, "creative_template_id": 99999}}
                }
            }
        }
    }
    mock_db_session.execute.return_value.fetchone.side_effect = [
        (json.dumps(impl_config),),  # Product impl_config
        None,  # No tenant custom format
    ]

    # Assume base format has platform_config for another platform
    with patch("src.core.format_resolver.FORMAT_REGISTRY") as mock_registry:
        mock_registry.get.return_value = Format(
            format_id="display_300x250",
            name="Display",
            type="display",
            requirements={"width": 300, "height": 250},
            platform_config={"kevel": {"some_config": "value"}},
        )

        format_obj = _get_product_format_override("tenant_123", "product_456", "display_300x250")

    # Should have both platform configs
    assert "kevel" in format_obj.platform_config
    assert "gam" in format_obj.platform_config
    assert format_obj.platform_config["gam"]["creative_placeholder"]["creative_template_id"] == 99999
