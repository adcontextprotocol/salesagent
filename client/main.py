import asyncio
import argparse
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

console = Console()

async def main(brief: str):
    """
    A client to negotiate media buys with an ADCP server.
    """
    server_url = "http://localhost:8001/sse"
    console.print(f"Connecting to server at [bold cyan]{server_url}[/]...")
    
    try:
        async with Client(server_url) as client:
            console.print("[bold green]Connection successful![/bold green]")
            
            console.print(f"\n[magenta]Sending brief to server:[/] [italic]{brief}[/italic]")
            try:
                proposal = await client.call_tool("get_proposal", {"brief": brief})
                
                console.print(Panel("[bold green]Proposal Received![/bold green]", expand=False))
                console.print(Pretty(proposal))

            except Exception as e:
                console.print(Panel(f"[bold red]An error occurred during tool call:[/bold red]\n{e}", expand=False))

    except Exception as e:
        console.print(f"[bold red]Failed to connect or communicate with the server:[/bold red] {e}")
        console.print("Please ensure the server is running: fastmcp run main.py --transport sse --port 8001")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ADCP Client for testing media buys.")
    parser.add_argument("brief", type=str, help="The campaign brief to send to the server.")
    args = parser.parse_args()
    
    asyncio.run(main(args.brief))
