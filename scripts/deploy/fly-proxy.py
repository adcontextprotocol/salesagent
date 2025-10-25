#!/usr/bin/env python3
"""
Simple HTTP proxy for Fly.io deployment to route between MCP server and Admin UI
"""

import asyncio
import logging

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    # Check if this should go to admin UI
    for admin_path in ADMIN_PATHS:
        if path.startswith(admin_path):
            # For /admin route, strip the prefix and forward to /
            if path == "/admin":
                target_url = "http://localhost:8001/"
            else:
                target_url = f"http://localhost:8001{path}"
            break
    else:
        # Default to MCP server
        target_url = f"http://localhost:8080{path}"

    logger.info(f"Proxying {request.method} {path} -> {target_url}")

    try:
        # Create session for backend request
        async with aiohttp.ClientSession() as session:
            # Copy headers
            headers = dict(request.headers)
            headers.pop("Host", None)
            headers.pop("Content-Length", None)

            # Add proxy headers for proper URL generation
            headers["X-Forwarded-Host"] = request.headers.get("Host", "adcp-sales-agent.fly.dev")
            headers["X-Forwarded-Proto"] = "https"
            headers["X-Forwarded-Port"] = "443"

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
    # Proxy listens on 8000 to avoid conflict with MCP server on 8080
    web.run_app(app, host="0.0.0.0", port=8000)
