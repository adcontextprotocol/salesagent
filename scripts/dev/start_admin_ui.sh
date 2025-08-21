#!/bin/bash
# Start admin UI using a simple HTTP server

# Set environment to production
export FLASK_ENV=production
export FLASK_DEBUG=0

# Use Python's built-in HTTP server with WSGI
exec python -c "
import os
import sys
from wsgiref.simple_server import make_server
sys.path.insert(0, os.path.dirname('$0'))

# Import without executing module-level code
os.environ['WERKZEUG_RUN_MAIN'] = 'true'
from src.admin.app import create_app

app, _ = create_app()

port = int(os.environ.get('ADMIN_UI_PORT', 8001))
print(f'Starting Admin UI on port {port} (wsgiref server)')

with make_server('0.0.0.0', port, app) as httpd:
    print(f'Serving on http://0.0.0.0:{port}')
    httpd.serve_forever()
"
