#!/usr/bin/env python
"""Production entry point for refactored admin UI."""

import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Import the refactored app
    from src.admin.app import create_app

    # Create the app
    app, socketio = create_app()

    # Get configuration from environment
    port = int(os.environ.get("ADMIN_UI_PORT", 8001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    # Determine which server to use
    use_werkzeug = debug or os.environ.get("USE_WERKZEUG", "").lower() == "true"

    if use_werkzeug:
        logger.info(f"Starting Admin UI with Werkzeug on port {port} (debug={debug})")
        socketio.run(app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True)
    else:
        logger.info(f"Starting Admin UI with Waitress on port {port}")
        from waitress import serve

        serve(app, host="0.0.0.0", port=port, threads=4)
