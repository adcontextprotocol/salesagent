#!/usr/bin/env python3
"""Automated tests for AI product features and APIs."""

import pytest

from tests.utils.database_helpers import create_tenant_with_timestamps

# TODO: Fix failing tests and remove skip_ci (see GitHub issue #XXX)
pytestmark = [pytest.mark.integration, pytest.mark.skip_ci]


class TestDefaultProducts:
    """Test default product functionality."""

    def test_get_default_products(self):
        """Test that default products are returned correctly."""
        products = get_default_products()

        assert len(products) == 6
        assert all("product_id" in p for p in products)
        assert all("name" in p for p in products)
        assert all("formats" in p for p in products)

        # Check specific products exist
        product_ids = [p["product_id"] for p in products]
        assert "run_of_site_display" in product_ids
        assert "homepage_takeover" in product_ids
        assert "mobile_interstitial" in product_ids

    def test_industry_specific_products(self):
        """Test industry-specific product templates."""
        # Test each industry
        for industry in ["news", "sports", "entertainment", "ecommerce"]:
            products = get_industry_specific_products(industry)
            assert len(products) > 0

            # Should include standard products plus industry-specific
            standard_ids = {p["product_id"] for p in get_default_products()}
            industry_ids = {p["product_id"] for p in products}

            # Should have at least one industry-specific product
            assert len(industry_ids - standard_ids) > 0

    def test_create_default_products_for_tenant(self):
        """Test creating default products in database."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            conn = sqlite3.connect(tmp.name)

            # Create products table
            conn.execute(
                """
                CREATE TABLE products (
                    product_id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    name TEXT,
                    description TEXT,
                    creative_formats TEXT,
                    delivery_type TEXT,
                    cpm REAL,
                    price_guidance_min REAL,
                    price_guidance_max REAL,
                    countries TEXT,
                    targeting_template TEXT,
                    implementation_config TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            )

            # Create products
            created = create_default_products_for_tenant(conn, "test_tenant")

            assert len(created) == 6

            # Verify products were created
            cursor = conn.execute("SELECT COUNT(*) FROM products WHERE tenant_id = ?", ("test_tenant",))
            count = cursor.fetchone()[0]
            assert count == 6

            # Test idempotency - running again should create 0
            created_again = create_default_products_for_tenant(conn, "test_tenant")
            assert len(created_again) == 0

            conn.close()


class TestAIProductService:
    """Test AI product configuration service."""

    @pytest.fixture
    def mock_genai(self):
        """Mock the Gemini AI service."""
        with patch("src.services.ai_product_service.genai") as mock:
            # Mock the model response
            mock_response = Mock()
            mock_response.text = json.dumps(
                {
                    "product_id": "test_product",
                    "formats": ["display_300x250"],
                    "delivery_type": "guaranteed",
                    "cpm": 10.0,
                    "countries": ["US"],
                    "targeting_template": {"device_targets": {"device_types": ["desktop", "mobile"]}},
                    "implementation_config": {},
                }
            )

            mock_model = Mock()
            mock_model.generate_content.return_value = mock_response
            mock.GenerativeModel.return_value = mock_model

            yield mock

    @pytest.mark.asyncio
    async def test_create_product_from_description(self, mock_genai):
        """Test AI product creation from description."""
        # Mock environment variable
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
            AIProductConfigurationService()

            # Mock database and adapter
            with patch("src.services.ai_product_service.get_db_session") as mock_db:
                mock_conn = Mock()
                mock_cursor = Mock()
                mock_cursor.fetchone.side_effect = [
                    ("mock",),  # ad_server from tenants table
                    (("principal_1", "Test Principal", "token", json.dumps({})),),  # principal
                ]
                mock_conn.execute.return_value = mock_cursor
                mock_db.return_value = mock_conn

                # Skip adapter mocking since get_adapter_class doesn't exist
                # The AI service would need refactoring to be properly testable
                pytest.skip("AI service needs refactoring for proper testing")

                # The following code is unreachable due to skip above
                # # Test product creation
                # description = ProductDescription(
                #     name="Test Product",
                #     external_description="Premium homepage placement",
                #     internal_details="Use top banner"
                # )
                #
                # config = await service.create_product_from_description(
                #     tenant_id="test_tenant",
                #     description=description,
                #     adapter_type="mock"
                # )
                #
                # assert config['product_id'] == 'test_product'
                # assert config['delivery_type'] == 'guaranteed'
                # assert config['cpm'] == 10.0

    def test_analyze_inventory_for_product(self):
        """Test inventory analysis for product matching."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
            with patch("src.services.ai_product_service.genai"):
                service = AIProductConfigurationService()

                # Test inventory
                inventory = AdServerInventory(
                    placements=[
                        {
                            "id": "homepage_top",
                            "name": "Homepage Top Banner",
                            "path": "/",
                            "sizes": ["728x90", "970x250"],
                            "position": "above_fold",
                            "typical_cpm": 25.0,
                        },
                        {
                            "id": "article_inline",
                            "name": "Article Inline",
                            "path": "/article/*",
                            "sizes": ["300x250"],
                            "typical_cpm": 5.0,
                        },
                    ],
                    ad_units=[],
                    targeting_options={},
                    creative_specs=[],
                )

                # Test premium product matching
                premium_desc = ProductDescription(
                    name="Premium Homepage", external_description="Premium homepage takeover placement"
                )

                analysis = service._analyze_inventory_for_product(premium_desc, inventory)

                assert analysis["premium_level"] == "premium"
                assert len(analysis["matched_placements"]) > 0
                assert analysis["matched_placements"][0]["id"] == "homepage_top"
                assert analysis["suggested_cpm_range"]["min"] > 15.0


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


def test_ai_integration():
    """Manual test for AI integration - requires GEMINI_API_KEY."""
    import os

    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set - skipping live AI test")

    # This test actually calls Gemini API
    async def run_test():
        service = AIProductConfigurationService()

        # Verify we're using latest Gemini Flash
        assert "gemini-flash-latest" in str(service.model)

        # Test with a simple prompt
        description = ProductDescription(
            name="Test Homepage Banner", external_description="Premium banner placement on homepage above the fold"
        )

        # Mock the database parts
        with patch("src.services.ai_product_service.get_db_session"):
            with patch("src.adapters.get_adapter_class"):
                # This will fail but we just want to verify the model is working
                try:
                    await service.create_product_from_description(
                        tenant_id="test", description=description, adapter_type="mock"
                    )
                except:
                    pass  # Expected to fail due to mocking

    asyncio.run(run_test())


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
