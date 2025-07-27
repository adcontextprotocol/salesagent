#!/usr/bin/env python3
"""
Automated simulation runner for AdCP:Buy server with FastMCP authentication.
Starts server on random port, runs simulation, then cleans up.
"""

import asyncio
import argparse
import os
import random
import socket
import subprocess
import sys
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def find_free_port() -> int:
    """Find a free port on the system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class SimulationRunner:
    def __init__(self, simulation_type: str = "full", dry_run: bool = False, adapter: str = "mock"):
        self.port = find_free_port()
        self.server_process = None
        self.server_url = f"http://127.0.0.1:{self.port}"
        self.simulation_type = simulation_type
        self.dry_run = dry_run
        self.adapter = adapter
        self.server_logs = []
        
    async def _capture_server_logs(self):
        """Capture server logs in the background."""
        try:
            while self.server_process:
                if self.server_process.poll() is not None:
                    break
                line = self.server_process.stdout.readline()
                if line:
                    self.server_logs.append(line.strip())
                    if "[DRY RUN]" in line:
                        console.print(f"[dim]{line.strip()}[/dim]")
                await asyncio.sleep(0.01)
        except Exception as e:
            console.print(f"[red]Log capture error: {e}[/red]")
    
    async def start_server(self) -> bool:
        """Start the AdCP server on the random port."""
        try:
            # First, ensure database is initialized
            console.print("📊 Initializing database...")
            db_proc = subprocess.run([sys.executable, "database.py"], capture_output=True, text=True)
            if db_proc.returncode != 0:
                console.print(f"[red]Database initialization failed: {db_proc.stderr}[/red]")
                return False
                
            # Start the server
            console.print(f"🚀 Starting server on port {self.port}...")
            
            # Set environment for dry run and adapter if needed
            env = os.environ.copy()
            env["ADCP_SALES_PORT"] = str(self.port)
            env["ADCP_SALES_HOST"] = "127.0.0.1"
            if self.dry_run:
                env["ADCP_DRY_RUN"] = "true"
            env["ADCP_ADAPTER"] = self.adapter
            
            # Start server process using run_server.py
            self.server_process = subprocess.Popen(
                [sys.executable, "run_server.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Wait for server to start
            max_attempts = 30
            for i in range(max_attempts):
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                        console.print(f"[green]✓ Server started successfully on port {self.port}[/green]")
                        return True
                except (socket.error, ConnectionRefusedError):
                    await asyncio.sleep(0.5)
            
            console.print("[red]✗ Server failed to start[/red]")
            return False
            
        except Exception as e:
            console.print(f"[red]Error starting server: {e}[/red]")
            return False
    
    async def run_simulation(self) -> bool:
        """Run the simulation script."""
        try:
            console.print(f"\n🧪 Running {self.simulation_type} simulation...")
            
            # Map simulation types to scripts
            simulation_scripts = {
                "full": "simulation_full.py",
                "auth": "test_auth.py"  # Auth test if explicitly requested
            }
            
            script_name = simulation_scripts.get(self.simulation_type, "simulation_full.py")
            
            # Create a modified simulation script that uses our port
            sim_py = Path(script_name)
            original_sim = sim_py.read_text()
            
            # Replace the hardcoded URLs with our dynamic one
            modified_sim = original_sim.replace(
                'server_url="http://127.0.0.1:8000"',
                f'server_url="{self.server_url}"'
            ).replace(
                'acme_transport = StreamableHttpTransport(url="http://127.0.0.1:8000/mcp/"',
                f'acme_transport = StreamableHttpTransport(url="{self.server_url}/mcp/"'
            )
            
            # Write to temporary file
            temp_sim = Path(f"temp_{script_name}")
            temp_sim.write_text(modified_sim)
            
            # Run simulation
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(temp_sim), self.server_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            # Clean up temp file
            temp_sim.unlink()
            
            if proc.returncode == 0:
                console.print("[green]✓ Simulation completed successfully[/green]")
                console.print("\n[bold]Simulation Output:[/bold]")
                console.print(Panel(stdout.decode(), title="Output", border_style="green"))
                return True
            else:
                console.print(f"[red]✗ Simulation failed with code {proc.returncode}[/red]")
                if stderr:
                    console.print(f"[red]Error: {stderr.decode()}[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error running simulation: {e}[/red]")
            return False
    
    def stop_server(self):
        """Stop the server process."""
        if self.server_process:
            console.print("\n🛑 Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
                console.print("[green]✓ Server stopped[/green]")
            except subprocess.TimeoutExpired:
                console.print("[yellow]⚠️  Server didn't stop gracefully, forcing...[/yellow]")
                self.server_process.kill()
                self.server_process.wait()
                console.print("[green]✓ Server force stopped[/green]")
    
    async def run(self):
        """Run the complete simulation cycle."""
        simulation_titles = {
            "full": "Full Lifecycle",
            "auth": "Authentication Test"
        }
        title = simulation_titles.get(self.simulation_type, self.simulation_type.title())
        dry_run_text = " (DRY RUN)" if self.dry_run else ""
        console.print(Panel.fit(
            f"[bold cyan]AdCP:Buy Simulation Runner[/bold cyan]\n"
            f"Type: {title}{dry_run_text}\n"
            f"Adapter: {self.adapter.upper()}\n"
            f"Port: {self.port}",
            border_style="cyan"
        ))
        
        success = True
        
        try:
            # Start server
            if not await self.start_server():
                success = False
                return
            
            # Wait a bit for server to fully initialize
            await asyncio.sleep(2)
            
            # Run simulation
            if not await self.run_simulation():
                success = False
                
        finally:
            # Always stop server
            self.stop_server()
            
            # Show note about dry run logs
            if self.dry_run:
                console.print("\n[bold yellow]Note: Dry run logs are shown in server output above[/bold yellow]")
            
            # Final status
            if success:
                console.print(Panel(
                    "[bold green]✓ Simulation completed successfully![/bold green]",
                    border_style="green"
                ))
            else:
                console.print(Panel(
                    "[bold red]✗ Simulation failed[/bold red]",
                    border_style="red"
                ))
                sys.exit(1)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Run AdCP:Buy simulations')
    parser.add_argument(
        '--simulation',
        choices=['full', 'auth'],
        default='full',
        help='Select simulation type (default: full lifecycle)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Enable dry run mode to see adapter calls that would be made'
    )
    parser.add_argument(
        '--adapter',
        choices=['mock', 'gam', 'kevel', 'triton'],
        default='mock',
        help='Select the ad server adapter to use (default: mock)'
    )
    args = parser.parse_args()
    
    runner = SimulationRunner(args.simulation, dry_run=args.dry_run, adapter=args.adapter)
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)