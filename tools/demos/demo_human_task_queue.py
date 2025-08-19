#!/usr/bin/env python3
"""
Test script for human-in-the-loop task queue functionality.
"""

import asyncio
from datetime import datetime

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8080"
ADMIN_TOKEN = "admin"
ACME_TOKEN = "acme_corp_token"


def make_request(endpoint: str, data: dict, token: str = ACME_TOKEN):
    """Make a request to the AdCP server."""
    headers = {"x-adcp-auth": token, "content-type": "application/json"}

    response = requests.post(f"{BASE_URL}/{endpoint}", headers=headers, json=data)

    return response.json()


async def test_creative_approval_task():
    """Test creating a human task for creative approval."""
    console.print("\n[bold cyan]Testing Creative Approval Task[/bold cyan]")

    # Create a creative that requires human approval
    create_req = {
        "format_id": "dooh_billboard",  # Not in auto-approve list
        "content_uri": "https://example.com/creative/billboard.jpg",
        "name": "Test Billboard Creative",
        "click_through_url": "https://example.com/landing",
        "metadata": {"size": "1920x1080", "duration": 10},
    }

    response = make_request("create_creative", create_req)
    console.print(f"Creative created: {response}")

    # Check status - should be pending review
    creative_id = response["creative"]["creative_id"]
    status_req = {"creative_ids": [creative_id]}

    status_response = make_request("check_creative_status", status_req)
    console.print(f"Creative status: {status_response['statuses'][0]}")

    # Create a manual task for the creative
    task_req = {
        "task_type": "creative_approval",
        "priority": "high",
        "creative_id": creative_id,
        "error_detail": "Billboard format requires manual review for brand safety",
        "context_data": {"format": "dooh_billboard", "size": "1920x1080"},
        "due_in_hours": 4,
    }

    task_response = make_request("create_human_task", task_req)
    console.print(f"[green]Task created: {task_response}[/green]")

    return task_response["task_id"]


async def test_permission_exception_task():
    """Test creating a task for permission exceptions."""
    console.print("\n[bold cyan]Testing Permission Exception Task[/bold cyan]")

    # Simulate a permission error scenario
    task_req = {
        "task_type": "permission_exception",
        "priority": "urgent",
        "adapter_name": "google_ad_manager",
        "media_buy_id": "gam_12345",
        "operation": "create_line_item",
        "error_detail": "PermissionError: Service account lacks 'Orders.write' permission in GAM",
        "context_data": {"advertiser_id": "123456", "order_name": "Q4 Campaign", "required_permission": "Orders.write"},
        "due_in_hours": 2,
    }

    response = make_request("create_human_task", task_req)
    console.print(f"[red]Permission task created: {response}[/red]")

    return response["task_id"]


async def test_get_pending_tasks():
    """Test retrieving pending tasks."""
    console.print("\n[bold cyan]Testing Get Pending Tasks[/bold cyan]")

    # Get all pending tasks
    req = {"priority": None, "include_overdue": True}

    # First as regular principal
    response = make_request("get_pending_tasks", req)
    console.print(f"Tasks for principal: {response['total_count']} tasks")

    # Now as admin to see all tasks
    admin_response = make_request("get_pending_tasks", req, token=ADMIN_TOKEN)
    console.print(f"Tasks for admin: {admin_response['total_count']} tasks")

    # Display tasks in a table
    if admin_response["tasks"]:
        table = Table(title="Pending Human Tasks")
        table.add_column("Task ID", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Priority", style="red")
        table.add_column("Status")
        table.add_column("Due By")
        table.add_column("Details", max_width=40)

        for task in admin_response["tasks"]:
            due_by = task.get("due_by", "N/A")
            if due_by != "N/A":
                due_dt = datetime.fromisoformat(due_by.replace("Z", "+00:00"))
                due_by = due_dt.strftime("%Y-%m-%d %H:%M")

            table.add_row(
                task["task_id"],
                task["task_type"],
                task["priority"],
                task["status"],
                due_by,
                task.get("error_detail", "")[:40] + "...",
            )

        console.print(table)

    return admin_response["tasks"]


async def test_assign_and_complete_task(task_id: str):
    """Test assigning and completing a task."""
    console.print("\n[bold cyan]Testing Task Assignment and Completion[/bold cyan]")

    # Assign task (admin only)
    assign_req = {"task_id": task_id, "assigned_to": "john.doe@company.com"}

    assign_response = make_request("assign_task", assign_req, token=ADMIN_TOKEN)
    console.print(f"Task assigned: {assign_response}")

    # Complete task
    complete_req = {
        "task_id": task_id,
        "resolution": "approved",
        "resolution_detail": "Creative meets brand safety guidelines",
        "resolved_by": "john.doe@company.com",
    }

    complete_response = make_request("complete_task", complete_req, token=ADMIN_TOKEN)
    console.print(f"[green]Task completed: {complete_response}[/green]")


async def main():
    """Run all tests."""
    console.print(Panel.fit("[bold blue]Human-in-the-Loop Task Queue Test[/bold blue]"))

    # Create test tasks
    await test_creative_approval_task()
    await test_permission_exception_task()

    # Wait a moment for tasks to be created
    await asyncio.sleep(1)

    # Get pending tasks
    tasks = await test_get_pending_tasks()

    # Assign and complete one task
    if tasks:
        await test_assign_and_complete_task(tasks[0]["task_id"])

    # Show updated task list
    await test_get_pending_tasks()

    console.print("\n[bold green]✓ Human task queue test completed![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
