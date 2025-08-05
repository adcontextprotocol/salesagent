#!/usr/bin/env python3
"""Production wrapper for admin UI that works around Docker Flask issues."""

import os
import sys

# Force production settings
os.environ.pop('WERKZEUG_SERVER_FD', None)
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'
os.environ['WERKZEUG_DEBUG_PIN'] = 'off'

# Import admin_ui module
import admin_ui

# Start the application directly without app.run()
if __name__ == '__main__':
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))
    
    # Use waitress if available, otherwise fallback to werkzeug
    try:
        from waitress import serve
        print(f"Starting Admin UI with Waitress on port {port}")
        serve(admin_ui.app, host='0.0.0.0', port=port, threads=4)
    except ImportError:
        # Use werkzeug directly to avoid Flask's app.run() issues
        from werkzeug.serving import make_server
        print(f"Starting Admin UI with Werkzeug on port {port}")
        server = make_server('0.0.0.0', port, admin_ui.app, threaded=True)
        server.serve_forever()