#!/usr/bin/env python3
"""Production wrapper for refactored admin UI."""

import os

# Force production settings
os.environ.pop("WERKZEUG_SERVER_FD", None)
os.environ["FLASK_ENV"] = "production"
os.environ["FLASK_DEBUG"] = "0"
os.environ["WERKZEUG_DEBUG_PIN"] = "off"

# Import the refactored app
from src.admin.app import create_app

# Create the Flask app and SocketIO instance
app, socketio = create_app()

# Import remaining routes from original admin_ui that haven't been migrated yet
# This allows incremental migration while keeping all functionality
import admin_ui

# Register the original app's routes that aren't migrated yet
# We need to be selective to avoid conflicts
for rule in admin_ui.app.url_map.iter_rules():
    endpoint = rule.endpoint

    # Skip routes we've already migrated
    migrated_routes = {
        "health",  # Migrated to app.py
        "api_health",  # Migrated to api blueprint
        "index",  # Migrated to app.py
        "login",  # In auth blueprint
        "logout",  # In auth blueprint
        "google_auth",  # In auth blueprint
        "google_callback",  # In auth blueprint
        "tenant_login",  # In auth blueprint
        "tenant_google_auth",  # In auth blueprint
        "static",  # Handled by Flask
    }

    if endpoint not in migrated_routes and endpoint in admin_ui.app.view_functions:
        # Register the view function with our app
        view_func = admin_ui.app.view_functions[endpoint]
        for method in rule.methods:
            if method != "HEAD" and method != "OPTIONS":
                try:
                    app.add_url_rule(rule.rule, endpoint=endpoint, view_func=view_func, methods=[method])
                except Exception:
                    # Route might already exist or conflict
                    pass

if __name__ == "__main__":
    port = int(os.environ.get("ADMIN_UI_PORT", 8001))

    # Use waitress if available, otherwise use socketio
    try:
        from waitress import serve

        print(f"Starting Refactored Admin UI with Waitress on port {port}")
        print("✨ Using new blueprint architecture with incremental migration")
        serve(app, host="0.0.0.0", port=port, threads=4)
    except ImportError:
        # Use SocketIO's run method for WebSocket support
        print(f"Starting Refactored Admin UI with SocketIO on port {port}")
        print("✨ Using new blueprint architecture with incremental migration")
        socketio.run(app, host="0.0.0.0", port=port, debug=False)
