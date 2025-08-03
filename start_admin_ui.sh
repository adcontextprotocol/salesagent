#!/bin/bash
# Start admin UI without debug mode issues

# Set environment to production
export FLASK_ENV=production
export FLASK_DEBUG=0
export WERKZEUG_RUN_MAIN=true

# Run the admin UI directly, bypassing Flask's built-in server issues
exec python admin_ui.py