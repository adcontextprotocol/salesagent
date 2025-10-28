"""
Integration tests for ToolResult format verification.

Verifies that MCP tool wrappers correctly return ToolResult objects with
both human-readable text content and structured JSON data.
"""

import pytest

from tests.integration_v2.conftest_v2 import get_fastmcp_client


@pytest.mark.requires_server
@pytest.mark.asyncio
async def test_get_products_returns_tool_result():
    """Verify get_products MCP wrapper returns ToolResult with correct structure."""
    async with get_fastmcp_client() as client:
        result = await client.call_tool(
            "get_products",
            {"brief": "display ads", "brand_manifest": {"name": "Test Brand"}},
        )

        # Verify ToolResult structure
        assert hasattr(result, "content"), "Result must have content attribute"
        assert hasattr(result, "structured_content"), "Result must have structured_content attribute"

        # Verify content is human-readable text
        assert isinstance(result.content, list), "Content should be a list of content blocks"
        assert len(result.content) > 0, "Content should not be empty"
        text_content = result.content[0].text
        assert isinstance(text_content, str), "Text content should be a string"
        assert len(text_content) > 0, "Text content should not be empty"
        # Verify it's human-readable, not JSON
        assert not text_content.startswith("{"), "Text should be human-readable, not JSON"
        assert "product" in text_content.lower(), "Text should mention products"

        # Verify structured_content is JSON data
        assert isinstance(result.structured_content, dict), "Structured content should be a dict"
        assert "products" in result.structured_content, "Structured content should have products field"
        assert isinstance(result.structured_content["products"], list), "Products should be a list"


@pytest.mark.requires_server
@pytest.mark.asyncio
async def test_list_creative_formats_returns_tool_result():
    """Verify list_creative_formats MCP wrapper returns ToolResult with correct structure."""
    async with get_fastmcp_client() as client:
        result = await client.call_tool("list_creative_formats", {})

        # Verify ToolResult structure
        assert hasattr(result, "content"), "Result must have content attribute"
        assert hasattr(result, "structured_content"), "Result must have structured_content attribute"

        # Verify content is human-readable text
        text_content = result.content[0].text
        assert isinstance(text_content, str), "Text content should be a string"
        assert len(text_content) > 0, "Text content should not be empty"
        assert not text_content.startswith("{"), "Text should be human-readable, not JSON"
        assert "format" in text_content.lower(), "Text should mention formats"

        # Verify structured_content is JSON data
        assert isinstance(result.structured_content, dict), "Structured content should be a dict"
        assert "formats" in result.structured_content, "Structured content should have formats field"


@pytest.mark.requires_server
@pytest.mark.asyncio
async def test_list_authorized_properties_returns_tool_result():
    """Verify list_authorized_properties MCP wrapper returns ToolResult with correct structure."""
    async with get_fastmcp_client() as client:
        result = await client.call_tool("list_authorized_properties", {})

        # Verify ToolResult structure
        assert hasattr(result, "content"), "Result must have content attribute"
        assert hasattr(result, "structured_content"), "Result must have structured_content attribute"

        # Verify content is human-readable text
        text_content = result.content[0].text
        assert isinstance(text_content, str), "Text content should be a string"
        assert len(text_content) > 0, "Text content should not be empty"
        assert not text_content.startswith("{"), "Text should be human-readable, not JSON"

        # Verify structured_content is JSON data
        assert isinstance(result.structured_content, dict), "Structured content should be a dict"
        assert "publisher_domains" in result.structured_content, "Should have publisher_domains field"


@pytest.mark.requires_server
@pytest.mark.asyncio
async def test_tool_result_content_differs_from_structured():
    """Verify that text content is different from structured content (not just JSON dump)."""
    async with get_fastmcp_client() as client:
        result = await client.call_tool(
            "get_products",
            {"brief": "video ads", "brand_manifest": {"name": "Test Brand"}},
        )

        text_content = result.content[0].text
        structured_content = result.structured_content

        # Text should be a summary, not the full JSON
        import json

        json_dump = json.dumps(structured_content)
        assert text_content != json_dump, "Text should be a summary, not full JSON dump"
        assert len(text_content) < len(json_dump), "Text should be shorter than full JSON"

        # Text should be human-readable
        assert "product" in text_content.lower(), "Text should describe products"
        # Common patterns: "Found N products" or "No products"
        assert any(
            phrase in text_content.lower() for phrase in ["found", "no products", "products matching"]
        ), "Text should have human-readable summary"
