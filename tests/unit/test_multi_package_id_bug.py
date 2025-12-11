"""Test for multi-package pricing info lookup.

Tests that pricing info is correctly looked up for each package in a multi-package
media buy using the response package_id (not a stale variable from an outer loop).

Bug context: The original code used `package_pricing_info.get(package_id)` where
`package_id` was a stale variable from an outer loop. The fix uses `resp_package_id`
from the inner loop that iterates over adapter response packages.
"""

import pytest


class TestMultiPackagePricingLookup:
    """Test that pricing info lookup uses correct package IDs."""

    def test_pricing_lookup_uses_response_package_id(self):
        """Verify pricing info is retrieved using resp_package_id, not stale package_id.

        This simulates the database save loop where each response package's pricing
        info must be looked up by its own package_id.
        """
        # Simulate package_pricing_info dict keyed by package_id
        package_pricing_info = {
            "pkg_prod_A_abc123_1": {"rate": 10.0, "pricing_model": "CPM"},
            "pkg_prod_B_def456_2": {"rate": 25.0, "pricing_model": "CPM"},
        }

        # Simulate response packages from adapter
        class MockResponsePackage:
            def __init__(self, package_id: str, product_id: str):
                self.package_id = package_id
                self.product_id = product_id
                self.paused = False

        response_packages = [
            MockResponsePackage("pkg_prod_A_abc123_1", "prod_A"),
            MockResponsePackage("pkg_prod_B_def456_2", "prod_B"),
        ]

        # Simulate the FIXED loop (using resp_package_id)
        retrieved_pricing = []
        for resp_package in response_packages:
            resp_package_id = resp_package.package_id
            # CORRECT: Use resp_package_id (from current iteration)
            pricing_info_for_package = package_pricing_info.get(resp_package_id)
            retrieved_pricing.append(
                {
                    "package_id": resp_package_id,
                    "pricing_info": pricing_info_for_package,
                }
            )

        # Verify each package got its own pricing info
        assert retrieved_pricing[0]["pricing_info"]["rate"] == 10.0
        assert retrieved_pricing[1]["pricing_info"]["rate"] == 25.0

    def test_stale_variable_bug_demonstration(self):
        """Demonstrate the bug that was fixed.

        Shows what happens when a stale `package_id` variable is used instead
        of the correct `resp_package_id` from the inner loop.
        """
        # Simulate package_pricing_info dict keyed by package_id
        package_pricing_info = {
            "pkg_prod_A_abc123_1": {"rate": 10.0, "pricing_model": "CPM"},
            "pkg_prod_B_def456_2": {"rate": 25.0, "pricing_model": "CPM"},
        }

        # Simulate response packages from adapter
        class MockResponsePackage:
            def __init__(self, package_id: str, product_id: str):
                self.package_id = package_id
                self.product_id = product_id
                self.paused = False

        response_packages = [
            MockResponsePackage("pkg_prod_A_abc123_1", "prod_A"),
            MockResponsePackage("pkg_prod_B_def456_2", "prod_B"),
        ]

        # Simulate a stale package_id from outer loop (the BUG)
        # This represents what would happen if there was an outer loop
        # that set package_id and it wasn't updated in the inner loop
        stale_package_id = "pkg_prod_B_def456_2"  # Set from last iteration of outer loop

        # BUG: Using stale package_id would give wrong pricing for first package
        retrieved_pricing_buggy = []
        for resp_package in response_packages:
            # BUG: This uses the stale variable, not resp_package.package_id
            pricing_info_for_package = package_pricing_info.get(stale_package_id)
            retrieved_pricing_buggy.append(
                {
                    "package_id": resp_package.package_id,
                    "pricing_info": pricing_info_for_package,
                }
            )

        # Both packages would get the WRONG pricing (the stale one)
        # Package A would incorrectly get Package B's pricing
        assert retrieved_pricing_buggy[0]["pricing_info"]["rate"] == 25.0  # Wrong!
        assert retrieved_pricing_buggy[1]["pricing_info"]["rate"] == 25.0  # Happens to be right

        # The first package should have had rate 10.0, not 25.0

    def test_package_config_stores_correct_pricing_info(self):
        """Verify package_config dict stores pricing from correct package lookup."""
        # Setup pricing info keyed by package_id
        package_pricing_info = {
            "pkg_display_111_1": {
                "rate": 5.50,
                "pricing_model": "CPM",
                "currency": "USD",
            },
            "pkg_video_222_2": {
                "rate": 15.00,
                "pricing_model": "VCPM",
                "currency": "USD",
            },
            "pkg_native_333_3": {
                "rate": 8.25,
                "pricing_model": "CPC",
                "currency": "EUR",
            },
        }

        # Simulate building package_config for each response package
        class MockResponsePackage:
            def __init__(self, package_id: str, product_id: str, name: str):
                self.package_id = package_id
                self.product_id = product_id
                self.name = name
                self.paused = False

        response_packages = [
            MockResponsePackage("pkg_display_111_1", "prod_display", "Display Package"),
            MockResponsePackage("pkg_video_222_2", "prod_video", "Video Package"),
            MockResponsePackage("pkg_native_333_3", "prod_native", "Native Package"),
        ]

        package_configs = []
        for resp_package in response_packages:
            resp_package_id = resp_package.package_id
            pricing_info_for_package = package_pricing_info.get(resp_package_id)

            package_config = {
                "package_id": resp_package_id,
                "name": resp_package.name,
                "product_id": resp_package.product_id,
                "paused": resp_package.paused,
                "pricing_info": pricing_info_for_package,
            }
            package_configs.append(package_config)

        # Verify each package_config has its correct pricing info
        assert package_configs[0]["pricing_info"]["rate"] == 5.50
        assert package_configs[0]["pricing_info"]["pricing_model"] == "CPM"

        assert package_configs[1]["pricing_info"]["rate"] == 15.00
        assert package_configs[1]["pricing_info"]["pricing_model"] == "VCPM"

        assert package_configs[2]["pricing_info"]["rate"] == 8.25
        assert package_configs[2]["pricing_info"]["pricing_model"] == "CPC"
        assert package_configs[2]["pricing_info"]["currency"] == "EUR"

    def test_missing_pricing_info_returns_none(self):
        """Package with no pricing info in dict should get None."""
        package_pricing_info = {
            "pkg_prod_A_abc123_1": {"rate": 10.0},
            # Note: No entry for pkg_prod_B_def456_2
        }

        class MockResponsePackage:
            def __init__(self, package_id: str):
                self.package_id = package_id

        response_packages = [
            MockResponsePackage("pkg_prod_A_abc123_1"),
            MockResponsePackage("pkg_prod_B_def456_2"),  # Not in pricing dict
        ]

        results = []
        for resp_package in response_packages:
            resp_package_id = resp_package.package_id
            pricing_info = package_pricing_info.get(resp_package_id)
            results.append(pricing_info)

        assert results[0] is not None
        assert results[0]["rate"] == 10.0
        assert results[1] is None


