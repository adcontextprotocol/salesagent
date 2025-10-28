"""Unit tests for media_buy_helpers module.

Tests for shared media buy helper functions used across all adapters.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.core.helpers.media_buy_helpers import (
    build_order_name,
    build_package_responses,
    calculate_total_budget,
)
from src.core.schemas import CreateMediaBuyRequest, MediaPackage, Budget


class TestBuildOrderName:
    """Tests for build_order_name helper function."""

    def test_build_order_name_with_default_template(self):
        """Test order name building with default template."""
        request = MagicMock()
        request.buyer_ref = "buyer_123"

        packages = [
            MagicMock(package_id="pkg1", name="Package 1", product_id="prod1"),
            MagicMock(package_id="pkg2", name="Package 2", product_id="prod2"),
        ]

        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 31, 23, 59, 59)

        # Should not raise and should return a non-empty string
        result = build_order_name(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            tenant_id=None,
            adapter_type="gam"
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_order_name_with_tenant_database_error(self):
        """Test order name building gracefully handles database errors."""
        request = MagicMock()
        request.buyer_ref = "buyer_123"

        packages = [MagicMock(package_id="pkg1", name="Package 1", product_id="prod1")]

        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 31, 23, 59, 59)

        # Should use default template even if tenant_id provided
        result = build_order_name(
            request=request,
            packages=packages,
            start_time=start_time,
            end_time=end_time,
            tenant_id="tenant_123",
            adapter_type="gam"
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_order_name_respects_adapter_type(self):
        """Test that order name builder accepts different adapter types."""
        request = MagicMock()
        request.buyer_ref = "buyer_123"

        packages = [MagicMock(package_id="pkg1", name="Package 1", product_id="prod1")]

        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 31, 23, 59, 59)

        # Test multiple adapter types
        for adapter_type in ["gam", "mock", "kevel", "xandr", "triton"]:
            result = build_order_name(
                request=request,
                packages=packages,
                start_time=start_time,
                end_time=end_time,
                tenant_id=None,
                adapter_type=adapter_type
            )
            assert isinstance(result, str)
            assert len(result) > 0


class TestBuildPackageResponses:
    """Tests for build_package_responses helper function."""

    def test_build_package_responses_basic(self):
        """Test basic package response building."""
        package = MagicMock()
        package.package_id = "pkg1"
        package.product_id = "prod1"
        package.name = "Package 1"
        package.delivery_type = "guaranteed"
        package.cpm = 10.0
        package.impressions = 1000000
        package.targeting_overlay = None
        package.creative_ids = None

        request = MagicMock()
        request.packages = []

        result = build_package_responses([package], request)

        assert len(result) == 1
        assert result[0]["package_id"] == "pkg1"
        assert result[0]["product_id"] == "prod1"
        assert result[0]["name"] == "Package 1"

    def test_build_package_responses_with_budget(self):
        """Test package responses include budget when available."""
        package = MagicMock()
        package.package_id = "pkg1"
        package.product_id = "prod1"
        package.name = "Package 1"
        package.delivery_type = "guaranteed"
        package.cpm = 10.0
        package.impressions = 1000000
        package.targeting_overlay = None
        package.creative_ids = None

        # Create request package with budget
        request_package = MagicMock()
        request_package.buyer_ref = "buyer_123"
        request_package.budget = 5000.0

        request = MagicMock()
        request.packages = [request_package]

        result = build_package_responses([package], request)

        assert len(result) == 1
        assert "budget" in result[0]
        # Budget should be dict format {total, currency}
        assert isinstance(result[0]["budget"], dict)
        assert result[0]["budget"]["total"] == 5000.0

    def test_build_package_responses_with_budget_object(self):
        """Test package responses handle Budget objects properly."""
        package = MagicMock()
        package.package_id = "pkg1"
        package.product_id = "prod1"
        package.name = "Package 1"
        package.delivery_type = "guaranteed"
        package.cpm = 10.0
        package.impressions = 1000000
        package.targeting_overlay = None
        package.creative_ids = None

        # Create request package with Budget object
        budget = MagicMock()
        budget.model_dump = MagicMock(return_value={"total": 5000.0, "currency": "USD"})

        request_package = MagicMock()
        request_package.buyer_ref = "buyer_123"
        request_package.budget = budget

        request = MagicMock()
        request.packages = [request_package]

        result = build_package_responses([package], request)

        assert len(result) == 1
        assert "budget" in result[0]
        assert result[0]["budget"]["total"] == 5000.0
        assert result[0]["budget"]["currency"] == "USD"

    def test_build_package_responses_with_line_item_ids(self):
        """Test package responses include platform line item IDs."""
        packages = [
            MagicMock(package_id="pkg1", product_id="prod1", name="Package 1",
                     delivery_type="guaranteed", cpm=10.0, impressions=1000000,
                     targeting_overlay=None, creative_ids=None),
            MagicMock(package_id="pkg2", product_id="prod2", name="Package 2",
                     delivery_type="guaranteed", cpm=10.0, impressions=1000000,
                     targeting_overlay=None, creative_ids=None),
        ]

        request = MagicMock()
        request.packages = []

        line_item_ids = ["li_123", "li_456"]
        result = build_package_responses(packages, request, line_item_ids=line_item_ids)

        assert len(result) == 2
        assert result[0]["platform_line_item_id"] == "li_123"
        assert result[1]["platform_line_item_id"] == "li_456"

    def test_build_package_responses_with_creative_ids(self):
        """Test package responses include creative IDs."""
        package = MagicMock()
        package.package_id = "pkg1"
        package.product_id = "prod1"
        package.name = "Package 1"
        package.delivery_type = "guaranteed"
        package.cpm = 10.0
        package.impressions = 1000000
        package.targeting_overlay = None
        package.creative_ids = ["creative_123", "creative_456"]

        request = MagicMock()
        request.packages = []

        result = build_package_responses([package], request)

        assert len(result) == 1
        assert result[0]["creative_ids"] == ["creative_123", "creative_456"]

    def test_build_package_responses_multiple_packages(self):
        """Test building responses for multiple packages."""
        packages = [
            MagicMock(package_id="pkg1", product_id="prod1", name="Package 1",
                     delivery_type="guaranteed", cpm=10.0, impressions=1000000,
                     targeting_overlay=None, creative_ids=None),
            MagicMock(package_id="pkg2", product_id="prod2", name="Package 2",
                     delivery_type="non_guaranteed", cpm=5.0, impressions=2000000,
                     targeting_overlay=None, creative_ids=None),
            MagicMock(package_id="pkg3", product_id="prod3", name="Package 3",
                     delivery_type="guaranteed", cpm=15.0, impressions=500000,
                     targeting_overlay=None, creative_ids=None),
        ]

        request = MagicMock()
        request.packages = []

        result = build_package_responses(packages, request)

        assert len(result) == 3
        assert result[0]["package_id"] == "pkg1"
        assert result[1]["package_id"] == "pkg2"
        assert result[2]["package_id"] == "pkg3"


class TestCalculateTotalBudget:
    """Tests for calculate_total_budget helper function."""

    def test_calculate_total_budget_from_request_method(self):
        """Test budget calculation using request.get_total_budget() method."""
        request = MagicMock()
        request.get_total_budget = MagicMock(return_value=5000.0)

        packages = []  # Empty packages since we're using request method

        result = calculate_total_budget(request, packages)

        assert result == 5000.0
        request.get_total_budget.assert_called_once()

    def test_calculate_total_budget_from_package_budgets(self):
        """Test budget calculation from package budgets (AdCP v2.2.0)."""
        # Create request without get_total_budget method
        request = MagicMock(spec=[])  # Empty spec - no methods

        # Create packages with budget objects
        pkg1_budget = MagicMock()
        pkg1_budget.total = 2000.0
        pkg1_budget.currency = "USD"

        pkg2_budget = MagicMock()
        pkg2_budget.total = 3000.0
        pkg2_budget.currency = "USD"

        package1 = MagicMock()
        package1.budget = pkg1_budget
        package1.delivery_type = None

        package2 = MagicMock()
        package2.budget = pkg2_budget
        package2.delivery_type = None

        with patch("src.core.helpers.media_buy_helpers.extract_budget_amount") as mock_extract:
            mock_extract.side_effect = [(2000.0, "USD"), (3000.0, "USD")]
            result = calculate_total_budget(request, [package1, package2])

        assert result == 5000.0

    def test_calculate_total_budget_from_pricing_info(self):
        """Test budget calculation from pricing_info (pricing_option flow)."""
        request = MagicMock(spec=[])  # No get_total_budget method

        package = MagicMock()
        package.package_id = "pkg1"
        package.delivery_type = "guaranteed"
        package.budget = None  # No direct budget
        package.cpm = 0  # CPM will be overridden by pricing_info
        package.impressions = 1000000

        pricing_info = {
            "pkg1": {
                "is_fixed": True,
                "rate": 10.0,  # $10 fixed rate
                "bid_price": None
            }
        }

        result = calculate_total_budget(request, [package], package_pricing_info=pricing_info)

        # (10 * 1000000) / 1000 = 10,000
        assert result == 10000.0

    def test_calculate_total_budget_auction_pricing(self):
        """Test budget calculation with auction pricing."""
        request = MagicMock(spec=[])  # No get_total_budget method

        package = MagicMock()
        package.package_id = "pkg1"
        package.delivery_type = "guaranteed"
        package.budget = None
        package.cpm = 5.0  # Default CPM (will be used as fallback)
        package.impressions = 1000000

        pricing_info = {
            "pkg1": {
                "is_fixed": False,  # Auction pricing
                "rate": None,
                "bid_price": 15.0
            }
        }

        result = calculate_total_budget(request, [package], package_pricing_info=pricing_info)

        # (15 * 1000000) / 1000 = 15,000 (uses bid_price for auction)
        assert result == 15000.0

    def test_calculate_total_budget_mixed_packages(self):
        """Test budget calculation with mixed package types."""
        request = MagicMock(spec=[])  # No get_total_budget method

        # Package with explicit budget
        budget = MagicMock()
        budget.total = 2000.0
        pkg_with_budget = MagicMock()
        pkg_with_budget.budget = budget
        pkg_with_budget.delivery_type = "guaranteed"

        # Package with pricing info
        pkg_with_pricing = MagicMock()
        pkg_with_pricing.package_id = "pkg2"
        pkg_with_pricing.budget = None
        pkg_with_pricing.delivery_type = "guaranteed"
        pkg_with_pricing.cpm = 0
        pkg_with_pricing.impressions = 1000000

        pricing_info = {
            "pkg2": {
                "is_fixed": True,
                "rate": 10.0,
                "bid_price": None
            }
        }

        with patch("src.core.helpers.media_buy_helpers.extract_budget_amount") as mock_extract:
            mock_extract.return_value = (2000.0, "USD")
            result = calculate_total_budget(
                request,
                [pkg_with_budget, pkg_with_pricing],
                package_pricing_info=pricing_info
            )

        # 2000 + 10000 = 12000
        assert result == 12000.0

    def test_calculate_total_budget_zero_packages(self):
        """Test budget calculation with no packages."""
        request = MagicMock(spec=[])  # No get_total_budget method

        result = calculate_total_budget(request, [])

        assert result == 0.0

    def test_calculate_total_budget_fallback_to_package_cpm(self):
        """Test budget calculation falls back to package.cpm when no pricing_info."""
        request = MagicMock(spec=[])  # No get_total_budget method

        package = MagicMock()
        package.budget = None
        package.delivery_type = "guaranteed"
        package.cpm = 12.5
        package.impressions = 800000

        result = calculate_total_budget(request, [package], package_pricing_info=None)

        # (12.5 * 800000) / 1000 = 10,000
        assert result == 10000.0


class TestBuildPackageResponsesEdgeCases:
    """Tests for edge cases in build_package_responses."""

    def test_build_package_responses_missing_optional_fields(self):
        """Test package responses handle missing optional fields gracefully."""
        package = MagicMock()
        package.package_id = "pkg1"
        package.product_id = "prod1"
        package.name = "Package 1"

        # Remove all optional attributes
        del package.delivery_type
        del package.cpm
        del package.impressions
        del package.targeting_overlay
        del package.creative_ids

        request = MagicMock()
        request.packages = []

        result = build_package_responses([package], request)

        assert len(result) == 1
        assert result[0]["package_id"] == "pkg1"
        assert "delivery_type" not in result[0]
        assert "cpm" not in result[0]

    def test_build_package_responses_line_item_ids_mismatch(self):
        """Test package responses handle mismatched line_item_ids gracefully."""
        packages = [
            MagicMock(package_id="pkg1", product_id="prod1", name="Package 1",
                     delivery_type="guaranteed", cpm=10.0, impressions=1000000,
                     targeting_overlay=None, creative_ids=None),
            MagicMock(package_id="pkg2", product_id="prod2", name="Package 2",
                     delivery_type="guaranteed", cpm=10.0, impressions=1000000,
                     targeting_overlay=None, creative_ids=None),
        ]

        request = MagicMock()
        request.packages = []

        # Only one line_item_id for two packages
        line_item_ids = ["li_123"]
        result = build_package_responses(packages, request, line_item_ids=line_item_ids)

        assert len(result) == 2
        assert result[0].get("platform_line_item_id") == "li_123"
        assert "platform_line_item_id" not in result[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
