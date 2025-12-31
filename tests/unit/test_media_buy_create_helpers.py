"""Unit tests for media_buy_create helper functions.

Tests the helper functions used in media buy creation, particularly
format specification retrieval, creative validation, status determination,
and URL extraction.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastmcp.exceptions import ToolError

from src.core.database.models import Creative as DBCreative
from src.core.schemas import PackageRequest
from src.core.tools.media_buy_create import (
    _get_format_spec_sync
)

class TestGetFormatSpecSync:
    """Test synchronous format specification retrieval."""

    def test_successful_format_retrieval(self):
        """Test successful format spec retrieval."""
        format_spec = _get_format_spec_sync(
            "https://creative.adcontextprotocol.org", "display_300x250_image"
        )
        assert format_spec is not None
        assert format_spec.format_id.id == "display_300x250_image"
        assert format_spec.name == "Medium Rectangle - Image"

        # Test unknown format returns None
        format_spec = _get_format_spec_sync(
            "https://creative.adcontextprotocol.org", "unknown_format_xyz"
        )
        assert format_spec is None