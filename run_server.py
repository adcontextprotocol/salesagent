#!/usr/bin/env python3
"""Start the MCP server."""

import os

from src.core.database.database import init_db

# Initialize database first (exit on error since this is the main process)
init_db(exit_on_error=True)

# Import after DB init to avoid circular imports
from main import mcp

if __name__ == "__main__":
    port = int(os.environ.get("ADCP_SALES_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")

    print(f"🌐 Starting MCP server on {host}:{port}")

    # Start the MCP server
    mcp.run(transport="http", host=host, port=port)
