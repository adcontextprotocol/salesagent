import asyncio
import json
from datetime import datetime, timedelta
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.live import Live
from rich.spinner import Spinner

console = Console()

class Simulation:
    """Orchestrates a full media buy lifecycle simulation."""

    def __init__(self, server_script: str, brief_path: str):
        self.client = Client(server_script)
        self.brief_path = brief_path
        self.today = datetime(2025, 6, 15)
        self.proposal = None
        self.media_buy_id = None

    async def run(self):
        """Executes the entire simulation flow."""
        async with self.client:
            console.rule("[bold magenta]Phase 1: Negotiation[/bold magenta]")
            await self.step(self.negotiate_proposal, "Negotiate Proposal", "2025-06-15")
            
            if not self.proposal or not self.proposal.structured_content.get("media_packages"):
                console.print("[bold red]Proposal negotiation failed or resulted in no packages. Halting simulation.[/bold red]")
                return

            console.rule("[bold magenta]Phase 2: Setup[/bold magenta]")
            await self.step(self.accept_proposal, "Accept Proposal", "2025-06-18")
            await self.step(self.submit_creatives, "Submit Creatives", "2025-06-22")
            await self.step(self.check_creative_status_fail, "Check Creative Status (Pending)", "2025-06-23")
            await self.step(self.check_creative_status_pass, "Check Creative Status (Approved)", "2025-06-24")

            console.rule("[bold magenta]Phase 3: Execution & Reporting[/bold magenta]")
            # Note: The start_time of the campaign is determined by the AI proposal,
            # which is usually the current date. We simulate a few days passing.
            start_date = datetime.fromisoformat(self.proposal.structured_content['start_time'].replace('Z', '+00:00'))
            
            await self.step(self.check_delivery_lag, "Check Delivery (Lag Day)", (start_date + timedelta(days=1)).strftime('%Y-%m-%d'))
            await self.step(self.check_first_day_delivery, "Check Delivery (First Day)", (start_date + timedelta(days=2)).strftime('%Y-%m-%d'))
            await self.step(self.update_performance, "Update Performance Index", (start_date + timedelta(days=8)).strftime('%Y-%m-%d'))
            await self.step(self.reallocate_budget, "Reallocate Budget", (start_date + timedelta(days=10)).strftime('%Y-%m-%d'))
            await self.step(self.check_delivery_post_realloc, "Check Delivery (Post-Reallocation)", (start_date + timedelta(days=12)).strftime('%Y-%m-%d'))

    async def step(self, func, title: str, date_str: str):
        """Executes a single step in the simulation."""
        # Ensure the datetime is timezone-aware
        tz = datetime.now().astimezone().tzinfo
        self.today = datetime.fromisoformat(date_str).replace(tzinfo=tz)
        
        spinner = Spinner("dots", text=f" [bold yellow]Executing:[/bold yellow] {title} (Simulated Date: {date_str})...")
        with Live(spinner, console=console, transient=True, vertical_overflow="visible"):
            await asyncio.sleep(1) # For dramatic effect
            result = await func()
        
        console.print(f"[green] ✓[/green] [bold green]Finished:[/bold green] {title}")
        
        # --- Enhanced Logging ---
        if result and hasattr(result, 'stdout') and result.stdout:
            console.print(Panel(result.stdout, title="[cyan]Server Output[/cyan]", border_style="cyan", expand=False))
        
        console.print(Panel(Pretty(result.structured_content if result else "No result"), title="[green]Client Result[/green]", expand=False, border_style="green"))
        # --- End Enhanced Logging ---

    async def negotiate_proposal(self):
        console.print("--> Calling tool: [bold]get_proposal[/bold]")
        with open(self.brief_path, 'r') as f:
            brief_data = json.load(f)
        
        self.proposal = await self.client.call_tool(
            "get_proposal", 
            {"brief": brief_data["brief"], "provided_signals": brief_data["provided_signals"]}
        )
        
        # --- DEBUGGING STEP ---
        console.print("\n[bold cyan]Inspecting returned object type...[/bold cyan]")
        console.print(f"Type of self.proposal: {type(self.proposal)}")
        if hasattr(self.proposal, 'structured_content'):
            console.print(f"Type of self.proposal.structured_content: {type(self.proposal.structured_content)}")
        console.print("-------------------------------------\n")
        # --- END DEBUGGING ---

        return self.proposal

    async def accept_proposal(self):
        console.print("--> Calling tool: [bold]accept_proposal[/bold]")
        prop = self.proposal.structured_content
        result = await self.client.call_tool("accept_proposal", {
            "proposal_id": prop["proposal_id"],
            "accepted_packages": [p["package_id"] for p in prop["media_packages"]],
            "billing_entity": "Purina Inc.",
            "po_number": "PUR-2025-Q3-001",
            "today": self.today
        })
        self.media_buy_id = result.structured_content["media_buy_id"]
        return result

    async def submit_creatives(self):
        console.print("--> Calling tool: [bold]add_creative_assets[/bold]")
        return await self.client.call_tool("add_creative_assets", {
            "media_buy_id": self.media_buy_id,
            "assets": [{"creative_id": "cat_video_15s", "format": "E2E mobile video", "name": "Cat Food Ad", "video_url": "...", "companion_assets": {}, "click_url": "...", "package_assignments": []}],
            "today": self.today
        })

    async def check_creative_status_fail(self):
        console.print("--> Calling tool: [bold]check_media_buy_status[/bold]")
        return await self.client.call_tool("check_media_buy_status", {"media_buy_id": self.media_buy_id, "today": self.today})

    async def check_creative_status_pass(self):
        console.print("--> Calling tool: [bold]check_media_buy_status[/bold]")
        return await self.client.call_tool("check_media_buy_status", {"media_buy_id": self.media_buy_id, "today": self.today})

    async def check_delivery_lag(self):
        console.print("--> Calling tool: [bold]get_media_buy_delivery[/bold]")
        return await self.client.call_tool("get_media_buy_delivery", {
            "media_buy_id": self.media_buy_id,
            "date_range": {"start": "2025-07-01", "end": "2025-07-01"},
            "today": self.today
        })

    async def check_first_day_delivery(self):
        console.print("--> Calling tool: [bold]get_media_buy_delivery[/bold]")
        return await self.client.call_tool("get_media_buy_delivery", {
            "media_buy_id": self.media_buy_id,
            "date_range": {"start": "2025-07-01", "end": "2025-07-01"},
            "today": self.today
        })
        
    async def update_performance(self):
        console.print("--> Calling tool: [bold]update_media_buy_performance_index[/bold]")
        prop = self.proposal.structured_content
        return await self.client.call_tool("update_media_buy_performance_index", {
            "media_buy_id": self.media_buy_id,
            "package_performance": [{"package_id": p["package_id"], "performance_index": 120 if "Cat" in p["name"] else 80} for p in prop["media_packages"]],
            "today": self.today
        })

    async def reallocate_budget(self):
        console.print("--> Calling tool: [bold]update_media_buy[/bold]")
        prop = self.proposal.structured_content
        best_pkg = max(prop["media_packages"], key=lambda p: 120 if "Cat" in p["name"] else 80)
        return await self.client.call_tool("update_media_buy", {
            "media_buy_id": self.media_buy_id,
            "action": "change_package_budget",
            "package_id": best_pkg["package_id"],
            "budget": best_pkg["budget"] + 20000,
            "today": self.today
        })

    async def check_delivery_post_realloc(self):
        console.print("--> Calling tool: [bold]get_media_buy_delivery[/bold]")
        return await self.client.call_tool("get_media_buy_delivery", {
            "media_buy_id": self.media_buy_id,
            "date_range": {"start": "2025-07-01", "end": "2025-07-11"},
            "today": self.today
        })

if __name__ == "__main__":
    sim = Simulation(server_script="main.py", brief_path="brief.json")
    asyncio.run(sim.run())