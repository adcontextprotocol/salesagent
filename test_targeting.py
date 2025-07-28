#!/usr/bin/env python3
"""Quick test of the targeting system with OpenRTB-aligned schema."""

from schemas import Targeting, Dayparting, DaypartSchedule, FrequencyCap
from targeting_utils import TargetingValidator, TargetingMapper, DEVICE_TYPES, MEDIA_TYPES
import json

# Create a comprehensive targeting example using new schema
targeting = Targeting(
    # Geographic targeting
    geo_country_any_of=["US", "CA"],
    geo_region_any_of=["CA", "NY", "ON"],  # California, New York, Ontario
    geo_metro_any_of=["501", "803"],  # New York DMA, Los Angeles DMA
    geo_city_any_of=["New York", "Los Angeles", "Toronto"],
    geo_zip_any_of=["10001", "90210"],
    geo_country_none_of=["MX"],  # Exclude Mexico
    
    # Device and platform targeting (using OpenRTB device type IDs)
    device_type_any_of=[1, 2, 3],  # Mobile/Tablet, PC, CTV
    device_type_none_of=[7],  # No Set Top Box
    os_any_of=["iOS", "Android"],
    browser_any_of=["Chrome", "Safari"],
    
    # Media type targeting
    media_type_any_of=["video", "display"],
    
    # Content and audience targeting
    content_cat_any_of=["IAB17", "IAB19"],  # Sports, Technology
    content_cat_none_of=["IAB7", "IAB14"],  # Health, Society
    keywords_any_of=["sports", "technology", "innovation"],
    keywords_none_of=["gambling", "controversy"],
    audiences_any_of=["3p:sports_fans", "behavior:early_adopters"],
    
    # Time-based targeting
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
    
    # Frequency capping
    frequency_cap=FrequencyCap(
        impressions=5,
        period="day",
        per="user"
    ),
    
    # Connection type targeting (WiFi and 4G/5G)
    connection_type_any_of=[2, 6, 7]
)

print("Testing OpenRTB-Aligned Targeting System")
print("=" * 50)

# Test validation
print("\n1. Validating targeting...")
issues = TargetingValidator.validate_targeting(targeting)
if issues:
    print(f"Validation issues: {json.dumps(issues, indent=2)}")
else:
    print("✓ All targeting parameters valid")

# Show OpenRTB device types
print("\n2. Device Type Mapping (OpenRTB 2.6):")
for device_id in targeting.device_type_any_of:
    print(f"  {device_id}: {DEVICE_TYPES[device_id]}")

# Show media types
print("\n3. Media Types:")
print(f"  Included: {targeting.media_type_any_of}")

# Test platform mappings
print("\n4. Testing platform mappings...")

# GAM
print("\n  Google Ad Manager:")
gam_targeting = TargetingMapper.to_gam_targeting(targeting)
if gam_targeting:
    print(f"  Targeting keys: {list(gam_targeting.keys())}")
    if 'technologyTargeting' in gam_targeting:
        print(f"  Device categories: {gam_targeting['technologyTargeting'].get('deviceCategories', [])}")

# Kevel
print("\n  Kevel:")
kevel_targeting = TargetingMapper.to_kevel_targeting(targeting)
if kevel_targeting:
    print(f"  Targeting keys: {list(kevel_targeting.keys())}")
    if 'geo' in kevel_targeting:
        print(f"  Geo targeting: {list(kevel_targeting['geo'].keys())}")

# Triton
print("\n  Triton Digital:")
triton_targeting = TargetingMapper.to_triton_targeting(targeting)
if triton_targeting:
    print(f"  Targeting keys: {list(triton_targeting.keys())}")

# Test compatibility
print("\n5. Testing platform compatibility...")
for platform in ['google_ad_manager', 'kevel', 'triton_digital']:
    compat = TargetingMapper.check_platform_compatibility(targeting, platform)
    print(f"\n  {platform}:")
    if compat['unsupported']:
        print(f"    Unsupported: {compat['unsupported']}")
    if compat['warnings']:
        print(f"    Warnings: {compat['warnings']}")
    if not compat['unsupported'] and not compat['warnings']:
        print("    ✓ Fully compatible")

# Show any_of/none_of pattern
print("\n6. Any/None Pattern Examples:")
print(f"  Countries included: {targeting.geo_country_any_of}")
print(f"  Countries excluded: {targeting.geo_country_none_of}")
print(f"  Device types included: {targeting.device_type_any_of}")
print(f"  Device types excluded: {targeting.device_type_none_of}")

print("\n✓ OpenRTB-aligned targeting system test complete!")