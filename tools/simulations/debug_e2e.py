#!/usr/bin/env python3
"""
AdCP Debug E2E Simulation

Developer tool for debugging the AdCP protocol with full request/response visibility.
Shows exactly what data flows between client and server for both MCP and A2A protocols.

Similar to other simulations but focuses on protocol debugging rather than business scenarios.
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()

# Set up logging - INFO level to avoid massive DEBUG schema dumps
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Suppress noisy library loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

# Add project root to path (now we're in tools/simulations/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.e2e.test_adcp_full_lifecycle import AdCPTestClient


async def get_or_create_test_token() -> str:
    """Get a valid test token - use environment variable or known working token."""
    # Try environment variable first
    if os.getenv("TEST_AUTH_TOKEN"):
        token = os.getenv("TEST_AUTH_TOKEN")
        print(f"✅ Using token from TEST_AUTH_TOKEN: {token[:8]}...")
        return token

    # Try to get an existing token from the database via container
    try:
        container_result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=adcp-server"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if container_result.returncode == 0 and container_result.stdout.strip():
            container_name = container_result.stdout.strip().split("\n")[0]
            print(f"🐳 Using container: {container_name}")

            # Query for actual database tokens
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container_name,
                    "python",
                    "-c",
                    """
import sys
sys.path.append('/app')
try:
    from src.core.database.models import Principal
    from src.core.database.database_session import get_db_session
    with get_db_session() as session:
        principal = session.query(Principal).first()
        if principal:
            print(principal.access_token)
        else:
            print('7HP-ulnyvAxALOuYPMeDujwKjwjgfUpriSuXAzfKa5c')
except Exception as e:
    print('7HP-ulnyvAxALOuYPMeDujwKjwjgfUpriSuXAzfKa5c')
