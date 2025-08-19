#!/usr/bin/env python3
"""Run the unified AdCP server with Admin UI."""

import os

# Set unified mode
os.environ["ADCP_UNIFIED_MODE"] = "1"

# Import and run
from main import mcp

if __name__ == "__main__":
    port = int(os.environ.get("ADCP_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")

    print(f"Starting Unified AdCP Server on {host}:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print(f"MCP Interface: http://localhost:{port}/mcp/")
    print(f"Tenant Admin: http://localhost:{port}/tenant/{{tenant_id}}/admin/")
    print("Tenant MCP: Use x-adcp-tenant header or subdomain")

    mcp.run(transport="http", host=host, port=port)
