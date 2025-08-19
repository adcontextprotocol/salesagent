import asyncio
from datetime import date

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from rich.console import Console
from rich.rule import Rule

from schemas import *

pytestmark = pytest.mark.unit

console = Console()
PURINA_TOKEN = "purina_secret_token_abc123"
ACME_TOKEN = "acme_secret_token_xyz789"


class CustomAuthSimulation:
    """A simulation demonstrating the custom header authentication model."""

    def __init__(self, server_url: str, token: str, principal_id: str):
        # Add the custom auth header to the transport
        headers = {"x-adcp-auth": token}
        transport = StreamableHttpTransport(url=f"{server_url}/mcp/", headers=headers)
        self.client = Client(transport=transport)
        self.principal_id = principal_id
        self.media_buy_id: str = ""

    async def run(self):
        console.print(
            Rule(
                f"[bold magenta]AdCP V2.3 Custom Auth Simulation (Principal: {self.principal_id})[/bold magenta]",
                style="magenta",
            )
        )
        async with self.client:
            await self._phase_1_buy()
            if not self.media_buy_id:
                return
            await self._phase_2_verify_access()

    async def _step(self, title: str, tool_name: str, params: dict = None) -> dict:
        if params is None:
            params = {}
        console.print(f"\n[bold cyan]{title}[/bold cyan]")
        try:
            result = await self.client.call_tool(tool_name, params)
            console.print(f"[green]✓ Success[/green]: {result.structured_content}")
            return result.structured_content if hasattr(result, "structured_content") else {}
        except Exception as e:
            console.print(f"[red]✗ Error[/red]: {e}")
            return {}

    async def _phase_1_buy(self):
        buy_req = CreateMediaBuyRequest(
            product_ids=["prod_video_guaranteed_sports"],
            flight_start_date=date(2025, 8, 1),
            flight_end_date=date(2025, 8, 15),
            total_budget=50000.00,
            targeting_overlay=Targeting(geography=["USA-CA"]),
        )
        create_res = await self._step("Create Media Buy", "create_media_buy", {"req": buy_req.model_dump(mode="json")})
        self.media_buy_id = create_res.get("media_buy_id")

    async def _phase_2_verify_access(self):
        console.print(Rule("Phase 2: Verify Access Controls", style="cyan"))

        console.print("\n[yellow]Attempting access with CORRECT token... (should succeed)[/yellow]")
        delivery_req = GetMediaBuyDeliveryRequest(media_buy_id=self.media_buy_id, today=date(2025, 8, 5))
        await self._step(
            "Get Delivery (Correct Token)", "get_media_buy_delivery", {"req": delivery_req.model_dump(mode="json")}
        )

        console.print("\n[bold red]Attempting access with INCORRECT token... (should fail)[/bold red]")
        acme_headers = {"x-adcp-auth": ACME_TOKEN}
        acme_transport = StreamableHttpTransport(url="http://127.0.0.1:8000/mcp/", headers=acme_headers)
        acme_client = Client(transport=acme_transport)
        async with acme_client:
            try:
                await acme_client.call_tool("get_media_buy_delivery", {"req": delivery_req.model_dump(mode="json")})
            except Exception:
                console.print("[bold green] \u2713 Successfully failed as expected.[/bold green]")


if __name__ == "__main__":
    sim = CustomAuthSimulation(server_url="http://127.0.0.1:8000", token=PURINA_TOKEN, principal_id="purina")
    asyncio.run(sim.run())
