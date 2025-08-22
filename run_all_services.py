#!/usr/bin/env python3
"""
Run all AdCP services in a single process for Fly.io deployment.
This allows us to run MCP server, Admin UI, and ADK agent together.
"""

import os
import signal
import subprocess
import sys
import threading
import time

# Store process references for cleanup
processes = []


def cleanup(signum=None, frame=None):
    """Clean up all processes on exit."""
    print("\nShutting down all services...")
    for proc in processes:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    sys.exit(0)


# Register cleanup handlers
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def run_migrations():
    """Run database migrations before starting services."""
    print("Running database migrations...")
    try:
        result = subprocess.run(
            [sys.executable, "migrate.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("✅ Migrations complete")
        else:
            print(f"⚠️ Migration warnings: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Migration error (non-fatal): {e}")


def run_mcp_server():
    """Run the MCP server."""
    print("Starting MCP server on port 8080...")
    env = os.environ.copy()
    env["ADCP_SALES_PORT"] = "8080"
    proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)

    # Monitor the process output
    for line in iter(proc.stdout.readline, b""):
        if line:
            print(f"[MCP] {line.decode().rstrip()}")
    print("MCP server stopped")


def run_admin_ui():
    """Run the Admin UI."""
    print("Starting Admin UI on port 8001...")
    env = os.environ.copy()
    env["ADMIN_UI_PORT"] = "8001"
    env["PYTHONPATH"] = "/app"
    proc = subprocess.Popen(
        [sys.executable, "src/admin/server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)

    # Monitor the process output
    for line in iter(proc.stdout.readline, b""):
        if line:
            print(f"[Admin] {line.decode().rstrip()}")
    print("Admin UI stopped")


def run_adk_agent():
    """Run the ADK agent web interface."""
    print("Starting ADK agent on port 8091...")
    time.sleep(10)  # Wait for MCP server to be ready

    env = os.environ.copy()
    proc = subprocess.Popen(
        [".venv/bin/adk", "web", "adcp_agent", "--host", "0.0.0.0", "--port", "8091"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)

    # Monitor the process output
    for line in iter(proc.stdout.readline, b""):
        if line:
            print(f"[ADK] {line.decode().rstrip()}")
    print("ADK agent stopped")


def run_nginx():
    """Run nginx as reverse proxy."""
    print("Starting nginx reverse proxy on port 8000...")

    # Create nginx directories if they don't exist
    os.makedirs("/var/log/nginx", exist_ok=True)
    os.makedirs("/var/run", exist_ok=True)

    # Start nginx
    proc = subprocess.Popen(
        ["nginx", "-g", "daemon off;"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(proc)

    # Monitor the process output
    for line in iter(proc.stdout.readline, b""):
        if line:
            print(f"[Nginx] {line.decode().rstrip()}")
    print("Nginx stopped")


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

    # Give services time to start before nginx
    time.sleep(5)

    # Nginx reverse proxy thread
    nginx_thread = threading.Thread(target=run_nginx, daemon=True)
    nginx_thread.start()
    threads.append(nginx_thread)

    print("\n✅ All services started with unified routing:")
    print("  - MCP Server: http://localhost:8000/mcp")
    print("  - Admin UI: http://localhost:8000/admin")
    print("  - ADK Agent: http://localhost:8000/a2a")
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
