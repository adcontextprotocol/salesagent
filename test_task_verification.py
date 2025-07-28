#!/usr/bin/env python3
"""
Test script for AI task verification functionality.
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

async def create_test_task():
    """Create a test task for verification."""
    console.print("\n[bold cyan]Creating Test Task[/bold cyan]")
    
    # Create a manual approval task
    task_req = {
        "task_type": "manual_approval",
        "priority": "high",
        "media_buy_id": "gam_12345",
        "operation": "update_media_buy",
        "error_detail": "Update daily budget to $100/day",
        "context_data": {
            "request": {
                "media_buy_id": "gam_12345",
                "daily_budget": 100.0,
                "packages": [
                    {
                        "package_id": "premium_sports",
                        "budget": 500.0
                    }
                ]
            },
            "principal_id": "acme_corp"
        },
        "due_in_hours": 2
    }
    
    response = make_request("create_human_task", task_req)
    console.print(f"Task created: {response}")
    
    return response["task_id"]

async def test_verify_task(task_id: str):
    """Test verifying a task."""
    console.print(f"\n[bold cyan]Verifying Task: {task_id}[/bold cyan]")
    
    # Verify the task
    verify_req = {
        "task_id": task_id,
        "expected_outcome": {
            "daily_budget": 100.0,
            "package_premium_sports_budget": 500.0
        }
    }
    
    response = make_request("verify_task", verify_req)
    
    console.print("\n[bold]Verification Result:[/bold]")
    console.print(f"Verified: {'✅' if response['verified'] else '❌'} {response['verified']}")
    console.print(f"Actual State: {response['actual_state']}")
    console.print(f"Expected State: {response['expected_state']}")
    
    if response['discrepancies']:
        console.print("\n[red]Discrepancies:[/red]")
        for discrepancy in response['discrepancies']:
            console.print(f"  - {discrepancy}")
    
    return response

async def test_mark_task_complete(task_id: str, override: bool = False):
    """Test marking a task as complete with verification."""
    console.print(f"\n[bold cyan]Marking Task Complete: {task_id}[/bold cyan]")
    console.print(f"Override verification: {override}")
    
    mark_req = {
        "task_id": task_id,
        "override_verification": override,
        "completed_by": "admin@publisher.com"
    }
    
    response = make_request("mark_task_complete", mark_req, token=ADMIN_TOKEN)
    
    console.print("\n[bold]Mark Complete Result:[/bold]")
    console.print(f"Status: {response['status']}")
    
    if response['status'] == "verification_failed":
        console.print("[red]Verification failed![/red]")
        console.print(f"Message: {response['message']}")
        console.print("Discrepancies:")
        for discrepancy in response.get('discrepancies', []):
            console.print(f"  - {discrepancy}")
    else:
        console.print(f"Verified: {'✅' if response['verified'] else '❌ (overridden)'}")
        console.print(f"Message: {response['message']}")
        
        if 'verification_details' in response:
            details = response['verification_details']
            console.print("\nVerification Details:")
            console.print(f"  Actual: {details['actual_state']}")
            console.print(f"  Expected: {details['expected_state']}")
            if details['discrepancies']:
                console.print("  Discrepancies:")
                for d in details['discrepancies']:
                    console.print(f"    - {d}")
    
    return response

async def test_creative_approval_verification():
    """Test verification of creative approval tasks."""
    console.print("\n[bold cyan]Testing Creative Approval Verification[/bold cyan]")
    
    # Create a creative approval task
    task_req = {
        "task_type": "creative_approval",
        "priority": "medium",
        "creative_id": "creative_123",
        "error_detail": "Manual review required for billboard format",
        "context_data": {
            "format": "dooh_billboard",
            "name": "Test Billboard"
        }
    }
    
    response = make_request("create_human_task", task_req)
    task_id = response["task_id"]
    console.print(f"Creative approval task created: {task_id}")
    
    # Complete the task
    complete_req = {
        "task_id": task_id,
        "resolution": "approved",
        "resolution_detail": "Creative meets standards",
        "resolved_by": "reviewer@publisher.com"
    }
    
    complete_response = make_request("complete_task", complete_req, token=ADMIN_TOKEN)
    console.print(f"Task completed: {complete_response}")
    
    # Now verify it
    verify_req = {
        "task_id": task_id
    }
    
    verify_response = make_request("verify_task", verify_req)
    console.print(f"\nVerification: {verify_response}")

async def main():
    """Run task verification tests."""
    console.print(Panel.fit("[bold blue]Task Verification Test Suite[/bold blue]"))
    
    # Test 1: Create and verify a task
    task_id = await create_test_task()
    await asyncio.sleep(1)
    
    # Test 2: Verify the task (should fail since nothing was done)
    verification = await test_verify_task(task_id)
    
    # Test 3: Try to mark complete without override (should fail)
    console.print("\n[yellow]Attempting to mark complete without override...[/yellow]")
    result = await test_mark_task_complete(task_id, override=False)
    
    # Test 4: Mark complete with override
    if result['status'] == "verification_failed":
        console.print("\n[yellow]Now trying with override...[/yellow]")
        await test_mark_task_complete(task_id, override=True)
    
    # Test 5: Test creative approval verification
    await test_creative_approval_verification()
    
    console.print("\n[bold green]✓ Task verification tests completed![/bold green]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")