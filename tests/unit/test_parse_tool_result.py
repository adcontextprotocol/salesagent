"""
Unit tests for parse_tool_result helper function.

Tests that the helper correctly handles both old and new ToolResult formats.
"""

import json
from typing import Any

import pytest

from tests.e2e.adcp_request_builder import parse_tool_result


class MockToolResultNew:
    """Mock new ToolResult format with structured_content field."""

    def __init__(self, structured_content: dict[str, Any]):
        self.structured_content = structured_content


class MockTextContent:
    """Mock text content object."""

    def __init__(self, text: str):
        self.text = text


class MockToolResultOld:
    """Mock old ToolResult format with content[0].text field."""

    def __init__(self, text_content: str):
        self.content = [MockTextContent(text_content)]


class TestParseToolResult:
    """Test parse_tool_result helper function."""

    def test_parse_new_format_with_structured_content(self):
        """Test parsing new ToolResult format (structured_content field)."""
        expected_data = {"products": [{"product_id": "p1", "name": "Test Product"}], "count": 1}

        result = MockToolResultNew(structured_content=expected_data)
        parsed = parse_tool_result(result)

        assert parsed == expected_data
        assert "products" in parsed
        assert len(parsed["products"]) == 1

    def test_parse_old_format_with_json_text(self):
        """Test parsing old ToolResult format (JSON string in content[0].text)."""
        expected_data = {"creatives": [{"creative_id": "c1", "name": "Test Creative"}], "count": 1}

        result = MockToolResultOld(text_content=json.dumps(expected_data))
        parsed = parse_tool_result(result)

        assert parsed == expected_data
        assert "creatives" in parsed
        assert len(parsed["creatives"]) == 1

    def test_parse_new_format_takes_precedence(self):
        """Test that new format (structured_content) takes precedence over old format."""
        new_data = {"method": "new", "value": 100}
        old_data = {"method": "old", "value": 50}

        # Create result with both formats
        result = MockToolResultNew(structured_content=new_data)
        result.content = [MockTextContent(json.dumps(old_data))]

        parsed = parse_tool_result(result)

        # Should use new format (structured_content)
        assert parsed == new_data
        assert parsed["method"] == "new"
        assert parsed["value"] == 100

    def test_parse_empty_structured_content_falls_back_to_text(self):
        """Test fallback to old format when structured_content is None."""
        old_data = {"fallback": True, "message": "Using old format"}

        result = MockToolResultNew(structured_content=None)
        result.content = [MockTextContent(json.dumps(old_data))]

        parsed = parse_tool_result(result)

        # Should fall back to old format
        assert parsed == old_data
        assert parsed["fallback"] is True

    def test_parse_complex_nested_data(self):
        """Test parsing complex nested data structures."""
        complex_data = {
            "media_buy_id": "mb_123",
            "packages": [
                {"package_id": "pkg1", "budget": 5000.0, "targeting": {"countries": ["US", "CA"]}},
                {"package_id": "pkg2", "budget": 3000.0, "targeting": {"countries": ["UK"]}},
            ],
            "status": "active",
            "metadata": {"created_at": "2025-10-27T12:00:00Z"},
        }

        result = MockToolResultNew(structured_content=complex_data)
        parsed = parse_tool_result(result)

        assert parsed == complex_data
        assert len(parsed["packages"]) == 2
        assert parsed["packages"][0]["budget"] == 5000.0

    def test_parse_invalid_result_raises_error(self):
        """Test that invalid result raises ValueError."""

        class InvalidResult:
            """Result with no content or structured_content."""

            pass

        result = InvalidResult()

        with pytest.raises(ValueError, match="Unable to parse tool result"):
            parse_tool_result(result)

    def test_parse_result_with_empty_content_raises_error(self):
        """Test that result with empty content list raises error."""

        class EmptyContentResult:
            content = []

        result = EmptyContentResult()

        with pytest.raises(ValueError, match="Unable to parse tool result"):
            parse_tool_result(result)

    def test_parse_invalid_json_raises_json_decode_error(self):
        """Test that invalid JSON in old format raises JSONDecodeError."""
        result = MockToolResultOld(text_content="not valid json {invalid}")

        with pytest.raises(json.JSONDecodeError):
            parse_tool_result(result)
