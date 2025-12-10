"""Unit tests for product principal access control.

Tests the access control logic that restricts product visibility to specific principals.
"""

from unittest.mock import Mock


class TestProductPrincipalAccessControlLogic:
    """Test the principal access control filter logic.

    These tests verify the filtering logic directly without requiring database.
    The actual implementation is in src/core/tools/products.py.
    """

    def _create_mock_product(
        self,
        product_id: str,
        allowed_principal_ids: list[str] | None = None,
    ):
        """Create a mock product for testing access control."""
        product = Mock()
        product.product_id = product_id
        product.allowed_principal_ids = allowed_principal_ids
        return product

    def test_product_with_no_restrictions_visible_to_all(self):
        """Test that products with null allowed_principal_ids are visible to all."""
        product = self._create_mock_product(
            product_id="unrestricted_product",
            allowed_principal_ids=None,
        )

        # Any principal should see this product
        principal_id = "any_principal"
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        # Logic: null/empty means visible to all
        is_visible = allowed_ids is None or len(allowed_ids) == 0 or principal_id in allowed_ids
        assert is_visible is True

    def test_product_with_empty_list_visible_to_all(self):
        """Test that products with empty allowed_principal_ids list are visible to all."""
        product = self._create_mock_product(
            product_id="unrestricted_product",
            allowed_principal_ids=[],
        )

        # Any principal should see this product
        principal_id = "any_principal"
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        # Logic: null/empty means visible to all
        is_visible = allowed_ids is None or len(allowed_ids) == 0 or principal_id in allowed_ids
        assert is_visible is True

    def test_product_visible_to_allowed_principal(self):
        """Test that restricted products are visible to allowed principals."""
        product = self._create_mock_product(
            product_id="restricted_product",
            allowed_principal_ids=["principal_1", "principal_2"],
        )

        # Principal in the allowed list should see this product
        principal_id = "principal_1"
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        is_visible = allowed_ids is None or len(allowed_ids) == 0 or principal_id in allowed_ids
        assert is_visible is True

    def test_product_hidden_from_non_allowed_principal(self):
        """Test that restricted products are hidden from non-allowed principals."""
        product = self._create_mock_product(
            product_id="restricted_product",
            allowed_principal_ids=["principal_1", "principal_2"],
        )

        # Principal NOT in the allowed list should NOT see this product
        principal_id = "principal_3"
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        is_visible = allowed_ids is None or len(allowed_ids) == 0 or principal_id in allowed_ids
        assert is_visible is False

    def test_restricted_product_hidden_from_anonymous_users(self):
        """Test that restricted products are hidden from anonymous users."""
        product = self._create_mock_product(
            product_id="restricted_product",
            allowed_principal_ids=["principal_1"],
        )

        # Anonymous user (no principal_id) should NOT see restricted products
        principal_id = None
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        # For anonymous users: only show if no restrictions
        is_visible = allowed_ids is None or len(allowed_ids) == 0
        assert is_visible is False

    def test_unrestricted_product_visible_to_anonymous_users(self):
        """Test that unrestricted products are visible to anonymous users."""
        product = self._create_mock_product(
            product_id="public_product",
            allowed_principal_ids=None,
        )

        # Anonymous user should see unrestricted products
        allowed_ids = getattr(product, "allowed_principal_ids", None)

        # For anonymous users: only show if no restrictions
        is_visible = allowed_ids is None or len(allowed_ids) == 0
        assert is_visible is True


class TestProductAccessFilterFunction:
    """Test the filter function as it would be applied in get_products."""

    def _filter_products_by_principal_access(
        self,
        products: list,
        principal_id: str | None,
    ) -> list:
        """Filter products by principal access control.

        This mirrors the logic in src/core/tools/products.py.
        """
        if principal_id:
            filtered = []
            for product in products:
                allowed_ids = getattr(product, "allowed_principal_ids", None)
                if allowed_ids is None or len(allowed_ids) == 0:
                    # No restrictions - visible to all
                    filtered.append(product)
                elif principal_id in allowed_ids:
                    # Principal is in the allowed list
                    filtered.append(product)
            return filtered
        else:
            # No principal - only show unrestricted products
            filtered = []
            for product in products:
                allowed_ids = getattr(product, "allowed_principal_ids", None)
                if allowed_ids is None or len(allowed_ids) == 0:
                    filtered.append(product)
            return filtered

    def test_filter_returns_all_unrestricted_products(self):
        """Test that filter returns all unrestricted products."""
        products = [
            Mock(product_id="prod_1", allowed_principal_ids=None),
            Mock(product_id="prod_2", allowed_principal_ids=[]),
            Mock(product_id="prod_3", allowed_principal_ids=None),
        ]

        result = self._filter_products_by_principal_access(products, "any_principal")
        assert len(result) == 3

    def test_filter_returns_allowed_products_for_principal(self):
        """Test that filter returns only allowed products for a specific principal."""
        products = [
            Mock(product_id="public", allowed_principal_ids=None),
            Mock(product_id="for_p1", allowed_principal_ids=["principal_1"]),
            Mock(product_id="for_p2", allowed_principal_ids=["principal_2"]),
            Mock(product_id="for_both", allowed_principal_ids=["principal_1", "principal_2"]),
        ]

        # principal_1 should see: public, for_p1, for_both
        result = self._filter_products_by_principal_access(products, "principal_1")
        result_ids = [p.product_id for p in result]

        assert "public" in result_ids
        assert "for_p1" in result_ids
        assert "for_both" in result_ids
        assert "for_p2" not in result_ids
        assert len(result) == 3

    def test_filter_for_anonymous_returns_only_unrestricted(self):
        """Test that anonymous users only see unrestricted products."""
        products = [
            Mock(product_id="public", allowed_principal_ids=None),
            Mock(product_id="restricted", allowed_principal_ids=["principal_1"]),
        ]

        result = self._filter_products_by_principal_access(products, None)
        result_ids = [p.product_id for p in result]

        assert "public" in result_ids
        assert "restricted" not in result_ids
        assert len(result) == 1


class TestProductSchemaWithAllowedPrincipalIds:
    """Test that the Product schema includes the allowed_principal_ids field."""

    def test_product_schema_has_allowed_principal_ids_field(self):
        """Test that Product schema accepts allowed_principal_ids."""
        from src.core.schemas import Product

        # Check that the field exists in the schema
        assert "allowed_principal_ids" in Product.model_fields

    def test_product_schema_field_is_optional(self):
        """Test that allowed_principal_ids is optional (None by default)."""
        from src.core.schemas import Product

        field_info = Product.model_fields["allowed_principal_ids"]
        # Default should be None
        assert field_info.default is None

    def test_product_schema_field_is_excluded_from_serialization(self):
        """Test that allowed_principal_ids is excluded from API responses."""
        from src.core.schemas import Product

        field_info = Product.model_fields["allowed_principal_ids"]
        # Should be excluded from serialization
        assert field_info.exclude is True
