#!/usr/bin/env python3
"""Admin UI - Refactored modular version using blueprints."""

import logging
import os

from src.admin.app import create_app

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create the Flask app and SocketIO instance
app, socketio = create_app()

# Import remaining route handlers that haven't been modularized yet
# These will be moved to blueprints in future iterations
try:
    # Import the original admin_ui module for remaining routes
    import admin_ui_legacy_routes

    admin_ui_legacy_routes.register_legacy_routes(app)
except ImportError:
    logger.info("No legacy routes to import")

if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_UI_PORT", 8001))

    # Check if we're in production mode
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        logger.info(f"Starting Admin UI in production mode on port {port}")
        # Use SocketIO's run method for production with WebSocket support
        socketio.run(app, host="0.0.0.0", port=port, debug=False)
    else:
        logger.info(f"Starting Admin UI in development mode on port {port}")
        # Use SocketIO's run method with debug enabled for development
        socketio.run(app, host="0.0.0.0", port=port, debug=True)
