#!/usr/bin/env python3
"""
Simple HTTP proxy to route between MCP server, Admin UI, and A2A server.
Used for local development and quickstart deployments.
"""

import asyncio
import logging
import os

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Port configuration (can be overridden by env vars)
MCP_PORT = os.environ.get("ADCP_SALES_PORT", "8080")
ADMIN_PORT = os.environ.get("ADMIN_UI_PORT", "8001")
A2A_PORT = os.environ.get("A2A_PORT", "8091")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8000"))

# Routes that should go to Admin UI
ADMIN_PATHS = {
    "/admin",
    "/static",
    "/auth",
    "/api",
    "/callback",
    "/logout",
    "/login",
    "/test",
    "/health/admin",
    "/tenant",
    "/signup",
}

# Routes that should go to A2A server
A2A_PATHS = {
    "/a2a",
    "/.well-known",
    "/agent.json",
}


async def proxy_handler(request):
    """Route requests to appropriate backend service"""
    path = request.path_qs

    # Special case for root - redirect to admin
    if path == "/":
        return web.Response(status=302, headers={"Location": "/admin"})

    # Health check
    if path == "/health":
        return web.Response(text="healthy\n")

    # Check if this should go to A2A server
    for a2a_path in A2A_PATHS:
        if path.startswith(a2a_path):
            target_url = f"http://localhost:{A2A_PORT}{path}"
            break
    else:
        # Check if this should go to admin UI
        for admin_path in ADMIN_PATHS:
            if path.startswith(admin_path):
                # For /admin route, strip the prefix and forward to /
                if path == "/admin":
                    target_url = f"http://localhost:{ADMIN_PORT}/"
                else:
                    target_url = f"http://localhost:{ADMIN_PORT}{path}"
                break
        else:
            # Default to MCP server
            target_url = f"http://localhost:{MCP_PORT}{path}"

    logger.info(f"Proxying {request.method} {path} -> {target_url}")

    try:
        # Create session for backend request
        async with aiohttp.ClientSession() as session:
            # Copy headers
            headers = dict(request.headers)
            headers.pop("Host", None)
            headers.pop("Content-Length", None)

            # Add proxy headers for proper URL generation
            headers["X-Forwarded-Host"] = request.headers.get("Host", "localhost")
            headers["X-Forwarded-Proto"] = request.headers.get("X-Forwarded-Proto", "http")
            headers["X-Forwarded-Port"] = request.headers.get("X-Forwarded-Port", str(PROXY_PORT))

            # Make backend request
            async with session.request(
                method=request.method, url=target_url, headers=headers, data=await request.read(), allow_redirects=False
            ) as resp:
                # Check if this is an SSE response
                content_type = resp.headers.get("Content-Type", "")
                if "text/event-stream" in content_type:
                    # Stream SSE responses
                    response = web.StreamResponse(status=resp.status, headers=resp.headers)
                    await response.prepare(request)

                    # Stream chunks from backend to client
                    async for chunk in resp.content.iter_any():
                        await response.write(chunk)

                    await response.write_eof()
                    return response
                else:
                    # Regular response - read entire body
                    body = await resp.read()
                    response = web.Response(body=body, status=resp.status, headers=resp.headers)
                    return response

    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return web.Response(status=502, text=f"Proxy error: {str(e)}")


async def init_app():
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy_handler)
    return app


if __name__ == "__main__":
    app = asyncio.run(init_app())
    print(f"Starting proxy on port {PROXY_PORT}")
    print(f"  /mcp/* -> localhost:{MCP_PORT}")
    print(f"  /admin/*, /auth/*, etc -> localhost:{ADMIN_PORT}")
    print(f"  /a2a, /.well-known/*, /agent.json -> localhost:{A2A_PORT}")
    web.run_app(app, host="0.0.0.0", port=PROXY_PORT)
