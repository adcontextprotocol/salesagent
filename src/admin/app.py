"""Flask application factory for Admin UI."""

import logging
import os
import secrets

from flask import Flask, request
from flask_socketio import SocketIO, join_room
from werkzeug.middleware.proxy_fix import ProxyFix as WerkzeugProxyFix

from src.admin.blueprints.adapters import adapters_bp
from src.admin.blueprints.api import api_bp
from src.admin.blueprints.auth import auth_bp, init_oauth
from src.admin.blueprints.core import core_bp
from src.admin.blueprints.creatives import creatives_bp
from src.admin.blueprints.gam import gam_bp
from src.admin.blueprints.inventory import inventory_bp
from src.admin.blueprints.mcp_test import mcp_test_bp
from src.admin.blueprints.operations import operations_bp
from src.admin.blueprints.policy import policy_bp
from src.admin.blueprints.principals import principals_bp
from src.admin.blueprints.products import products_bp
from src.admin.blueprints.settings import settings_bp, superadmin_settings_bp
from src.admin.blueprints.tenants import tenants_bp
from src.admin.blueprints.users import users_bp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Custom ProxyFix for handling X-Script-Name and fixing redirect URLs
class CustomProxyFix:
    """Fix for proxy headers when running behind a reverse proxy with path prefix.
    
    Also fixes hardcoded URLs in redirects to include the script name prefix.
    """

    def __init__(self, app, script_name="/admin"):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        # Handle X-Script-Name (standard for mounting path) or X-Forwarded-Prefix
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if not script_name:
            script_name = environ.get("HTTP_X_FORWARDED_PREFIX", "")
        
        # Use configured script_name if provided in production
        if not script_name and os.environ.get("PRODUCTION") == "true":
            script_name = self.script_name
        
        if script_name:
            # Store for use in response wrapper
            self.active_script_name = script_name
            # Set SCRIPT_NAME so Flask knows it's mounted at this path
            environ["SCRIPT_NAME"] = script_name
            # Also ensure PATH_INFO is correct
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):]
                if not environ["PATH_INFO"]:
                    environ["PATH_INFO"] = "/"
        else:
            self.active_script_name = ""
        
        # Wrap start_response to fix redirect headers
        def custom_start_response(status, headers, exc_info=None):
            # Check if this is a redirect and we have a script_name
            if status.startswith('30') and self.active_script_name:
                # Fix Location header to include script_name if needed
                new_headers = []
                for name, value in headers:
                    if name.lower() == 'location':
                        # If location starts with / but not /admin, prepend /admin
                        if value.startswith('/') and not value.startswith(self.active_script_name):
                            # Skip external URLs
                            if '://' not in value:
                                value = self.active_script_name + value
                        new_headers.append((name, value))
                    else:
                        new_headers.append((name, value))
                headers = new_headers
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)


