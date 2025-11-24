"""Unit tests for validate_creative_format_against_product helper function."""

from src.core.helpers import validate_creative_format_against_product


class TestValidateCreativeFormatAgainstProduct:
    """Test creative format validation against a product (binary check)."""

    def test_valid_format_matches_product(self):
        """Test that a valid creative format matches a product."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}
        product = {
            "product_id": "product_1",
            "name": "Banner Product",
            "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_invalid_format_no_match(self):
        """Test that an invalid creative format does not match the product."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_15s"}
        product = {
            "product_id": "product_1",
            "name": "Banner Product",
            "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None
        assert "does not match product" in error
        assert "video_instream_15s" in error
        assert "Banner Product" in error

    def test_product_with_no_format_restrictions_matches_all(self):
        """Test that products with no format_ids accept all creative formats."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "any_format"}
        product = {
            "product_id": "product_1",
            "name": "Unrestricted Product",
            "format_ids": [],  # No format restrictions
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_product_with_multiple_formats(self):
        """Test that creative matches when product supports multiple formats."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"}
        product = {
            "product_id": "product_1",
            "name": "Multi-Format Product",
            "format_ids": [
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"},
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_15s"},
            ],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_error_message_includes_supported_formats(self):
        """Test that error message includes supported formats."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}
        product = {
            "product_id": "product_1",
            "name": "Video Product",
            "format_ids": [
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_15s"},
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_30s"},
            ],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None
        assert "display_300x250_image" in error
        assert "video_instream_15s" in error
        assert "video_instream_30s" in error
        assert "Video Product" in error

    def test_works_with_pydantic_objects(self):
        """Test that validation works with Pydantic Product objects."""
        from unittest.mock import Mock

        # Mock Creative format_id object
        creative_format_id = Mock()
        creative_format_id.agent_url = "https://creative.adcontextprotocol.org"
        creative_format_id.id = "display_300x250_image"

        # Mock Product object
        product = Mock()
        product.product_id = "product_1"
        product.name = "Banner Product"

        # Mock format_ids with Pydantic-like objects
        format_obj = Mock()
        format_obj.agent_url = "https://creative.adcontextprotocol.org"
        format_obj.id = "display_300x250_image"
        product.format_ids = [format_obj]

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_different_agent_urls_do_not_match(self):
        """Test that creatives from different agents do not match."""
        creative_format_id = {"agent_url": "https://different-agent.example.com", "id": "display_300x250_image"}
        product = {
            "product_id": "product_1",
            "name": "Banner Product",
            "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None

    def test_missing_format_id_fields(self):
        """Test that missing format_id fields return error."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org"}  # Missing 'id'
        product = {
            "product_id": "product_1",
            "name": "Banner Product",
            "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None
        assert "missing agent_url or id" in error

    def test_exact_match_required(self):
        """Test that format_id must match exactly (agent_url + id)."""
        creative_format_id = {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}
        product = {
            "product_id": "product_1",
            "name": "Banner Product",
            "format_ids": [
                {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x600_image"}  # Different size
            ],
        }

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None
