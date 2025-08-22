#!/usr/bin/env python3
"""
Run all AdCP services in a single process for Fly.io deployment.
This allows us to run MCP server, Admin UI, and ADK agent together.
"""

import os
import subprocess
import sys
import threading
import time


def run_migrations():
    """Run database migrations before starting services."""
    print("Running database migrations...")
    subprocess.run([sys.executable, "migrate.py"], check=True)
    print("✅ Migrations complete")


def run_mcp_server():
    """Run the MCP server in a thread."""
    print("Starting MCP server on port 8080...")
    subprocess.run([sys.executable, "main.py"])


def run_admin_ui():
    """Run the Admin UI in a thread."""
    print("Starting Admin UI on port 8001...")
    os.environ["ADMIN_UI_PORT"] = "8001"
    subprocess.run([sys.executable, "admin_ui.py"])


def run_adk_agent():
    """Run the ADK agent web interface."""
    print("Starting ADK agent on port 8091...")
    time.sleep(5)  # Wait for MCP server to be ready
    subprocess.run([".venv/bin/adk", "web", "adcp_agent", "--host", "0.0.0.0", "--port", "8091"])


def main():
    """Main entry point to run all services."""
    print("=" * 60)
    print("AdCP Sales Agent - Starting All Services")
    print("=" * 60)

    # Run migrations first
    try:
        run_migrations()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

    # Start services in threads
    threads = []

    # MCP Server thread
    mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
    mcp_thread.start()
    threads.append(mcp_thread)

    # Admin UI thread
    admin_thread = threading.Thread(target=run_admin_ui, daemon=True)
    admin_thread.start()
    threads.append(admin_thread)

    # ADK Agent thread
    adk_thread = threading.Thread(target=run_adk_agent, daemon=True)
    adk_thread.start()
    threads.append(adk_thread)

    print("\n✅ All services started:")
    print("  - MCP Server: http://localhost:8080")
    print("  - Admin UI: http://localhost:8001")
    print("  - ADK Agent: http://localhost:8091")
    print("\nPress Ctrl+C to stop all services")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down all services...")
        sys.exit(0)


if __name__ == "__main__":
    main()
