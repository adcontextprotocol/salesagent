"""Test budget format backwards compatibility across all three formats.

This test suite ensures that the server correctly handles:
1. Budget object format (legacy) - Budget(total=5000, currency="USD")
2. Number format (v1.8.0) - budget=5000.0, currency="USD" (separate field)
3. Dict format (intermediate) - {"total": 5000, "currency": "USD"}

Tests cover both Package.budget and CreateMediaBuyRequest.budget fields.
"""

from decimal import Decimal

import pytest

from src.core.schemas import Budget, CreateMediaBuyRequest, Package


class TestBudgetFormatCompatibility:
    """Test that all budget formats are handled correctly."""

    def test_package_budget_as_number(self):
        """Test Package with budget as number (v1.8.0 format)."""
        package = Package(product_id="prod_1", budget=5000.0)

        # Extract budget using the pattern from main.py
        if isinstance(package.budget, dict):
            budget_amount = Decimal(str(package.budget.get("total", 0)))
        elif isinstance(package.budget, int | float):
            budget_amount = Decimal(str(package.budget))
        else:
            # Budget object with .total attribute
            budget_amount = Decimal(str(package.budget.total))

        assert budget_amount == Decimal("5000.0")
        assert isinstance(package.budget, float)

    def test_package_budget_as_budget_object(self):
        """Test Package with budget as Budget object (legacy format)."""
        package = Package(product_id="prod_1", budget=Budget(total=3000.0, currency="USD"))

        # Extract budget using the pattern from main.py
        if isinstance(package.budget, dict):
            budget_amount = Decimal(str(package.budget.get("total", 0)))
        elif isinstance(package.budget, int | float):
            budget_amount = Decimal(str(package.budget))
        else:
            # Budget object with .total attribute
            budget_amount = Decimal(str(package.budget.total))

        assert budget_amount == Decimal("3000.0")
        assert isinstance(package.budget, Budget)
        assert package.budget.currency == "USD"

    def test_package_budget_as_dict(self):
        """Test Package with budget as dict (intermediate format).

        Note: Pydantic automatically converts dicts to Budget objects during validation,
        so we verify that dict input is accepted and properly converted.
        """
        package = Package(product_id="prod_1", budget={"total": 2500.0, "currency": "EUR"})

        # Extract budget using the pattern from main.py
        if isinstance(package.budget, dict):
            budget_amount = Decimal(str(package.budget.get("total", 0)))
        elif isinstance(package.budget, int | float):
            budget_amount = Decimal(str(package.budget))
        else:
            # Budget object with .total attribute
            budget_amount = Decimal(str(package.budget.total))

        assert budget_amount == Decimal("2500.0")
        # Pydantic converts dict to Budget object automatically
        assert isinstance(package.budget, Budget)
        assert package.budget.currency == "EUR"

    def test_request_budget_as_number_with_currency_field(self):
        """Test CreateMediaBuyRequest with budget as number (v1.8.0 format)."""
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget=5000.0,  # Number format
            currency="USD",  # Separate currency field
            packages=[Package(product_id="prod_1", budget=2500.0)],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Extract budget and currency using the pattern from naming.py
        if request.budget:
            if isinstance(request.budget, dict):
                budget_amount = request.budget.get("total", 0)
                currency = request.budget.get("currency", request.currency or "USD")
            elif isinstance(request.budget, int | float):
                budget_amount = request.budget
                currency = request.currency or "USD"
            else:
                # Budget object with .total and .currency attributes
                budget_amount = request.budget.total
                currency = request.budget.currency

        assert budget_amount == 5000.0
        assert currency == "USD"
        assert isinstance(request.budget, float)

    def test_request_budget_as_budget_object(self):
        """Test CreateMediaBuyRequest with Budget object (legacy format)."""
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget=Budget(total=3000.0, currency="EUR"),
            packages=[Package(product_id="prod_1")],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Extract budget and currency using the pattern from naming.py
        if request.budget:
            if isinstance(request.budget, dict):
                budget_amount = request.budget.get("total", 0)
                currency = request.budget.get("currency", request.currency or "USD")
            elif isinstance(request.budget, int | float):
                budget_amount = request.budget
                currency = request.currency or "USD"
            else:
                # Budget object with .total and .currency attributes
                budget_amount = request.budget.total
                currency = request.budget.currency

        assert budget_amount == 3000.0
        assert currency == "EUR"
        assert isinstance(request.budget, Budget)

    def test_request_budget_as_dict(self):
        """Test CreateMediaBuyRequest with budget as dict.

        Note: Pydantic automatically converts dicts to Budget objects during validation,
        so we verify that dict input is accepted and properly converted.
        """
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget={"total": 7500.0, "currency": "GBP"},
            packages=[Package(product_id="prod_1")],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Extract budget and currency using the pattern from naming.py
        if request.budget:
            if isinstance(request.budget, dict):
                budget_amount = request.budget.get("total", 0)
                currency = request.budget.get("currency", request.currency or "USD")
            elif isinstance(request.budget, int | float):
                budget_amount = request.budget
                currency = request.currency or "USD"
            else:
                # Budget object with .total and .currency attributes
                budget_amount = request.budget.total
                currency = request.budget.currency

        assert budget_amount == 7500.0
        assert currency == "GBP"
        # Pydantic converts dict to Budget object automatically
        assert isinstance(request.budget, Budget)

    def test_request_with_number_budget_falls_back_to_currency_field(self):
        """Test that number format uses currency field for currency."""
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget=5000.0,
            currency="JPY",
            packages=[Package(product_id="prod_1")],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Extract budget and currency
        if isinstance(request.budget, int | float):
            budget_amount = request.budget
            currency = request.currency or "USD"

        assert budget_amount == 5000.0
        assert currency == "JPY"

    def test_request_with_number_budget_defaults_to_usd_if_no_currency(self):
        """Test that number format defaults to USD if no currency field."""
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget=5000.0,
            packages=[Package(product_id="prod_1")],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Extract budget and currency
        if isinstance(request.budget, int | float):
            budget_amount = request.budget
            currency = request.currency or "USD"

        assert budget_amount == 5000.0
        assert currency == "USD"

    def test_multiple_packages_mixed_budget_formats(self):
        """Test request with packages using different budget formats."""
        request = CreateMediaBuyRequest(
            brand_manifest={"name": "Test Campaign"},
            buyer_ref="test-123",
            budget=10000.0,
            currency="USD",
            packages=[
                Package(product_id="prod_1", budget=5000.0),  # Number
                Package(product_id="prod_2", budget=Budget(total=3000.0, currency="USD")),  # Budget object
                Package(product_id="prod_3", budget={"total": 2000.0, "currency": "USD"}),  # Dict
            ],
            start_time="2025-02-15T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
        )

        # Verify each package budget can be extracted
        for package in request.packages:
            if isinstance(package.budget, dict):
                budget_amount = Decimal(str(package.budget.get("total", 0)))
            elif isinstance(package.budget, int | float):
                budget_amount = Decimal(str(package.budget))
            else:
                # Budget object with .total attribute
                budget_amount = Decimal(str(package.budget.total))

            assert budget_amount > 0

    def test_integer_budget_works(self):
        """Test that integer budget values work (not just float).

        Note: Pydantic may coerce integers to floats for numeric fields,
        but the value is preserved correctly.
        """
        package = Package(product_id="prod_1", budget=5000)  # int, not float

        # Extract budget
        if isinstance(package.budget, int | float):
            budget_amount = Decimal(str(package.budget))

        assert budget_amount == Decimal("5000")
        # Pydantic may coerce to float, but that's okay for our use case
        assert isinstance(package.budget, int | float)

    def test_zero_budget_in_dict(self):
        """Test that zero budget in dict format is handled correctly.

        Note: Pydantic converts dict to Budget object.
        """
        package = Package(product_id="prod_1", budget={"total": 0, "currency": "USD"})

        # Extract budget (dict gets converted to Budget object by Pydantic)
        if isinstance(package.budget, dict):
            budget_amount = Decimal(str(package.budget.get("total", 0)))
        elif isinstance(package.budget, int | float):
            budget_amount = Decimal(str(package.budget))
        else:
            # Budget object with .total attribute
            budget_amount = Decimal(str(package.budget.total))

        assert budget_amount == Decimal("0")

    def test_budget_object_serialization(self):
        """Test that Budget objects can be serialized to dict."""
        budget = Budget(total=5000.0, currency="USD")
        budget_dict = budget.model_dump()

        assert budget_dict["total"] == 5000.0
        assert budget_dict["currency"] == "USD"

    def test_package_with_none_budget(self):
        """Test that None budget is handled correctly."""
        package = Package(product_id="prod_1", budget=None)

        # Skip extraction if budget is None
        if package.budget:
            pytest.fail("Should not extract budget when it's None")

        assert package.budget is None


