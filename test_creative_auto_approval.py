#!/usr/bin/env python3
"""
Test creative auto-approval based on format configuration.

This demonstrates how certain formats can bypass human review.
"""

import asyncio
import json
from datetime import date, datetime
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from rich.console import Console
from rich.table import Table

console = Console()

# Test token
PURINA_TOKEN = "purina_secret_token_abc123"

async def test_auto_approval(server_url: str):
    """Test creative auto-approval for configured formats."""
    console.print("[bold cyan]Testing Creative Auto-Approval by Format[/bold cyan]\n")
    
    headers = {"x-adcp-auth": PURINA_TOKEN}
    transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        # Create a creative group
        group_result = await client.call_tool("create_creative_group", {
            "req": {
                "name": "Auto-Approval Test Campaign",
                "description": "Testing format-based auto-approval"
            }
        })
        group_id = group_result.structured_content['group']['group_id']
        console.print(f"Created group: {group_id}\n")
        
        # Test different formats
        test_formats = [
            # Standard display formats (should be auto-approved if configured)
            ("display_320x50", "Mobile Banner", True),
            ("display_728x90", "Leaderboard", True),
            ("display_300x250", "Medium Rectangle", True),
            
            # Rich media formats (should require review)
            ("rich_media_expandable", "Expandable Rich Media", False),
            ("html5_interactive", "Interactive HTML5", False),
            
            # Video formats (should require review)
            ("video_16x9", "Standard Video", False),
            ("video_vertical", "Vertical Video", False),
        ]
        
        # Create creatives and check their status
        results = []
        
        for format_id, name, expected_auto in test_formats:
            console.print(f"Creating creative: {name} ({format_id})...")
            
            try:
                creative_result = await client.call_tool("create_creative", {
                    "req": {
                        "group_id": group_id,
                        "format_id": format_id,
                        "content_uri": f"https://cdn.example.com/test/{format_id}.jpg",
                        "name": f"Test {name}",
                        "click_through_url": "https://example.com"
                    }
                })
                
                creative = creative_result.structured_content['creative']
                status = creative_result.structured_content['status']
                
                results.append({
                    "format_id": format_id,
                    "name": name,
                    "creative_id": creative['creative_id'],
                    "status": status['status'],
                    "detail": status['detail'],
                    "expected_auto": expected_auto,
                    "actual_auto": status['status'] == "approved"
                })
                
            except Exception as e:
                console.print(f"[red]Error creating {format_id}: {e}[/red]")
        
        # Display results in a table
        console.print("\n[bold]Auto-Approval Test Results[/bold]")
        
        table = Table()
        table.add_column("Format ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Auto-Approved?", style="bold")
        table.add_column("Expected", style="dim")
        table.add_column("Detail", style="dim", max_width=40)
        
        for result in results:
            status_style = "green" if result['status'] == "approved" else "yellow"
            auto_style = "green" if result['actual_auto'] else "red"
            expected_text = "✓ Auto" if result['expected_auto'] else "✗ Review"
            actual_text = "✓ Yes" if result['actual_auto'] else "✗ No"
            
            table.add_row(
                result['format_id'],
                result['name'],
                f"[{status_style}]{result['status']}[/{status_style}]",
                f"[{auto_style}]{actual_text}[/{auto_style}]",
                expected_text,
                result['detail']
            )
        
        console.print(table)
        
        # Show configuration tip
        console.print("\n[yellow]Configuration Tip:[/yellow]")
        console.print("To enable auto-approval for specific formats, update config.json:")
        console.print(json.dumps({
            "creative_engine": {
                "adapter": "mock_creative_engine",
                "human_review_required": True,
                "auto_approve_formats": [
                    "display_320x50",
                    "display_728x90",
                    "display_300x250"
                ]
            }
        }, indent=2))

async def main():
    """Run the creative auto-approval test."""
    server_url = "http://localhost:8000"
    
    console.print("[bold magenta]Creative Auto-Approval Test[/bold magenta]")
    console.print("This test demonstrates format-based auto-approval.\n")
    
    # Show current configuration
    console.print("[dim]Current config.json should include:[/dim]")
    console.print(json.dumps({
        "creative_engine": {
            "adapter": "mock_creative_engine",
            "auto_approve_formats": ["display_320x50", "display_728x90", "display_300x250"]
        }
    }, indent=2))
    console.print()
    
    try:
        await test_auto_approval(server_url)
        console.print("\n[bold green]✓ Auto-approval test completed![/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())