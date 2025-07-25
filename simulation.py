import asyncio
from datetime import datetime, timedelta
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

console = Console()

class SimulationV2_2:
    """Orchestrates a full lifecycle simulation for the V2.2 API."""

    def __init__(self, server_script: str):
        self.client = Client(server_script)
        self.today = datetime(2025, 7, 1)

    async def run(self):
        """Executes all simulation scenarios."""
        async with self.client:
            await self.run_scenario_1()
            await self.run_scenario_2()
            await self.run_scenario_3()

    async def step(self, title: str, tool_name: str, params: dict = {}):
        """Executes a single tool call and prints the result."""
        console.print(f"\n[bold yellow]>> Executing Step:[/bold yellow] {title}")
        console.print(f"--> Calling tool: [bold]{tool_name}[/bold]")
        result = await self.client.call_tool(tool_name, params)
        console.print(f"[green] \u2713 Result:[/green]")
        console.print(Panel(Pretty(result.structured_content if result else "No result"), expand=False))
        return result.structured_content if result else None

    async def run_scenario_1(self):
        """Scenario 1: Standard Catalog Buy"""
        console.rule("[bold magenta]Scenario 1: Standard Catalog Buy[/bold magenta]")
        
        # 1. Discover packages without a brief
        discover_req = {"media_types": ["display"]}
        packages_res = await self.step("Discover Catalog Packages", "get_packages", {"request": discover_req})
        
        # 2. Select a catalog package and create a media buy with a targeting overlay
        catalog_pkg = next(p for p in packages_res['packages'] if p['type'] == 'catalog')
        buy_req = {
            "query_id": packages_res['query_id'],
            "selected_packages": [{"package_id": catalog_pkg['package_id']}],
            "po_number": "SCENARIO-1-PO",
            "targeting": {
                "geo": {"countries": ["US"]},
                "schedule": {"days": ["mon-fri"]}
            },
            "creatives": [{"id": "cr-1", "format_id": "std_banner_300x250", "spec": {}}],
            "creative_assignments": [{"package_id": catalog_pkg['package_id'], "creative_id": "cr-1"}]
        }
        await self.step("Create Media Buy", "create_media_buy", {"request": buy_req})

    async def run_scenario_2(self):
        """Scenario 2: Brief-Driven Mixed Buy"""
        console.rule("[bold magenta]Scenario 2: Brief-Driven Mixed Buy[/bold magenta]")
        
        # 1. Discover packages with a brief
        discover_req = {"brief": "I want to reach cat lovers with a new brand campaign."}
        packages_res = await self.step("Discover Custom & Catalog Packages", "get_packages", {"request": discover_req})
        
        # 2. Select one custom and one catalog package
        custom_pkg = next(p for p in packages_res['packages'] if p['type'] == 'custom')
        catalog_pkg = next(p for p in packages_res['packages'] if p['type'] == 'catalog')
        
        buy_req = {
            "query_id": packages_res['query_id'],
            "selected_packages": [
                {"package_id": custom_pkg['package_id']},
                {"package_id": catalog_pkg['package_id']}
            ],
            "po_number": "SCENARIO-2-PO",
            "creatives": [], "creative_assignments": []
        }
        await self.step("Create Mixed Media Buy", "create_media_buy", {"request": buy_req})

    async def run_scenario_3(self):
        """Scenario 3: Custom Format Buy"""
        console.rule("[bold magenta]Scenario 3: Custom Format Buy[/bold magenta]")
        
        # 1. Discover packages
        packages_res = await self.step("Discover Packages", "get_packages", {"request": {}})
        
        # 2. Find the custom format package
        custom_format_pkg = next(p for p in packages_res['packages'] if p['package_id'] == 'pkg_3')
        
        # 3. Create the media buy with a custom creative
        buy_req = {
            "query_id": packages_res['query_id'],
            "selected_packages": [{"package_id": custom_format_pkg['package_id']}],
            "po_number": "SCENARIO-3-PO",
            "creatives": [
                {
                    "id": "cr-custom-e2e", "format_id": "custom_e2e_video",
                    "spec": {
                        "format_type": "custom",
                        "assets": {"primary_video": {"url": "..."}, "end_card": {"url": "..."}}
                    }
                }
            ],
            "creative_assignments": [{"package_id": custom_format_pkg['package_id'], "creative_id": "cr-custom-e2e"}]
        }
        await self.step("Create Custom Format Media Buy", "create_media_buy", {"request": buy_req})

if __name__ == "__main__":
    sim = SimulationV2_2(server_script="main.py")
    asyncio.run(sim.run())
