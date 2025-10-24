#!/usr/bin/env python3
"""
Test service account authentication for GAM by fetching advertisers.

This script tests the complete service account authentication flow including:
- Config validation
- Credential wrapping
- GAM API calls

Usage:
    python scripts/test_service_account_auth.py --tenant <tenant_name>
    python scripts/test_service_account_auth.py --tenant weather-company
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from src.core.database.database_session import get_db_session
from src.core.database.models import Tenant
from src.adapters.google_ad_manager import GoogleAdManager
from src.adapters.gam import build_gam_config_from_adapter
from src.core.schemas import Principal


def test_service_account_auth(tenant_name: str):
    """Test service account authentication for a tenant."""
    print(f"\n🔍 Testing service account authentication for tenant: {tenant_name}")
    print("=" * 80)

    with get_db_session() as session:
        # Find tenant by name
        stmt = select(Tenant).where(Tenant.name == tenant_name)
        tenant = session.scalars(stmt).first()

        if not tenant:
            print(f"❌ Tenant '{tenant_name}' not found")
            return False

        print(f"✓ Found tenant: {tenant.name} (ID: {tenant.tenant_id})")

        # Check if GAM is configured
        if not tenant.adapter_config:
            print("❌ No adapter config found")
            return False

        if tenant.adapter_config.adapter_type != "google_ad_manager":
            print(f"❌ Adapter type is {tenant.adapter_config.adapter_type}, not google_ad_manager")
            return False

        print("✓ GAM adapter configured")

        # Check auth method
        auth_method = tenant.adapter_config.gam_auth_method
        print(f"✓ Auth method: {auth_method}")

        if auth_method == "service_account":
            has_json = bool(tenant.adapter_config.gam_service_account_json)
            print(f"  - Has service_account_json: {has_json}")
            if not has_json:
                print("  ❌ Service account JSON is missing!")
                return False
        elif auth_method == "oauth":
            has_token = bool(tenant.adapter_config.gam_refresh_token)
            print(f"  - Has refresh_token: {has_token}")
            if not has_token:
                print("  ❌ Refresh token is missing!")
                return False
        else:
            print(f"  ❌ Unknown auth method: {auth_method}")
            return False

        # Check network code
        if not tenant.adapter_config.gam_network_code:
            print("❌ GAM network code not configured")
            return False

        print(f"✓ Network code: {tenant.adapter_config.gam_network_code}")

        # Build config
        print("\n📋 Building GAM config...")
        try:
            gam_config = build_gam_config_from_adapter(tenant.adapter_config)
            print("✓ Config built successfully")

            # Show what's in the config (without sensitive data)
            config_keys = list(gam_config.keys())
            print(f"  Config keys: {config_keys}")

            if "service_account_json" in gam_config:
                json_len = len(gam_config["service_account_json"])
                print(f"  ✓ service_account_json present ({json_len} chars)")
            elif "refresh_token" in gam_config:
                token_len = len(gam_config["refresh_token"])
                print(f"  ✓ refresh_token present ({token_len} chars)")

        except Exception as e:
            print(f"❌ Failed to build config: {e}")
            return False

        # Create adapter
        print("\n🔧 Creating GAM adapter...")
        try:
            # Create a mock principal (needed for adapter init)
            mock_principal = Principal(
                principal_id="test",
                name="Test Principal",
                platform_mappings={
                    "google_ad_manager": {
                        "advertiser_id": "test_advertiser",
                        "advertiser_name": "Test Advertiser",
                    }
                },
            )

            adapter = GoogleAdManager(
                config=gam_config,
                principal=mock_principal,
                network_code=tenant.adapter_config.gam_network_code,
                advertiser_id=None,  # Not needed for get_advertisers
                trafficker_id=tenant.adapter_config.gam_trafficker_id,
                dry_run=False,
                tenant_id=tenant.tenant_id,
            )
            print("✓ Adapter created successfully")

        except Exception as e:
            print(f"❌ Failed to create adapter: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Fetch advertisers
        print("\n📞 Fetching advertisers from GAM...")
        try:
            advertisers = adapter.get_advertisers()
            print(f"✓ Successfully fetched {len(advertisers)} advertisers")

            if advertisers:
                print("\n📊 Advertisers:")
                for adv in advertisers[:5]:  # Show first 5
                    print(f"  - {adv.get('name')} (ID: {adv.get('id')})")
                if len(advertisers) > 5:
                    print(f"  ... and {len(advertisers) - 5} more")
            else:
                print("  ℹ️  No advertisers found (this is okay)")

        except Exception as e:
            print(f"❌ Failed to fetch advertisers: {e}")
            import traceback
            traceback.print_exc()
            return False

    print("\n" + "=" * 80)
    print("✅ All tests passed! Service account authentication is working.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Test service account authentication for GAM")
    parser.add_argument("--tenant", required=True, help="Tenant name to test (e.g., 'weather-company')")
    args = parser.parse_args()

    success = test_service_account_auth(args.tenant)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