def create_app(config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="../../templates", static_folder="../../static")

    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
    app.logger.setLevel(logging.INFO)
    
    # Trust proxy headers in production
    if os.environ.get("PRODUCTION") == "true":
        app.config["PREFERRED_URL_SCHEME"] = "https"
        # Force external URLs to use HTTPS
        app.config["SERVER_NAME"] = None  # Let Flask detect from request
        app.config["APPLICATION_ROOT"] = "/"

    # Apply any additional config
    if config:
        app.config.update(config)

    # Apply proxy fixes for production
    if os.environ.get("PRODUCTION") == "true":
        # Use Werkzeug's ProxyFix to handle X-Forwarded headers
        # x_for=1 for X-Forwarded-For, x_proto=1 for X-Forwarded-Proto, x_host=1 for X-Forwarded-Host
        app.wsgi_app = WerkzeugProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=0)
        # Apply custom fix for X-Forwarded-Prefix  
        app.wsgi_app = CustomProxyFix(app.wsgi_app)
    else:
        # In development, still apply custom proxy fix if needed
        app.wsgi_app = CustomProxyFix(app.wsgi_app)

    # Initialize OAuth
    init_oauth(app)

    # Initialize SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    app.socketio = socketio
    
    # Add context processor to make script_name available in templates
    @app.context_processor
    def inject_script_name():
        """Make the script_name (e.g., /admin) available in all templates."""
        if os.environ.get("PRODUCTION") == "true":
            return {"script_name": "/admin"}
        return {"script_name": ""}
    
    # Add after_request handler to fix hardcoded URLs in HTML responses
    @app.after_request
    def fix_hardcoded_urls(response):
        """Fix hardcoded URLs in HTML responses to include script_name prefix."""
        if os.environ.get("PRODUCTION") == "true" and response.content_type and 'text/html' in response.content_type:
            # Only process HTML responses
            try:
                html = response.get_data(as_text=True)
                # Fix common hardcoded patterns
                html = html.replace('href="/', 'href="/admin/')
                html = html.replace("href='/", "href='/admin/")
                html = html.replace('action="/', 'action="/admin/')
                html = html.replace("action='/", "action='/admin/")
                # Fix any that were already prefixed (avoid double prefixing)
                html = html.replace('/admin/admin/', '/admin/')
                response.set_data(html)
            except Exception as e:
                logger.error(f"Error fixing URLs in response: {e}")
        return response

    # Register blueprints
    app.register_blueprint(core_bp)  # Core routes (/, /health, /static, /mcp-test)
    app.register_blueprint(auth_bp)  # No url_prefix - auth routes are at root
    app.register_blueprint(superadmin_settings_bp)  # Superadmin settings at /settings
    app.register_blueprint(tenants_bp, url_prefix="/tenant")
    app.register_blueprint(products_bp, url_prefix="/tenant/<tenant_id>/products")
    app.register_blueprint(principals_bp, url_prefix="/tenant/<tenant_id>")
    app.register_blueprint(users_bp)  # Already has url_prefix in blueprint
    app.register_blueprint(gam_bp)
    app.register_blueprint(operations_bp, url_prefix="/tenant/<tenant_id>")
    app.register_blueprint(creatives_bp, url_prefix="/tenant/<tenant_id>/creative-formats")
    app.register_blueprint(policy_bp, url_prefix="/tenant/<tenant_id>/policy")
    app.register_blueprint(settings_bp, url_prefix="/tenant/<tenant_id>/settings")
    app.register_blueprint(adapters_bp, url_prefix="/tenant/<tenant_id>")
    app.register_blueprint(inventory_bp)  # Has its own internal routing
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(mcp_test_bp)

    # Import and register existing blueprints
    try:
        from src.admin.superadmin_api import superadmin_api

        app.register_blueprint(superadmin_api)
    except ImportError:
        logger.warning("superadmin_api blueprint not found")

    try:
        from src.admin.sync_api import sync_api

        app.register_blueprint(sync_api, url_prefix="/api/sync")
    except ImportError:
        logger.warning("sync_api blueprint not found")

    try:
        from src.adapters.gam_reporting_api import gam_reporting_api

        app.register_blueprint(gam_reporting_api)
    except ImportError:
        logger.warning("gam_reporting_api blueprint not found")

    # Register adapter-specific routes
    register_adapter_routes(app)

    # WebSocket handlers
    @socketio.on("connect")
    def handle_connect():
        """Handle WebSocket connection."""
        logger.info(f"Client connected: {request.sid}")

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle WebSocket disconnection."""
        logger.info(f"Client disconnected: {request.sid}")

    @socketio.on("subscribe")
    def handle_subscribe(data):
        """Handle subscription to tenant events."""
        tenant_id = data.get("tenant_id")
        if tenant_id:
            join_room(f"tenant_{tenant_id}")
            logger.info(f"Client {request.sid} subscribed to tenant {tenant_id}")

    return app, socketio


def register_adapter_routes(app):
    """Register adapter-specific configuration routes."""
    try:
        # Import adapter modules that have UI routes
        from src.adapters.google_ad_manager import GoogleAdManager
        from src.adapters.mock_ad_server import MockAdServer

        # Register routes for each adapter that supports UI routes
        # Note: We skip instantiation errors since routes are optional
        adapter_configs = [
            (GoogleAdManager, {"config": {}, "principal": None}),
            (MockAdServer, {"principal": None, "dry_run": False}),
        ]

        for adapter_class, kwargs in adapter_configs:
            try:
                # Try to create instance for route registration
                adapter_instance = adapter_class(**kwargs)
                if hasattr(adapter_instance, "register_ui_routes"):
                    adapter_instance.register_ui_routes(app)
                    logger.info(f"Registered UI routes for {adapter_class.__name__}")
            except Exception as e:
                # This is expected for some adapters that require specific config
                logger.debug(f"Could not register {adapter_class.__name__} routes: {e}")

    except Exception as e:
        logger.warning(f"Error importing adapter modules: {e}")


def broadcast_activity_to_websocket(tenant_id: str, activity: dict):
    """Broadcast activity to WebSocket clients."""
    try:
        from flask import current_app

        if hasattr(current_app, "socketio"):
            current_app.socketio.emit(
                "activity",
                activity,
                room=f"tenant_{tenant_id}",
                namespace="/",
            )
    except Exception as e:
        logger.error(f"Error broadcasting to WebSocket: {e}")
