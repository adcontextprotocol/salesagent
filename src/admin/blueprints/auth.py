"""Authentication blueprint for admin UI."""

import json
import logging
import os

from authlib.integrations.flask_client import OAuth
from database_session import get_db_session
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from src.admin.utils import is_super_admin
from src.core.database.models import Tenant, User

logger = logging.getLogger(__name__)

# Create Blueprint
auth_bp = Blueprint("auth", __name__)


def init_oauth(app):
    """Initialize OAuth with the Flask app."""
    oauth = OAuth(app)

    # Google OAuth configuration
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Try to load from file if env vars not set
    if not client_id or not client_secret:
        for filename in [
            "client_secret.json",
            "client_secret_819081116704-kqh8lrv0nvqmu8onqmvnadqtlajbqbbn.apps.googleusercontent.com.json",
        ]:
            filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath) as f:
                        creds = json.load(f)
                        if "web" in creds:
                            client_id = creds["web"]["client_id"]
                            client_secret = creds["web"]["client_secret"]
                            break
                except Exception as e:
                    logger.error(f"Failed to load OAuth credentials from {filepath}: {e}")

    if client_id and client_secret:
        oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        app.oauth = oauth
        return oauth
    else:
        logger.warning("Google OAuth not configured - authentication will not work")
        return None


@auth_bp.route("/login")
def login():
    """Show login page."""
    return render_template("login.html", test_mode=os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true")


@auth_bp.route("/tenant/<tenant_id>/login")
def tenant_login(tenant_id):
    """Show tenant-specific login page."""
    # Verify tenant exists
    with get_db_session() as db_session:
        tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        if not tenant:
            abort(404)

    return render_template(
        "login.html",
        tenant_id=tenant_id,
        tenant_name=tenant.name,
        test_mode=os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() == "true",
    )


@auth_bp.route("/auth/google")
def google_auth():
    """Initiate Google OAuth flow for super admin."""
    oauth = current_app.oauth if hasattr(current_app, "oauth") else None
    if not oauth:
        flash("OAuth not configured", "error")
        return redirect(url_for("auth.login"))

    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/tenant/<tenant_id>/auth/google")
def tenant_google_auth(tenant_id):
    """Initiate Google OAuth flow for tenant login."""
    oauth = current_app.oauth if hasattr(current_app, "oauth") else None
    if not oauth:
        flash("OAuth not configured", "error")
        return redirect(url_for("auth.tenant_login", tenant_id=tenant_id))

    # Store tenant_id in session for callback
    session["oauth_tenant_id"] = tenant_id
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    oauth = current_app.oauth if hasattr(current_app, "oauth") else None
    if not oauth:
        flash("OAuth not configured", "error")
        return redirect(url_for("auth.login"))

    try:
        token = oauth.google.authorize_access_token()
        if not token:
            flash("Authentication failed", "error")
            return redirect(url_for("auth.login"))

        # Get user info
        user = token.get("userinfo")
        if not user:
            # Try to get user info from ID token
            import jwt

            id_token = token.get("id_token")
            if id_token:
                # Decode without verification since we trust Google's response
                user = jwt.decode(id_token, options={"verify_signature": False})

        if not user or not user.get("email"):
            flash("Could not retrieve user information", "error")
            return redirect(url_for("auth.login"))

        email = user["email"].lower()
        session["user"] = email
        session["user_name"] = user.get("name", email)
        session["user_picture"] = user.get("picture", "")

        # Check if this is a tenant-specific login
        tenant_id = session.pop("oauth_tenant_id", None)
        if tenant_id:
            # Verify user has access to this tenant
            with get_db_session() as db_session:
                tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
                if not tenant:
                    flash("Invalid tenant", "error")
                    return redirect(url_for("auth.login"))

                # Check if user is super admin or has tenant access
                if is_super_admin(email):
                    session["tenant_id"] = tenant_id
                    session["tenant_name"] = tenant.name
                    session["is_super_admin"] = True
                    flash(f"Welcome {user.get('name', email)}! (Super Admin)", "success")
                    return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))

                # Check if user has access to this tenant
                user_record = db_session.query(User).filter_by(email=email, tenant_id=tenant_id, is_active=True).first()

                if user_record:
                    session["tenant_id"] = tenant_id
                    session["tenant_name"] = tenant.name
                    session["is_tenant_admin"] = user_record.is_admin
                    flash(f"Welcome {user.get('name', email)}!", "success")
                    return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))
                else:
                    flash("You don't have access to this tenant", "error")
                    session.clear()
                    return redirect(url_for("auth.tenant_login", tenant_id=tenant_id))

        # Regular login flow - check if super admin
        if is_super_admin(email):
            session["is_super_admin"] = True
            session["role"] = "super_admin"  # Set role for template checks
            session["authenticated"] = True
            session["email"] = email
            flash(f"Welcome {user.get('name', email)}! (Super Admin)", "success")
            return redirect(url_for("core.index"))

        # Check if user is a tenant admin for any tenant
        with get_db_session() as db_session:
            user_tenants = (
                db_session.query(User, Tenant)
                .join(Tenant, User.tenant_id == Tenant.tenant_id)
                .filter(User.email == email, User.is_active)
                .all()
            )

            if user_tenants:
                if len(user_tenants) == 1:
                    # Single tenant - redirect directly
                    user, tenant = user_tenants[0]
                    session["tenant_id"] = tenant.tenant_id
                    session["tenant_name"] = tenant.name
                    session["is_tenant_admin"] = user.is_admin
                    flash(f"Welcome {user.name or email}!", "success")
                    return redirect(url_for("tenants.dashboard", tenant_id=tenant.tenant_id))
                else:
                    # Multiple tenants - let user choose
                    session["available_tenants"] = [
                        {"tenant_id": t.tenant_id, "name": t.name, "is_admin": u.is_admin} for u, t in user_tenants
                    ]
                    return redirect(url_for("auth.select_tenant"))
            else:
                # No access
                flash("You don't have access to any tenants. Please contact your administrator.", "error")
                session.clear()
                return redirect(url_for("auth.login"))

    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        flash("Authentication failed. Please try again.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/select-tenant", methods=["GET", "POST"])
