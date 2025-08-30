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
            [sys.executable, "scripts/ops/migrate.py"],
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
        [sys.executable, "scripts/run_server.py"],
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
    admin_port = os.environ.get("ADMIN_UI_PORT", "8001")
    print(f"Starting Admin UI on port {admin_port}...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app"
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.admin.server"],
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


def run_a2a_server():
    """Run the A2A server for agent-to-agent interactions."""
    try:
        print("Starting A2A server on port 8091...")
        print("[A2A] Waiting 10 seconds for MCP server to be ready...")
        time.sleep(10)  # Wait for MCP server to be ready

        env = os.environ.copy()
        env["A2A_MOCK_MODE"] = "true"  # Use mock mode in production for now

        print("[A2A] Launching standard python-a2a server...")
        # Use standard python-a2a server implementation - no custom protocol code
        proc = subprocess.Popen(
            [sys.executable, "src/a2a/adcp_a2a_server.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)

        print("[A2A] Process started, monitoring output...")
        # Monitor the process output
        for line in iter(proc.stdout.readline, b""):
            if line:
                print(f"[A2A] {line.decode().rstrip()}")
        print("A2A server stopped")
    except Exception as e:
        print(f"[A2A] ERROR: Failed to start A2A server: {e}")
        import traceback

        traceback.print_exc()


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

    # A2A Server thread for agent-to-agent communication
    a2a_thread = threading.Thread(target=run_a2a_server, daemon=True)
    a2a_thread.start()
    threads.append(a2a_thread)

    # Check if we should skip nginx (useful for docker-compose with separate services)
    skip_nginx = os.environ.get("SKIP_NGINX", "false").lower() == "true"

    if not skip_nginx:
        # Give services time to start before nginx
        time.sleep(5)

        # Nginx reverse proxy thread
        nginx_thread = threading.Thread(target=run_nginx, daemon=True)
        nginx_thread.start()
        threads.append(nginx_thread)

        print("\n✅ All services started with unified routing:")
        print("  - MCP Server: http://localhost:8000/mcp")
        print("  - Admin UI: http://localhost:8000/admin")
        print("  - A2A Server: http://localhost:8000/a2a")
        print("\nPress Ctrl+C to stop all services")
    else:
        admin_port = os.environ.get("ADMIN_UI_PORT", "8001")
        print("\n✅ Services started (nginx skipped):")
        print("  - MCP Server: http://localhost:8080")
        print(f"  - Admin UI: http://localhost:{admin_port}")
        print("  - A2A Server: http://localhost:8091")
        print("\nℹ️  Nginx reverse proxy skipped (SKIP_NGINX=true)")
        print("Press Ctrl+C to stop all services")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down all services...")
        sys.exit(0)


if __name__ == "__main__":
    main()
