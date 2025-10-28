"""
Unit tests for parse_tool_result helper function.

Tests that the helper correctly extracts structured data from ToolResult.
"""

from typing import Any

import pytest

from tests.e2e.adcp_request_builder import parse_tool_result


class MockToolResult:
    """Mock ToolResult format with structured_content field."""

    def __init__(self, structured_content: dict[str, Any] | None):
        self.structured_content = structured_content


class TestParseToolResult:
    """Test parse_tool_result helper function."""

    def test_parse_with_structured_content(self):
        """Test parsing ToolResult with structured_content field."""
        expected_data = {"products": [{"product_id": "p1", "name": "Test Product"}], "count": 1}

        result = MockToolResult(structured_content=expected_data)
        parsed = parse_tool_result(result)

        assert parsed == expected_data
        assert "products" in parsed
        assert len(parsed["products"]) == 1

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

        result = MockToolResult(structured_content=complex_data)
        parsed = parse_tool_result(result)

        assert parsed == complex_data
        assert len(parsed["packages"]) == 2
        assert parsed["packages"][0]["budget"] == 5000.0

    def test_parse_invalid_result_raises_error(self):
        """Test that result without structured_content raises ValueError."""

        class InvalidResult:
            """Result with no structured_content."""

            pass

        result = InvalidResult()

        with pytest.raises(ValueError, match="has no structured_content field"):
            parse_tool_result(result)

    def test_parse_none_structured_content_raises_error(self):
        """Test that result with None structured_content raises error."""
        result = MockToolResult(structured_content=None)

        with pytest.raises(ValueError, match="has no structured_content field"):
            parse_tool_result(result)
