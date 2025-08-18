#!/usr/bin/env python3
"""MCP client for testing the AdCP Buy Server."""

import argparse
import asyncio
from contextlib import AsyncExitStack

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from rich.console import Console
from rich.table import Table

console = Console()


async def main():
    parser = argparse.ArgumentParser(description="AdCP Sales Agent MCP Client")
    parser.add_argument(
        "--server", default="http://localhost:8000/mcp/", help="Server URL (default: http://localhost:8000/mcp/)"
    )
    parser.add_argument("--token", help="Authentication token (x-adcp-auth header)")
    parser.add_argument("--test", action="store_true", help="Run a test flow")

    args = parser.parse_args()

    # Set up headers for authentication
    headers = {}
    if args.token:
        headers["x-adcp-auth"] = args.token
        console.print("[green]Using authentication token[/green]")
    else:
        console.print("[yellow]No authentication token provided - requests will fail[/yellow]")

    # Create transport with headers
    transport = StreamableHttpTransport(args.server, headers=headers)

    async with AsyncExitStack() as stack:
        client = Client(transport=transport)
        await stack.enter_async_context(client)

        console.print(f"[cyan]Connected to {args.server}[/cyan]")

        # List available tools
        tools = await client.list_tools()

        console.print("\n[bold]Available Tools:[/bold]")
        for tool in tools:
            console.print(f"  • {tool.name}: {tool.description}")

        if args.test:
            await run_test_flow(client)
        else:
            await interactive_mode(client)


async def run_test_flow(client: Client):
    """Run a test media buy flow."""
    console.print("\n[bold cyan]Running test media buy flow...[/bold cyan]")

    try:
        # 1. List products
        console.print("\n[bold]1. Listing available products:[/bold]")
        result = await client.call_tool("get_products", {})

        if result and hasattr(result, "products"):
            table = Table(title="Available Products")
            table.add_column("Product ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("CPM", style="magenta")

            for product in result.products[:5]:  # Show first 5
                table.add_row(
                    product.product_id,
                    product.name,
                    product.delivery_type,
                    f"${product.cpm:.2f}" if product.cpm else "Variable",
                )

            console.print(table)

        # 2. Create a media buy
        console.print("\n[bold]2. Creating media buy:[/bold]")
        media_buy_request = {
            "product_id": "prod_video_guaranteed_sports",
            "start_date": "2025-02-01",
            "end_date": "2025-02-07",
            "total_budget": 50000.0,
            "targeting_overlay": {
                "audiences": ["sports_enthusiasts", "nfl_fans"],
                "age_ranges": ["25-34", "35-44"],
                "gender": "all",
            },
        }

        result = await client.call_tool("create_media_buy", media_buy_request)
        if result:
            media_buy_id = result.media_buy_id
            console.print(f"[green]✓ Created media buy: {media_buy_id}[/green]")
            console.print(f"  Status: {result.status}")
            console.print(f"  Total budget: ${result.media_buy.total_budget:,.2f}")

    except Exception as e:
        console.print(f"[red]Error in test flow: {e}[/red]")


async def interactive_mode(client: Client):
    """Interactive mode for testing tools."""
    console.print("\n[bold cyan]Interactive Mode[/bold cyan]")
    console.print("Commands: get_products, create_buy, submit_creative, status, quit")

    while True:
        try:
            command = console.input("\n[cyan]> [/cyan]").strip().lower()

            if command == "quit":
                break
            elif command == "get_products":
                result = await client.call_tool("get_products", {})
                if result and hasattr(result, "products"):
                    for product in result.products[:5]:
                        console.print(f"  • {product.product_id}: {product.name}")
            elif command == "create_buy":
                # Simple example
                result = await client.call_tool(
                    "create_media_buy",
                    {
                        "product_id": "prod_video_guaranteed_sports",
                        "start_date": "2025-02-01",
                        "end_date": "2025-02-07",
                        "total_budget": 10000.0,
                    },
                )
                if result:
                    console.print(f"[green]Created: {result.media_buy_id}[/green]")
            else:
                console.print(f"[yellow]Unknown command: {command}[/yellow]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    asyncio.run(main())
