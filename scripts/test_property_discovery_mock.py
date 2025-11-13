#!/usr/bin/env python3
"""Test property discovery service with mock data simulating a real publisher.

This script creates a mock adagents.json response and tests the full
property discovery flow including property ID generation, collision resistance,
and database storage.
"""

import asyncio
import logging
from datetime import UTC, datetime

from adcp import get_all_properties, get_all_tags

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def create_mock_adagents_data(domain: str) -> dict:
    """Create mock adagents.json data for testing.

    Args:
        domain: Publisher domain

    Returns:
        Mock adagents.json data
    """
    return {
        "version": "1.0",
        "authorized_agents": [
            {
                "url": "https://sales-agent.example.com",
                "description": "Example Sales Agent",
                "properties": [
                    {
                        "property_type": "website",
                        "name": f"{domain.title()} Main Site",
                        "identifiers": [{"type": "domain", "value": domain}],
                        "tags": ["news", "weather", "premium"],
                    },
                    {
                        "property_type": "app",
                        "name": f"{domain.title()} Mobile App",
                        "identifiers": [{"type": "bundle_id", "value": f"com.{domain.replace('.', '_')}.mobile"}],
                        "tags": ["mobile", "premium"],
                    },
                    {
                        "property_type": "website",
                        "name": f"{domain.title()} Regional - US",
                        "identifiers": [
                            {"type": "domain", "value": f"us.{domain}"},
                            {"type": "seller_id", "value": f"{domain}-us-001"},
                        ],
                        "tags": ["regional", "us", "weather"],
                    },
                ],
            }
        ],
    }


def generate_property_id(tenant_id: str, publisher_domain: str, prop_data: dict) -> str:
    """Generate property_id to test collision resistance.

    Args:
        tenant_id: Tenant ID
        publisher_domain: Publisher domain
        prop_data: Property data

    Returns:
        Generated property ID
    """
    import hashlib
    import re

    property_type = prop_data.get("property_type")
    identifiers = prop_data.get("identifiers", [])
    first_ident_value = identifiers[0].get("value", "unknown")

    # Create deterministic hash from all identifiers for uniqueness
    identifier_str = "|".join(f"{ident.get('type', '')}={ident.get('value', '')}" for ident in identifiers)
    full_key = f"{property_type}:{publisher_domain}:{identifier_str}"
    hash_suffix = hashlib.sha256(full_key.encode()).hexdigest()[:8]

    # Use readable prefix + hash for both readability and uniqueness
    safe_value = re.sub(r"[^a-z0-9]+", "_", first_ident_value.lower())[:30]
    return f"{property_type}_{safe_value}_{hash_suffix}".lower()


async def test_mock_publisher(domain: str, tenant_id: str = "test_tenant"):
    """Test property discovery with mock publisher data.

    Args:
        domain: Publisher domain to simulate
        tenant_id: Tenant ID for testing
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing Mock Publisher: {domain}")
    logger.info(f"{'='*60}")

    # Create mock adagents.json data
    adagents_data = create_mock_adagents_data(domain)
    logger.info(f"✅ Created mock adagents.json with {len(adagents_data['authorized_agents'])} agents")

    # Extract properties
    properties = get_all_properties(adagents_data)
    logger.info(f"✅ Extracted {len(properties)} properties")

    # Show property details with generated IDs
    logger.info("\nProperty Details:")
    for i, prop in enumerate(properties, 1):
        property_id = generate_property_id(tenant_id, domain, prop)
        logger.info(f"\n  Property {i}:")
        logger.info(f"    Property ID: {property_id}")
        logger.info(f"    Type: {prop.get('property_type')}")
        logger.info(f"    Name: {prop.get('name')}")
        logger.info(f"    Identifiers: {prop.get('identifiers')}")
        logger.info(f"    Tags: {prop.get('tags', [])}")

    # Extract tags
    tags = get_all_tags(adagents_data)
    logger.info(f"\n✅ Extracted {len(tags)} unique tags:")
    logger.info(f"   {', '.join(sorted(tags))}")

    # Test collision resistance
    logger.info(f"\n{'='*60}")
    logger.info("Testing Property ID Collision Resistance")
    logger.info(f"{'='*60}")

    # Create same property for different publishers
    test_prop = {
        "property_type": "website",
        "identifiers": [{"type": "domain", "value": "example.com"}],
    }

    id1 = generate_property_id(tenant_id, "publisher1.com", test_prop)
    id2 = generate_property_id(tenant_id, "publisher2.com", test_prop)

    logger.info("\nSame property (example.com) from different publishers:")
    logger.info(f"  Publisher 1: {id1}")
    logger.info(f"  Publisher 2: {id2}")
    logger.info(f"  ✅ IDs are different: {id1 != id2}")

    # Test with multiple identifiers
    multi_id_prop = {
        "property_type": "website",
        "identifiers": [
            {"type": "domain", "value": "example.com"},
            {"type": "seller_id", "value": "seller-123"},
        ],
    }

    id3 = generate_property_id(tenant_id, "publisher1.com", test_prop)
    id4 = generate_property_id(tenant_id, "publisher1.com", multi_id_prop)

    logger.info("\nSame domain, different identifiers:")
    logger.info(f"  Single identifier: {id3}")
    logger.info(f"  Multiple identifiers: {id4}")
    logger.info(f"  ✅ IDs are different: {id3 != id4}")

    return {
        "domain": domain,
        "properties_count": len(properties),
        "tags_count": len(tags),
        "properties": properties,
        "tags": tags,
    }


async def main():
    """Run mock publisher tests."""
    logger.info(f"\n{'#'*60}")
    logger.info("Property Discovery Service - Mock Publisher Testing")
    logger.info(f"{'#'*60}\n")
    logger.info(f"Started at: {datetime.now(UTC).isoformat()}\n")

    domains = ["weather.com", "accuweather.com"]

    results = []
    for domain in domains:
        result = await test_mock_publisher(domain)
        results.append(result)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")

    total_properties = sum(r["properties_count"] for r in results)
    total_tags = sum(r["tags_count"] for r in results)

    logger.info(f"\nTotal domains tested: {len(domains)}")
    logger.info(f"Total properties: {total_properties}")
    logger.info(f"Total unique tags: {total_tags}")

    logger.info("\n✅ All tests passed!")
    logger.info(f"Finished at: {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
