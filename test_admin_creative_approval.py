#!/usr/bin/env python3
"""
Test admin creative approval workflow.

This demonstrates:
1. Creating creatives as a principal
2. Admin viewing pending creatives
3. Admin approving/rejecting creatives
"""

import asyncio
import json
from datetime import date, datetime
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from rich.console import Console
from rich.table import Table

console = Console()

# Test tokens
PURINA_TOKEN = "purina_secret_token_abc123"
ADMIN_TOKEN = "admin_secret_token_xyz789"  # Should match config.json

async def create_test_creatives(server_url: str):
    """Create some test creatives as Purina."""
    console.print("\n[bold cyan]1. Creating test creatives as Purina[/bold cyan]")
    
    headers = {"x-adcp-auth": PURINA_TOKEN}
    transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        # Create a creative group
        console.print("Creating creative group...")
        group_result = await client.call_tool("create_creative_group", {
            "req": {
                "name": "Q3 2025 Pet Food Campaign",
                "description": "Creatives for our Q3 campaign",
                "tags": ["pet-food", "q3-2025"]
            }
        })
        group_id = group_result.structured_content['group']['group_id']
        console.print(f"✓ Created group: {group_id}")
        
        # Create several creatives
        creative_ids = []
        formats = [
            ("display_728x90", "Leaderboard Banner"),
            ("display_300x250", "Medium Rectangle"),
            ("video_16x9", "Video Ad")
        ]
        
        for format_id, name in formats:
            console.print(f"Creating creative: {name}...")
            creative_result = await client.call_tool("create_creative", {
                "req": {
                    "group_id": group_id,
                    "format_id": format_id,
                    "content_uri": f"https://cdn.example.com/purina/{format_id}.jpg",
                    "name": f"Purina {name} - Q3 2025",
                    "click_through_url": "https://purina.com/campaign",
                    "metadata": {
                        "campaign": "Q3-2025",
                        "brand": "Purina ONE"
                    }
                }
            })
            creative = creative_result.structured_content['creative']
            status = creative_result.structured_content['status']
            creative_ids.append(creative['creative_id'])
            console.print(f"✓ Created: {creative['creative_id']} (Status: {status['status']})")
        
        return creative_ids

async def view_pending_creatives(server_url: str):
    """View pending creatives as admin."""
    console.print("\n[bold cyan]2. Viewing pending creatives as Admin[/bold cyan]")
    
    headers = {"x-adcp-auth": ADMIN_TOKEN}
    transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        result = await client.call_tool("get_pending_creatives", {
            "req": {
                "limit": 10
            }
        })
        
        pending = result.structured_content['pending_creatives']
        
        if not pending:
            console.print("[yellow]No pending creatives found[/yellow]")
            return []
        
        # Display in a table
        table = Table(title="Pending Creatives")
        table.add_column("Creative ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Principal", style="yellow")
        table.add_column("Format", style="magenta")
        table.add_column("Created", style="white")
        
        creative_ids = []
        for item in pending:
            creative = item['creative']
            principal = item['principal']
            creative_ids.append(creative['creative_id'])
            
            table.add_row(
                creative['creative_id'],
                creative['name'],
                f"{principal['name']} ({principal['principal_id']})",
                creative['format_id'],
                creative['created_at'][:19]  # Trim microseconds
            )
        
        console.print(table)
        return creative_ids

async def approve_creatives(server_url: str, creative_ids: list):
    """Approve/reject creatives as admin."""
    console.print("\n[bold cyan]3. Approving/rejecting creatives as Admin[/bold cyan]")
    
    headers = {"x-adcp-auth": ADMIN_TOKEN}
    transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        # Approve first two creatives
        for i, creative_id in enumerate(creative_ids[:2]):
            console.print(f"Approving creative: {creative_id}")
            result = await client.call_tool("approve_creative", {
                "req": {
                    "creative_id": creative_id,
                    "action": "approve",
                    "reason": "Meets brand guidelines and quality standards"
                }
            })
            response = result.structured_content
            console.print(f"✓ {response['creative_id']}: {response['new_status']} - {response['detail']}")
        
        # Reject the third creative if it exists
        if len(creative_ids) > 2:
            creative_id = creative_ids[2]
            console.print(f"\nRejecting creative: {creative_id}")
            result = await client.call_tool("approve_creative", {
                "req": {
                    "creative_id": creative_id,
                    "action": "reject",
                    "reason": "Video quality does not meet standards - please resubmit in HD"
                }
            })
            response = result.structured_content
            console.print(f"✗ {response['creative_id']}: {response['new_status']} - {response['detail']}")

async def verify_creative_status(server_url: str, creative_ids: list):
    """Verify creative status after approval as Purina."""
    console.print("\n[bold cyan]4. Verifying creative status as Purina[/bold cyan]")
    
    headers = {"x-adcp-auth": PURINA_TOKEN}
    transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        result = await client.call_tool("check_creative_status", {
            "req": {
                "creative_ids": creative_ids
            }
        })
        
        statuses = result.structured_content['statuses']
        
        table = Table(title="Creative Status After Admin Review")
        table.add_column("Creative ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Detail", style="white")
        
        for status in statuses:
            style = "green" if status['status'] == "approved" else "red" if status['status'] == "rejected" else "yellow"
            table.add_row(
                status['creative_id'],
                f"[{style}]{status['status']}[/{style}]",
                status['detail']
            )
        
        console.print(table)

async def main():
    """Run the admin creative approval workflow test."""
    server_url = "http://localhost:8000"
    
    console.print("[bold magenta]Admin Creative Approval Workflow Test[/bold magenta]")
    console.print("This test demonstrates the admin approval process for creatives.\n")
    
    try:
        # Step 1: Create test creatives
        creative_ids = await create_test_creatives(server_url)
        
        # Step 2: View pending creatives as admin
        pending_ids = await view_pending_creatives(server_url)
        
        # Step 3: Approve/reject creatives
        if pending_ids:
            await approve_creatives(server_url, pending_ids)
        
        # Step 4: Verify status
        if creative_ids:
            await verify_creative_status(server_url, creative_ids)
        
        console.print("\n[bold green]✓ Admin creative approval workflow test completed![/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # First, update config.json to include admin token
    console.print("[yellow]Note: Make sure to add admin token to config.json:[/yellow]")
    console.print(json.dumps({
        "admin": {
            "token": ADMIN_TOKEN
        }
    }, indent=2))
    console.print()
    
    asyncio.run(main())