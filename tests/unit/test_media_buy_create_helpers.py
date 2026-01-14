"""Unit tests for media_buy_create helper functions.

Tests the helper functions used in media buy creation, particularly
format specification retrieval, creative validation, status determination,
and URL extraction.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from src.core.tools.media_buy_create import _get_format_spec_sync


class TestGetFormatSpecSync:
    """Test synchronous format specification retrieval."""

    def test_successful_format_retrieval(self):
        """Test successful format spec retrieval with mocked registry.

        Note: We mock the registry to avoid real HTTP calls. The actual creative
        agent at creative.adcontextprotocol.org returns formats with an 'assets'
        field that causes validation failures in the current adcp library version.
        """
        # Create mock format matching expected schema
        mock_format = SimpleNamespace(
            format_id=SimpleNamespace(id="display_300x250_image", agent_url="https://creative.adcontextprotocol.org"),
            name="Medium Rectangle - Image",
        )

        # Create mock registry
        mock_registry = Mock()
        mock_registry.get_format = AsyncMock(return_value=mock_format)

        with patch("src.core.creative_agent_registry.get_creative_agent_registry", return_value=mock_registry):
            format_spec = _get_format_spec_sync("https://creative.adcontextprotocol.org", "display_300x250_image")
            assert format_spec is not None
            assert format_spec.format_id.id == "display_300x250_image"
            assert format_spec.name == "Medium Rectangle - Image"

    def test_unknown_format_returns_none(self):
        """Test that unknown format returns None."""
        # Create mock registry that returns None for unknown formats
        mock_registry = Mock()
        mock_registry.get_format = AsyncMock(return_value=None)

        with patch("src.core.creative_agent_registry.get_creative_agent_registry", return_value=mock_registry):
            format_spec = _get_format_spec_sync("https://creative.adcontextprotocol.org", "unknown_format_xyz")
            assert format_spec is None
