"""Unit tests for new list_creative_formats filter parameters.

Tests the is_responsive, name_search, asset_types, and dimension filters
that were added to match the AdCP spec.
"""

from adcp.types import FormatCategory

from src.core.schemas import FormatId, ListCreativeFormatsRequest

DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"


def make_format_id(format_id: str) -> FormatId:
    """Helper to create FormatId objects."""
    return FormatId(agent_url=DEFAULT_AGENT_URL, id=format_id)


class TestListCreativeFormatsNewFilters:
    """Test new filter parameters on ListCreativeFormatsRequest."""

    def test_is_responsive_filter_accepts_bool(self):
        """Test that is_responsive filter accepts boolean values."""
        req = ListCreativeFormatsRequest(is_responsive=True)
        assert req.is_responsive is True

        req = ListCreativeFormatsRequest(is_responsive=False)
        assert req.is_responsive is False

    def test_name_search_filter_accepts_string(self):
        """Test that name_search filter accepts string values."""
        req = ListCreativeFormatsRequest(name_search="banner")
        assert req.name_search == "banner"

    def test_asset_types_filter_accepts_list(self):
        """Test that asset_types filter accepts list of strings."""
        req = ListCreativeFormatsRequest(asset_types=["image", "video"])
        assert req.asset_types is not None
        # The library will convert strings to enum values
        assert len(req.asset_types) == 2

    def test_dimension_filters_accept_integers(self):
        """Test that dimension filters accept integer values."""
        req = ListCreativeFormatsRequest(
            min_width=300,
            max_width=728,
            min_height=250,
            max_height=600,
        )
        assert req.min_width == 300
        assert req.max_width == 728
        assert req.min_height == 250
        assert req.max_height == 600

    def test_all_new_filters_combined(self):
        """Test that all new filters can be used together."""
        req = ListCreativeFormatsRequest(
            type="display",
            is_responsive=False,
            name_search="leaderboard",
            asset_types=["image"],
            min_width=300,
            max_width=1000,
            min_height=50,
            max_height=300,
        )
        # Pydantic coerces string "display" to FormatCategory.display enum
        assert req.type == FormatCategory.display
        assert req.is_responsive is False
        assert req.name_search == "leaderboard"
        assert req.asset_types is not None
        assert req.min_width == 300
        assert req.max_width == 1000
        assert req.min_height == 50
        assert req.max_height == 300

    def test_model_dump_includes_new_filters(self):
        """Test that model_dump includes the new filter fields."""
        req = ListCreativeFormatsRequest(
            is_responsive=True,
            name_search="video",
            min_width=640,
        )
        dump = req.model_dump(exclude_none=True)

        assert "is_responsive" in dump
        assert dump["is_responsive"] is True
        assert "name_search" in dump
        assert dump["name_search"] == "video"
        assert "min_width" in dump
        assert dump["min_width"] == 640

    def test_new_filters_inherited_from_library(self):
        """Verify that new filters come from adcp library (not hand-coded)."""
        from adcp import ListCreativeFormatsRequest as LibraryRequest

        # Verify the library has these fields
        lib_fields = LibraryRequest.model_fields
        assert "is_responsive" in lib_fields
        assert "name_search" in lib_fields
        assert "asset_types" in lib_fields
        assert "min_width" in lib_fields
        assert "max_width" in lib_fields
        assert "min_height" in lib_fields
        assert "max_height" in lib_fields

    def test_request_with_only_new_filters(self):
        """Test creating a request with only the new filters."""
        req = ListCreativeFormatsRequest(
            is_responsive=True,
            name_search="banner",
        )
        # Old filters should be None
        assert req.type is None
        assert req.format_ids is None
        # New filters should be set
        assert req.is_responsive is True
        assert req.name_search == "banner"


class TestListCreativeFormatsMCPToolSignature:
    """Test that MCP tool accepts AdCP-compliant parameter types.

    MCP tools receive JSON primitives, not Pydantic objects. These tests verify
    that the tool function signature accepts the types that clients actually send.
    """

    def test_mcp_tool_accepts_format_ids_as_dicts(self):
        """Test that list_creative_formats MCP tool accepts format_ids as FormatId dicts.

        This is a regression test for a prod error where the MCP tool rejected
        FormatId objects sent as dicts:

            Error: 2 validation errors for call[list_creative_formats]
            format_ids.0
              Input should be a valid string [type=string_type,
              input_value={'agent_url': '...', 'id': '...'}, input_type=dict]

        Per AdCP spec, format_ids should be list[FormatId] (objects with agent_url and id).
        """
        from unittest.mock import MagicMock, patch

        from src.core.tools.creative_formats import list_creative_formats

        # This is how clients send format_ids - as FormatId dicts
        format_ids_as_dicts = [
            {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_15s_hosted"},
            {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250"},
        ]

        # Mock the implementation to avoid needing full context
        with patch("src.core.tools.creative_formats._list_creative_formats_impl") as mock_impl:
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"formats": []}
            mock_impl.return_value = mock_response

            # This should NOT raise a validation error
            result = list_creative_formats(format_ids=format_ids_as_dicts)

            # Verify the impl was called with FormatId objects
            call_args = mock_impl.call_args
            req = call_args[0][0]  # First positional arg is the request
            assert req.format_ids is not None
            assert len(req.format_ids) == 2
            # Verify FormatId objects were created from dicts
            assert req.format_ids[0].id == "video_15s_hosted"
            assert req.format_ids[1].id == "display_300x250"

    def test_mcp_tool_format_ids_parameter_type_is_list_dict(self):
        """Verify the MCP tool signature accepts list[dict] for format_ids.

        This ensures we don't accidentally change the signature back to list[str].
        """
        import inspect

        from src.core.tools.creative_formats import list_creative_formats

        sig = inspect.signature(list_creative_formats)
        format_ids_param = sig.parameters["format_ids"]

        # The annotation should be list[dict] | None, not list[str] | None
        annotation_str = str(format_ids_param.annotation)
        assert "dict" in annotation_str, f"Expected list[dict], got {annotation_str}"
        assert (
            "str" not in annotation_str or "str]" not in annotation_str
        ), f"Should NOT be list[str], got {annotation_str}"
