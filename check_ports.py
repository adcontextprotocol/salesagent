#!/usr/bin/env python3
"""
Port availability checker for AdCP Sales Agent.
Validates that required ports are available before starting services.
"""

import socket
import sys
import os
from typing import List, Tuple


def check_port(host: str, port: int) -> bool:
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def get_ports_from_env() -> List[Tuple[str, int]]:
    """Get configured ports from environment variables."""
    ports = []
    
    # PostgreSQL port
    pg_port = int(os.environ.get('POSTGRES_PORT', '5432'))
    ports.append(('PostgreSQL', pg_port))
    
    # MCP Server port
    mcp_port = int(os.environ.get('ADCP_SALES_PORT', '8080'))
    ports.append(('MCP Server', mcp_port))
    
    # Admin UI port
    admin_port = int(os.environ.get('ADMIN_UI_PORT', '8001'))
    ports.append(('Admin UI', admin_port))
    
    return ports


def main():
    """Check all configured ports and report availability."""
    print("Checking port availability for AdCP Sales Agent...")
    print("-" * 50)
    
    ports = get_ports_from_env()
    all_available = True
    unavailable_ports = []
    
    for service_name, port in ports:
        if check_port('0.0.0.0', port):
            print(f"✓ {service_name} port {port} is available")
        else:
            print(f"✗ {service_name} port {port} is NOT available")
            all_available = False
            unavailable_ports.append((service_name, port))
    
    print("-" * 50)
    
    if all_available:
        print("✓ All ports are available. Services can be started.")
        sys.exit(0)
    else:
        print("✗ Some ports are not available:")
        for service_name, port in unavailable_ports:
            print(f"  - {service_name}: {port}")
        print("\nTo find what's using a port, run:")
        print("  lsof -i :<port> (on macOS/Linux)")
        print("  netstat -ano | findstr :<port> (on Windows)")
        sys.exit(1)


if __name__ == "__main__":
    main()