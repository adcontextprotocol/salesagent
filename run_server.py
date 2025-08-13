#!/usr/bin/env python3
"""Run the AdCP Sales Agent MCP server."""

import os
import sys
import logging
import asyncio
from database import init_db
from main import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Initialize database and run the MCP server."""
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")
    
    # Get port from environment
    port = int(os.environ.get('ADCP_SALES_PORT', '8080'))
    host = os.environ.get('ADCP_HOST', '0.0.0.0')
    
    logger.info(f"Starting AdCP Sales Agent MCP server on {host}:{port}")
    
    # Run the FastMCP server
    mcp.run(
        transport="http",
        host=host,
        port=port
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)