import asyncio
from datetime import datetime, timedelta
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

console = Console()

class SimulationV2_1:
    """Orchestrates a simulation using the V2.1 API."""

    def __init__(self, server_script: str):
        self.client = Client(server_script)
        self.today = datetime(2025, 7, 1)
        self.query_id = None
        self.packages = []
        self.media_buy_id = None

    async def run(self):
        """Executes the entire simulation flow."""
        async with self.client:
            console.rule("[bold magenta]Phase 1: Discovery[/bold magenta]")
            publisher_formats = await self.step(self.get_formats, "Get Publisher Creative Formats")
            await self.step(self.get_available_packages, "Get Available Packages", publisher_formats)
            
            if not self.packages:
                console.print("[bold red]No compatible packages found. Halting.[/bold red]")
                return

            console.rule("[bold magenta]Phase 2: Execution[/bold magenta]")
            await self.step(self.create_the_media_buy, "Create Media Buy")

    async def step(self, func, title: str, *args):
        """Executes a single step in the simulation."""
        console.print(f" [bold yellow]Executing:[/bold yellow] {title}...")
        result = await func(*args)
        console.print(f"[green] ✓[/green] [bold green]Finished:[/bold green] {title}")
        console.print(Panel(Pretty(result.structured_content if result else "No result"), expand=False))
        return result.structured_content if result else None

    async def get_formats(self):
        return await self.client.call_tool("get_publisher_creative_formats")

    async def get_available_packages(self, formats_response):
        console.print("--> Calling tool: [bold]get_packages[/bold]")
        
        # Define buyer creatives, one standard and one custom
        buyer_creatives = [
            {
                "id": "cr-banner-1", "format_id": "std_banner_300x250",
                "spec": {"format_type": "standard", "media_type": "display", "mime": "image/png", "w": 300, "h": 250}
            },
            {
                "id": "cr-custom-1", "format_id": "custom_e2e_video",
                "spec": {"format_type": "custom", "assets": {"primary_video": {}, "end_card": {}}}
            }
        ]

        request = {
            "budget": 50000.0, "currency": "USD",
            "start_time": self.today, "end_time": self.today + timedelta(days=30),
            "creatives": buyer_creatives, "targeting": {}
        }
        
        response = await self.client.call_tool("get_packages", {"request": request})
        
        if response and response.structured_content:
            self.query_id = response.structured_content.get("query_id")
            self.packages = response.structured_content.get("packages", [])
        
        return response

    async def create_the_media_buy(self):
        console.print("--> Calling tool: [bold]create_media_buy[/bold]")
        
        # Select the first compatible package
        selected_package_id = self.packages[0]['package_id']
        
        request = {
            "selected_packages": [{"package_id": selected_package_id}],
            "billing_entity": "Test Buyer Inc.", "po_number": "PO-V2.1-001"
        }

        return await self.client.call_tool("create_media_buy", {"request": request, "query_id": self.query_id})

if __name__ == "__main__":
    sim = SimulationV2_1(server_script="main.py")
    asyncio.run(sim.run())