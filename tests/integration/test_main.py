import pytest
from sqlalchemy import select

from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ProductModel


@pytest.mark.requires_db
def test_product_catalog_schema_conformance(integration_db, sample_tenant, sample_products):
    """
    Test that products can be queried from the database and have required fields.

    Uses real PostgreSQL database with migrations applied via integration_db fixture.
    """
    # Fixtures provide test tenant and products
    tenant_id = sample_tenant["tenant_id"]

    with get_db_session() as db_session:
        # Query products for the test tenant
        products = db_session.scalars(select(ProductModel).filter_by(tenant_id=tenant_id)).all()

        # Convert to list of dicts for assertions
        rows = []
        for product in products:
            rows.append(
                {
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "formats": product.formats,
                    "delivery_type": product.delivery_type,
                }
            )

    # 1. Primary Assertion: The catalog must not be empty
    assert len(rows) > 0, "Product catalog should not be empty"

    # 2. Secondary Assertion: Check that products have required fields
    for product_data in rows:
        # Verify required fields exist
        assert "product_id" in product_data
        assert "name" in product_data
        assert "description" in product_data
        assert "formats" in product_data
        assert "delivery_type" in product_data

        # Verify field types
        assert isinstance(product_data["product_id"], str)
        assert isinstance(product_data["name"], str)
        assert isinstance(product_data["formats"], list)
        assert product_data["delivery_type"] in ["guaranteed", "non_guaranteed"]
