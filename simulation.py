import asyncio
from datetime import date, timedelta
import uuid

from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule

from schemas import *

console = Console()

class FinalSim:
    """A simulation for the final V2.3 protocol with advanced pricing and pacing."""

    def __init__(self, server_script: str):
        self.client = Client(server_script)
        self.today = date(2025, 7, 25)
        self.media_buy_id: str = ""
        self.products: List[Product] = []
        self.buy_request: CreateMediaBuyRequest = None

    async def run(self):
        console.print(Rule("[bold magenta]AdCP V2.3 Final Simulation[/bold magenta]", style="magenta"))
        async with self.client:
            await self._phase_1_discover_and_buy()
            if not self.media_buy_id: return
            await self._phase_2_reporting()

    async def _step(self, title: str, tool_name: str, params: dict = {}) -> Dict:
        console.print(f"\n[bold yellow]>> {title}[/bold yellow]")
        console.print(f"--> Calling tool: [bold]{tool_name}[/bold]")
        result = await self.client.call_tool(tool_name, params)
        content = result.structured_content if result else {}
        console.print(Panel(Pretty(content), expand=False, border_style="green"))
        return content

    async def _phase_1_discover_and_buy(self):
        console.print(Rule("Phase 1: Discovery and Purchase", style="cyan"))
        list_req = ListProductsRequest(brief="Brief for a mix of guaranteed and non-guaranteed products.")
        list_res = await self._step("Discover Products", "list_products", {"req": list_req.model_dump()})
        self.products = [Product(**p) for p in list_res.get("products", [])]

        self.buy_request = CreateMediaBuyRequest(
            product_ids=[p.product_id for p in self.products],
            flight_start_date=self.today,
            flight_end_date=self.today + timedelta(days=30),
            total_budget=250000.00,
            targeting_overlay=Targeting(geography=["USA-NY"]),
            pacing="daily_budget",
            daily_budget=8000.00
        )
        create_res = await self._step("Create Media Buy with Daily Budget", "create_media_buy", {"req": self.buy_request.model_dump(mode='json')})
        self.media_buy_id = create_res.get("media_buy_id")

    async def _phase_2_reporting(self):
        console.print(Rule("Phase 2: Reporting Flight", style="cyan"))
        flight_duration = (self.buy_request.flight_end_date - self.buy_request.flight_start_date).days
        for week in range(0, (flight_duration // 7) + 2):
            sim_date = self.buy_request.flight_start_date + timedelta(weeks=week)
            if sim_date > self.buy_request.flight_end_date + timedelta(days=1): break
            
            console.print(f"\n--- Reporting for Week {week+1} (Simulated Date: {sim_date}) ---")
            await self._step(
                f"Get Delivery Data",
                "get_media_buy_delivery",
                {"media_buy_id": self.media_buy_id, "today": sim_date.isoformat()}
            )
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    sim = FinalSim(server_script="main.py")
    asyncio.run(sim.run())