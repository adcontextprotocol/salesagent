"""Test format_id parsing in sync_creatives and related operations."""

from src.core.main import _normalize_format_value
from src.core.schemas import FormatId


def test_normalize_format_value_with_string():
    """Test _normalize_format_value with legacy string format."""
    result = _normalize_format_value("display_300x250")
    assert result == "display_300x250"


def test_normalize_format_value_with_dict():
    """Test _normalize_format_value with new dict format from wire."""
    result = _normalize_format_value({"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"})
    assert result == "display_300x250"


def test_normalize_format_value_with_format_id_object():
    """Test _normalize_format_value with FormatId object."""
    format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")
    result = _normalize_format_value(format_id)
    assert result == "display_300x250"


def test_normalize_format_value_extracts_id_from_complex_dict():
    """Test that _normalize_format_value extracts 'id' field from dicts."""
    complex_dict = {"agent_url": "https://example.com", "id": "video_640x480", "extra_field": "ignored"}
    result = _normalize_format_value(complex_dict)
    assert result == "video_640x480"
