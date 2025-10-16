"""Test that product format updates are properly saved to database.

This tests the bug fix for JSONB columns not being flagged as modified.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import attributes

from src.core.database.models import Product


@pytest.fixture
def sample_product(integration_db):
    """Create a sample product for testing."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import Tenant

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Tenant",
            subdomain="test",
        )
        session.add(tenant)
        session.flush()

        # Create product with initial formats
        product = Product(
            tenant_id="test_tenant",
            product_id="test_product",
            name="Test Product",
            description="Test Description",
            formats=[
                {"agent_url": "http://localhost:8888", "id": "old_format_1"},
                {"agent_url": "http://localhost:8888", "id": "old_format_2"},
            ],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)
        session.commit()

        return product.product_id


@pytest.mark.requires_db
def test_product_formats_update_with_flag_modified(integration_db, sample_product):
    """Test that updating product.formats with flag_modified saves changes."""
    from src.core.database.database_session import get_db_session

    # Update the product's formats
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None

        # Update formats
        product.formats = [
            {"agent_url": "http://localhost:8888", "id": "new_format_1"},
            {"agent_url": "http://localhost:8888", "id": "new_format_2"},
            {"agent_url": "http://localhost:8888", "id": "new_format_3"},
        ]

        # Flag as modified (this is the fix)
        attributes.flag_modified(product, "formats")

        session.commit()

    # Verify the changes were saved
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None
        assert len(product.formats) == 3
        assert product.formats[0]["id"] == "new_format_1"
        assert product.formats[1]["id"] == "new_format_2"
        assert product.formats[2]["id"] == "new_format_3"


@pytest.mark.requires_db
def test_product_formats_update_without_flag_modified_fails(integration_db, sample_product):
    """Test that updating product.formats WITHOUT flag_modified does NOT save changes.

    This demonstrates the bug that was fixed.
    """
    from src.core.database.database_session import get_db_session

    # Update the product's formats WITHOUT flag_modified
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None

        # Update formats
        product.formats = [
            {"agent_url": "http://localhost:8888", "id": "should_not_save_1"},
            {"agent_url": "http://localhost:8888", "id": "should_not_save_2"},
        ]

        # NOTE: NOT calling flag_modified - this is the bug
        # attributes.flag_modified(product, "formats")

        session.commit()

    # Verify the changes were NOT saved (demonstrates the bug)
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None
        # Changes were not saved - still has old formats
        assert len(product.formats) == 2
        assert product.formats[0]["id"] == "old_format_1"
        assert product.formats[1]["id"] == "old_format_2"


@pytest.mark.requires_db
def test_product_countries_update_with_flag_modified(integration_db, sample_product):
    """Test that updating product.countries with flag_modified saves changes."""
    from src.core.database.database_session import get_db_session

    # Update the product's countries
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None

        # Update countries
        product.countries = ["US", "CA", "GB"]

        # Flag as modified (this is the fix)
        attributes.flag_modified(product, "countries")

        session.commit()

    # Verify the changes were saved
    with get_db_session() as session:
        stmt = select(Product).filter_by(product_id=sample_product)
        product = session.scalars(stmt).first()
        assert product is not None
        assert product.countries == ["US", "CA", "GB"]
