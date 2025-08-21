#!/usr/bin/env python3
"""Unified FastAPI application serving both Admin UI and MCP."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import RedirectResponse

from database import init_db

# Import the MCP server
from main import mcp

# Import admin UI Flask app
from src.admin.app import create_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db(exit_on_error=True)  # Exit on error in production
    yield


# Create the Flask app
flask_admin_app, _ = create_app()

# Create the main FastAPI app
app = FastAPI(title="AdCP Sales Agent", description="Unified server for Admin UI and MCP interface", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Flask admin app under /admin
app.mount("/admin", WSGIMiddleware(flask_admin_app))

# Mount MCP at /mcp
mcp_app = mcp.http_app()
app.mount("/mcp", mcp_app)


# Tenant-specific routing
@app.get("/tenant/{tenant_id}")
async def tenant_root(tenant_id: str):
    """Redirect to tenant admin."""
    return RedirectResponse(url=f"/tenant/{tenant_id}/admin/")


@app.get("/tenant/{tenant_id}/admin")
async def tenant_admin_redirect(tenant_id: str):
    """Redirect to admin with trailing slash."""
    return RedirectResponse(url=f"/tenant/{tenant_id}/admin/")


class TenantAdminMiddleware:
    """Middleware to handle tenant admin routing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]

            # Handle /tenant/{id}/admin/* paths
            if path.startswith("/tenant/") and "/admin" in path:
                parts = path.split("/")
                if len(parts) >= 4 and parts[3] == "admin":
                    parts[2]
                    # Rewrite path to route to Flask admin
                    admin_path = "/".join(parts[2:])  # Keep tenant/id/admin/...
                    scope["path"] = f"/admin/{admin_path}"

        await self.app(scope, receive, send)


# Apply tenant middleware
app.add_middleware(TenantAdminMiddleware)


class TenantMCPMiddleware:
    """Middleware to handle tenant MCP routing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]

            # Handle /tenant/{id}/mcp/* paths
            if path.startswith("/tenant/") and "/mcp" in path:
                parts = path.split("/")
                if len(parts) >= 4 and parts[3] == "mcp":
                    tenant_id = parts[2]
                    # Rewrite path for MCP
                    mcp_path = "/".join(parts[4:]) if len(parts) > 4 else ""
                    scope["path"] = f"/mcp/{mcp_path}"
                    # Add tenant to headers for MCP resolution
                    headers = list(scope.get("headers", []))
                    headers.append((b"x-adcp-tenant", tenant_id.encode()))
                    scope["headers"] = headers

        await self.app(scope, receive, send)


# Apply MCP middleware
app.add_middleware(TenantMCPMiddleware)


@app.get("/")
async def root():
    """Redirect root to admin."""
    return RedirectResponse(url="/admin/")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "unified"}


# OAuth redirect handling for tenants
@app.get("/tenant/{tenant_id}/auth/google/callback")
async def tenant_oauth_callback(tenant_id: str, request: Request):
    """Forward OAuth callbacks to admin app."""
    # Build the admin URL
    admin_url = f"/admin/tenant/{tenant_id}/auth/google/callback"
    # Include query params
    if request.url.query:
        admin_url += f"?{request.url.query}"
    return RedirectResponse(url=admin_url)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("ADCP_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")

    print(f"Starting Unified AdCP Server on {host}:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print(f"MCP Interface: http://localhost:{port}/mcp/")
    print("Tenant URLs:")
    print(f"  Admin: http://localhost:{port}/tenant/{{tenant_id}}/admin/")
    print(f"  MCP: http://localhost:{port}/tenant/{{tenant_id}}/mcp/")

    uvicorn.run(app, host=host, port=port)
