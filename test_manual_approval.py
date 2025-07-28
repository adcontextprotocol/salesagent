#!/usr/bin/env python3
"""
Test manual approval mode for create_media_buy and update_media_buy.
"""

import json
import asyncio
from datetime import datetime, date, timedelta
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BASE_URL = "http://localhost:8080"
ADMIN_TOKEN = "admin"
ACME_TOKEN = "acme_corp_token"

def make_request(endpoint: str, data: dict, token: str = ACME_TOKEN):
    """Make a request to the AdCP server."""
    headers = {
        "x-adcp-auth": token,
        "content-type": "application/json"
    }
    
    response = requests.post(
        f"{BASE_URL}/{endpoint}",
        headers=headers,
        json=data
    )
    
    return response.json()

async def test_manual_approval_create():
    """Test manual approval for create_media_buy."""
    console.print("\n[bold cyan]Testing Manual Approval for Create Media Buy[/bold cyan]")
    
    # First, ensure the adapter has manual approval enabled
    # This would normally be in config.json
    console.print("[yellow]Note: Ensure your adapter config has manual_approval_required: true[/yellow]")
    
    # Try to create a media buy
    create_req = {
        "product_ids": ["prod_1", "prod_2"],
        "flight_start_date": str(date.today()),
        "flight_end_date": str(date.today() + timedelta(days=30)),
        "total_budget": 10000.0,
        "targeting_overlay": {
            "geo_country_any_of": ["US"],
            "device_type_any_of": ["mobile", "desktop"]
        },
        "po_number": "TEST-MANUAL-001"
    }
    
    console.print(f"\nCreating media buy with PO: {create_req['po_number']}")
    response = make_request("create_media_buy", create_req)
    
    if response.get("status") == "pending_manual":
        console.print(f"[green]✓ Manual approval required as expected[/green]")
        console.print(f"Task created: {response.get('detail')}")
        
        # Extract task ID from detail message
        task_id = response.get("detail", "").split("Task ID: ")[-1] if "Task ID:" in response.get("detail", "") else None
        return task_id, create_req
    else:
        console.print(f"[red]✗ Expected pending_manual status, got: {response}[/red]")
        return None, None

async def test_manual_approval_update():
    """Test manual approval for update_media_buy."""
    console.print("\n[bold cyan]Testing Manual Approval for Update Media Buy[/bold cyan]")
    
    # Use a dummy media buy ID (in real scenario, would use an existing one)
    update_req = {
        "media_buy_id": "gam_12345",
        "active": False,  # Pause the campaign
        "packages": [{
            "package_id": "prod_1",
            "budget": 5000.0
        }]
    }
    
    console.print(f"\nUpdating media buy: {update_req['media_buy_id']}")
    response = make_request("update_media_buy", update_req)
    
    if response.get("status") == "pending_manual":
        console.print(f"[green]✓ Manual approval required as expected[/green]")
        console.print(f"Task created: {response.get('detail')}")
        
        # Extract task ID
        task_id = response.get("detail", "").split("Task ID: ")[-1] if "Task ID:" in response.get("detail", "") else None
        return task_id, update_req
    else:
        console.print(f"[red]✗ Expected pending_manual status, got: {response}[/red]")
        return None, None

async def review_pending_tasks():
    """Review all pending manual approval tasks."""
    console.print("\n[bold cyan]Reviewing Pending Manual Approval Tasks[/bold cyan]")
    
    req = {
        "task_type": "manual_approval",
        "include_overdue": True
    }
    
    response = make_request("get_pending_tasks", req, token=ADMIN_TOKEN)
    
    if response.get("tasks"):
        table = Table(title="Manual Approval Queue")
        table.add_column("Task ID", style="cyan")
        table.add_column("Operation", style="yellow")
        table.add_column("Principal", style="green")
        table.add_column("Priority")
        table.add_column("Created", style="dim")
        table.add_column("Details", max_width=40)
        
        for task in response["tasks"]:
            created = datetime.fromisoformat(task["created_at"].replace("Z", "+00:00"))
            table.add_row(
                task["task_id"],
                task.get("operation", "N/A"),
                task["principal_id"],
                task["priority"],
                created.strftime("%H:%M:%S"),
                task.get("error_detail", "")[:40]
            )
        
        console.print(table)
        console.print(f"\n[bold]Total pending tasks: {response['total_count']}[/bold]")
        return response["tasks"]
    else:
        console.print("[yellow]No pending manual approval tasks[/yellow]")
        return []

async def approve_task(task_id: str, task_type: str):
    """Approve a manual approval task."""
    console.print(f"\n[bold cyan]Approving Task: {task_id}[/bold cyan]")
    
    # First assign the task
    assign_req = {
        "task_id": task_id,
        "assigned_to": "test@publisher.com"
    }
    
    assign_response = make_request("assign_task", assign_req, token=ADMIN_TOKEN)
    console.print(f"Assignment: {assign_response}")
    
    # Then complete it with approval
    complete_req = {
        "task_id": task_id,
        "resolution": "approved",
        "resolution_detail": f"Approved {task_type} after manual review",
        "resolved_by": "test@publisher.com"
    }
    
    complete_response = make_request("complete_task", complete_req, token=ADMIN_TOKEN)
    console.print(f"[green]✓ Task approved: {complete_response}[/green]")

async def reject_task(task_id: str, reason: str):
    """Reject a manual approval task."""
    console.print(f"\n[bold cyan]Rejecting Task: {task_id}[/bold cyan]")
    
    complete_req = {
        "task_id": task_id,
        "resolution": "rejected",
        "resolution_detail": reason,
        "resolved_by": "test@publisher.com"
    }
    
    complete_response = make_request("complete_task", complete_req, token=ADMIN_TOKEN)
    console.print(f"[red]✗ Task rejected: {complete_response}[/red]")

async def main():
    """Run manual approval workflow test."""
    console.print(Panel.fit("[bold blue]Manual Approval Mode Test[/bold blue]"))
    
    # Test 1: Create media buy with manual approval
    create_task_id, create_req = await test_manual_approval_create()
    
    # Test 2: Update media buy with manual approval
    update_task_id, update_req = await test_manual_approval_update()
    
    # Wait for tasks to be created
    await asyncio.sleep(1)
    
    # Review pending tasks
    tasks = await review_pending_tasks()
    
    # Demonstrate approval workflow
    if create_task_id:
        await approve_task(create_task_id, "create_media_buy")
        
        # Check if media buy was created after approval
        console.print("\n[bold]Verifying media buy creation after approval...[/bold]")
        # In a real test, would call get_media_buy_delivery or similar
    
    # Demonstrate rejection workflow
    if update_task_id:
        await reject_task(update_task_id, "Budget change exceeds approval limit")
    
    # Show final task status
    await asyncio.sleep(1)
    await review_pending_tasks()
    
    console.print("\n[bold green]✓ Manual approval workflow test completed![/bold green]")
    console.print("\n[dim]Note: For this test to work properly, ensure your adapter")
    console.print("configuration has manual_approval_required: true[/dim]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")