"""Test FormatId and Creative format_id field."""

from datetime import datetime

import pytest

from src.core.schemas import Creative, FormatId


def test_format_id_object_structure():
    """Test that FormatId accepts AdCP v2.4 structure."""
    format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")
    assert format_id.agent_url == "https://creative.adcontextprotocol.org"
    assert format_id.id == "display_300x250"


def test_format_id_validation():
    """Test FormatId validation."""
    # Valid format
    FormatId(agent_url="https://example.com", id="valid_format-123")

    # Invalid id pattern
    with pytest.raises(ValueError):
        FormatId(agent_url="https://example.com", id="invalid format!")


def test_creative_accepts_string_format():
    """Test Creative accepts legacy string format_id."""
    creative = Creative(
        creative_id="c1",
        name="Test Creative",
        format_id="display_300x250",  # Legacy string (using alias)
        content_uri="https://example.com/creative.jpg",  # Using alias
        principal_id="p1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    assert creative.format == "display_300x250"
    assert creative.get_format_string() == "display_300x250"
    assert creative.get_format_agent_url() is None


def test_creative_accepts_format_id_object():
    """Test Creative accepts new FormatId object format."""
    format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")
    creative = Creative(
        creative_id="c1",
        name="Test Creative",
        format_id=format_id,  # Using alias
        content_uri="https://example.com/creative.jpg",  # Using alias
        principal_id="p1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    assert isinstance(creative.format, FormatId)
    assert creative.get_format_string() == "display_300x250"
    assert creative.get_format_agent_url() == "https://creative.adcontextprotocol.org"


def test_creative_from_dict_with_format_id_object():
    """Test Creative can be created from dict with format_id as object."""
    data = {
        "creative_id": "c1",
        "name": "Test Creative",
        "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
        "content_uri": "https://example.com/creative.jpg",
        "principal_id": "p1",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    creative = Creative(**data)
    assert creative.get_format_string() == "display_300x250"
    assert creative.get_format_agent_url() == "https://creative.adcontextprotocol.org"


def test_normalize_format_value():
    """Test _normalize_format_value helper function."""
    from src.core.main import _normalize_format_value

    # String format
    assert _normalize_format_value("display_300x250") == "display_300x250"

    # Dict format
    assert _normalize_format_value({"agent_url": "https://example.com", "id": "display_300x250"}) == "display_300x250"

    # FormatId object
    format_id = FormatId(agent_url="https://example.com", id="display_300x250")
    assert _normalize_format_value(format_id) == "display_300x250"
