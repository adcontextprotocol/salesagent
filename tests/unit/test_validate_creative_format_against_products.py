"""Unit tests for validate_creative_format_against_products helper function."""

from src.core.helpers import validate_creative_format_against_products


class TestValidateCreativeFormatAgainstProducts:
    """Test creative format validation against product formats."""

    def test_valid_format_matches_product(self):
        """Test that a valid creative format matches a product."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="display_300x250_image",
            products=products,
        )

        assert is_valid is True
        assert matching_products == ["product_1"]
        assert error is None

    def test_invalid_format_no_match(self):
        """Test that an invalid creative format does not match any product."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="video_instream_15s",  # Different format
            products=products,
        )

        assert is_valid is False
        assert matching_products == []
        assert error is not None
        assert "not supported by any product" in error
        assert "video_instream_15s" in error

    def test_format_matches_multiple_products(self):
        """Test that a creative format can match multiple products."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product 1",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
            },
            {
                "product_id": "product_2",
                "name": "Banner Product 2",
                "format_ids": [
                    {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"},
                    {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
                ],
            },
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="display_300x250_image",
            products=products,
        )

        assert is_valid is True
        assert set(matching_products) == {"product_1", "product_2"}
        assert error is None

    def test_product_with_no_format_restrictions_matches_all(self):
        """Test that products with no format_ids accept all creative formats."""
        products = [
            {
                "product_id": "product_1",
                "name": "Unrestricted Product",
                "format_ids": [],  # No format restrictions
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="any_format",
            products=products,
        )

        assert is_valid is True
        assert matching_products == ["product_1"]
        assert error is None

    def test_url_normalization_with_trailing_slash(self):
        """Test that URL normalization handles trailing slashes."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [
                    {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_image"}
                ],  # Trailing slash
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",  # No trailing slash
            creative_format_id="display_300x250_image",
            products=products,
            normalize_url=True,
        )

        assert is_valid is True
        assert matching_products == ["product_1"]
        assert error is None

    def test_url_normalization_with_mcp_suffix(self):
        """Test that URL normalization handles /mcp suffix."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org/mcp",  # /mcp suffix
            creative_format_id="display_300x250_image",
            products=products,
            normalize_url=True,
        )

        assert is_valid is True
        assert matching_products == ["product_1"]
        assert error is None

    def test_no_normalization_requires_exact_match(self):
        """Test that without normalization, URLs must match exactly."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_image"}],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",  # No trailing slash
            creative_format_id="display_300x250_image",
            products=products,
            normalize_url=False,  # Disable normalization
        )

        # Should not match because URLs differ
        assert is_valid is False
        assert matching_products == []
        assert error is not None

    def test_error_message_includes_supported_formats(self):
        """Test that error message includes supported formats."""
        products = [
            {
                "product_id": "product_1",
                "name": "Video Product",
                "format_ids": [
                    {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_15s"},
                    {"agent_url": "https://creative.adcontextprotocol.org", "id": "video_instream_30s"},
                ],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="display_300x250_image",  # Wrong format
            products=products,
        )

        assert is_valid is False
        assert error is not None
        assert "display_300x250_image" in error
        assert "video_instream_15s" in error
        assert "Video Product" in error

    def test_works_with_pydantic_objects(self):
        """Test that validation works with Pydantic Product objects."""
        from unittest.mock import Mock

        # Mock Product object
        product = Mock()
        product.product_id = "product_1"
        product.name = "Banner Product"
        product.format_ids = [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="display_300x250_image",
            products=[product],
        )

        assert is_valid is True
        assert matching_products == ["product_1"]
        assert error is None

    def test_empty_products_list_fails(self):
        """Test that validation fails with empty products list."""
        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://creative.adcontextprotocol.org",
            creative_format_id="display_300x250_image",
            products=[],
        )

        assert is_valid is False
        assert matching_products == []
        assert error is not None
        assert "not supported by any product" in error

    def test_different_agent_urls_do_not_match(self):
        """Test that creatives from different agents do not match."""
        products = [
            {
                "product_id": "product_1",
                "name": "Banner Product",
                "format_ids": [{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"}],
            }
        ]

        is_valid, matching_products, error = validate_creative_format_against_products(
            creative_agent_url="https://different-agent.example.com",  # Different agent
            creative_format_id="display_300x250_image",
            products=products,
        )

        assert is_valid is False
        assert matching_products == []
        assert error is not None
