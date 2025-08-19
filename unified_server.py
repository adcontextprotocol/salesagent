#!/usr/bin/env python3
"""Unified AdCP server combining MCP and Admin UI on a single port."""

import os
import secrets
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# Import admin UI
from admin_ui import app as flask_admin_app

# Import and setup database first
from database import init_db

# Import MCP server
from main import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db(exit_on_error=True)  # Exit on error in production
    yield


# Create unified FastAPI app
app = FastAPI(title="AdCP Unified Server", lifespan=lifespan)

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", secrets.token_hex(32)))

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


# Middleware to handle tenant MCP routing
@app.middleware("http")
async def tenant_mcp_middleware(request: Request, call_next):
    """Extract tenant from path and add to headers for MCP."""
    path = request.url.path

    # Check if this is a tenant-specific MCP request
    if path.startswith("/tenant/") and "/mcp" in path:
        parts = path.split("/")
        if len(parts) >= 4 and parts[3] == "mcp":
            tenant_id = parts[2]
            # Add tenant header for MCP
            mutable_headers = dict(request.headers)
            mutable_headers["x-adcp-tenant"] = tenant_id

            # Create new scope with updated path
            scope = request.scope.copy()
            # Rewrite path to remove /tenant/{id}/mcp prefix
            mcp_path = "/" + "/".join(parts[4:]) if len(parts) > 4 else "/"
            scope["path"] = "/mcp" + mcp_path
            scope["raw_path"] = scope["path"].encode()

            # Update headers in scope
            scope["headers"] = [(k.encode(), v.encode()) for k, v in mutable_headers.items()]

            # Create new request with updated scope
            request = Request(scope, request.receive)

    response = await call_next(request)
    return response


# Mount MCP at /mcp (it needs a prefix to avoid conflicts)
mcp_app = mcp.http_app()
app.mount("/mcp", mcp_app)

if __name__ == "__main__":
    port = int(os.environ.get("ADCP_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")

    print(f"Starting Unified AdCP Server on {host}:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print(f"MCP Interface: http://localhost:{port}/mcp/")
    print("Tenant URLs:")
    print(f"  Admin: http://localhost:{port}/tenant/{{tenant_id}}/admin/")
    print(f"  MCP: http://localhost:{port}/tenant/{{tenant_id}}/mcp/")

    # Run with uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")
