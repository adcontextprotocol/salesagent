"""Test FormatId validation in MediaPackage and Format classes.

These tests verify that FormatId objects (per AdCP v2.4 spec) are properly
handled throughout the schema, particularly when converting from Product
to MediaPackage which is where the production error occurred.
"""

from src.core.schemas import Format, FormatId, MediaPackage


class TestMediaPackageFormatIds:
    """Tests for MediaPackage.format_ids field accepting FormatId objects."""

    def test_media_package_accepts_format_id_objects(self):
        """MediaPackage should accept FormatId objects per AdCP spec."""
        format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")

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
        assert package.format_ids[0].agent_url == "https://creative.adcontextprotocol.org"

    def test_media_package_accepts_strings_for_backward_compatibility(self):
        """MediaPackage should still accept strings for legacy compatibility."""
        package = MediaPackage(
            package_id="test_pkg",
            name="Test Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=1000,
            format_ids=["display_300x250", "display_728x90"],
        )

        assert len(package.format_ids) == 2
        assert all(isinstance(fmt, str) for fmt in package.format_ids)

    def test_media_package_accepts_mixed_formatid_and_strings(self):
        """MediaPackage should accept mix of FormatId objects and strings."""
        format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")

        package = MediaPackage(
            package_id="test_pkg",
            name="Test Package",
            delivery_type="guaranteed",
            cpm=10.0,
            impressions=1000,
            format_ids=[format_id, "display_728x90"],  # Mixed types
        )

        assert len(package.format_ids) == 2
        assert isinstance(package.format_ids[0], FormatId)
        assert isinstance(package.format_ids[1], str)

    def test_product_formats_to_media_package_conversion(self):
        """Test the production code path: Product.formats[0] → MediaPackage.format_ids.

        This replicates the error that occurred in production at src/core/main.py:4519
        where product.formats contained FormatId objects but MediaPackage expected strings.
        """
        # Simulate product.formats containing FormatId object (from database/API)
        product_format = FormatId(agent_url="https://creative.adcontextprotocol.org", id="leaderboard_728x90")

        # This is what main.py:4519 does - should NOT raise ValidationError
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
        """Format.format_id should accept FormatId object per AdCP spec."""
        format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250")

        format_obj = Format(format_id=format_id, name="300x250 Display Banner", type="display")

        assert isinstance(format_obj.format_id, FormatId)

    def test_format_accepts_string_for_format_id_field(self):
        """Format.format_id should accept string for backward compatibility."""
        format_obj = Format(format_id="display_300x250", name="300x250 Display Banner", type="display")

        assert isinstance(format_obj.format_id, str)

    def test_format_output_format_ids_accepts_formatid_objects(self):
        """Format.output_format_ids should accept FormatId objects per AdCP spec."""
        output_formats = [
            FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250"),
            FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_728x90"),
        ]

        format_obj = Format(
            format_id="generative_banner",
            name="Generative Banner Format",
            type="generative",
            output_format_ids=output_formats,
        )

        assert len(format_obj.output_format_ids) == 2
        assert all(isinstance(fmt, FormatId) for fmt in format_obj.output_format_ids)

    def test_format_output_format_ids_accepts_strings(self):
        """Format.output_format_ids should accept strings for backward compatibility."""
        format_obj = Format(
            format_id="generative_banner",
            name="Generative Banner Format",
            type="generative",
            output_format_ids=["display_300x250", "display_728x90"],
        )

        assert len(format_obj.output_format_ids) == 2
        assert all(isinstance(fmt, str) for fmt in format_obj.output_format_ids)
