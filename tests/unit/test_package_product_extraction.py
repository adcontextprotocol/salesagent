"""Test Package product extraction handles both product_id and products fields.

This tests the fix for the bug where packages using product_id (singular) were
silently ignored, causing "At least one product is required" validation errors.
"""

from src.core.schemas import CreateMediaBuyRequest, Package


class TestPackageProductExtraction:
    """Test get_product_ids() supports both product_id and products per AdCP spec."""

    def test_get_product_ids_with_products_array(self):
        """Test extraction from products (plural) field."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test1",
            po_number="PO-001",
            packages=[Package(buyer_ref="pkg1", products=["prod1", "prod2"])],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1", "prod2"]
        assert len(product_ids) == 2

    def test_get_product_ids_with_single_product_id(self):
        """Test extraction from product_id (singular) field."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test2",
            po_number="PO-002",
            packages=[Package(buyer_ref="pkg2", product_id="prod1")],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1"]
        assert len(product_ids) == 1

    def test_get_product_ids_with_mixed_packages(self):
        """Test extraction from mix of products and product_id."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test3",
            po_number="PO-003",
            packages=[
                Package(buyer_ref="pkg1", products=["prod1", "prod2"]),
                Package(buyer_ref="pkg2", product_id="prod3"),
                Package(buyer_ref="pkg3", products=["prod4"]),
            ],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1", "prod2", "prod3", "prod4"]
        assert len(product_ids) == 4

    def test_get_product_ids_with_empty_package(self):
        """Test extraction from package with neither field set."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test4",
            po_number="PO-004",
            packages=[Package(buyer_ref="pkg1")],
        )

        product_ids = req.get_product_ids()
        assert product_ids == []

    def test_get_product_ids_prioritizes_products_over_product_id(self):
        """Test that products (array) takes precedence when both are set."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test5",
            po_number="PO-005",
            packages=[
                Package(
                    buyer_ref="pkg1",
                    products=["prod1", "prod2"],
                    product_id="prod_ignored",  # Should be ignored when products is set
                )
            ],
        )

        product_ids = req.get_product_ids()
        # Should only get products array, not product_id
        assert product_ids == ["prod1", "prod2"]
        assert "prod_ignored" not in product_ids

    def test_get_product_ids_fallback_to_legacy_product_ids(self):
        """Test fallback to legacy product_ids field when no packages."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test6",
            po_number="PO-006",
            product_ids=["legacy1", "legacy2"],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["legacy1", "legacy2"]

    def test_get_product_ids_packages_override_legacy(self):
        """Test that packages take precedence over legacy product_ids."""
        req = CreateMediaBuyRequest(
            promoted_offering="Test",
            buyer_ref="test7",
            po_number="PO-007",
            packages=[Package(buyer_ref="pkg1", products=["prod1"])],
            product_ids=["legacy1", "legacy2"],  # Should be ignored
        )

        product_ids = req.get_product_ids()
        # Should get from packages, not legacy product_ids
        assert product_ids == ["prod1"]
        assert "legacy1" not in product_ids
        assert "legacy2" not in product_ids
