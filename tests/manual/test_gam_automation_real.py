#!/usr/bin/env python3
"""
Manual test script for GAM automatic activation with real GAM test account.

This script tests the implementation of Issue #116 using a real GAM test publisher account.
It creates actual orders in GAM, tests activation, and cleans up afterwards.

Usage:
    python test_gam_automation_real.py --network-code 12345678 --advertiser-id 987654 --trafficker-id 123456

Prerequisites:
    - Valid GAM test account credentials
    - GAM test advertiser and trafficker setup
    - Test ad units configured

Environment Variables:
    GAM_TEST_REFRESH_TOKEN: OAuth refresh token for GAM API access
    GAM_TEST_NETWORK_CODE: GAM network code
    GAM_TEST_ADVERTISER_ID: Test advertiser/company ID
    GAM_TEST_TRAFFICKER_ID: Test trafficker user ID
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.adapters.google_ad_manager import GoogleAdManager
from src.core.database.database_session import get_db_session
from src.core.database.models import Product
from src.core.schemas import CreateMediaBuyRequest, MediaPackage, Principal, Targeting


class GAMAutomationTester:
    """Test harness for GAM automation features."""

    def __init__(self, network_code: str, advertiser_id: str, trafficker_id: str, refresh_token: str):
        self.network_code = network_code
        self.advertiser_id = advertiser_id
        self.trafficker_id = trafficker_id
        self.refresh_token = refresh_token

        # Track created orders for cleanup
        self.created_orders: list[str] = []
        self.test_tenant_id = "gam_test_tenant"

        self.principal = Principal(
            tenant_id=self.test_tenant_id,
            principal_id="test_advertiser",
            name="GAM Test Advertiser",
            access_token="test_token",
            platform_mappings={"gam_advertiser_id": advertiser_id},
        )

        self.gam_config = {"network_code": network_code, "refresh_token": refresh_token, "trafficker_id": trafficker_id}

    def setup_test_products(self):
        """Create test products in database with different automation configurations."""
        print("📦 Setting up test products...")

        with get_db_session() as db_session:
            # Remove any existing test products
            db_session.query(Product).filter_by(tenant_id=self.test_tenant_id).delete()

            # Automatic activation product (NETWORK type)
            product_auto = Product(
                tenant_id=self.test_tenant_id,
                product_id="gam_test_auto",
                name="GAM Auto Activation Test",
                implementation_config=json.dumps(
                    {
                        "order_name_template": "TEST-AUTO-{po_number}-{timestamp}",
                        "line_item_type": "NETWORK",
                        "non_guaranteed_automation": "automatic",
                        "priority": 12,
                        "cost_type": "CPM",
                        "creative_rotation_type": "EVEN",
                        "delivery_rate_type": "EVENLY",
                        "primary_goal_type": "LIFETIME",
                        "primary_goal_unit_type": "IMPRESSIONS",
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )

            # Confirmation required product (HOUSE type)
            product_confirm = Product(
                tenant_id=self.test_tenant_id,
                product_id="gam_test_confirm",
                name="GAM Confirmation Test",
                implementation_config=json.dumps(
                    {
                        "order_name_template": "TEST-CONF-{po_number}-{timestamp}",
                        "line_item_type": "HOUSE",
                        "non_guaranteed_automation": "confirmation_required",
                        "priority": 16,
                        "cost_type": "CPM",
                        "creative_rotation_type": "EVEN",
                        "delivery_rate_type": "EVENLY",
                        "primary_goal_type": "LIFETIME",
                        "primary_goal_unit_type": "IMPRESSIONS",
                        "creative_placeholders": [{"width": 728, "height": 90, "expected_creative_count": 1}],
                    }
                ),
            )

            # Manual product (NETWORK type with manual override)
            product_manual = Product(
                tenant_id=self.test_tenant_id,
                product_id="gam_test_manual",
                name="GAM Manual Test",
                implementation_config=json.dumps(
                    {
                        "order_name_template": "TEST-MANUAL-{po_number}-{timestamp}",
                        "line_item_type": "NETWORK",
                        "non_guaranteed_automation": "manual",
                        "priority": 12,
                        "cost_type": "CPM",
                        "creative_rotation_type": "EVEN",
                        "delivery_rate_type": "EVENLY",
                        "primary_goal_type": "LIFETIME",
                        "primary_goal_unit_type": "IMPRESSIONS",
                        "creative_placeholders": [{"width": 320, "height": 50, "expected_creative_count": 1}],
                    }
                ),
            )

            # Guaranteed product (should ignore automation)
            product_guaranteed = Product(
                tenant_id=self.test_tenant_id,
                product_id="gam_test_guaranteed",
                name="GAM Guaranteed Test",
                implementation_config=json.dumps(
                    {
                        "order_name_template": "TEST-GUARANTEED-{po_number}-{timestamp}",
                        "line_item_type": "STANDARD",
                        "non_guaranteed_automation": "automatic",  # Should be ignored
                        "priority": 8,
                        "cost_type": "CPM",
                        "creative_rotation_type": "EVEN",
                        "delivery_rate_type": "EVENLY",
                        "primary_goal_type": "LIFETIME",
                        "primary_goal_unit_type": "IMPRESSIONS",
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )

            db_session.add_all([product_auto, product_confirm, product_manual, product_guaranteed])
            db_session.commit()

        print("✅ Test products created successfully")

    def cleanup_test_products(self):
        """Remove test products from database."""
        print("🧹 Cleaning up test products...")
        with get_db_session() as db_session:
            db_session.query(Product).filter_by(tenant_id=self.test_tenant_id).delete()
            db_session.commit()
        print("✅ Test products cleaned up")

    def test_automatic_activation(self) -> dict[str, Any]:
        """Test automatic activation for NETWORK line item type."""
        print("\n🚀 Testing Automatic Activation...")

        adapter = GoogleAdManager(
            config=self.gam_config,
            principal=self.principal,
            dry_run=False,  # REAL GAM CALLS
            tenant_id=self.test_tenant_id,
        )

        package = MediaPackage(
            package_id="gam_test_auto",
            name="Auto Activation Test Package",
            impressions=1000,  # Small test amount
            cpm=1.00,
            format="display",
        )

        request = CreateMediaBuyRequest(
            po_number="AUTO001", total_budget=10.00, targeting_overlay=Targeting()  # $10 test budget
        )

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(days=1)

        try:
            response = adapter.create_media_buy(request, [package], start_time, end_time)
            self.created_orders.append(response.media_buy_id)

            result = {
                "test": "automatic_activation",
                "success": True,
                "order_id": response.media_buy_id,
                "status": response.status,
                "detail": response.detail,
                "expected_status": "active",
            }

            print(f"✅ Order created: {response.media_buy_id}")
            print(f"   Status: {response.status}")
            print(f"   Detail: {response.detail}")

            # Verify status
            if response.status == "active":
                print("✅ Automatic activation successful!")
            else:
                print(f"❌ Expected 'active' status, got '{response.status}'")
                result["success"] = False

            return result

        except Exception as e:
            print(f"❌ Automatic activation test failed: {str(e)}")
            return {"test": "automatic_activation", "success": False, "error": str(e)}

    def test_confirmation_required(self) -> dict[str, Any]:
        """Test confirmation required workflow for HOUSE line item type."""
        print("\n⏳ Testing Confirmation Required...")

        adapter = GoogleAdManager(
            config=self.gam_config, principal=self.principal, dry_run=False, tenant_id=self.test_tenant_id
        )

        package = MediaPackage(
            package_id="gam_test_confirm", name="Confirmation Test Package", impressions=500, cpm=0.50, format="display"
        )

        request = CreateMediaBuyRequest(po_number="CONF001", total_budget=5.00, targeting_overlay=Targeting())

        start_time = datetime.now() + timedelta(hours=2)
        end_time = start_time + timedelta(days=1)

        try:
            response = adapter.create_media_buy(request, [package], start_time, end_time)
            self.created_orders.append(response.media_buy_id)

            result = {
                "test": "confirmation_required",
                "success": True,
                "order_id": response.media_buy_id,
                "status": response.status,
                "detail": response.detail,
                "expected_status": "pending_confirmation",
            }

            print(f"✅ Order created: {response.media_buy_id}")
            print(f"   Status: {response.status}")
            print(f"   Detail: {response.detail}")

            # Verify status and workflow step creation
            if response.status == "pending_confirmation":
                print("✅ Confirmation workflow created successfully!")
                # TODO: Check database for workflow step
            else:
                print(f"❌ Expected 'pending_confirmation' status, got '{response.status}'")
                result["success"] = False

            return result

        except Exception as e:
            print(f"❌ Confirmation required test failed: {str(e)}")
            return {"test": "confirmation_required", "success": False, "error": str(e)}

    def test_manual_mode(self) -> dict[str, Any]:
        """Test manual mode (no automation) for NETWORK line item type."""
        print("\n✋ Testing Manual Mode...")

        adapter = GoogleAdManager(
            config=self.gam_config, principal=self.principal, dry_run=False, tenant_id=self.test_tenant_id
        )

        package = MediaPackage(
            package_id="gam_test_manual", name="Manual Test Package", impressions=750, cpm=0.75, format="display"
        )

        request = CreateMediaBuyRequest(po_number="MAN001", total_budget=7.50, targeting_overlay=Targeting())

        start_time = datetime.now() + timedelta(hours=3)
        end_time = start_time + timedelta(days=1)

        try:
            response = adapter.create_media_buy(request, [package], start_time, end_time)
            self.created_orders.append(response.media_buy_id)

            result = {
                "test": "manual_mode",
                "success": True,
                "order_id": response.media_buy_id,
                "status": response.status,
                "detail": response.detail,
                "expected_status": "pending_activation",
            }

            print(f"✅ Order created: {response.media_buy_id}")
            print(f"   Status: {response.status}")
            print(f"   Detail: {response.detail}")

            # Verify status remains pending
            if response.status == "pending_activation":
                print("✅ Manual mode working correctly!")
            else:
                print(f"❌ Expected 'pending_activation' status, got '{response.status}'")
                result["success"] = False

            return result

        except Exception as e:
            print(f"❌ Manual mode test failed: {str(e)}")
            return {"test": "manual_mode", "success": False, "error": str(e)}

    def test_guaranteed_ignores_automation(self) -> dict[str, Any]:
        """Test that guaranteed line item types ignore automation settings."""
        print("\n🔒 Testing Guaranteed Orders Ignore Automation...")

        adapter = GoogleAdManager(
            config=self.gam_config, principal=self.principal, dry_run=False, tenant_id=self.test_tenant_id
        )

        package = MediaPackage(
            package_id="gam_test_guaranteed",
            name="Guaranteed Test Package",
            impressions=10000,
            cpm=5.00,
            format="display",
        )

        request = CreateMediaBuyRequest(po_number="GUAR001", total_budget=500.00, targeting_overlay=Targeting())

        start_time = datetime.now() + timedelta(hours=4)
        end_time = start_time + timedelta(days=7)

        try:
            response = adapter.create_media_buy(request, [package], start_time, end_time)
            self.created_orders.append(response.media_buy_id)

            result = {
                "test": "guaranteed_ignores_automation",
                "success": True,
                "order_id": response.media_buy_id,
                "status": response.status,
                "detail": response.detail,
                "expected_status": "pending_activation",
            }

            print(f"✅ Order created: {response.media_buy_id}")
            print(f"   Status: {response.status}")
            print(f"   Detail: {response.detail}")

            # Guaranteed should always be pending regardless of automation config
            if response.status == "pending_activation":
                print("✅ Guaranteed order correctly ignores automation setting!")
            else:
                print(f"❌ Expected 'pending_activation' status, got '{response.status}'")
                result["success"] = False

            return result

        except Exception as e:
            print(f"❌ Guaranteed order test failed: {str(e)}")
            return {"test": "guaranteed_ignores_automation", "success": False, "error": str(e)}

    def cleanup_gam_orders(self):
        """Archive created orders in GAM for cleanup."""
        if not self.created_orders:
            print("🧹 No orders to clean up")
            return

        print(f"\n🧹 Cleaning up {len(self.created_orders)} GAM orders...")

        adapter = GoogleAdManager(
            config=self.gam_config, principal=self.principal, dry_run=False, tenant_id=self.test_tenant_id
        )

        for order_id in self.created_orders:
            try:
                # Archive the order (safer than deletion)
                if hasattr(adapter, "_archive_order"):
                    adapter._archive_order(order_id)
                    print(f"✅ Archived order {order_id}")
                else:
                    print(f"⚠️  Manual cleanup required for order {order_id}")
                    print(f"   Go to GAM UI and archive order: https://admanager.google.com/orders/{order_id}")

            except Exception as e:
                print(f"❌ Failed to archive order {order_id}: {str(e)}")
                print("   Manual cleanup required in GAM UI")

    def run_all_tests(self) -> list[dict[str, Any]]:
        """Run all automation tests and return results."""
        print("🧪 Starting GAM Automation Tests")
        print(f"Network Code: {self.network_code}")
        print(f"Advertiser ID: {self.advertiser_id}")
        print(f"Trafficker ID: {self.trafficker_id}")

        try:
            # Setup
            self.setup_test_products()

            # Run tests
            results = [
                self.test_automatic_activation(),
                self.test_confirmation_required(),
                self.test_manual_mode(),
                self.test_guaranteed_ignores_automation(),
            ]

            # Cleanup
            self.cleanup_gam_orders()
            self.cleanup_test_products()

            return results

        except Exception as e:
            print(f"❌ Test suite failed: {str(e)}")
            # Still try cleanup
            try:
                self.cleanup_gam_orders()
                self.cleanup_test_products()
            except:
                pass

            return [{"test": "suite_error", "success": False, "error": str(e)}]


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Test GAM automation with real GAM account")
    parser.add_argument("--network-code", required=True, help="GAM network code")
    parser.add_argument("--advertiser-id", required=True, help="GAM advertiser/company ID")
    parser.add_argument("--trafficker-id", required=True, help="GAM trafficker user ID")
    parser.add_argument("--refresh-token", help="GAM OAuth refresh token (or set GAM_TEST_REFRESH_TOKEN env var)")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (no real GAM calls)")

    args = parser.parse_args()

    # Get refresh token from arg or environment
    refresh_token = args.refresh_token or os.getenv("GAM_TEST_REFRESH_TOKEN")
    if not refresh_token:
        print("❌ Error: GAM refresh token required via --refresh-token or GAM_TEST_REFRESH_TOKEN env var")
        sys.exit(1)

    if args.dry_run:
        print("🏃 Running in DRY-RUN mode - no real GAM calls will be made")
        # TODO: Implement dry-run version
        return

    # Create tester and run
    tester = GAMAutomationTester(
        network_code=args.network_code,
        advertiser_id=args.advertiser_id,
        trafficker_id=args.trafficker_id,
        refresh_token=refresh_token,
    )

    results = tester.run_all_tests()

    # Print summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)

    passed = 0
    failed = 0

    for result in results:
        test_name = result.get("test", "unknown")
        success = result.get("success", False)
        status = "✅ PASS" if success else "❌ FAIL"

        print(f"{status} {test_name}")

        if success:
            passed += 1
            if "order_id" in result:
                print(f"      Order: {result['order_id']} (Status: {result['status']})")
        else:
            failed += 1
            if "error" in result:
                print(f"      Error: {result['error']}")

    print(f"\nTotal: {passed} passed, {failed} failed")

    if failed > 0:
        print("\n❌ Some tests failed. Check GAM account setup and credentials.")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed! GAM automation is working correctly.")


if __name__ == "__main__":
    main()
