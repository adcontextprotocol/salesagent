#!/usr/bin/env python
"""
A2A CLI Wrapper - Workaround for a2a-cli --server flag bug
This wrapper provides a working interface to A2A servers until the a2a-cli bug is fixed.

Usage:
    python a2a_cli_wrapper.py --server https://adcp-sales-agent.fly.dev/a2a send "get products"
    python a2a_cli_wrapper.py --server http://localhost:8091 chat
"""

import asyncio
import json
import uuid

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()
app = typer.Typer()

# Global session ID for conversation continuity
SESSION_ID = str(uuid.uuid4())


async def send_task(server_url: str, message: str, wait: bool = False) -> dict:
    """Send a task to the A2A server using JSON-RPC."""
    # Ensure URL ends with /rpc
    if not server_url.endswith("/rpc"):
        server_url = server_url.rstrip("/") + "/rpc"

    # Create JSON-RPC request
    rpc_request = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {"message": {"role": "user", "parts": [{"text": message}]}},
        "id": str(uuid.uuid4()),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(server_url, json=rpc_request)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            console.print(f"[red]Error: {result['error']['message']}[/red]")
            return result

        # Handle nested result structure
        if "result" in result:
            task = result["result"]
        else:
            task = result

        # The task ID might be in different places depending on the response structure
        task_id = task.get("id") if task else None

        if wait and task_id:
            # Poll for task completion
            console.print(f"[yellow]Task {task_id} created, waiting for completion...[/yellow]")

            while True:
                await asyncio.sleep(1)

                # Get task status
                status_request = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                    "id": str(uuid.uuid4()),
                }

                status_response = await client.post(server_url, json=status_request)
                status_result = status_response.json()

                if "result" in status_result:
                    task = status_result["result"]
                    status = task.get("status", {})
                    state = status.get("state") if isinstance(status, dict) else status

                    if state in ["completed", "failed", "cancelled"]:
                        break

                    console.print(f"[dim]Status: {state}[/dim]")

        return task


async def stream_task(server_url: str, message: str):
    """Send a task and stream the response using SSE."""
    # Ensure URL ends with /rpc
    if not server_url.endswith("/rpc"):
        server_url = server_url.rstrip("/") + "/rpc"

    # Create JSON-RPC request for streaming
    rpc_request = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {"message": {"role": "user", "parts": [{"text": message}]}},
        "id": str(uuid.uuid4()),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", server_url, json=rpc_request) as response:
            response.raise_for_status()

            console.print("[green]Streaming response...[/green]")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "result" in data:
                            result = data["result"]
                            event_type = result.get("type", "")
                            task = result.get("task", {})

                            if event_type == "task.created":
                                console.print(f"[yellow]Task created: {task.get('id')}[/yellow]")
                            elif event_type == "task.status":
                                status = task.get("status", {})
                                state = status.get("state") if isinstance(status, dict) else status
                                console.print(f"[dim]Status: {state}[/dim]")
                            elif event_type == "task.done":
                                output = task.get("output", {})
                                if output:
                                    console.print(
                                        Panel(
                                            Syntax(json.dumps(output, indent=2), "json"),
                                            title="Task Output",
                                            border_style="green",
                                        )
                                    )
                                break
                    except json.JSONDecodeError:
                        pass


@app.command()
def send(
    server: str = typer.Option("http://localhost:8091", "--server", "-s", help="A2A server URL"),
    message: str = typer.Argument(..., help="Message to send"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for task completion"),
    stream: bool = typer.Option(False, "--stream", help="Stream the response"),
):
    """Send a message to the A2A server."""
    console.print(f"[cyan]Sending to: {server}[/cyan]")
    console.print(f"[cyan]Message: {message}[/cyan]\n")

    if stream:
        asyncio.run(stream_task(server, message))
    else:
        task = asyncio.run(send_task(server, message, wait))

        # Display result
        if task:
            output = task.get("output")
            if output:
                if "message" in output:
                    console.print(Panel(output["message"], title="Response", border_style="green"))
                elif "products" in output:
                    products = output["products"]
                    console.print(f"[green]Found {len(products)} products:[/green]")
                    for p in products:
                        console.print(f"  • {p['name']}: {p['description']}")
                        console.print(f"    CPM: ${p.get('pricing', {}).get('cpm', 'N/A')}")
                else:
                    console.print(
                        Panel(Syntax(json.dumps(output, indent=2), "json"), title="Task Output", border_style="green")
                    )
            else:
                console.print(
                    Panel(Syntax(json.dumps(task, indent=2), "json"), title="Task Details", border_style="yellow")
                )


@app.command()
def chat(server: str = typer.Option("http://localhost:8091", "--server", "-s", help="A2A server URL")):
    """Interactive chat mode with the A2A server."""
    console.print(
        Panel(
            f"[cyan]Connected to: {server}[/cyan]\n"
            f"[dim]Session ID: {SESSION_ID}[/dim]\n"
            f"[yellow]Type 'exit' or 'quit' to end the chat[/yellow]",
            title="A2A Chat Mode",
            border_style="blue",
        )
    )

    while True:
        try:
            message = console.input("\n[bold cyan]You:[/bold cyan] ")

            if message.lower() in ["exit", "quit"]:
                console.print("[yellow]Goodbye![/yellow]")
                break

            console.print("[dim]Sending...[/dim]")
            task = asyncio.run(send_task(server, message, wait=True))

            if task and "output" in task:
                output = task["output"]
                if "message" in output:
                    console.print(f"\n[bold green]Agent:[/bold green] {output['message']}")
                else:
                    console.print("\n[bold green]Agent:[/bold green]")
                    console.print(Syntax(json.dumps(output, indent=2), "json"))

        except KeyboardInterrupt:
            console.print("\n[yellow]Chat interrupted[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command()
def info(server: str = typer.Option("http://localhost:8091", "--server", "-s", help="A2A server URL")):
    """Get agent information from the A2A server."""

    async def get_info():
        # Try to get agent card
        base_url = server.rstrip("/rpc").rstrip("/")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Get agent card
                response = await client.get(f"{base_url}/")
                response.raise_for_status()
                agent_card = response.json()

                console.print(
                    Panel(Syntax(json.dumps(agent_card, indent=2), "json"), title="Agent Card", border_style="blue")
                )

                # Display skills if available
                if "skills" in agent_card:
                    console.print("\n[cyan]Available Skills:[/cyan]")
                    for skill in agent_card["skills"]:
                        console.print(f"  • [green]{skill['name']}[/green]: {skill['description']}")

            except Exception as e:
                console.print(f"[red]Error getting agent info: {e}[/red]")

    asyncio.run(get_info())


@app.command()
def test(server: str = typer.Option("http://localhost:8091", "--server", "-s", help="A2A server URL")):
    """Run test queries against the A2A server."""
    test_queries = [
        "What products are available?",
        "Show me video advertising products",
        "Create a campaign with $5000 budget",
        "Get performance reports",
    ]

    console.print(Panel(f"[cyan]Testing server: {server}[/cyan]", title="A2A Server Test Suite", border_style="blue"))

    for query in test_queries:
        console.print(f"\n[yellow]Test:[/yellow] {query}")
        task = asyncio.run(send_task(server, query, wait=True))

        if task and "output" in task:
            console.print("[green]✓ Success[/green]")
        else:
            console.print("[red]✗ Failed[/red]")


if __name__ == "__main__":
    app()
