#!/usr/bin/env python3
"""Simple wrapper to run admin UI without debug mode."""
import os
import sys
from werkzeug.serving import run_simple

# Force disable debug mode
os.environ['FLASK_DEBUG'] = '0'
os.environ['FLASK_ENV'] = 'production'

# Import the admin UI app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app object directly - avoid running the main script
import admin_ui
app = admin_ui.app

if __name__ == '__main__':
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))
    print(f"Starting Admin UI on port {port} (production mode)")
    # Use werkzeug directly without Flask's wrapper
    run_simple('0.0.0.0', port, app, use_reloader=False, use_debugger=False)