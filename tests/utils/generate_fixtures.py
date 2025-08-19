#!/usr/bin/env python3
"""
Utility to generate test fixtures and sample data.

Usage:
    python tests/utils/generate_fixtures.py --type tenant --count 5
    python tests/utils/generate_fixtures.py --scenario complete --output fixtures.json
"""

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.fixtures import CreativeFactory, MediaBuyFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.fixtures.builders import TargetingBuilder, TestDataBuilder


class FixtureGenerator:
    """Generate test fixtures and sample data."""

    def __init__(self):
        """Initialize generator."""
        self.factories = {
            "tenant": TenantFactory,
            "principal": PrincipalFactory,
            "product": ProductFactory,
            "media_buy": MediaBuyFactory,
            "creative": CreativeFactory,
        }

    def generate_single(self, fixture_type: str, **kwargs) -> dict:
        """Generate a single fixture."""
        if fixture_type not in self.factories:
            raise ValueError(f"Unknown fixture type: {fixture_type}")

        factory = self.factories[fixture_type]
        return factory.create(**kwargs)

    def generate_batch(self, fixture_type: str, count: int, **kwargs) -> list:
        """Generate multiple fixtures."""
        if fixture_type not in self.factories:
            raise ValueError(f"Unknown fixture type: {fixture_type}")

        factory = self.factories[fixture_type]

        if hasattr(factory, "create_batch"):
            return factory.create_batch(count, **kwargs)
        else:
            return [factory.create(**kwargs) for _ in range(count)]

    def generate_complete_scenario(self, name: str = "Test Scenario") -> dict:
        """Generate a complete test scenario."""
        TestDataBuilder()

        # Create tenant
        tenant = TenantFactory.create(name=f"{name} Publisher", subdomain=name.lower().replace(" ", "-"))

        # Create principals (advertisers)
        principals = [
            PrincipalFactory.create(tenant_id=tenant["tenant_id"], name=f"{name} Advertiser {i+1}") for i in range(3)
        ]

        # Create products
        products = [
            ProductFactory.create(
                tenant_id=tenant["tenant_id"], name="Display Product", formats=["display_300x250", "display_728x90"]
            ),
            ProductFactory.create_video_product(tenant_id=tenant["tenant_id"], name="Video Product"),
            ProductFactory.create(
                tenant_id=tenant["tenant_id"],
                name="Native Product",
                formats=["native_content"],
                inventory_type="native",
            ),
        ]

        # Create media buys
        media_buys = []
        for principal in principals[:2]:  # First 2 principals have active campaigns
            buy = MediaBuyFactory.create_active(
                tenant_id=tenant["tenant_id"],
                principal_id=principal["principal_id"],
                total_budget=random.randint(5000, 25000),
            )
            media_buys.append(buy)

        # Create creatives
        creatives = []
        for principal in principals[:2]:
            for format_id in ["display_300x250", "display_728x90", "video_16x9"]:
                creative = CreativeFactory.create_approved(
                    tenant_id=tenant["tenant_id"], principal_id=principal["principal_id"], format_id=format_id
                )
                creatives.append(creative)

        return {
            "scenario_name": name,
            "tenant": tenant,
            "principals": principals,
            "products": products,
            "media_buys": media_buys,
            "creatives": creatives,
            "created_at": datetime.utcnow().isoformat(),
        }

    def generate_performance_dataset(self, size: str = "medium") -> dict:
        """Generate dataset for performance testing."""
        sizes = {
            "small": {"tenants": 1, "principals": 5, "products": 10, "media_buys": 20},
            "medium": {"tenants": 5, "principals": 25, "products": 50, "media_buys": 100},
            "large": {"tenants": 20, "principals": 100, "products": 200, "media_buys": 500},
            "xlarge": {"tenants": 100, "principals": 500, "products": 1000, "media_buys": 2500},
        }

        if size not in sizes:
            raise ValueError(f"Unknown size: {size}. Choose from: {list(sizes.keys())}")

        config = sizes[size]

        print(f"Generating {size} dataset...")

        # Generate tenants
        tenants = TenantFactory.create_batch(config["tenants"])

        # Generate principals distributed across tenants
        principals = []
        principals_per_tenant = config["principals"] // config["tenants"]
        for tenant in tenants:
            tenant_principals = PrincipalFactory.create_batch(principals_per_tenant, tenant_id=tenant["tenant_id"])
            principals.extend(tenant_principals)

        # Generate products distributed across tenants
        products = []
        products_per_tenant = config["products"] // config["tenants"]
        for tenant in tenants:
            tenant_products = ProductFactory.create_batch(products_per_tenant, tenant_id=tenant["tenant_id"])
            products.extend(tenant_products)

        # Generate media buys distributed across principals
        media_buys = []
        buys_per_principal = config["media_buys"] // len(principals)
        for principal in principals:
            principal_buys = MediaBuyFactory.create_batch(
                buys_per_principal, tenant_id=principal["tenant_id"], principal_id=principal["principal_id"]
            )
            media_buys.extend(principal_buys)

        return {
            "size": size,
            "stats": config,
            "tenants": tenants,
            "principals": principals,
            "products": products,
            "media_buys": media_buys,
            "created_at": datetime.utcnow().isoformat(),
        }

    def generate_edge_cases(self) -> dict:
        """Generate edge case test data."""
        cases = {}

        # Empty/minimal data
        cases["empty_tenant"] = TenantFactory.create(config={}, name="", subdomain="")

        # Maximum length data
        cases["max_length_product"] = ProductFactory.create(
            name="A" * 255,
            formats=["display_300x250"] * 20,  # Many formats
            targeting_template=TargetingBuilder().build_comprehensive(),
        )

        # Special characters
        cases["special_chars_principal"] = PrincipalFactory.create(
            name="Test & Co. <script>alert('xss')</script>", access_token="token-with-special-chars-!@#$%^&*()"
        )

        # Extreme values
        cases["extreme_budget_buy"] = MediaBuyFactory.create(total_budget=0.01, spent_amount=0.01)  # Minimum

        cases["huge_budget_buy"] = MediaBuyFactory.create(
            total_budget=999999999.99, spent_amount=500000000.00  # Maximum
        )

        # Date edge cases
        cases["past_dates_buy"] = MediaBuyFactory.create(
            flight_start_date=(datetime.utcnow() - timedelta(days=365)).date(),
            flight_end_date=(datetime.utcnow() - timedelta(days=300)).date(),
        )

        cases["far_future_buy"] = MediaBuyFactory.create(
            flight_start_date=(datetime.utcnow() + timedelta(days=365)).date(),
            flight_end_date=(datetime.utcnow() + timedelta(days=730)).date(),
        )

        # Invalid/malformed data
        cases["invalid_json_config"] = {
            "tenant_id": "test",
            "config": "not-a-json-string",
            "platform_mappings": "{'invalid': json}",
        }

        return cases

    def generate_targeting_samples(self) -> dict:
        """Generate various targeting configuration samples."""
        builder = TargetingBuilder()

        samples = {
            "minimal": builder.build_minimal(),
            "comprehensive": builder.build_comprehensive(),
            "geo_only": builder.with_geo(
                countries=["US", "CA", "MX"], regions=["CA", "TX", "NY"], cities=["New York", "Los Angeles", "Chicago"]
            ).build(),
            "demographic_focused": TargetingBuilder()
            .with_demographics(
                age_ranges=["18-24", "25-34", "35-44"],
                genders=["male", "female"],
                income_ranges=["50k-75k", "75k-100k", "100k+"],
            )
            .build(),
            "device_specific": TargetingBuilder()
            .with_devices(types=["mobile", "tablet"], os=["ios", "android"], browsers=["safari", "chrome"])
            .build(),
            "content_targeted": TargetingBuilder()
            .with_content(
                categories=["news", "sports", "entertainment"],
                keywords=["olympics", "football", "basketball"],
                topics=["sports", "fitness", "health"],
            )
            .build(),
            "signal_based": TargetingBuilder()
            .with_signals(["auto_intenders_q1_2025", "travel_enthusiasts", "luxury_shoppers", "sports_fans"])
            .build(),
        }

        return samples


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate test fixtures")

    parser.add_argument(
        "--type",
        choices=[
            "tenant",
            "principal",
            "product",
            "media_buy",
            "creative",
            "scenario",
            "performance",
            "edge_cases",
            "targeting",
        ],
        help="Type of fixture to generate",
    )

    parser.add_argument("--count", type=int, default=1, help="Number of fixtures to generate")

    parser.add_argument(
        "--size", choices=["small", "medium", "large", "xlarge"], default="medium", help="Size for performance dataset"
    )

    parser.add_argument("--output", help="Output file path (JSON)")

    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")

    args = parser.parse_args()

    generator = FixtureGenerator()

    # Generate fixtures based on type
    if args.type == "scenario":
        data = generator.generate_complete_scenario("Test Scenario")
    elif args.type == "performance":
        data = generator.generate_performance_dataset(args.size)
    elif args.type == "edge_cases":
        data = generator.generate_edge_cases()
    elif args.type == "targeting":
        data = generator.generate_targeting_samples()
    elif args.type:
        if args.count > 1:
            data = generator.generate_batch(args.type, args.count)
        else:
            data = generator.generate_single(args.type)
    else:
        # Generate sample of everything
        data = {
            "tenant": generator.generate_single("tenant"),
            "principal": generator.generate_single("principal"),
            "product": generator.generate_single("product"),
            "media_buy": generator.generate_single("media_buy"),
            "creative": generator.generate_single("creative"),
            "targeting": generator.generate_targeting_samples(),
        }

    # Output results
    json_str = json.dumps(data, indent=2 if args.pretty else None, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str)
        print(f"✅ Fixtures saved to: {output_path}")
    else:
        print(json_str)

    # Print summary
    if not args.output or args.type == "performance":
        print("\n📊 Summary:")
        if isinstance(data, list):
            print(f"  Generated {len(data)} fixtures")
        elif isinstance(data, dict):
            if "stats" in data:
                for key, value in data["stats"].items():
                    print(f"  {key}: {value}")
            else:
                for key, value in data.items():
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} items")
                    elif isinstance(value, dict):
                        print(f"  {key}: {len(value)} fields")


if __name__ == "__main__":
    main()
