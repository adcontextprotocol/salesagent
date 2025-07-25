import asyncio
from datetime import datetime, timedelta
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.live import Live
from rich.spinner import Spinner

# V2 Schemas are imported implicitly via the client, but we can define them for clarity
# This script assumes the schemas in `schemas.py` are V2 compliant.

console = Console()

class SimulationV2:
    """Orchestrates a full media buy lifecycle simulation using the V2 API."""

    def __init__(self, server_script: str):
        self.client = Client(server_script)
        self.today = datetime(2025, 7, 1)
        self.query_id = None
        self.packages = []
        self.media_buy_id = None
        self.selected_package_id = None

    async def run(self):
        """Executes the entire simulation flow."""
        async with self.client:
            console.rule("[bold magenta]Phase 1: Package Discovery[/bold magenta]")
            await self.step(self.get_available_packages, "Get Available Packages", "2025-07-01")
            
            if not self.packages:
                console.print("[bold red]No compatible packages found. Halting simulation.[/bold red]")
                return

            console.rule("[bold magenta]Phase 2: Media Buy Creation[/bold magenta]")
            await self.step(self.create_the_media_buy, "Create Media Buy", "2025-07-02")
            
            console.rule("[bold magenta]Phase 3: Execution & Reporting[/bold magenta]")
            await self.step(self.submit_creatives, "Submit Creatives", "2025-07-03")
            await self.step(self.check_status, "Check Media Buy Status", "2025-07-10")

    async def step(self, func, title: str, date_str: str):
        """Executes a single step in the simulation."""
        tz = datetime.now().astimezone().tzinfo
        self.today = datetime.fromisoformat(date_str).replace(tzinfo=tz)
        
        spinner = Spinner("dots", text=f" [bold yellow]Executing:[/bold yellow] {title} (Simulated Date: {date_str})...")
        with Live(spinner, console=console, transient=True, vertical_overflow="visible"):
            await asyncio.sleep(1)
            result = await func()
        
        console.print(f"[green] ✓[/green] [bold green]Finished:[/bold green] {title}")
        
        if result and hasattr(result, 'stdout') and result.stdout:
            console.print(Panel(result.stdout, title="[cyan]Server Output[/cyan]", border_style="cyan", expand=False))
        
        console.print(Panel(Pretty(result.structured_content if result else "No result"), title="[green]Client Result[/green]", expand=False, border_style="green"))

    async def get_available_packages(self):
        console.print("--> Calling tool: [bold]get_packages[/bold]")
        
        # Define the creatives the buyer has
        buyer_creatives = [
            {"id": "cr-banner-1", "media_type": "display", "mime": "image/png", "w": 300, "h": 250},
            {"id": "cr-video-1", "media_type": "video", "mime": "video/mp4", "w": 1920, "h": 1080, "dur": 30}
        ]

        request = {
            "budget": 50000.0,
            "currency": "USD",
            "start_time": self.today,
            "end_time": self.today + timedelta(days=30),
            "creatives": buyer_creatives,
            "targeting": {
                "provided_signals": [
                    {"type": "interest", "value": "cats"}
                ]
            }
        }
        
        response = await self.client.call_tool("get_packages", {"request": request})
        
        if response and response.structured_content:
            self.query_id = response.structured_content.get("query_id")
            all_packages = response.structured_content.get("packages", [])
            
            # Find the first package that is compatible with at least one of our creatives
            for pkg in all_packages:
                if any(comp.get("compatible") for comp in pkg.get("creative_compatibility", {}).values()):
                    self.packages.append(pkg)
                    self.selected_package_id = pkg.get("package_id")
                    break # Select the first compatible package for simplicity
        
        return response

    async def create_the_media_buy(self):
        console.print("--> Calling tool: [bold]create_media_buy[/bold]")
        
        selected_pkg = {
            "package_id": self.selected_package_id
        }
        # If it were a non-guaranteed package, we'd add max_cpm here
        # selected_pkg["max_cpm"] = 8.50 

        request = {
            "selected_packages": [selected_pkg],
            "billing_entity": "Purina Inc.",
            "po_number": "PUR-V2-2025-001"
        }

        response = await self.client.call_tool("create_media_buy", {"request": request, "query_id": self.query_id})
        
        if response and response.structured_content:
            self.media_buy_id = response.structured_content.get("media_buy_id")
            
        return response

    async def submit_creatives(self):
        console.print("--> Calling tool: [bold]add_creative_assets[/bold]")
        
        # Submit the creative that we know is compatible
        asset_to_submit = {
            "id": "cr-banner-1", "media_type": "display", "mime": "image/png", "w": 300, "h": 250
        }
        
        return await self.client.call_tool("add_creative_assets", {
            "media_buy_id": self.media_buy_id,
            "assets": [asset_to_submit]
        })

    async def check_status(self):
        console.print("--> Calling tool: [bold]check_media_buy_status[/bold]")
        return await self.client.call_tool("check_media_buy_status", {"media_buy_id": self.media_buy_id})

if __name__ == "__main__":
    sim = SimulationV2(server_script="main.py")
    asyncio.run(sim.run())