class TestBudgetExtractionHelpers:
    """Test the extract_budget_amount helper function from schemas.py."""

    def test_extract_float_budget(self):
        """Test extracting budget from float format (v1.8.0)."""
        from src.core.schemas import extract_budget_amount

        amount, currency = extract_budget_amount(5000.0, "USD")
        assert amount == 5000.0
        assert currency == "USD"

    def test_extract_float_budget_with_different_currency(self):
        """Test extracting budget from float format with non-USD currency."""
        from src.core.schemas import extract_budget_amount

        amount, currency = extract_budget_amount(3500.0, "EUR")
        assert amount == 3500.0
        assert currency == "EUR"

    def test_extract_integer_budget(self):
        """Test extracting budget from integer format."""
        from src.core.schemas import extract_budget_amount

        amount, currency = extract_budget_amount(10000, "GBP")
        assert amount == 10000.0
        assert currency == "GBP"

    def test_extract_budget_object(self):
        """Test extracting budget from Budget object (legacy format)."""
        from src.core.schemas import extract_budget_amount

        budget = Budget(total=3000.0, currency="USD")
        amount, currency = extract_budget_amount(budget, "EUR")

        assert amount == 3000.0
        assert currency == "USD"  # Budget object's currency takes precedence

    def test_extract_dict_budget(self):
        """Test extracting budget from dict format."""
        from src.core.schemas import extract_budget_amount

        budget_dict = {"total": 2500.0, "currency": "EUR"}
        amount, currency = extract_budget_amount(budget_dict, "USD")

        assert amount == 2500.0
        assert currency == "EUR"  # Dict's currency takes precedence

    def test_extract_none_budget(self):
        """Test extracting None budget returns default currency."""
        from src.core.schemas import extract_budget_amount

        amount, currency = extract_budget_amount(None, "CAD")

        assert amount == 0.0
        assert currency == "CAD"

    def test_extract_dict_without_currency(self):
        """Test extracting dict budget without currency field uses default."""
        from src.core.schemas import extract_budget_amount

        budget_dict = {"total": 1500.0}
        amount, currency = extract_budget_amount(budget_dict, "JPY")

        assert amount == 1500.0
        assert currency == "JPY"  # Falls back to default

    def test_extract_zero_budget(self):
        """Test extracting zero budget."""
        from src.core.schemas import extract_budget_amount

        amount, currency = extract_budget_amount(0.0, "USD")

        assert amount == 0.0
        assert currency == "USD"
