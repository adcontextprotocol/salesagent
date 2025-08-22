#!/usr/bin/env python3
"""
Test script for simple display campaign on Google Ad Manager.

This script tests the complete flow of creating a simple display campaign:
1. Validates configuration
2. Creates media buy (order + line items)
3. Uploads creatives
4. Monitors initial delivery
5. Tests update operations

Run with: python test_gam_simple_display.py [--dry-run]
"""

import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from src.core.database.database import db_session
from src.core.database.models import Principal, Product, Tenant

console = Console()


class GAMSimpleDisplayTest:
    """Test harness for simple GAM display campaigns."""

    def __init__(self, dry_run: bool = False, server_url: str = "http://localhost:8080"):
        self.dry_run = dry_run
        self.server_url = server_url
        self.test_results = []
        self.media_buy_id = None
        self.client = None

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result."""
        self.test_results.append(
            {
                "name": name,
                "success": success,
                "details": details,
                "timestamp": datetime.now(),
            }
        )

        if success:
            console.print(f"✅ {name}")
            if details:
                console.print(f"   [dim]{details}[/dim]")
        else:
            console.print(f"❌ {name}")
            if details:
                console.print(f"   [red]{details}[/red]")

    async def validate_configuration(self) -> bool:
        """Validate GAM configuration before testing."""
        console.print("\n[bold]1. Validating Configuration[/bold]")

        try:
            # Check for test tenant
            tenant = db_session.query(Tenant).filter_by(name="GAM Test Publisher").first()

            if not tenant:
                self.log_test(
                    "Find test tenant",
                    False,
                    "Test tenant 'GAM Test Publisher' not found. Run setup_test_gam.py first.",
                )
                return False

            self.log_test("Find test tenant", True, f"Tenant ID: {tenant.tenant_id}")

            # Check GAM adapter configuration
            # GAM config is now stored in the adapter_config table
            gam_config = {}
            required_fields = [
                "network_code",
                "service_account_key_file",
                "company_id",
                "trafficker_id",
            ]

            missing_fields = [f for f in required_fields if not gam_config.get(f)]
            if missing_fields:
                self.log_test(
                    "Validate GAM config",
                    False,
                    f"Missing fields: {', '.join(missing_fields)}",
                )
                return False

            self.log_test("Validate GAM config", True, f"Network: {gam_config['network_code']}")

            # Check for test principal
            principal = (
                db_session.query(Principal).filter_by(tenant_id=tenant.tenant_id, name="Test Advertiser").first()
            )

            if not principal:
                self.log_test("Find test principal", False, "Test principal not found")
                return False

            self.log_test("Find test principal", True, f"Token: {principal.access_token[:10]}...")
            self.access_token = principal.access_token

            # Check GAM advertiser mapping
            gam_mapping = principal.platform_mappings.get("gam", {})
            if not gam_mapping.get("advertiser_id"):
                self.log_test(
                    "Validate advertiser mapping",
                    False,
                    "No GAM advertiser_id in principal mapping",
                )
                return False

            self.log_test(
                "Validate advertiser mapping",
                True,
                f"Advertiser ID: {gam_mapping['advertiser_id']}",
            )

            # Check for test product
            product = (
                db_session.query(Product).filter_by(tenant_id=tenant.tenant_id, name="Simple Display Test").first()
            )

            if not product:
                self.log_test("Find test product", False, "Test product not found")
                return False

            self.log_test("Find test product", True, f"Product ID: {product.product_id}")
            self.product_id = product.product_id

            # Validate product implementation config
            impl_config = product.implementation_config or {}
            if not impl_config.get("creative_placeholders"):
                self.log_test("Validate product config", False, "No creative placeholders defined")
                return False

            self.log_test(
                "Validate product config",
                True,
                f"{len(impl_config['creative_placeholders'])} creative sizes configured",
            )

            # Check service account file exists
            key_file = Path(gam_config["service_account_key_file"])
            if not key_file.exists():
                self.log_test(
                    "Check service account",
                    False,
                    f"Service account file not found: {key_file}",
                )
                return False

            self.log_test("Check service account", True, "Key file exists")

            return True

        except Exception as e:
            self.log_test("Configuration validation", False, str(e))
            return False

    async def test_connection(self) -> bool:
        """Test connection to MCP server."""
        console.print("\n[bold]2. Testing MCP Connection[/bold]")

        try:
            headers = {"x-adcp-auth": self.access_token}
            transport = StreamableHttpTransport(url=f"{self.server_url}/mcp/", headers=headers)
            self.client = Client(transport=transport)

            async with self.client:
                # Test by getting products
                products = await self.client.tools.get_products()
                self.log_test(
                    "Connect to MCP server",
                    True,
                    f"Found {len(products.products)} products",
                )
                return True

        except Exception as e:
            self.log_test("Connect to MCP server", False, str(e))
            return False

    async def create_media_buy(self) -> bool:
        """Create a simple media buy."""
        console.print("\n[bold]3. Creating Media Buy[/bold]")

        try:
            async with self.client:
                # Create media buy with simple targeting
                flight_start = date.today() + timedelta(days=1)
                flight_end = flight_start + timedelta(days=7)

                params = {
                    "product_ids": [self.product_id],
                    "total_budget": 100.0,  # $100 test budget
                    "flight_start_date": flight_start,
                    "flight_end_date": flight_end,
                    "targeting_overlay": {
                        "geo_country_any_of": ["US"],
                        "frequency_caps": [{"max_impressions": 3, "time_unit": "DAY", "time_range": 1}],
                    },
                    "po_number": f"TEST-GAM-{int(time.time())}",
                }

                if self.dry_run:
                    console.print("[yellow]DRY RUN: Would create media buy with:[/yellow]")
                    console.print(f"  Budget: ${params['total_budget']}")
                    console.print(f"  Dates: {flight_start} to {flight_end}")
                    console.print(f"  PO: {params['po_number']}")
                    self.log_test("Create media buy", True, "Dry run - no API calls made")
                    self.media_buy_id = "dry_run_12345"
                    return True

                result = await self.client.tools.create_media_buy(**params)

                if result.status == "failed":
                    self.log_test("Create media buy", False, result.detail or "Unknown error")
                    return False

                self.media_buy_id = result.media_buy_id
                self.log_test(
                    "Create media buy",
                    True,
                    f"Media buy ID: {self.media_buy_id}, Status: {result.status}",
                )

                # Check creative deadline
                if result.creative_deadline:
                    deadline = result.creative_deadline.strftime("%Y-%m-%d %H:%M")
                    console.print(f"   [dim]Creative deadline: {deadline}[/dim]")

                return True

        except Exception as e:
            self.log_test("Create media buy", False, str(e))
            return False

    async def upload_creatives(self) -> bool:
        """Upload test creatives."""
        console.print("\n[bold]4. Uploading Creatives[/bold]")

        if self.dry_run:
            self.log_test("Upload creatives", True, "Dry run - skipping creative upload")
            return True

        try:
            async with self.client:
                # Create simple test creatives
                creatives = [
                    {
                        "creative_id": f"test_300x250_{int(time.time())}",
                        "name": "Test Display 300x250",
                        "format": "display_300x250",
                        "media_url": "https://via.placeholder.com/300x250",
                        "click_url": "https://example.com/landing",
                        "is_tag": False,
                    },
                    {
                        "creative_id": f"test_728x90_{int(time.time())}",
                        "name": "Test Display 728x90",
                        "format": "display_728x90",
                        "media_url": "https://via.placeholder.com/728x90",
                        "click_url": "https://example.com/landing",
                        "is_tag": False,
                    },
                ]

                result = await self.client.tools.upload_creatives(media_buy_id=self.media_buy_id, creatives=creatives)

                # Check results
                approved = sum(1 for c in result.creative_statuses if c.status == "approved")
                failed = sum(1 for c in result.creative_statuses if c.status == "failed")

                if failed > 0:
                    self.log_test(
                        "Upload creatives",
                        False,
                        f"{approved} approved, {failed} failed",
                    )
                    return False

                self.log_test("Upload creatives", True, f"{approved} creatives approved")
                return True

        except Exception as e:
            self.log_test("Upload creatives", False, str(e))
            return False

    async def check_status(self) -> bool:
        """Check media buy status."""
        console.print("\n[bold]5. Checking Status[/bold]")

        if self.dry_run:
            self.log_test("Check status", True, "Dry run - status would be 'pending'")
            return True

        try:
            async with self.client:
                result = await self.client.tools.check_media_buy_status(media_buy_id=self.media_buy_id)

                self.log_test("Check status", True, f"Status: {result.status}")

                # Show additional details
                if result.active_packages:
                    console.print(f"   [dim]Active packages: {result.active_packages}[/dim]")
                if result.impressions_delivered:
                    console.print(f"   [dim]Impressions: {result.impressions_delivered:,}[/dim]")

                return True

        except Exception as e:
            self.log_test("Check status", False, str(e))
            return False

    async def test_update_operations(self) -> bool:
        """Test update operations (pause/resume)."""
        console.print("\n[bold]6. Testing Update Operations[/bold]")

        if self.dry_run:
            self.log_test("Test updates", True, "Dry run - skipping update tests")
            return True

        try:
            async with self.client:
                # Test pause
                result = await self.client.tools.update_media_buy(
                    media_buy_id=self.media_buy_id, action="pause_media_buy"
                )

                if result.status != "accepted":
                    self.log_test("Pause media buy", False, result.reason or "Unknown error")
                    return False

                self.log_test("Pause media buy", True, "Pause accepted")

                # Wait a moment
                await asyncio.sleep(2)

                # Test resume
                result = await self.client.tools.update_media_buy(
                    media_buy_id=self.media_buy_id, action="resume_media_buy"
                )

                if result.status != "accepted":
                    self.log_test("Resume media buy", False, result.reason or "Unknown error")
                    return False

                self.log_test("Resume media buy", True, "Resume accepted")
                return True

        except Exception as e:
            self.log_test("Test updates", False, str(e))
            return False

    def print_summary(self):
        """Print test summary."""
        console.print("\n[bold]Test Summary[/bold]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Test", style="cyan", width=40)
        table.add_column("Result", justify="center", width=10)
        table.add_column("Details", width=50)

        for result in self.test_results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            status_style = "green" if result["success"] else "red"

            table.add_row(
                result["name"],
                f"[{status_style}]{status}[/{status_style}]",
                result["details"][:50] + "..." if len(result["details"]) > 50 else result["details"],
            )

        console.print(table)

        # Overall result
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["success"])

        if passed == total:
            console.print(
                Panel(
                    f"[bold green]All tests passed! ({passed}/{total})[/bold green]",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    f"[bold red]Some tests failed ({passed}/{total} passed)[/bold red]",
                    border_style="red",
                )
            )

    async def run_all_tests(self):
        """Run all tests in sequence."""
        console.print(
            Panel.fit(
                "[bold cyan]GAM Simple Display Campaign Test[/bold cyan]\n"
                + f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}\n"
                + f"Server: {self.server_url}",
                border_style="cyan",
            )
        )

        # Run tests in order
        tests = [
            self.validate_configuration,
            self.test_connection,
            self.create_media_buy,
            self.upload_creatives,
            self.check_status,
            self.test_update_operations,
        ]

        for test in tests:
            success = await test()
            if not success:
                console.print("\n[red]Stopping due to test failure[/red]")
                break

        # Print summary
        self.print_summary()

        # Return overall success
        return all(r["success"] for r in self.test_results)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test simple display campaign on Google Ad Manager")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual API calls)",
    )
    parser.add_argument(
        "--server-url",
        default="http://localhost:8080",
        help="MCP server URL (default: http://localhost:8080)",
    )

    args = parser.parse_args()

    # Run tests
    tester = GAMSimpleDisplayTest(dry_run=args.dry_run, server_url=args.server_url)

    success = await tester.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        sys.exit(1)
