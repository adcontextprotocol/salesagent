#!/usr/bin/env python3
"""Unified AdCP server with proxy approach for MCP."""

import os
import sys
import secrets
import httpx
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.middleware.wsgi import WSGIMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

# Import and setup database first
from database import init_db

# Import admin UI
from admin_ui import app as flask_admin_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db(exit_on_error=True)  # Exit on error in production
    yield

# Create unified FastAPI app
app = FastAPI(title="AdCP Unified Server", lifespan=lifespan)

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET', secrets.token_hex(32)))

# Mount Flask admin app at /admin
app.mount("/admin", WSGIMiddleware(flask_admin_app))

# Root redirects
@app.get("/")
async def root():
    """Redirect root to admin."""
    return RedirectResponse(url="/admin/")

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}

# Tenant routing handlers  
@app.get("/tenant/{tenant_id}")
async def tenant_root(tenant_id: str):
    """Redirect to tenant admin."""
    return RedirectResponse(url=f"/admin/tenant/{tenant_id}/")

@app.get("/tenant/{tenant_id}/admin")
async def tenant_admin_redirect(tenant_id: str):
    """Redirect to tenant admin with trailing slash."""
    return RedirectResponse(url=f"/admin/tenant/{tenant_id}/")

# MCP proxy handler
MCP_INTERNAL_PORT = int(os.environ.get('MCP_INTERNAL_PORT', '8081'))
MCP_BASE_URL = f"http://localhost:{MCP_INTERNAL_PORT}"

async def proxy_to_mcp(request: Request, path: str = "", tenant_id: str = None):
    """Proxy requests to the internal MCP server."""
    # Build the target URL
    target_url = f"{MCP_BASE_URL}/{path}"
    
    # Prepare headers
    headers = dict(request.headers)
    headers.pop("host", None)  # Remove host header
    
    # Add tenant header if provided
    if tenant_id:
        headers["x-adcp-tenant"] = tenant_id
    
    # Read request body
    body = await request.body()
    
    # Create HTTP client
    async with httpx.AsyncClient() as client:
        # Forward the request
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
            follow_redirects=False
        )
        
        # Return the response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )

# MCP routes
@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def mcp_handler(request: Request, path: str = ""):
    """Handle MCP requests."""
    return await proxy_to_mcp(request, path)

@app.api_route("/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def mcp_root(request: Request):
    """Handle MCP root requests."""
    return await proxy_to_mcp(request, "")

# Tenant MCP routes
@app.api_route("/tenant/{tenant_id}/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def tenant_mcp_handler(request: Request, tenant_id: str, path: str = ""):
    """Handle tenant-specific MCP requests."""
    return await proxy_to_mcp(request, path, tenant_id)

@app.api_route("/tenant/{tenant_id}/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def tenant_mcp_root(request: Request, tenant_id: str):
    """Handle tenant-specific MCP root requests."""
    return await proxy_to_mcp(request, "", tenant_id)

if __name__ == "__main__":
    import subprocess
    import time
    import atexit
    
    # Start MCP server on internal port
    mcp_process = subprocess.Popen(
        [sys.executable, "run_server.py"],
        env={**os.environ, "ADCP_SALES_PORT": str(MCP_INTERNAL_PORT)}
    )
    
    # Register cleanup
    def cleanup():
        if mcp_process.poll() is None:
            mcp_process.terminate()
            mcp_process.wait()
    
    atexit.register(cleanup)
    
    # Give MCP server time to start
    time.sleep(2)
    
    # Run unified server
    port = int(os.environ.get('ADCP_PORT', '8080'))
    host = os.environ.get('ADCP_HOST', '0.0.0.0')
    
    print(f"Starting Unified AdCP Server on {host}:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print(f"MCP Interface: http://localhost:{port}/mcp/")
    print(f"Tenant URLs:")
    print(f"  Admin: http://localhost:{port}/tenant/{{tenant_id}}/admin/")
    print(f"  MCP: http://localhost:{port}/tenant/{{tenant_id}}/mcp/")
    print(f"\nInternal MCP server running on port {MCP_INTERNAL_PORT}")
    
    try:
        # Run with uvicorn
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        cleanup()