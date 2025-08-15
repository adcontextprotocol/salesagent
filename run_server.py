#!/usr/bin/env python3
"""Start the MCP server."""

import os
import sys
import uvicorn
from database import init_db

# Initialize database first
init_db()

# Import after DB init to avoid circular imports
from main import mcp

if __name__ == "__main__":
    port = int(os.environ.get("ADCP_SALES_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")
    
    print(f"🌐 Starting MCP server on {host}:{port}")
    
    # Start the MCP server
    uvicorn.run(
        mcp.get_asgi_app(),
        host=host,
        port=port,
        log_level="info"
    )