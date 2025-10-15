"""Test Package product extraction using product_id field per AdCP spec.

Per AdCP specification, packages use product_id (singular) field, not products (plural).
This test verifies that get_product_ids() correctly extracts product IDs from packages.
"""

from src.core.schemas import CreateMediaBuyRequest, Package


class TestPackageProductExtraction:
    """Test get_product_ids() extracts product_id per AdCP spec."""

    def test_get_product_ids_with_single_product_id(self):
        """Test extraction from product_id field (AdCP spec compliant)."""
        req = CreateMediaBuyRequest(
            brand_manifest="Test",
            buyer_ref="test1",
            po_number="PO-001",
            packages=[Package(buyer_ref="pkg1", product_id="prod1")],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1"]
        assert len(product_ids) == 1

    def test_get_product_ids_with_multiple_packages(self):
        """Test extraction from multiple packages."""
        req = CreateMediaBuyRequest(
            brand_manifest="Test",
            buyer_ref="test2",
            po_number="PO-002",
            packages=[
                Package(buyer_ref="pkg1", product_id="prod1"),
                Package(buyer_ref="pkg2", product_id="prod2"),
                Package(buyer_ref="pkg3", product_id="prod3"),
            ],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1", "prod2", "prod3"]
        assert len(product_ids) == 3

    def test_get_product_ids_with_empty_package(self):
        """Test extraction from package with no product_id."""
        req = CreateMediaBuyRequest(
            brand_manifest="Test",
            buyer_ref="test3",
            po_number="PO-003",
            packages=[Package(buyer_ref="pkg1")],
        )

        product_ids = req.get_product_ids()
        assert product_ids == []

    def test_get_product_ids_skips_packages_without_product_id(self):
        """Test that packages without product_id are skipped."""
        req = CreateMediaBuyRequest(
            brand_manifest="Test",
            buyer_ref="test6",
            po_number="PO-006",
            packages=[
                Package(buyer_ref="pkg1", product_id="prod1"),
                Package(buyer_ref="pkg2"),  # No product_id
                Package(buyer_ref="pkg3", product_id="prod3"),
            ],
        )

        product_ids = req.get_product_ids()
        assert product_ids == ["prod1", "prod3"]
        assert len(product_ids) == 2
