#!/usr/bin/env python3
"""Demonstration of dry-run mode with different adapters."""

import subprocess
import sys
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_demo(adapter: str):
    """Run a simple demo with the specified adapter."""
    console.print(Panel(f"[bold cyan]Testing {adapter.upper()} Adapter in Dry-Run Mode[/bold cyan]"))
    
    # Run a simple Python script that tests the adapter
    code = f'''
import os
os.environ['ADCP_ADAPTER'] = '{adapter}'
os.environ['ADCP_DRY_RUN'] = 'true'

# Now import after setting env vars
from main import get_principal_object, get_adapter
from schemas import CreateMediaBuyRequest, MediaPackage
from datetime import date, datetime

principal = get_principal_object('purina')
adapter = get_adapter(principal, dry_run=True)

request = CreateMediaBuyRequest(
    product_ids=['prod_video_guaranteed_sports'],
    flight_start_date=date(2025, 8, 1),
    flight_end_date=date(2025, 8, 15),
    total_budget=50000.0,
    targeting_overlay={{
        'geography': ['CA', 'NY'],
        'content_categories_exclude': ['controversial']
    }},
    po_number='PO-DEMO-2025'
)

packages = [MediaPackage(
    package_id='prod_video_guaranteed_sports',
    name='Sports Video Package',
    delivery_type='guaranteed',
    cpm=15.0,
    impressions=3333333,
    format_ids=['video_standard']
)]

print("\\nCreating media buy...")
response = adapter.create_media_buy(
    request, packages,
    datetime(2025, 8, 1), datetime(2025, 8, 15)
)
print(f"\\nCreated: {{response.media_buy_id}}")
'''
    
    # Run the code
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True,
        text=True
    )
    
    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(f"[red]{result.stderr}[/red]")
    
    console.print()

if __name__ == "__main__":
    console.print("[bold]AdCP:Buy Dry-Run Mode Demonstration[/bold]\n")
    console.print("This demonstrates how each adapter logs the API calls it would make.\n")
    
    # Test Mock adapter
    run_demo('mock')
    
    # Test GAM adapter
    run_demo('gam')
    
    console.print("[bold green]✅ Demonstration complete![/bold green]")
    console.print("\n[dim]Key features demonstrated:[/dim]")
    console.print("[dim]- Command-line arguments: --dry-run --adapter <name>[/dim]")
    console.print("[dim]- Adapter-specific API call logging[/dim]")
    console.print("[dim]- Principal-based authentication with adapter mappings[/dim]")