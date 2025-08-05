#!/usr/bin/env python3
"""
Simple HTTP proxy for Fly.io deployment to route between MCP server and Admin UI
"""
import asyncio
import aiohttp
from aiohttp import web
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Routes that should go to Admin UI
ADMIN_PATHS = {
    '/admin', '/static', '/auth', '/api', '/callback', 
    '/logout', '/login', '/test', '/health/admin'
}

async def proxy_handler(request):
    """Route requests to appropriate backend service"""
    path = request.path_qs
    
    # Check if this should go to admin UI
    for admin_path in ADMIN_PATHS:
        if path.startswith(admin_path):
            target_url = f"http://localhost:8001{path}"
            break
    else:
        # Default to MCP server
        target_url = f"http://localhost:8080{path}"
    
    # Special case for root - redirect to admin
    if path == '/':
        return web.Response(status=302, headers={'Location': '/admin'})
    
    # Health check
    if path == '/health':
        return web.Response(text='healthy\n')
    
    logger.info(f"Proxying {request.method} {path} -> {target_url}")
    
    try:
        # Create session for backend request
        async with aiohttp.ClientSession() as session:
            # Copy headers
            headers = dict(request.headers)
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            
            # Make backend request
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=await request.read(),
                allow_redirects=False
            ) as resp:
                # Create response
                body = await resp.read()
                response = web.Response(
                    body=body,
                    status=resp.status,
                    headers=resp.headers
                )
                return response
                
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return web.Response(status=502, text=f"Proxy error: {str(e)}")

async def init_app():
    app = web.Application()
    app.router.add_route('*', '/{path:.*}', proxy_handler)
    return app

if __name__ == '__main__':
    app = asyncio.run(init_app())
    web.run_app(app, host='0.0.0.0', port=8080)