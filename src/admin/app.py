"""Flask application factory for Admin UI."""

import logging
import os
import secrets

from flask import Flask, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO, join_room

from database_session import get_db_session
from models import Tenant
from src.admin.blueprints.auth import auth_bp, init_oauth
from src.admin.blueprints.products import products_bp
from src.admin.blueprints.tenants import tenants_bp
from src.admin.utils import is_super_admin, require_auth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProxyFix:
    """Fix for proxy headers when running behind a reverse proxy."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Handle X-Forwarded-* headers
        scheme = environ.get("HTTP_X_FORWARDED_PROTO", "")
        host = environ.get("HTTP_X_FORWARDED_HOST", "")
        prefix = environ.get("HTTP_X_FORWARDED_PREFIX", "")

        if scheme:
            environ["wsgi.url_scheme"] = scheme
        if host:
            environ["HTTP_HOST"] = host
        if prefix:
            environ["SCRIPT_NAME"] = prefix

        return self.app(environ, start_response)


def create_app(config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="../../templates", static_folder="../../static")

    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
    app.logger.setLevel(logging.INFO)

    # Apply any additional config
    if config:
        app.config.update(config)

    # Apply proxy fix
    app.wsgi_app = ProxyFix(app.wsgi_app)

    # Initialize OAuth
    init_oauth(app)

    # Initialize SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    app.socketio = socketio

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(products_bp)

    # Import and register existing blueprints
    try:
        from superadmin_api import superadmin_api

        app.register_blueprint(superadmin_api)
    except ImportError:
        logger.warning("superadmin_api blueprint not found")

    try:
        from sync_api import sync_api

        app.register_blueprint(sync_api, url_prefix="/api/sync")
    except ImportError:
        logger.warning("sync_api blueprint not found")

    try:
        from adapters.gam_reporting_api import gam_reporting_api

        app.register_blueprint(gam_reporting_api)
    except ImportError:
        logger.warning("gam_reporting_api blueprint not found")

    # Register adapter-specific routes
    register_adapter_routes(app)

    # Core routes
    @app.route("/health")
    def health():
        """Health check endpoint."""
        return {"status": "healthy"}, 200

    @app.route("/")
    @require_auth()
    def index():
        """Main index page."""
        email = session.get("user")

        # If super admin, show all tenants
        if is_super_admin(email):
            try:
                with get_db_session() as db_session:
                    tenants = db_session.query(Tenant).order_by(Tenant.name).all()
                    return render_template("index.html", tenants=tenants)
            except Exception as e:
                logger.error(f"Error loading tenants: {e}")
                return render_template("error.html", error="Failed to load tenants"), 500

        # If regular user, redirect to their tenant
        if "tenant_id" in session:
            return redirect(url_for("tenants.dashboard", tenant_id=session["tenant_id"]))

        # Otherwise show limited view
        return render_template("index.html", tenants=[])

    @app.route("/settings")
    @require_auth(admin_only=True)
    def settings():
        """Global settings page (super admin only)."""
        return render_template("settings.html")

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
        from adapters.google_ad_manager import GoogleAdManager
        from adapters.mock_ad_server import MockAdServer

        # Register routes for each adapter that supports UI configuration
        adapters = [
            GoogleAdManager(principal=None),  # Dummy instance for route registration
            MockAdServer(principal=None, dry_run=False),
        ]

        for adapter in adapters:
            if hasattr(adapter, "register_ui_routes"):
                adapter.register_ui_routes(app)

    except Exception as e:
        logger.warning(f"Error registering adapter routes: {e}")


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
