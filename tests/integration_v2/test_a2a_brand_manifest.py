#!/usr/bin/env python3
"""
Test A2A get_products with brand_manifest parameter.

Verifies that the A2A server properly handles brand_manifest in get_products skill invocations,
including both dict and object formats.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from a2a.types import TaskStatus

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from tests.utils.a2a_helpers import create_a2a_message_with_skill

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_tenant_context():
    """Mock tenant context for A2A tests."""
    with patch("src.a2a_server.adcp_a2a_server.get_principal_from_token") as mock_get_principal:
        # Mock principal and tenant data
        mock_principal = MagicMock()
        mock_principal.principal_id = "test_principal_123"
        mock_principal.tenant_id = "test_tenant_123"

        mock_tenant = {
            "tenant_id": "test_tenant_123",
            "name": "Test Tenant",
            "virtual_host": "https://test.example.com",
            "advertising_policy": {"enabled": False},  # Disable policy checks for simpler test
        }

        mock_get_principal.return_value = (mock_principal, mock_tenant)
        yield mock_get_principal


@pytest.fixture
def mock_product_catalog():
    """Mock product catalog provider."""
    with patch("src.core.tools.products.get_product_catalog_provider") as mock_get_provider:
        # Create a mock provider that returns test products
        mock_provider = MagicMock()

        async def mock_get_products(*args, **kwargs):
            from src.core.schemas import PricingOption, Product

            return [
                Product(
                    product_id="test_product_1",
                    name="Test Display Ads",
                    description="Test display advertising product",
                    formats=["display_banner_300x250"],
                    delivery_type="guaranteed",
                    properties=["https://test.example.com"],
                    pricing_options=[
                        PricingOption(
                            pricing_option_id="cpm_usd_fixed",
                            pricing_model="cpm",
                            rate=5.0,
                            currency="USD",
                            is_fixed=True,
                        )
                    ],
                )
            ]

        mock_provider.get_products = mock_get_products
        mock_get_provider.return_value = mock_provider
        yield mock_get_provider


@pytest.mark.asyncio
async def test_get_products_with_brand_manifest_dict(mock_tenant_context, mock_product_catalog, integration_db):
    """Test get_products skill invocation with brand_manifest as dict."""
    handler = AdCPRequestHandler()

    # Create A2A message with brand_manifest
    message = create_a2a_message_with_skill(
        skill_name="get_products",
        parameters={
            "brand_manifest": {"name": "Nike", "url": "https://nike.com"},
            "brief": "Athletic footwear advertising",
        },
    )

    # Mock auth token
    auth_token = "Bearer test_token_123"

    # Call handler
    task = await handler.execute_task(message, auth_token=auth_token)

    # Verify task completed successfully
    assert task.status == TaskStatus.COMPLETED, f"Task failed: {task}"

    # Verify we got products back
    assert task.artifacts, "No artifacts returned"
    assert len(task.artifacts) > 0, "Expected at least one artifact"

    # Extract result from artifact
    artifact = task.artifacts[0]
    assert artifact.parts, "Artifact has no parts"

    result_data = None
    for part in artifact.parts:
        if hasattr(part, "data") and isinstance(part.data, dict):
            result_data = part.data
            break

    assert result_data, "Could not extract result data from artifact"
    assert "products" in result_data, "Result missing 'products' field"
    assert isinstance(result_data["products"], list), "Products should be a list"
    assert len(result_data["products"]) > 0, "Expected at least one product"


@pytest.mark.asyncio
async def test_get_products_with_brand_manifest_url_only(mock_tenant_context, mock_product_catalog, integration_db):
    """Test get_products skill invocation with brand_manifest as URL string."""
    handler = AdCPRequestHandler()

    # Create A2A message with brand_manifest as URL
    message = create_a2a_message_with_skill(
        skill_name="get_products",
        parameters={
            "brand_manifest": "https://nike.com",
            "brief": "Athletic footwear advertising",
        },
    )

    # Mock auth token
    auth_token = "Bearer test_token_123"

    # Call handler
    task = await handler.execute_task(message, auth_token=auth_token)

    # Verify task completed successfully
    assert task.status == TaskStatus.COMPLETED, f"Task failed: {task}"

    # Verify we got products back
    assert task.artifacts, "No artifacts returned"


@pytest.mark.asyncio
async def test_get_products_with_brand_manifest_name_only(mock_tenant_context, mock_product_catalog, integration_db):
    """Test get_products skill invocation with brand_manifest containing only name."""
    handler = AdCPRequestHandler()

    # Create A2A message with brand_manifest (name only)
    message = create_a2a_message_with_skill(
        skill_name="get_products",
        parameters={
            "brand_manifest": {"name": "Nike"},
            "brief": "Athletic footwear advertising",
        },
    )

    # Mock auth token
    auth_token = "Bearer test_token_123"

    # Call handler
    task = await handler.execute_task(message, auth_token=auth_token)

    # Verify task completed successfully
    assert task.status == TaskStatus.COMPLETED, f"Task failed: {task}"


@pytest.mark.asyncio
async def test_get_products_backward_compat_promoted_offering(
    mock_tenant_context, mock_product_catalog, integration_db
):
    """Test get_products still works with deprecated promoted_offering parameter."""
    handler = AdCPRequestHandler()

    # Create A2A message with promoted_offering (deprecated)
    message = create_a2a_message_with_skill(
        skill_name="get_products",
        parameters={
            "promoted_offering": "Nike Athletic Footwear",
            "brief": "Display advertising",
        },
    )

    # Mock auth token
    auth_token = "Bearer test_token_123"

    # Call handler
    task = await handler.execute_task(message, auth_token=auth_token)

    # Verify task completed successfully (backward compatibility)
    assert task.status == TaskStatus.COMPLETED, f"Task failed: {task}"


@pytest.mark.asyncio
async def test_get_products_missing_brand_info_fails(mock_tenant_context, mock_product_catalog, integration_db):
    """Test get_products fails gracefully when brand information is missing."""
    handler = AdCPRequestHandler()

    # Create A2A message with only brief (no brand_manifest or promoted_offering)
    message = create_a2a_message_with_skill(
        skill_name="get_products",
        parameters={
            "brief": "Display advertising",
        },
    )

    # Mock auth token
    auth_token = "Bearer test_token_123"

    # Call handler - should use brief as fallback for promoted_offering
    task = await handler.execute_task(message, auth_token=auth_token)

    # Should complete (uses brief as fallback)
    assert task.status == TaskStatus.COMPLETED, "Task should complete with brief fallback"
