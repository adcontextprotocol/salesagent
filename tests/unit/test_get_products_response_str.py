"""Test that GetProductsResponse __str__ provides human-readable content for MCP."""

from src.core.schemas import GetProductsResponse, Product


def test_get_products_response_str_with_message():
    """Test that __str__ returns the message field when present."""
    product = Product(
        product_id="test",
        name="Test Product",
        description="A test",
        formats=["banner"],
        delivery_type="guaranteed",
        is_fixed_price=True,
        is_custom=False,
        currency="USD",
        property_tags=["all_inventory"],  # Required per AdCP spec
    )

    response = GetProductsResponse(
        products=[product], message="Found 1 product matching your brief for running shoes on sports sites"
    )

    content = str(response)

    # Should return human-readable message, not JSON
    assert content == "Found 1 product matching your brief for running shoes on sports sites"
    assert "{" not in content  # Should not contain JSON
    assert "product_id" not in content  # Should not contain field names


def test_get_products_response_str_without_message():
    """Test that __str__ generates appropriate message when none provided."""
    products = [
        Product(
            product_id=f"test{i}",
            name=f"Test {i}",
            description="A test",
            formats=["banner"],
            delivery_type="guaranteed",
            is_fixed_price=True,
            is_custom=False,
            currency="USD",
            property_tags=["all_inventory"],  # Required per AdCP spec
        )
        for i in range(3)
    ]

    response = GetProductsResponse(products=products)
    content = str(response)

    assert content == "Found 3 products that match your requirements."
    assert "{" not in content


def test_get_products_response_str_empty():
    """Test that __str__ handles empty product list."""
    response = GetProductsResponse(products=[])
    content = str(response)

    assert content == "No products matched your requirements."


def test_get_products_response_model_dump_still_has_full_data():
    """Verify that model_dump() still returns full structured data."""
    product = Product(
        product_id="test",
        name="Test Product",
        description="A test",
        formats=["banner"],
        delivery_type="guaranteed",
        is_fixed_price=True,
        is_custom=False,
        currency="USD",
        property_tags=["all_inventory"],  # Required per AdCP spec
    )

    response = GetProductsResponse(products=[product], message="Found 1 product")

    # str() should be human-readable
    assert str(response) == "Found 1 product"

    # model_dump() should have full structure
    data = response.model_dump()
    assert "products" in data
    assert len(data["products"]) == 1
    assert data["products"][0]["product_id"] == "test"
    assert data["message"] == "Found 1 product"
