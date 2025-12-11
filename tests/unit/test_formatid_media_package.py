"""Test FormatId validation in MediaPackage and Format classes.

These tests verify that FormatId objects (per AdCP v2.4 spec) are properly
handled throughout the schema, particularly when converting from Product
to MediaPackage which is where the production error occurred.
"""

from src.core.schemas import Format, FormatId, MediaPackage

# Default agent URL for creating FormatId objects in tests
DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"


def make_format_id(format_id: str, agent_url: str = DEFAULT_AGENT_URL) -> FormatId:
    """Helper to create FormatId objects with default agent URL."""
    return FormatId(agent_url=agent_url, id=format_id)


class TestMediaPackageFormatIds:
    """Tests for MediaPackage.format_ids field accepting FormatId objects."""

    def test_media_package_accepts_format_id_objects(self):
        """MediaPackage must accept FormatId objects per AdCP spec."""
        format_id = make_format_id("display_300x250")

        package = MediaPackage(
            package_id="test_pkg",
            name="Test Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=1000,
            format_ids=[format_id],
        )

        assert len(package.format_ids) == 1
        assert isinstance(package.format_ids[0], FormatId)
        assert package.format_ids[0].id == "display_300x250"
        assert str(package.format_ids[0].agent_url).rstrip("/") == DEFAULT_AGENT_URL.rstrip(
            "/"
        )  # AnyUrl adds trailing slash

    def test_media_package_accepts_multiple_format_ids(self):
        """MediaPackage must accept multiple FormatId objects."""
        format_ids = [
            make_format_id("display_300x250"),
            make_format_id("display_728x90"),
        ]

        package = MediaPackage(
            package_id="test_pkg",
            name="Test Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=1000,
            format_ids=format_ids,
        )

        assert len(package.format_ids) == 2
        assert all(isinstance(fmt, FormatId) for fmt in package.format_ids)
        assert package.format_ids[0].id == "display_300x250"
        assert package.format_ids[1].id == "display_728x90"

    def test_product_formats_to_media_package_conversion(self):
        """Test the production code path: Product.formats[0] → MediaPackage.format_ids.

        This replicates the error that occurred in production at src/core/main.py:4519
        where product.format_ids contained FormatId objects but MediaPackage expected strings.
        """
        # Simulate product.format_ids containing FormatId object (from database/API)
        product_format = make_format_id("leaderboard_728x90")

        # This is what main.py:4519 does - must NOT raise ValidationError
        package = MediaPackage(
            package_id="prod_123",
            name="Product Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=5000,
            format_ids=[product_format] if product_format else [],
        )

        assert len(package.format_ids) == 1
        assert isinstance(package.format_ids[0], FormatId)
        assert package.format_ids[0].id == "leaderboard_728x90"


class TestFormatFormatIdFields:
    """Tests for Format class using FormatId objects per AdCP spec."""

    def test_format_accepts_formatid_for_format_id_field(self):
        """Format.format_id must accept FormatId object per AdCP spec."""
        format_id = make_format_id("display_300x250")

        format_obj = Format(format_id=format_id, name="300x250 Display Banner", type="display")

        assert isinstance(format_obj.format_id, FormatId)
        assert format_obj.format_id.id == "display_300x250"

    def test_format_output_format_ids_accepts_formatid_objects(self):
        """Format.output_format_ids must accept FormatId objects per AdCP spec."""
        output_formats = [
            make_format_id("display_300x250"),
            make_format_id("display_728x90"),
        ]

        # Use 'universal' type for formats that can output multiple types
        # Valid types per AdCP spec: audio, video, display, native, dooh, rich_media, universal
        format_obj = Format(
            format_id=make_format_id("universal_banner"),
            name="Universal Banner Format",
            type="universal",
            output_format_ids=output_formats,
        )

        assert len(format_obj.output_format_ids) == 2
        assert all(isinstance(fmt, FormatId) for fmt in format_obj.output_format_ids)
        assert format_obj.output_format_ids[0].id == "display_300x250"
        assert format_obj.output_format_ids[1].id == "display_728x90"


class TestFormatIdJsonSerialization:
    """Tests for FormatId JSON serialization (for database storage)."""

    def test_format_id_serializes_to_json(self):
        """FormatId.model_dump(mode='json') produces JSON-serializable dict.

        This tests the fix for the error:
        'Object of type FormatId is not JSON serializable'
        when inserting into media_packages.package_config JSONB column.

        Note: mode='json' is required because agent_url is AnyUrl type.
        """
        import json

        format_id = make_format_id("display_300x250")

        # This is what the fix does - serialize FormatId before storing in package_config
        # mode='json' converts AnyUrl to string
        serialized = format_id.model_dump(mode="json")

        # Must be a dict
        assert isinstance(serialized, dict)
        assert "id" in serialized
        assert "agent_url" in serialized
        # agent_url must be a string (not AnyUrl object)
        assert isinstance(serialized["agent_url"], str)

        # Must be JSON serializable (this is what failed before the fix)
        json_str = json.dumps(serialized)
        assert "display_300x250" in json_str

    def test_format_ids_list_serializes_to_json(self):
        """List of FormatIds must serialize for JSONB storage.

        Reproduces the exact error scenario: storing format_ids in package_config.
        """
        import json

        format_ids = [
            make_format_id("display_300x250"),
            make_format_id("video_preroll"),
        ]

        # This is what media_buy_create.py does now
        # mode='json' is required to convert AnyUrl to string
        format_ids_serialized = [
            fmt.model_dump(mode="json") if hasattr(fmt, "model_dump") else fmt for fmt in format_ids
        ]

        # Build package_config as in the real code
        package_config = {
            "package_id": "test_pkg",
            "product_id": "prod_1",
            "format_ids": format_ids_serialized,
        }

        # Must be JSON serializable (this would fail before the fix)
        json_str = json.dumps(package_config)
        assert "display_300x250" in json_str
        assert "video_preroll" in json_str
