#!/usr/bin/env python3
"""
A2A Real Data Flow Integration Tests

End-to-end A2A tests with actual database and real data flow to catch bugs
that mocking would miss. These tests validate the complete A2A request pipeline
including authentication, database queries, and schema conversion.

This addresses the gap identified in issue #161 where the A2A agent bug
'Product' object has no attribute 'pricing' reached production because tests
over-mocked the data flow and didn't test actual database interactions.
"""

import json
from datetime import UTC
from unittest.mock import patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from src.core.database.database_session import get_db_session
from src.core.database.models import Principal, Tenant
from src.core.database.models import Product as ProductModel


class TestA2ARealDataFlow:
    """Test A2A server with real database data flow."""

    @pytest.fixture
    def test_tenant_setup(self):
        """Set up test tenant with products and principal."""
        tenant_id = "test_a2a_tenant"
        principal_id = "test_a2a_principal"

        with get_db_session() as session:
            # Clean up existing test data (audit logs first to avoid foreign key violations)
            from src.core.database.models import AuditLog

            session.query(AuditLog).filter_by(tenant_id=tenant_id).delete()
            session.query(ProductModel).filter_by(tenant_id=tenant_id).delete()
            session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=principal_id).delete()
            session.query(Tenant).filter_by(tenant_id=tenant_id).delete()

            # Create test tenant
            from datetime import datetime

            now = datetime.now(UTC)
            tenant = Tenant(
                tenant_id=tenant_id,
                name="A2A Test Tenant",
                subdomain="a2a-test",
                billing_plan="test",
                created_at=now,
                updated_at=now,
            )
            session.add(tenant)

            # Create test principal
            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="A2A Test Principal",
                access_token="test_a2a_token_123",
                platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
            )
            session.add(principal)

            # Create test products with complete data
            products_data = [
                {
                    "product_id": "a2a_display_001",
                    "name": "A2A Display Product",
                    "description": "Display advertising for A2A testing",
                    "formats": ["display_300x250", "display_728x90"],
                    "targeting_template": {"geo": ["US"], "device": ["desktop", "mobile"]},
                    "delivery_type": "non_guaranteed",
                    "is_fixed_price": False,
                    "cpm": 5.50,
                    "min_spend": 1000.00,
                    "is_custom": False,
                },
                {
                    "product_id": "a2a_video_001",
                    "name": "A2A Video Product",
                    "description": "Video advertising for A2A testing",
                    "formats": ["video_15s", "video_30s"],
                    "targeting_template": {"geo": ["US", "CA"], "device": ["mobile"]},
                    "delivery_type": "guaranteed",
                    "is_fixed_price": True,
                    "cpm": 12.00,
                    "min_spend": 5000.00,
                    "is_custom": False,
                },
            ]

            for product_data in products_data:
                product = ProductModel(tenant_id=tenant_id, **product_data)
                session.add(product)

            session.commit()

        yield {"tenant_id": tenant_id, "principal_id": principal_id, "access_token": "test_a2a_token_123"}

        # Cleanup (in order to avoid foreign key violations)
        with get_db_session() as session:
            # Import AuditLog model and delete audit logs first
            from src.core.database.models import AuditLog

            session.query(AuditLog).filter_by(tenant_id=tenant_id).delete()
            session.query(ProductModel).filter_by(tenant_id=tenant_id).delete()
            session.query(Principal).filter_by(tenant_id=tenant_id, principal_id=principal_id).delete()
            session.query(Tenant).filter_by(tenant_id=tenant_id).delete()
            session.commit()

    @pytest.mark.asyncio
    async def test_a2a_get_products_real_database_flow(self, test_tenant_setup):
        """Test A2A get_products skill with real database query."""
        # Create A2A handler (minimal mocking)
        handler = AdCPRequestHandler()

        # Create realistic A2A message for get_products
        message = {
            "id": "test_message_001",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please get products for video advertising campaign targeting mobile users",
                        }
                    ],
                }
            },
        }

        # Mock authentication to use our test tenant
        with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
            with patch(
                "src.core.config_loader.get_current_tenant",
                return_value={"tenant_id": test_tenant_setup["tenant_id"], "name": "A2A Test Tenant"},
            ):
                with patch("src.core.main.get_principal_from_context", return_value=test_tenant_setup["principal_id"]):
                    with patch("src.core.main.get_principal_object") as mock_get_principal:
                        # Mock principal object
                        from src.core.schemas import Principal as PrincipalSchema

                        mock_principal = PrincipalSchema(
                            principal_id=test_tenant_setup["principal_id"],
                            name="Test Principal",
                            platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
                        )
                        mock_get_principal.return_value = mock_principal

                        # Test the handler - this should query real database
                        response = await handler._handle_get_products_skill(
                            parameters={
                                "brief": "video advertising campaign targeting mobile users",
                                "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                            },
                            auth_token="test_a2a_token_123",
                        )

                        # Validate response structure
                        assert isinstance(response, dict)
                        assert "products" in response

                        # Validate products came from real database
                        products = response["products"]
                        assert len(products) >= 1  # Should find at least one product

                        # Verify product structure (should be AdCP compliant)
                        for product in products:
                            assert "product_id" in product
                            assert "name" in product
                            assert "description" in product
                            assert "format_ids" in product  # AdCP spec field name
                            assert "delivery_type" in product

                            # Verify no internal fields leaked through
                            assert "targeting_template" not in product
                            assert "implementation_config" not in product
                            assert "tenant_id" not in product

                            # Verify fields that caused the original bug don't exist
                            assert "pricing" not in product  # This was the problematic field

                        # Find our test products
                        product_ids = [p["product_id"] for p in products]
                        assert "a2a_display_001" in product_ids or "a2a_video_001" in product_ids

    @pytest.mark.asyncio
    async def test_a2a_real_schema_validation(self, test_tenant_setup):
        """Test that A2A responses use real schema validation."""
        handler = AdCPRequestHandler()

        # Mock minimal auth context
        with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
            with patch(
                "src.core.config_loader.get_current_tenant",
                return_value={"tenant_id": test_tenant_setup["tenant_id"], "name": "A2A Test Tenant"},
            ):
                with patch("src.core.main.get_principal_from_context", return_value=test_tenant_setup["principal_id"]):
                    with patch("src.core.main.get_principal_object") as mock_get_principal:
                        from src.core.schemas import Principal as PrincipalSchema

                        mock_principal = PrincipalSchema(
                            principal_id=test_tenant_setup["principal_id"],
                            name="Test Principal",
                            platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
                        )
                        mock_get_principal.return_value = mock_principal

                        # Test get_products with real validation
                        response = await handler._handle_get_products_skill(
                            parameters={
                                "brief": "display advertising for sports content",
                                "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                            },
                            auth_token="test_a2a_token_123",
                        )

                        # Response should be valid JSON
                        json_str = json.dumps(response)
                        parsed = json.loads(json_str)
                        assert parsed == response

                        # Validate against expected AdCP schema structure
                        assert isinstance(parsed["products"], list)

                        for product in parsed["products"]:
                            # Required AdCP fields
                            required_fields = ["product_id", "name", "description", "format_ids", "delivery_type"]
                            for field in required_fields:
                                assert field in product, f"Missing required AdCP field: {field}"

                            # Verify types are JSON serializable
                            assert isinstance(product["product_id"], str)
                            assert isinstance(product["name"], str)
                            assert isinstance(product["description"], str)
                            assert isinstance(product["format_ids"], list)

                            # Verify no problematic fields
                            problematic_fields = ["pricing", "cost", "margin"]
                            for field in problematic_fields:
                                assert field not in product

    @pytest.mark.asyncio
    async def test_a2a_database_error_handling(self, test_tenant_setup):
        """Test A2A error handling with real database scenarios."""
        handler = AdCPRequestHandler()

        # Test 1: Invalid tenant (should handle gracefully)
        with patch.object(handler, "_get_auth_token", return_value="invalid_token"):
            with patch("src.core.config_loader.get_current_tenant", return_value=None):
                # This should not crash but handle the error
                try:
                    response = await handler._handle_get_products_skill(
                        parameters={
                            "brief": "test brief",
                            "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                        },
                        auth_token="test_a2a_token_123",
                    )
                    # Should return empty or error response, not crash
                    assert isinstance(response, dict)
                except Exception as e:
                    # If it raises an exception, it should be a handled one
                    assert "tenant" in str(e).lower() or "auth" in str(e).lower()

        # Test 2: Database connection issues (simulated)
        with patch("src.core.database.database_session.get_db_session") as mock_session:
            mock_session.side_effect = Exception("Database connection failed")

            with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
                try:
                    response = await handler._handle_get_products_skill(
                        parameters={
                            "brief": "test brief",
                            "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                        },
                        auth_token="test_a2a_token_123",
                    )
                    # Should handle database errors gracefully
                    assert isinstance(response, dict)
                except Exception as e:
                    # Should be a handled error (database or auth-related)
                    error_msg = str(e).lower()
                    assert any(
                        keyword in error_msg
                        for keyword in ["database", "connection", "authentication", "invalid", "missing"]
                    ), f"Unexpected error type: {e}"

    def test_a2a_handler_real_import_validation(self):
        """Test that A2A handler imports and functions are actually callable."""
        # Test imports work without mocking
        try:
            from src.a2a_server.adcp_a2a_server import AdCPRequestHandler, core_get_products_tool, create_agent_card
        except ImportError as e:
            pytest.fail(f"A2A server imports failed: {e}")

        # Test handler can be instantiated
        try:
            handler = AdCPRequestHandler()
            assert handler is not None
        except Exception as e:
            pytest.fail(f"A2A handler instantiation failed: {e}")

        # Test core functions are callable (this would catch .fn() bugs)
        try:
            assert callable(core_get_products_tool)
        except Exception as e:
            pytest.fail(f"Core function not callable: {e}")

        # Test agent card creation
        try:
            agent_card = create_agent_card()
            assert hasattr(agent_card, "name")
            assert hasattr(agent_card, "skills")
        except Exception as e:
            pytest.fail(f"Agent card creation failed: {e}")

    @pytest.mark.asyncio
    async def test_a2a_complete_request_cycle(self, test_tenant_setup):
        """Test complete A2A request cycle with real data."""
        handler = AdCPRequestHandler()

        # Simulate complete A2A message/request flow
        request_data = {
            "messageId": "test_msg_123",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Find display advertising products for sports content"}],
                }
            },
        }

        # Mock authentication for the complete flow
        with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
            with patch(
                "src.core.config_loader.get_current_tenant",
                return_value={"tenant_id": test_tenant_setup["tenant_id"], "name": "A2A Test Tenant"},
            ):
                with patch("src.core.main.get_principal_from_context", return_value=test_tenant_setup["principal_id"]):
                    with patch("src.core.main.get_principal_object") as mock_get_principal:
                        from src.core.schemas import Principal as PrincipalSchema

                        mock_principal = PrincipalSchema(
                            principal_id=test_tenant_setup["principal_id"],
                            name="Test Principal",
                            platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
                        )
                        mock_get_principal.return_value = mock_principal

                        # Test the complete message handling
                        try:
                            # Create proper MessageSendParams object with correct A2A format
                            from a2a.types import Message, MessageSendParams, Part, Role

                            params = MessageSendParams(
                                message=Message(
                                    message_id="test_msg_123",
                                    context_id="test_ctx_123",
                                    role=Role.user,
                                    parts=[Part(text="Find display advertising products for sports content")],
                                )
                            )

                            # This exercises the full A2A pipeline including skill detection
                            response = await handler.on_message_send(params)

                            # Validate response structure - can be Task or Message
                            assert response is not None

                            # Convert to dict for inspection if it's not already
                            if hasattr(response, "model_dump"):
                                response_dict = response.model_dump()
                            elif hasattr(response, "__dict__"):
                                response_dict = response.__dict__
                            else:
                                response_dict = response

                            # Response should contain actual data from database
                            response_str = str(response_dict)
                            assert (
                                "display" in response_str.lower()
                                or "product" in response_str.lower()
                                or "content" in response_str.lower()
                            )

                        except Exception as e:
                            pytest.fail(f"Complete A2A request cycle failed: {e}")

    @pytest.mark.asyncio
    async def test_a2a_field_access_regression_prevention(self, test_tenant_setup):
        """Specific test to prevent the 'pricing' field access regression."""
        handler = AdCPRequestHandler()

        # This test specifically targets the scenario that caused the original bug
        with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
            with patch(
                "src.core.config_loader.get_current_tenant",
                return_value={"tenant_id": test_tenant_setup["tenant_id"], "name": "A2A Test Tenant"},
            ):
                with patch("src.core.main.get_principal_from_context", return_value=test_tenant_setup["principal_id"]):
                    with patch("src.core.main.get_principal_object") as mock_get_principal:
                        from src.core.schemas import Principal as PrincipalSchema

                        mock_principal = PrincipalSchema(
                            principal_id=test_tenant_setup["principal_id"],
                            name="Test Principal",
                            platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
                        )
                        mock_get_principal.return_value = mock_principal

                        # Call get_products - this would fail if 'pricing' field is accessed
                        response = await handler._handle_get_products_skill(
                            parameters={
                                "brief": "test campaign",
                                "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                            },
                            auth_token="test_a2a_token_123",
                        )

                        # If we get here without AttributeError, the bug is prevented
                        assert isinstance(response, dict)
                        assert "products" in response

                        # Double-check that no problematic fields are in response
                        for product in response["products"]:
                            forbidden_fields = ["pricing", "cost_basis", "margin", "profit"]
                            for field in forbidden_fields:
                                assert field not in product, (
                                    f"Forbidden field '{field}' found in product response. "
                                    f"This indicates a field access bug similar to the original 'pricing' issue."
                                )

    @pytest.mark.asyncio
    async def test_a2a_database_model_conversion_validation(self, test_tenant_setup):
        """Test that database models convert to schemas correctly in A2A context."""
        handler = AdCPRequestHandler()

        # Verify our test products exist in database first
        with get_db_session() as session:
            db_products = session.query(ProductModel).filter_by(tenant_id=test_tenant_setup["tenant_id"]).all()

            assert len(db_products) >= 1, "Test products not found in database"

            # Test that each database product can be converted safely
            for db_product in db_products:
                # Test direct field access (what the conversion code does)
                assert hasattr(db_product, "product_id")
                assert hasattr(db_product, "name")
                assert hasattr(db_product, "description")
                assert hasattr(db_product, "formats")
                assert hasattr(db_product, "cpm")
                assert hasattr(db_product, "min_spend")

                # Test that problematic fields don't exist
                assert not hasattr(db_product, "pricing")
                assert not hasattr(db_product, "format_ids")  # Schema property, not DB field

                # Test safe value access
                product_id = db_product.product_id
                name = db_product.name
                cpm = db_product.cpm
                min_spend = db_product.min_spend

                assert product_id is not None
                assert name is not None
                # cpm and min_spend can be None, that's OK

        # Now test the complete A2A flow
        with patch.object(handler, "_get_auth_token", return_value=test_tenant_setup["access_token"]):
            with patch(
                "src.core.config_loader.get_current_tenant",
                return_value={"tenant_id": test_tenant_setup["tenant_id"], "name": "A2A Test Tenant"},
            ):
                with patch("src.core.main.get_principal_from_context", return_value=test_tenant_setup["principal_id"]):
                    with patch("src.core.main.get_principal_object") as mock_get_principal:
                        from src.core.schemas import Principal as PrincipalSchema

                        mock_principal = PrincipalSchema(
                            principal_id=test_tenant_setup["principal_id"],
                            name="Test Principal",
                            platform_mappings={"mock": {"advertiser_id": "test_advertiser"}},
                        )
                        mock_get_principal.return_value = mock_principal

                        # This exercises the real database → schema conversion
                        response = await handler._handle_get_products_skill(
                            parameters={
                                "brief": "test campaign",
                                "promoted_offering": "Nike Air Jordan 2025 basketball shoes",
                            },
                            auth_token="test_a2a_token_123",
                        )

                        # Verify successful conversion
                        assert "products" in response
                        products = response["products"]
                        assert len(products) >= 1

                        # Each product should be properly converted
                        for product in products:
                            # Should have AdCP schema fields
                            assert "product_id" in product
                            assert "name" in product
                            assert "format_ids" in product  # AdCP field name (not 'formats')

                            # Should not have database internal fields
                            assert "tenant_id" not in product
                            assert "targeting_template" not in product
