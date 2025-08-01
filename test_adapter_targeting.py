#!/usr/bin/env python3
"""Test targeting validation within each adapter."""

from schemas import Targeting, Dayparting, DaypartSchedule, FrequencyCap
from adapters.google_ad_manager import GoogleAdManager
from adapters.kevel import Kevel
from adapters.triton_digital import TritonDigital
from schemas import Principal
import json

# Create mock principal for testing
mock_principal = Principal(
    principal_id="test",
    name="Test Principal",
    platform_mappings={
        "gam_advertiser_id": "12345",
        "kevel_advertiser_id": "67890",
        "triton_advertiser_id": "11111"
    }
)

# Create comprehensive targeting that will challenge each adapter
full_targeting = Targeting(
    # Geographic targeting
    geo_country_any_of=["US", "CA"],
    geo_region_any_of=["CA", "NY"],
    geo_metro_any_of=["501", "803"],
    geo_city_any_of=["New York", "Los Angeles"],
    geo_zip_any_of=["10001", "90210"],
    
    # Device and platform targeting
    device_type_any_of=["mobile", "desktop", "ctv", "tablet"],
    os_any_of=["iOS", "Android", "Windows"],
    browser_any_of=["Chrome", "Safari"],
    
    # Media type targeting
    media_type_any_of=["video", "display", "audio"],
    
    # Content and audience targeting
    content_cat_any_of=["IAB17", "IAB19"],
    content_cat_none_of=["IAB7", "IAB14"],
    keywords_any_of=["sports", "technology"],
    keywords_none_of=["gambling"],
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
        ]
    ),
    
    # Frequency capping
    frequency_cap=FrequencyCap(
        suppress_minutes=1440,  # 24 hours
        scope="media_buy"
    )
)

print("Testing Adapter-Specific Targeting Validation")
print("=" * 50)

# Test Google Ad Manager
print("\n1. Google Ad Manager")
print("-" * 30)
gam_config = {"network_code": "123456", "dry_run": True}
gam = GoogleAdManager(gam_config, mock_principal, dry_run=True)

unsupported = gam._validate_targeting(full_targeting)
if unsupported:
    print(f"❌ Unsupported features:")
    for issue in unsupported:
        print(f"   - {issue}")
else:
    print("✅ All targeting features supported")

gam_targeting = gam._build_targeting(full_targeting)
print(f"   Mapped to GAM: {list(gam_targeting.keys())}")

# Test Kevel
print("\n2. Kevel")
print("-" * 30)
kevel_config = {"network_id": "123", "api_key": "test", "dry_run": True}
kevel = Kevel(kevel_config, mock_principal, dry_run=True)

unsupported = kevel._validate_targeting(full_targeting)
if unsupported:
    print(f"❌ Unsupported features:")
    for issue in unsupported:
        print(f"   - {issue}")
else:
    print("✅ All targeting features supported")

kevel_targeting = kevel._build_targeting(full_targeting)
print(f"   Mapped to Kevel: {list(kevel_targeting.keys())}")

# Test Triton Digital
print("\n3. Triton Digital")
print("-" * 30)
triton_config = {"auth_token": "test", "base_url": "https://api.triton.com", "dry_run": True}
triton = TritonDigital(triton_config, mock_principal, dry_run=True)

unsupported = triton._validate_targeting(full_targeting)
if unsupported:
    print(f"❌ Unsupported features:")
    for issue in unsupported:
        print(f"   - {issue}")
else:
    print("✅ All targeting features supported")

triton_targeting = triton._build_targeting(full_targeting)
print(f"   Mapped to Triton: {list(triton_targeting.keys())}")

# Test minimal targeting that should work everywhere
print("\n\n4. Testing Minimal Audio-Only Targeting")
print("-" * 40)

audio_targeting = Targeting(
    geo_country_any_of=["US"],
    geo_region_any_of=["CA", "NY"],
    device_type_any_of=["mobile", "desktop"],
    media_type_any_of=["audio"],
    dayparting=Dayparting(
        timezone="America/New_York",
        schedules=[],  # Empty schedules, using presets instead
        presets=["drive_time_morning", "drive_time_evening"]
    )
)

for name, adapter in [("GAM", gam), ("Kevel", kevel), ("Triton", triton)]:
    unsupported = adapter._validate_targeting(audio_targeting)
    if unsupported:
        print(f"{name}: ❌ {unsupported[0]}")
    else:
        print(f"{name}: ✅ Supported")

print("\n✓ Adapter-specific targeting validation test complete!")