""",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
                print(f"✅ Using token from container: {token[:8]}...")
                return token
            else:
                print(f"⚠️  Container query failed: {result.stderr}")
        else:
            print("⚠️  No running container found")

    except Exception as e:
        print(f"⚠️  Container access failed: {e}")

    # Use known working token as fallback (this token exists in database)
    print("🔄 Using fallback token from database")
    return "7HP-ulnyvAxALOuYPMeDujwKjwjgfUpriSuXAzfKa5c"


class DebugTestClient(AdCPTestClient):
    """Enhanced test client with detailed request/response logging."""

    def _clean_response_data(self, data):
        """Remove null fields from response data to reduce noise."""
        if isinstance(data, dict):
            cleaned = {}
            for key, value in data.items():
                if value is not None:
                    cleaned[key] = self._clean_response_data(value)
            return cleaned
        elif isinstance(data, list):
            return [self._clean_response_data(item) for item in data]
        else:
            return data

    async def call_mcp_tool(self, tool_name: str, params: dict) -> dict:
        """Call MCP tool with detailed logging."""
        console.print(f"\n[bold blue]🔵 MCP REQUEST: {tool_name}[/bold blue]")

        # Create a table for request details
        request_table = Table(show_header=False, show_edge=False, pad_edge=False)
        request_table.add_column("Field", style="cyan")
        request_table.add_column("Value", style="white")

        request_table.add_row("URL", f"{self.mcp_url}/mcp/")
        request_table.add_row("Headers", json.dumps(self._build_headers(), indent=2))
        request_table.add_row("Params", json.dumps(params, indent=2))

        console.print(request_table)

        try:
            result = await self.mcp_client.call_tool(tool_name, {"req": params})

            # Use the robust parsing from the parent class
            response_data = self._parse_mcp_response(result)

            console.print(f"[bold green]🟢 MCP RESPONSE: {tool_name}[/bold green]")

            # Clean up response data by removing null fields
            cleaned_data = self._clean_response_data(response_data)

            # Pretty print the cleaned response
            console.print(
                Panel(json.dumps(cleaned_data, indent=2), title="Response Data (cleaned)", border_style="green")
            )

            return response_data  # Return original data for processing

        except Exception as e:
            console.print(f"[bold red]🔴 MCP ERROR: {tool_name} - {e}[/bold red]")
            raise

    async def query_a2a(self, query: str) -> dict:
        """Query A2A with detailed logging."""
        console.print("\n[bold blue]🔵 A2A REQUEST[/bold blue]")

        headers = self._build_headers()
        headers["Authorization"] = f"Bearer {self.auth_token}"
        payload = {"message": query, "thread_id": self.test_session_id}

        # Create a table for request details
        request_table = Table(show_header=False, show_edge=False, pad_edge=False)
        request_table.add_column("Field", style="cyan")
        request_table.add_column("Value", style="white")

        request_table.add_row("URL", f"{self.a2a_url}/message")
        request_table.add_row("Query", query)
        request_table.add_row("Headers", json.dumps(headers, indent=2))
        request_table.add_row("Payload", json.dumps(payload, indent=2))

        console.print(request_table)

        try:
            response = await self.http_client.post(
                f"{self.a2a_url}/message",
                json=payload,
                headers=headers,
                timeout=10.0,
            )

            response.raise_for_status()
            response_data = response.json()

            console.print("[bold green]🟢 A2A RESPONSE[/bold green]")

            # Create summary table instead of data dump
            task_status = response_data.get("status", {}).get("state", "unknown")
            artifacts = response_data.get("artifacts", [])

            summary_table = Table(show_header=True, header_style="bold magenta")
            summary_table.add_column("Field", style="cyan")
            summary_table.add_column("Value", style="white")

            summary_table.add_row("HTTP Status", str(response.status_code))
            summary_table.add_row("Task Status", task_status)
            summary_table.add_row("Artifacts Count", str(len(artifacts)))

            console.print(summary_table)

            # Show artifact details in a readable format
            if artifacts:
                console.print("\n[bold yellow]📦 Artifact Details:[/bold yellow]")
                for i, artifact in enumerate(artifacts):
                    artifact_name = artifact.get("name", "unnamed")
                    parts = artifact.get("parts", [])

                    # Validate artifact type matches operation
                    expected_artifact = None
                    if "create" in query.lower() or "buy" in query.lower():
                        expected_artifact = "media_buy_created"
                    elif "product" in query.lower():
                        expected_artifact = "product_catalog"

                    artifact_status = ""
                    if expected_artifact:
                        if artifact_name == expected_artifact:
                            artifact_status = " [green]✓ Correct[/green]"
                        else:
                            artifact_status = f" [red]✗ Expected '{expected_artifact}'[/red]"

                    console.print(
                        f"[cyan]Artifact {i + 1}:[/cyan] {artifact_name} ({len(parts)} parts){artifact_status}"
                    )

                    # Show first 2 parts with intelligent summaries
                    for j, part in enumerate(parts[:2]):
                        part_data = part.get("data", {})
                        if isinstance(part_data, dict):
                            if "products" in part_data:
                                product_count = (
                                    len(part_data["products"]) if isinstance(part_data["products"], list) else "unknown"
                                )
                                console.print(f"  [green]Part {j + 1}:[/green] Contains {product_count} products")

                                # Show first product as example
                                if isinstance(part_data["products"], list) and len(part_data["products"]) > 0:
                                    first_product = part_data["products"][0]
                                    if isinstance(first_product, dict):
                                        console.print(
                                            f"    [dim]Example:[/dim] {first_product.get('name', 'Unnamed')} (ID: {first_product.get('product_id', 'N/A')})"
                                        )
                                    else:
                                        console.print(
                                            f"    [dim]Product IDs:[/dim] {', '.join(part_data['products'][:3])}"
                                        )
                            elif "media_buy_id" in part_data:
                                console.print(
                                    f"  [green]Part {j + 1}:[/green] Media buy ID: {part_data['media_buy_id']}"
                                )
                            elif "message" in part_data:
                                message = part_data["message"]
                                truncated = message[:100] + "..." if len(message) > 100 else message
                                console.print(f"  [green]Part {j + 1}:[/green] Message - {truncated}")
                            else:
                                key_count = len(part_data.keys()) if hasattr(part_data, "keys") else 0
                                console.print(f"  [green]Part {j + 1}:[/green] Data object with {key_count} keys")

            return response_data

        except Exception as e:
            console.print(f"[bold red]🔴 A2A ERROR: {query} - {e}[/bold red]")
            raise


async def run_debug_test(server_url: str = None, skip_a2a: bool = False, skip_mcp: bool = False, verbose: bool = False):
    """Run a debug test to see the protocol in action."""
    console.print(Rule("[bold magenta]🚀 AdCP E2E Debug Simulation[/bold magenta]", style="magenta"))

    if server_url:
        # External server mode
        mcp_url = server_url
        a2a_url = server_url.replace("8166", "8091")  # Assume A2A is on different port
        console.print(f"[yellow]🌐 Using external server: {server_url}[/yellow]")
    else:
        # Local development mode
        mcp_port = os.getenv("ADCP_SALES_PORT", "8166")
        a2a_port = os.getenv("A2A_PORT", "8091")
        mcp_url = f"http://localhost:{mcp_port}"
        a2a_url = f"http://localhost:{a2a_port}"

    # Display server info in a table
    server_table = Table(title="🖥️  Server Configuration", show_header=True, header_style="bold blue")
    server_table.add_column("Service", style="cyan")
    server_table.add_column("URL", style="white")

    server_table.add_row("MCP Server", mcp_url)
    if not skip_a2a:
        server_table.add_row("A2A Server", a2a_url)

    console.print(server_table)
    console.print()

    # Get or create a valid test token dynamically
    with console.status("[bold green]🔑 Getting authentication token..."):
        auth_token = await get_or_create_test_token()

    console.print(f"[green]✅ Token ready: {auth_token[:8]}...[/green]\n")

    async with DebugTestClient(mcp_url, a2a_url, auth_token, dry_run=True) as client:
        try:
            # Collect results for comparison
            mcp_products = None
            a2a_products = None
            mcp_media_buy = None
            a2a_media_buy = None

            # Test 1: Product Discovery
            console.print(Rule("[bold cyan]🧪 TEST 1: Product Discovery[/bold cyan]"))

            # MCP Product Discovery
            if not skip_mcp:
                console.print("\n[bold blue]📋 MCP Protocol[/bold blue]")
                mcp_products = await client.call_mcp_tool(
                    "get_products", {"brief": "Looking for display advertising", "promoted_offering": "test campaign"}
                )

                mcp_product_count = len(mcp_products.get("products", [])) if mcp_products else 0
                console.print(f"[green]✅ MCP: Found {mcp_product_count} products[/green]")

            # A2A Product Discovery
            if not skip_a2a:
                console.print("\n[bold blue]💬 A2A Protocol[/bold blue]")
                a2a_response = await client.query_a2a("What display advertising products do you offer?")

                if a2a_response and "status" in a2a_response:
                    task_status = a2a_response["status"]["state"]
                    # Try to extract products from A2A response
                    a2a_product_count = 0
                    artifacts = a2a_response.get("artifacts", [])
                    for artifact in artifacts:
                        for part in artifact.get("parts", []):
                            part_data = part.get("data", {})
                            if "products" in part_data and isinstance(part_data["products"], list):
                                a2a_product_count = len(part_data["products"])
                                break

                    console.print(f"[green]✅ A2A: Found {a2a_product_count} products (status: {task_status})[/green]")

            # Show standardized product comparison
            if mcp_products and "products" in mcp_products and len(mcp_products["products"]) > 0:
                console.print("\n[bold magenta]📦 Product Comparison[/bold magenta]")
                comparison_table = Table(show_header=True, header_style="bold cyan")
                comparison_table.add_column("Protocol", style="yellow")
                comparison_table.add_column("Count", style="white")
                comparison_table.add_column("Example Product", style="cyan")

                if not skip_mcp:
                    first_product = mcp_products["products"][0]
                    mcp_example = f"{first_product.get('name', 'N/A')} ({first_product.get('product_id', 'N/A')})"
                    comparison_table.add_row("MCP", str(mcp_product_count), mcp_example)

                if not skip_a2a:
                    a2a_example = "Same data via natural language" if a2a_product_count > 0 else "No products found"
                    comparison_table.add_row("A2A", str(a2a_product_count), a2a_example)

                console.print(comparison_table)

            # Test 2: Media Buy Creation
            if mcp_products and "products" in mcp_products and len(mcp_products["products"]) > 0:
                console.print(Rule("[bold cyan]🧪 TEST 2: Media Buy Creation[/bold cyan]"))

                product_id = mcp_products["products"][0].get("product_id", mcp_products["products"][0].get("id"))

                # MCP Media Buy Creation
                if not skip_mcp:
                    console.print("\n[bold blue]📋 MCP Protocol[/bold blue]")
                    mcp_media_buy = await client.call_mcp_tool(
                        "create_media_buy",
                        {
                            "product_ids": [product_id],
                            "budget": 5000.0,
                            "start_date": "2025-09-01",
                            "end_date": "2025-09-30",
                        },
                    )

                    mcp_buy_id = mcp_media_buy.get("media_buy_id", "N/A") if mcp_media_buy else "Failed"
                    mcp_status = mcp_media_buy.get("status", "N/A") if mcp_media_buy else "Failed"
                    console.print(f"[green]✅ MCP: Created media buy {mcp_buy_id} (status: {mcp_status})[/green]")

                # A2A Media Buy Creation
                if not skip_a2a:
                    console.print("\n[bold blue]💬 A2A Protocol[/bold blue]")
                    a2a_buy_response = await client.query_a2a(
                        f"Please create a media buy for product {product_id} with a budget of $5000 running from September 1 to September 30, 2025"
                    )

                    a2a_buy_id = None
                    if a2a_buy_response and "status" in a2a_buy_response:
                        a2a_task_status = a2a_buy_response["status"]["state"]
                        # Extract media buy ID from artifacts
                        if "artifacts" in a2a_buy_response:
                            for artifact in a2a_buy_response["artifacts"]:
                                if artifact.get("name") == "media_buy_created":
                                    for part in artifact.get("parts", []):
                                        if isinstance(part.get("data"), dict):
                                            a2a_buy_id = part["data"].get("media_buy_id")
                                            break
                                    if a2a_buy_id:
                                        break

                        a2a_buy_info = (
                            f"Created media buy {a2a_buy_id}"
                            if a2a_buy_id
                            else "Media buy creation via natural language"
                        )
                        console.print(f"[green]✅ A2A: {a2a_buy_info} (status: {a2a_task_status})[/green]")

                # Show standardized media buy comparison
                console.print("\n[bold magenta]💳 Media Buy Comparison[/bold magenta]")
                buy_comparison_table = Table(show_header=True, header_style="bold cyan")
                buy_comparison_table.add_column("Protocol", style="yellow")
                buy_comparison_table.add_column("Result", style="white")
                buy_comparison_table.add_column("Buy ID / Response", style="cyan")

                if not skip_mcp:
                    buy_comparison_table.add_row("MCP", mcp_status, mcp_buy_id)
                if not skip_a2a:
                    a2a_result = a2a_task_status if "a2a_task_status" in locals() else "Not tested"
                    a2a_display = a2a_buy_id if "a2a_buy_id" in locals() and a2a_buy_id else "Natural language response"
                    buy_comparison_table.add_row("A2A", a2a_result, a2a_display)

                console.print(buy_comparison_table)

            console.print(
                Rule("[bold green]🎉 Protocol comparison completed successfully![/bold green]", style="green")
            )

        except Exception as e:
            console.print(f"[bold red]❌ Debug test failed: {e}[/bold red]")
            if verbose:
                console.print_exception()


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="AdCP Debug E2E Simulation - Protocol debugging tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python debug_e2e.py                                    # Both protocols (default)
  python debug_e2e.py --skip-a2a                         # MCP protocol only
  python debug_e2e.py --skip-mcp                         # A2A protocol only
  python debug_e2e.py --server-url http://example.com:8166  # External server
  python debug_e2e.py --verbose                          # Full stack traces
        """.strip(),
    )

    parser.add_argument("--server-url", help="External server URL (default: local Docker services)")
    parser.add_argument("--skip-a2a", action="store_true", help="Skip A2A protocol testing, MCP only")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip MCP protocol testing, A2A only")
    parser.add_argument("--verbose", action="store_true", help="Show full stack traces on errors")

    args = parser.parse_args()

    # Run the debug test
    asyncio.run(
        run_debug_test(server_url=args.server_url, skip_a2a=args.skip_a2a, skip_mcp=args.skip_mcp, verbose=args.verbose)
    )


if __name__ == "__main__":
    main()