def select_tenant():
    """Allow user to select a tenant when they have access to multiple."""
    if "user" not in session or "available_tenants" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        tenant_id = request.form.get("tenant_id")

        # Verify user has access to selected tenant
        for tenant in session["available_tenants"]:
            if tenant["tenant_id"] == tenant_id:
                session["tenant_id"] = tenant_id
                session["tenant_name"] = tenant["name"]
                session["is_tenant_admin"] = tenant["is_admin"]
                session.pop("available_tenants", None)  # Clean up
                flash(f"Welcome to {tenant['name']}!", "success")
                return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))

        flash("Invalid tenant selection", "error")
        return redirect(url_for("auth.select_tenant"))

    return render_template("choose_tenant.html", tenants=session["available_tenants"])


@auth_bp.route("/logout")
def logout():
    """Log out the current user."""
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("auth.login"))


# Test authentication endpoints (only enabled in test mode)
@auth_bp.route("/test/auth", methods=["POST"])
def test_auth():
    """Test authentication endpoint (only works when ADCP_AUTH_TEST_MODE=true)."""
    if os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() != "true":
        abort(404)

    email = request.form.get("email", "").lower()
    password = request.form.get("password")
    tenant_id = request.form.get("tenant_id")

    # Define test users
    test_users = {
        os.environ.get("TEST_SUPER_ADMIN_EMAIL", "test_super_admin@example.com"): {
            "password": os.environ.get("TEST_SUPER_ADMIN_PASSWORD", "test123"),
            "name": "Test Super Admin",
            "role": "super_admin",
        },
        os.environ.get("TEST_TENANT_ADMIN_EMAIL", "test_tenant_admin@example.com"): {
            "password": os.environ.get("TEST_TENANT_ADMIN_PASSWORD", "test123"),
            "name": "Test Tenant Admin",
            "role": "tenant_admin",
        },
        os.environ.get("TEST_TENANT_USER_EMAIL", "test_tenant_user@example.com"): {
            "password": os.environ.get("TEST_TENANT_USER_PASSWORD", "test123"),
            "name": "Test Tenant User",
            "role": "tenant_user",
        },
    }

    if email in test_users and test_users[email]["password"] == password:
        user_info = test_users[email]
        session["test_user"] = email
        session["test_user_name"] = user_info["name"]
        session["test_user_role"] = user_info["role"]
        session["user"] = email  # For compatibility
        session["user_name"] = user_info["name"]

        if tenant_id:
            session["test_tenant_id"] = tenant_id
            return redirect(url_for("tenants.dashboard", tenant_id=tenant_id))
        else:
            return redirect(url_for("core.index"))

    flash("Invalid test credentials", "error")
    return redirect(request.referrer or url_for("auth.login"))


@auth_bp.route("/test/login")
def test_login_form():
    """Show test login form (only works when ADCP_AUTH_TEST_MODE=true)."""
    if os.environ.get("ADCP_AUTH_TEST_MODE", "").lower() != "true":
        abort(404)

    return render_template("login.html", test_mode=True, test_only=True)
