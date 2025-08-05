#!/usr/bin/env python3
"""Wrapper to run admin UI without debug mode in Docker."""

import os
import sys

# Force production mode
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'
os.environ['WERKZEUG_DEBUG_PIN'] = 'off'

# Clear any WERKZEUG_SERVER_FD that might be set
if 'WERKZEUG_SERVER_FD' in os.environ:
    del os.environ['WERKZEUG_SERVER_FD']

# Import and run the admin UI
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import admin_ui

if __name__ == '__main__':
    # Get port from environment
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))
    print(f"Starting Admin UI on port {port} (production mode)")
    
    # Use waitress as the production WSGI server
    try:
        from waitress import serve
        print(f"Using waitress WSGI server on port {port}")
        serve(admin_ui.app, host='0.0.0.0', port=port)
    except ImportError:
        # Fallback to Flask's built-in server
        print("Waitress not available, using Flask's built-in server")
        admin_ui.app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
