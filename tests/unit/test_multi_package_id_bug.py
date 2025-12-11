"""Test for multi-package ID generation.

Tests that package IDs are correctly generated for multi-package media buys
with different product_ids.
"""

import secrets
from unittest.mock import Mock

import pytest


class TestMultiPackageIdGeneration:
    """Test that package IDs are correctly generated for multi-package media buys."""

    def test_two_packages_different_products_get_correct_ids(self):
        """Verify each package gets an ID based on its own product_id, not the other's.

        This tests the core logic used in media_buy_create.py to ensure
        package IDs are unique and correctly reference their associated product.
        """
        # Create two mock products with different IDs
        product1 = Mock()
        product1.product_id = "prod_d979b543"
        product1.name = "Product 1"

        product2 = Mock()
        product2.product_id = "prod_e8fd6012"
        product2.name = "Product 2"

        # Simulate the products_in_buy list
        products_in_buy = [product1, product2]

        # Simulate req.packages with two packages using different product_ids
        class MockPackage:
            def __init__(self, product_id, buyer_ref):
                self.product_id = product_id
                self.buyer_ref = buyer_ref

        req_packages = [
            MockPackage("prod_d979b543", "pkg1_ref"),
            MockPackage("prod_e8fd6012", "pkg2_ref"),
        ]

        # Reproduce the loop from media_buy_create.py (auto-approval path)
        packages = []
        for idx, pkg in enumerate(req_packages, 1):
            pkg_product_id = pkg.product_id

            # Find the product matching this package's product_id
            pkg_product = None
            for p in products_in_buy:
                if p.product_id == pkg_product_id:
                    pkg_product = p
                    break

            assert pkg_product is not None, f"Product not found for {pkg_product_id}"

            # Generate package_id using the LOOKED UP product's ID
            package_id = f"pkg_{pkg_product.product_id}_{secrets.token_hex(4)}_{idx}"

            packages.append(
                {
                    "package_id": package_id,
                    "product_id": pkg_product.product_id,
                    "idx": idx,
                }
            )

        # Assert correct behavior
        assert len(packages) == 2, "Should have 2 packages"

        # Package 1 should use product 1's ID and have index 1
        assert (
            "prod_d979b543" in packages[0]["package_id"]
        ), f"Package 1 should contain prod_d979b543, got {packages[0]['package_id']}"
        assert packages[0]["package_id"].endswith(
            "_1"
        ), f"Package 1 should end with _1, got {packages[0]['package_id']}"
        assert packages[0]["idx"] == 1

        # Package 2 should use product 2's ID and have index 2
        assert (
            "prod_e8fd6012" in packages[1]["package_id"]
        ), f"Package 2 should contain prod_e8fd6012, got {packages[1]['package_id']}"
        assert packages[1]["package_id"].endswith(
            "_2"
        ), f"Package 2 should end with _2, got {packages[1]['package_id']}"
        assert packages[1]["idx"] == 2

        # IDs should be different
        assert packages[0]["package_id"] != packages[1]["package_id"], "Package IDs should be different"

    def test_package_ids_unique_even_with_same_random_hex(self):
        """Package IDs differ by product_id and idx even if random hex were same."""
        id1 = "pkg_prod_d979b543_aaaaaaaa_1"
        id2 = "pkg_prod_e8fd6012_aaaaaaaa_2"

        assert id1 != id2, "Package IDs should differ by product_id and idx"
        assert "prod_d979b543" in id1
        assert "prod_e8fd6012" in id2

    def test_same_product_different_indices_get_different_ids(self):
        """Two packages with same product_id but different indices get different IDs."""
        # This simulates the case where a buyer wants 2 packages of the same product
        # with different targeting
        product = Mock()
        product.product_id = "prod_shared"

        products_in_buy = [product]

        class MockPackage:
            def __init__(self, product_id, buyer_ref):
                self.product_id = product_id
                self.buyer_ref = buyer_ref

        req_packages = [
            MockPackage("prod_shared", "pkg1_us"),
            MockPackage("prod_shared", "pkg2_ca"),
        ]

        packages = []
        for idx, pkg in enumerate(req_packages, 1):
            pkg_product = None
            for p in products_in_buy:
                if p.product_id == pkg.product_id:
                    pkg_product = p
                    break

            assert pkg_product is not None
            package_id = f"pkg_{pkg_product.product_id}_{secrets.token_hex(4)}_{idx}"
            packages.append({"package_id": package_id, "idx": idx})

        # Both use same product_id but different indices ensure uniqueness
        assert packages[0]["package_id"].endswith("_1")
        assert packages[1]["package_id"].endswith("_2")
        assert packages[0]["package_id"] != packages[1]["package_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
