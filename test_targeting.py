#!/usr/bin/env python3
"""Quick test of the targeting system."""

from schemas import Targeting, Dayparting, DaypartSchedule, FrequencyCap
from targeting_utils import TargetingValidator, TargetingMapper
import json

# Create a comprehensive targeting example
targeting = Targeting(
    geography=["US", "US-CA", "DMA-501", "city:New York,NY", "postal:10001"],
    geography_exclude=["US-TX"],
    device_types=["mobile", "desktop", "ctv"],
    platforms=["ios", "android"],
    browsers=["chrome", "safari"],
    content_categories_include=["IAB17", "IAB19"],
    content_categories_exclude=["IAB7"],
    keywords_include=["sports", "technology"],
    keywords_exclude=["gambling"],
    audiences=["3p:sports_fans", "behavior:early_adopters"],
    dayparting=Dayparting(
        timezone="America/New_York",
        schedules=[
            DaypartSchedule(
                days=[1, 2, 3, 4, 5],
                start_hour=6,
                end_hour=10
            )
        ],
        presets=["drive_time_evening"]
    ),
    frequency_cap=FrequencyCap(
        impressions=5,
        period="day",
        per="user"
    )
)

print("Testing Targeting System")
print("=" * 50)

# Test validation
print("\n1. Validating targeting...")
issues = TargetingValidator.validate_targeting(targeting)
if issues:
    print(f"Validation issues: {json.dumps(issues, indent=2)}")
else:
    print("✓ All targeting parameters valid")

# Test geographic validation
print("\n2. Validating geography...")
geo_data = TargetingValidator.validate_geography(targeting.geography)
print(f"Geographic breakdown:")
print(f"  Countries: {geo_data['countries']}")
print(f"  States: {geo_data['states']}")
print(f"  DMAs: {geo_data['dmas']}")
print(f"  Cities: {geo_data['cities']}")
print(f"  Postal codes: {geo_data['postal_codes']}")

# Test platform mapping
print("\n3. Testing platform mappings...")

# GAM
print("\n  Google Ad Manager:")
gam_targeting = TargetingMapper.to_gam_targeting(targeting)
print(f"  Keys: {list(gam_targeting.keys())}")

# Kevel
print("\n  Kevel:")
kevel_targeting = TargetingMapper.to_kevel_targeting(targeting)
print(f"  Keys: {list(kevel_targeting.keys())}")

# Triton
print("\n  Triton Digital:")
triton_targeting = TargetingMapper.to_triton_targeting(targeting)
print(f"  Keys: {list(triton_targeting.keys())}")

# Test compatibility
print("\n4. Testing platform compatibility...")
for platform in ['google_ad_manager', 'kevel', 'triton_digital']:
    compat = TargetingMapper.check_platform_compatibility(targeting, platform)
    print(f"\n  {platform}:")
    if compat['unsupported']:
        print(f"    Unsupported: {compat['unsupported']}")
    if compat['warnings']:
        print(f"    Warnings: {compat['warnings']}")
    if not compat['unsupported'] and not compat['warnings']:
        print("    ✓ Fully compatible")

print("\n✓ Targeting system test complete!")