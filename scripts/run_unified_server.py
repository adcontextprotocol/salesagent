#!/usr/bin/env python3
"""Run the unified AdCP server with both MCP and Admin UI."""

import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# Import admin UI
from admin_ui import app as flask_admin_app

# Import and setup database
from database import init_db

init_db(exit_on_error=True)  # Exit on error when run as main script

# Import MCP server
from main import mcp

# Create FastAPI app
app = FastAPI(title="AdCP Unified Server")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", secrets.token_hex(32)))

# Mount Flask admin app
app.mount("/admin", WSGIMiddleware(flask_admin_app))


# Handle tenant routing
@app.api_route("/tenant/{tenant_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def tenant_router(tenant_id: str, path: str, request: Request):
    """Route tenant-specific requests."""

    if path.startswith("admin"):
        # Redirect to admin app
        new_path = f"/admin/tenant/{tenant_id}/{path}"
        if request.url.query:
            new_path += f"?{request.url.query}"
        return RedirectResponse(url=new_path)

    elif path.startswith("mcp"):
        # For MCP, we need to handle it specially
        # Extract the MCP path after /tenant/{id}/mcp/
        mcp_path = path[3:].lstrip("/")  # Remove 'mcp' prefix

        # Get the original request data
        headers = dict(request.headers)
        headers["x-adcp-tenant"] = tenant_id

        # Forward to MCP at root level
        # This is a simplified approach - in production you'd want proper proxying
        return {"error": "MCP tenant routing requires proxy setup", "tenant": tenant_id, "path": mcp_path}

    else:
        # Default redirect to admin
        return RedirectResponse(url=f"/admin/tenant/{tenant_id}")


@app.get("/tenant/{tenant_id}")
async def tenant_root(tenant_id: str):
    """Redirect to tenant admin."""
    return RedirectResponse(url=f"/admin/tenant/{tenant_id}")


@app.get("/")
async def root():
    """Redirect to admin."""
    return RedirectResponse(url="/admin/")


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.environ.get("ADCP_PORT", "8080"))
    host = os.environ.get("ADCP_HOST", "0.0.0.0")

    print(f"Starting Unified AdCP Server on {host}:{port}")
    print(f"Admin UI: http://localhost:{port}/admin/")
    print(f"Admin UI (Tenant): http://localhost:{port}/tenant/{{tenant_id}}/admin")
    print(f"MCP Server: http://localhost:{port}/ (use x-adcp-tenant header for tenant routing)")
    print("")
    print("Note: For production, use a reverse proxy (nginx/caddy) to properly route")
    print("tenant-specific MCP requests with path rewriting.")

    # Run the MCP server with the FastAPI app mounted
    mcp.run(transport="http", host=host, port=port, additional_routes=app)