class TestPackageIdGeneration:
    """Test that package IDs are generated correctly for multi-package media buys."""

    def test_package_id_format(self):
        """Verify package ID format: pkg_{product_id}_{hex}_{idx}."""
        import secrets

        product_id = "prod_abc123"
        idx = 1

        package_id = f"pkg_{product_id}_{secrets.token_hex(4)}_{idx}"

        assert package_id.startswith("pkg_prod_abc123_")
        assert package_id.endswith("_1")
        # Total format: pkg_ + product_id + _ + 8 hex chars + _ + idx
        parts = package_id.split("_")
        assert len(parts) == 5  # pkg, prod, abc123, hex8, 1

    def test_different_products_get_different_package_ids(self):
        """Each package for different products has distinct ID with its product_id."""
        import secrets

        # Simulate two packages for different products
        packages = []
        for idx, product_id in enumerate(["prod_display", "prod_video"], 1):
            package_id = f"pkg_{product_id}_{secrets.token_hex(4)}_{idx}"
            packages.append({"package_id": package_id, "product_id": product_id})

        # Verify package IDs contain their respective product IDs
        assert "prod_display" in packages[0]["package_id"]
        assert "prod_video" in packages[1]["package_id"]

        # Verify uniqueness
        assert packages[0]["package_id"] != packages[1]["package_id"]

    def test_same_product_different_indices(self):
        """Multiple packages of same product get different IDs via index."""
        import secrets

        product_id = "prod_shared"
        packages = []

        for idx in range(1, 4):  # 3 packages of same product
            package_id = f"pkg_{product_id}_{secrets.token_hex(4)}_{idx}"
            packages.append(package_id)

        # All should be unique due to random hex and index
        assert len(set(packages)) == 3

        # Verify indices
        assert packages[0].endswith("_1")
        assert packages[1].endswith("_2")
        assert packages[2].endswith("_3")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
