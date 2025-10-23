#!/usr/bin/env python3
"""Test to see if the AI provider has the Product validation bug."""

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

# Enable debug logging
logging.basicConfig(level=logging.INFO)

from product_catalog_providers.ai import AIProductCatalog

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


async def test_ai_provider_bug(integration_db):
    """Test if the AI provider has Product validation issues."""

    print("🔍 Testing AI provider for Product validation bug...")

    # First, let's create a problematic product in the database to test with
    # This simulates what might be causing the issue on the external server

    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from src.core.database.database_session import get_db_session
    from src.core.database.models import PricingOption, Tenant
    from src.core.database.models import Product as ProductModel

    with get_db_session() as session:
        # Create test tenant first
        now = datetime.now(UTC)
        tenant = Tenant(
            tenant_id="test_ai_bug",
            name="Test AI Bug Tenant",
            subdomain="test-ai-bug",
            ad_server="mock",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(tenant)

        # Create a test product with potentially problematic format data
        test_product = ProductModel(
            tenant_id="test_ai_bug",
            product_id="test_audio_bug",
            name="Test Audio Product",
            description="Test product to reproduce bug",
            formats=["audio_15s", "audio_30s"],  # JSONType expects list, not json.dumps()
            targeting_template={},
            delivery_type="guaranteed",
            is_custom=False,
            property_tags=["all_inventory"],  # Required: products must have properties OR property_tags
        )
        session.add(test_product)

        # Create pricing option (replaces old is_fixed_price + cpm fields)
        pricing_option = PricingOption(
            tenant_id="test_ai_bug",
            product_id="test_audio_bug",
            pricing_model="cpm",
            rate=Decimal("10.0"),
            currency="USD",
            is_fixed=True,
        )
        session.add(pricing_option)

        session.commit()
        print("   ✅ Created test tenant, product, and pricing option")

    try:
        # Test the AI provider
        config = {"model": "gemini-flash-latest", "max_products": 5}
        provider = AIProductCatalog(config)

        products = await provider.get_products(
            brief="test audio campaign",
            tenant_id="test_ai_bug",
            principal_id="test_principal",
            context={"brand_manifest": {"name": "test"}},
            principal_data={},
        )

        print(f"   ✅ AI provider returned {len(products)} products")

        # Check if any product has the validation issue
        for _i, product in enumerate(products):
            product_dict = product.model_dump()
            if product.product_id == "test_audio_bug":
                print(f"   🔍 Found test product: {product.product_id}")
                print(f"   📊 Product data: {json.dumps(product_dict, indent=2)}")

                # Check if audio fields leaked as top-level keys
                if "audio_15s" in product_dict or "audio_30s" in product_dict:
                    print("   ❌ BUG FOUND: Audio format fields are top-level Product keys!")
                    return False
                else:
                    print("   ✅ No audio fields as top-level keys")

    except Exception as e:
        print(f"   ❌ AI provider failed with error: {e}")
        import traceback

        traceback.print_exc()

        # Check if this is the specific validation error we're looking for
        if "Field required" in str(e) and "formats" in str(e):
            print("   🎯 This matches the original validation error!")
            return False

    finally:
        # Clean up test tenant (products and pricing options cascade delete automatically)
        with get_db_session() as session:
            test_tenant = session.scalars(select(Tenant).filter_by(tenant_id="test_ai_bug")).first()
            if test_tenant:
                session.delete(test_tenant)
                session.commit()
                print("   🧹 Cleaned up test tenant, product, and pricing options")

    print("   ✅ AI provider test completed without reproducing the bug")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_ai_provider_bug())
    sys.exit(0 if success else 1)
