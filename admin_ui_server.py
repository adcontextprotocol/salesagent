#!/usr/bin/env python3
"""Production server for admin UI using Uvicorn with ASGI adapter."""
import os
import sys
from asgiref.wsgi import WsgiToAsgi

# Ensure proper imports
sys.path.insert(0, os.path.dirname(__file__))

# Import app without running the module-level code
import admin_ui
app = admin_ui.app

# Create ASGI app
asgi_app = WsgiToAsgi(app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))
    print(f"Starting Admin UI with Uvicorn on port {port}")
    uvicorn.run(asgi_app, host="0.0.0.0", port=port, log_level="info")