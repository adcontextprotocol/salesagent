"""Test that anonymous users get products with empty pricing_options."""

from src.core.schemas import PricingOption, Product


def test_product_with_empty_pricing_options():
    """Test that Product can be created with empty pricing_options (anonymous user case)."""
    product = Product(
        product_id="test-1",
        name="Test Product",
        description="Test",
        format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_banner_728x90"}],
        delivery_type="guaranteed",
        pricing_options=[],
        property_tags=["all_inventory"],
    )

    # Verify the product serializes correctly without pricing_options field
    dump = product.model_dump()
    assert "pricing_options" not in dump, "Empty pricing_options should be excluded from serialization"
    assert "product_id" in dump
    assert "name" in dump
    assert "description" in dump


def test_product_with_pricing_options():
    """Test that Product includes pricing_options when populated (authenticated user case)."""
    product = Product(
        product_id="test-2",
        name="Test Product",
        description="Test",
        format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_banner_728x90"}],
        delivery_type="guaranteed",
        pricing_options=[
            PricingOption(
                pricing_option_id="po-1",
                pricing_model="cpm",
                currency="USD",
                is_fixed=True,
                rate=10.0,
            )
        ],
        property_tags=["all_inventory"],
    )

    # Verify the product serializes with pricing_options
    dump = product.model_dump()
    assert "pricing_options" in dump, "Non-empty pricing_options should be included in serialization"
    assert len(dump["pricing_options"]) == 1
    assert dump["pricing_options"][0]["pricing_model"] == "cpm"


def test_product_pricing_options_defaults_to_empty_list():
    """Test that pricing_options defaults to empty list if not provided."""
    product = Product(
        product_id="test-3",
        name="Test Product",
        description="Test",
        format_ids=[{"agent_url": "https://creative.adcontextprotocol.org", "id": "display_banner_728x90"}],
        delivery_type="guaranteed",
        property_tags=["all_inventory"],
        # pricing_options not provided - should default to []
    )

    # Verify pricing_options defaults to empty list
    assert product.pricing_options == []

    # Verify empty list is excluded from serialization
    dump = product.model_dump()
    assert "pricing_options" not in dump
