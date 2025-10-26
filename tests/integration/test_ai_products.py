#!/usr/bin/env python3
"""Automated tests for AI product features and APIs."""

import json
from unittest.mock import patch

import pytest

from tests.utils.database_helpers import create_tenant_with_timestamps

pytestmark = [pytest.mark.integration]


class TestDefaultProducts:
    """Test default product functionality."""

    def test_get_default_products(self):
        """Test that default products are returned correctly."""
        from src.services.default_products import get_default_products

        products = get_default_products()

        assert len(products) > 0
        assert all("product_id" in p for p in products)
        assert all("name" in p for p in products)

    def test_industry_specific_products(self):
        """Test industry-specific product templates."""
        from src.services.default_products import get_default_products, get_industry_specific_products

        # Test each industry
        for industry in ["news", "sports", "entertainment", "ecommerce"]:
            products = get_industry_specific_products(industry)
            assert len(products) > 0

            # Should include standard products plus industry-specific
            standard_ids = {p["product_id"] for p in get_default_products()}
            industry_ids = {p["product_id"] for p in products}

            # Should have at least one industry-specific product
            assert len(industry_ids - standard_ids) > 0


class TestAIProductService:
    """Test AI product configuration service."""

    def test_ai_service_initialization(self, mock_gemini_product_recommendations):
        """Test that AI service can be initialized with mocked Gemini."""
        from src.services.ai_product_service import AIProductConfigurationService

        # Service should initialize without errors when Gemini is mocked
        service = AIProductConfigurationService()
        assert service is not None
        assert service.model is not None


@pytest.mark.requires_db
class TestProductAPIs:
    """Test the Flask API endpoints - requires database."""

    @pytest.fixture
    def auth_client(self, integration_db):
        """Create authenticated test client using test mode."""

        app, _ = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_secret"
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["SESSION_COOKIE_PATH"] = "/"  # Allow session cookies for all paths in tests
        app.config["SESSION_COOKIE_HTTPONLY"] = False  # Allow test client to access cookies
        app.config["SESSION_COOKIE_SECURE"] = False  # Allow HTTP in tests

        client = app.test_client()

        # Use test_user for ADCP_AUTH_TEST_MODE
        with client.session_transaction() as sess:
            sess["test_user"] = "test@example.com"  # String format as expected by auth logic
            sess["user"] = "test@example.com"  # Also set user for consistency
            sess["test_user_name"] = "Test Admin"
            sess["test_user_role"] = "super_admin"
            print(f"Set session keys: {list(sess.keys())}")
            print(f"test_user: {sess.get('test_user')}")

        return client

    def test_product_suggestions_api(self, auth_client, integration_db):
        """Test product suggestions API endpoint."""
        # Debug auth test mode
        import os

        print(f"ADCP_AUTH_TEST_MODE: {os.environ.get('ADCP_AUTH_TEST_MODE')}")
        print(f"ADCP_TESTING: {os.environ.get('ADCP_TESTING')}")

        # Create a real tenant in the database with unique ID
        import uuid

        from src.core.database.database_session import get_db_session

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"

        with get_db_session() as session:
            tenant = create_tenant_with_timestamps(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain=f"test_{uuid.uuid4().hex[:8]}",  # Unique subdomain
                is_active=True,
                ad_server="mock",
                authorized_emails=["test@example.com"],
            )
            session.add(tenant)
            session.commit()

        # Mock only the product templates, use real database
        with patch("src.services.default_products.get_industry_specific_products") as mock_products:
            mock_products.return_value = [
                {
                    "product_id": "test_product",
                    "name": "Test Product",
                    "formats": ["display_300x250"],
                    "delivery_type": "guaranteed",
                    "cpm": 10.0,
                }
            ]

            # Test with industry filter using authenticated client
            response = auth_client.get(f"/api/tenant/{tenant_id}/products/suggestions?industry=news")
            if response.status_code != 200:
                print(f"Response: {response.status_code}")
                print(f"Data: {response.data}")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "suggestions" in data
            assert data["total_count"] > 0
            assert data["criteria"]["industry"] == "news"

    def test_quick_create_products_api(self, authenticated_admin_client, integration_db):
        """Test quick create API."""
        # Create tenant first with unique ID
        import uuid

        from src.core.database.database_session import get_db_session

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"

        with get_db_session() as session:
            tenant = create_tenant_with_timestamps(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain=f"test_{uuid.uuid4().hex[:8]}",  # Unique subdomain
                is_active=True,
                ad_server="mock",
                authorized_emails=["test@example.com"],
            )
            session.add(tenant)
            session.commit()

        with patch("src.services.default_products.get_default_products") as mock_products:
            mock_products.return_value = [
                {
                    "product_id": "run_of_site_display",
                    "name": "Run of Site Display",
                    "formats": ["display_300x250"],
                    "delivery_type": "non_guaranteed",
                    "price_guidance": {"min": 2.0, "max": 10.0},
                }
            ]

            response = authenticated_admin_client.post(
                f"/api/tenant/{tenant_id}/products/quick-create", json={"product_ids": ["run_of_site_display"]}
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert "run_of_site_display" in data["created"]
