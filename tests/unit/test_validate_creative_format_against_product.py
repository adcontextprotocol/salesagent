"""Unit tests for validate_creative_format_against_product helper function.

Uses Product.model_construct() to bypass Pydantic validation and create minimal
test objects without all required fields. This tests the actual code path with
proper types while keeping tests simple.
"""

from src.core.helpers import validate_creative_format_against_product
from src.core.schemas import FormatId, Product


class TestValidateCreativeFormatAgainstProduct:
    """Test creative format validation against a product (binary check)."""

    def test_valid_format_matches_product(self):
        """Test that a valid creative format matches a product."""
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")
        product = Product.model_construct(
            product_id="product_1",
            name="Banner Product",
            format_ids=[FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")],
        )

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_invalid_format_no_match(self):
        """Test that an invalid creative format does not match the product."""
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="video_instream_15s")
        product = Product.model_construct(
            product_id="product_1",
            name="Banner Product",
            format_ids=[FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")],
        )

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
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="any_format")
        product = Product.model_construct(
            product_id="product_1",
            name="Unrestricted Product",
            format_ids=[],  # No format restrictions
        )

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_product_with_multiple_formats(self):
        """Test that creative matches when product supports multiple formats."""
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_728x90_image")
        product = Product.model_construct(
            product_id="product_1",
            name="Multi-Format Product",
            format_ids=[
                FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image"),
                FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_728x90_image"),
                FormatId(agent_url="https://creative.adcontextprotocol.org", id="video_instream_15s"),
            ],
        )

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is True
        assert error is None

    def test_error_message_includes_supported_formats(self):
        """Test that error message includes supported formats."""
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")
        product = Product.model_construct(
            product_id="product_1",
            name="Video Product",
            format_ids=[
                FormatId(agent_url="https://creative.adcontextprotocol.org", id="video_instream_15s"),
                FormatId(agent_url="https://creative.adcontextprotocol.org", id="video_instream_30s"),
            ],
        )

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

    def test_different_agent_urls_do_not_match(self):
        """Test that creatives from different agents do not match."""
        creative_format_id = FormatId(agent_url="https://different-agent.example.com", id="display_300x250_image")
        product = Product.model_construct(
            product_id="product_1",
            name="Banner Product",
            format_ids=[FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")],
        )

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None

    def test_exact_match_required(self):
        """Test that format_id must match exactly (agent_url + id)."""
        creative_format_id = FormatId(agent_url="https://creative.adcontextprotocol.org", id="display_300x250_image")
        product = Product.model_construct(
            product_id="product_1",
            name="Banner Product",
            format_ids=[
                FormatId(
                    agent_url="https://creative.adcontextprotocol.org", id="display_300x600_image"
                )  # Different size
            ],
        )

        is_valid, error = validate_creative_format_against_product(
            creative_format_id=creative_format_id,
            product=product,
        )

        assert is_valid is False
        assert error is not None
