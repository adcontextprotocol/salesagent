#!/usr/bin/env python3
"""Admin UI with Google OAuth2 authentication."""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory, g
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets
import json
import os
import uuid
import logging
import asyncio
import traceback
from datetime import datetime, timezone
from functools import wraps
from authlib.integrations.flask_client import OAuth
from db_config import get_db_connection, DatabaseConfig
from validation import FormValidator, validate_form_data, sanitize_form_data

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.logger.setLevel(logging.INFO)

# Initialize SocketIO with Flask app
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Import schemas after Flask app is created
from schemas import Principal

# Import and register super admin API blueprint
from superadmin_api import superadmin_api
app.register_blueprint(superadmin_api)

# Import and register sync API blueprint
from sync_api import sync_api
app.register_blueprint(sync_api, url_prefix='/api/sync')

# Import and register GAM reporting API blueprint
from adapters.gam_reporting_api import gam_reporting_api
app.register_blueprint(gam_reporting_api)

# Import GAM inventory service for targeting browser
from gam_inventory_service import GAMInventoryService, create_inventory_endpoints as register_inventory_endpoints, SessionLocal, db_session

# Import activity feed for WebSocket support
from activity_feed import activity_feed

# Configure for being mounted at different paths and proxy headers
class ProxyFix:
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        # Handle being mounted under /admin
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        
        # Handle proxy headers for correct URL generation
        if environ.get('HTTP_X_FORWARDED_HOST'):
            environ['HTTP_HOST'] = environ['HTTP_X_FORWARDED_HOST']
        if environ.get('HTTP_X_FORWARDED_PROTO'):
            environ['wsgi.url_scheme'] = environ['HTTP_X_FORWARDED_PROTO']
        if environ.get('HTTP_X_FORWARDED_PORT'):
            environ['SERVER_PORT'] = environ['HTTP_X_FORWARDED_PORT']
            
        return self.app(environ, start_response)

app.wsgi_app = ProxyFix(app.wsgi_app)

# OAuth Configuration
GOOGLE_CLIENT_ID = None
GOOGLE_CLIENT_SECRET = None

print(f"DEBUG: Environment variables at startup:")
print(f"DEBUG: GOOGLE_CLIENT_ID={os.environ.get('GOOGLE_CLIENT_ID')}")
print(f"DEBUG: GOOGLE_CLIENT_SECRET exists={bool(os.environ.get('GOOGLE_CLIENT_SECRET'))}")
print(f"DEBUG: GOOGLE_OAUTH_CREDENTIALS_FILE={os.environ.get('GOOGLE_OAUTH_CREDENTIALS_FILE')}")

# Load Google OAuth credentials
# First check environment variable, then look for any client_secret*.json file
oauth_creds_file = os.environ.get('GOOGLE_OAUTH_CREDENTIALS_FILE')

if not oauth_creds_file:
    # Look for any client_secret*.json file in the current directory
    import glob
    creds_files = [f for f in glob.glob('client_secret*.json') if os.path.isfile(f)]
    if creds_files:
        oauth_creds_file = creds_files[0]
        
print(f"DEBUG: After file search, oauth_creds_file={repr(oauth_creds_file)}")

if oauth_creds_file and os.path.exists(oauth_creds_file):
    with open(oauth_creds_file) as f:
        creds = json.load(f)
        GOOGLE_CLIENT_ID = creds['web']['client_id']
        GOOGLE_CLIENT_SECRET = creds['web']['client_secret']
else:
    # Try environment variables as fallback
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    print(f"DEBUG: oauth_creds_file={oauth_creds_file}")
    print(f"DEBUG: GOOGLE_CLIENT_ID from env={GOOGLE_CLIENT_ID}")
    print(f"DEBUG: GOOGLE_CLIENT_SECRET exists={bool(GOOGLE_CLIENT_SECRET)}")

# Test mode configuration - ONLY FOR AUTOMATED TESTING
TEST_MODE_ENABLED = os.environ.get('ADCP_AUTH_TEST_MODE', '').lower() == 'true'
if TEST_MODE_ENABLED:
    print("⚠️  WARNING: Test authentication mode is ENABLED. This should NEVER be used in production!")
    print("⚠️  OAuth authentication is BYPASSED. Disable by removing ADCP_AUTH_TEST_MODE environment variable.")

# Super admin configuration from environment or config
SUPER_ADMIN_EMAILS = os.environ.get('SUPER_ADMIN_EMAILS', '').split(',') if os.environ.get('SUPER_ADMIN_EMAILS') else []
SUPER_ADMIN_DOMAINS = os.environ.get('SUPER_ADMIN_DOMAINS', '').split(',') if os.environ.get('SUPER_ADMIN_DOMAINS') else []

# Default super admin config if none provided
if not SUPER_ADMIN_EMAILS and not SUPER_ADMIN_DOMAINS:
    # You should set these via environment variables in production
    SUPER_ADMIN_EMAILS = []  # e.g., ['admin@example.com']
    SUPER_ADMIN_DOMAINS = []  # e.g., ['example.com']

# Test mode users - predefined for automated testing
# Passwords are loaded from environment variables with defaults for convenience
TEST_USERS = {}
if TEST_MODE_ENABLED:
    # Only populate test users when test mode is enabled
    TEST_USERS = {
        os.environ.get('TEST_SUPER_ADMIN_EMAIL', 'test_super_admin@example.com'): {
            'name': 'Test Super Admin',
            'role': 'super_admin',
            'password': os.environ.get('TEST_SUPER_ADMIN_PASSWORD', 'test123')
        },
        os.environ.get('TEST_TENANT_ADMIN_EMAIL', 'test_tenant_admin@example.com'): {
            'name': 'Test Tenant Admin', 
            'role': 'tenant_admin',
            'password': os.environ.get('TEST_TENANT_ADMIN_PASSWORD', 'test123')
        },
        os.environ.get('TEST_TENANT_USER_EMAIL', 'test_tenant_user@example.com'): {
            'name': 'Test Tenant User',
            'role': 'tenant_user', 
            'password': os.environ.get('TEST_TENANT_USER_PASSWORD', 'test123')
        }
    }
    
    # Log test mode configuration (without passwords)
    print("Test mode users configured:")
    for email in TEST_USERS:
        print(f"  - {email} ({TEST_USERS[email]['role']})")

# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@app.before_request
def before_request():
    """Set global variables for templates."""
    g.test_mode = TEST_MODE_ENABLED

def parse_json_config(config_str):
    """Parse JSON config from database, handling both string and dict types."""
    if isinstance(config_str, dict):
        return config_str
    elif config_str:
        return json.loads(config_str)
    else:
        return {}

def get_tenant_config_from_db(conn, tenant_id):
    """Build tenant config from individual database columns."""
    cursor = conn.execute("""
        SELECT ad_server, max_daily_budget, enable_aee_signals,
               authorized_emails, authorized_domains, slack_webhook_url,
               slack_audit_webhook_url, hitl_webhook_url, admin_token,
               auto_approve_formats, human_review_required, policy_settings
        FROM tenants WHERE tenant_id = ?
    """, (tenant_id,))
    
    row = cursor.fetchone()
    if not row:
        return None
    
    # Build config object from columns
    config = {
        'adapters': {},
        'features': {
            'max_daily_budget': row[1] or 10000,
            'enable_aee_signals': bool(row[2])
        },
        'creative_engine': {
            'human_review_required': bool(row[10])
        }
    }
    
    # Add adapter configuration
    if row[0]:  # ad_server
        # Get adapter-specific config from adapter_config table
        adapter_cursor = conn.execute(
            "SELECT * FROM adapter_config WHERE tenant_id = ? AND adapter_type = ?",
            (tenant_id, row[0])
        )
        adapter_row = adapter_cursor.fetchone()
        
        adapter_config = {'enabled': True}
        if adapter_row:
            # TODO: Map adapter-specific fields based on adapter type
            pass
        
        config['adapters'][row[0]] = adapter_config
    
    # Add optional fields
    if row[3]:  # authorized_emails
        config['authorized_emails'] = json.loads(row[3]) if isinstance(row[3], str) else row[3]
    if row[4]:  # authorized_domains
        config['authorized_domains'] = json.loads(row[4]) if isinstance(row[4], str) else row[4]
    if row[5]:  # slack_webhook_url
        config['features']['slack_webhook_url'] = row[5]
    if row[6]:  # slack_audit_webhook_url
        config['features']['slack_audit_webhook_url'] = row[6]
    if row[7]:  # hitl_webhook_url
        config['features']['hitl_webhook_url'] = row[7]
    if row[8]:  # admin_token
        config['admin_token'] = row[8]
    if row[9]:  # auto_approve_formats
        config['creative_engine']['auto_approve_formats'] = json.loads(row[9]) if isinstance(row[9], str) else row[9]
    if row[11]:  # policy_settings
        config['policy_settings'] = json.loads(row[11]) if isinstance(row[11], str) else row[11]
    
    return config

def is_super_admin(email):
    """Check if email is authorized as super admin."""
    # Debug logging
    app.logger.info(f"Checking super admin for email: {email}")
    app.logger.info(f"SUPER_ADMIN_EMAILS: {SUPER_ADMIN_EMAILS}")
    app.logger.info(f"SUPER_ADMIN_DOMAINS: {SUPER_ADMIN_DOMAINS}")
    
    # Check explicit email list
    if email in SUPER_ADMIN_EMAILS:
        app.logger.info(f"Email {email} found in SUPER_ADMIN_EMAILS")
        return True
    
    # Check domain
    domain = email.split('@')[1] if '@' in email else ''
    app.logger.info(f"Email domain: {domain}")
    if domain and domain in SUPER_ADMIN_DOMAINS:
        app.logger.info(f"Domain {domain} found in SUPER_ADMIN_DOMAINS")
        return True
    
    app.logger.info(f"Email {email} is not a super admin")
    return False

def is_tenant_admin(email, tenant_id=None):
    """Check if email is authorized for a specific tenant."""
    conn = get_db_connection()
    
    if tenant_id:
        # Check specific tenant
        cursor = conn.execute("""
            SELECT authorized_emails, authorized_domains
            FROM tenants
            WHERE tenant_id = ? AND is_active = ?
        """, (tenant_id, True))
        
        tenant = cursor.fetchone()
        if tenant:
            # Parse JSON arrays
            authorized_emails = json.loads(tenant[0]) if tenant[0] else []
            authorized_domains = json.loads(tenant[1]) if tenant[1] else []
            
            # Check authorized emails
            if email in authorized_emails:
                conn.close()
                return True
            
            # Check authorized domains
            domain = email.split('@')[1] if '@' in email else ''
            if domain and domain in authorized_domains:
                conn.close()
                return True
    else:
        # Check all tenants to find which one(s) this email can access
        cursor = conn.execute("""
            SELECT tenant_id, name, authorized_emails, authorized_domains
            FROM tenants
            WHERE is_active = ?
        """, (True,))
        
        authorized_tenants = []
        for row in cursor.fetchall():
            tenant_id = row[0]
            tenant_name = row[1]
            authorized_emails = json.loads(row[2]) if row[2] else []
            authorized_domains = json.loads(row[3]) if row[3] else []
            
            # Check authorized emails
            if email in authorized_emails:
                authorized_tenants.append((tenant_id, tenant_name))
                continue
            
            # Check authorized domains
            domain = email.split('@')[1] if '@' in email else ''
            if domain and domain in authorized_domains:
                authorized_tenants.append((tenant_id, tenant_name))
        
        conn.close()
        return authorized_tenants
    
    conn.close()
    return False

def require_auth(admin_only=False):
    """Decorator for authentication."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('authenticated'):
                # Store the URL the user was trying to access
                session['next_url'] = request.url
                # Check if we're in a tenant-specific route
                tenant_id = kwargs.get('tenant_id') or session.get('tenant_id')
                if tenant_id and not admin_only:
                    return redirect(url_for('tenant_login', tenant_id=tenant_id))
                return redirect(url_for('login'))
            
            # Check if super admin is required but user is tenant admin
            if admin_only and session.get('role') != 'super_admin':
                return "Access denied. Super admin required.", 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_tenant_access(api_mode=False):
    """Decorator that checks both authentication and tenant access.
    
    Args:
        api_mode: If True, returns JSON errors instead of HTML responses
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check authentication
            if not session.get('authenticated'):
                if api_mode:
                    return jsonify({'error': 'Authentication required'}), 401
                session['next_url'] = request.url
                tenant_id = kwargs.get('tenant_id') or session.get('tenant_id')
                if tenant_id:
                    return redirect(url_for('tenant_login', tenant_id=tenant_id))
                return redirect(url_for('login'))
            
            # Get tenant_id from route
            tenant_id = kwargs.get('tenant_id')
            if not tenant_id:
                if api_mode:
                    return jsonify({'error': 'Tenant ID required'}), 400
                return "Tenant ID required", 400
            
            # Check tenant access
            if session.get('role') != 'super_admin':
                if session.get('tenant_id') != tenant_id:
                    if api_mode:
                        return jsonify({'error': 'Access denied'}), 403
                    return "Access denied", 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login')
def login():
    """Show login page for super admin."""
    return render_template('login.html', tenant_id=None, test_mode=TEST_MODE_ENABLED)

@app.route('/tenant/<tenant_id>/login')
def tenant_login(tenant_id):
    """Show login page for specific tenant."""
    # Verify tenant exists
    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ? AND is_active = ?", (tenant_id, True))
    tenant = cursor.fetchone()
    conn.close()
    
    if not tenant:
        return "Tenant not found", 404
        
    return render_template('login.html', tenant_id=tenant_id, tenant_name=tenant[0], test_mode=TEST_MODE_ENABLED)

@app.route('/auth/google')
def google_auth():
    """Initiate Google OAuth flow for super admin."""
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/tenant/<tenant_id>/auth/google')
def tenant_google_auth(tenant_id):
    """Initiate Google OAuth flow for specific tenant."""
    # Store tenant_id in session for callback
    session['oauth_tenant_id'] = tenant_id
    # Use the centralized callback for all OAuth flows
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback for both super admin and tenant users."""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            # Check if this was a tenant-specific login attempt
            oauth_tenant_id = session.pop('oauth_tenant_id', None)
            if oauth_tenant_id:
                return redirect(url_for('tenant_login', tenant_id=oauth_tenant_id))
            return redirect(url_for('login'))
        
        email = user_info.get('email')
        if not email:
            oauth_tenant_id = session.pop('oauth_tenant_id', None)
            return render_template('login.html', 
                                 error='No email address provided by Google', 
                                 tenant_id=oauth_tenant_id)
        
        app.logger.info(f"OAuth callback received email: {email}")
        
        # Check if this is a tenant-specific login attempt
        oauth_tenant_id = session.pop('oauth_tenant_id', None)
        
        if oauth_tenant_id:
            # Tenant-specific authentication flow
            conn = get_db_connection()
            
            # First check if user is in the users table for this tenant
            cursor = conn.execute("""
                SELECT u.user_id, u.role, u.name, t.name as tenant_name, u.is_active
                FROM users u
                JOIN tenants t ON u.tenant_id = t.tenant_id
                WHERE u.email = ? AND u.tenant_id = ?
            """, (email, oauth_tenant_id))
            user_row = cursor.fetchone()
            
            # Update last login if user exists
            if user_row:
                user_id, user_role, user_name, tenant_name, is_active = user_row
                
                if not is_active:
                    conn.close()
                    return render_template('login.html', 
                                         error='Your account has been disabled',
                                         tenant_id=oauth_tenant_id)
                
                # Update last login and Google ID
                conn.execute("""
                    UPDATE users 
                    SET last_login = ?, google_id = ?
                    WHERE user_id = ?
                """, (datetime.now().isoformat(), user_info.get('sub'), user_id))
                conn.connection.commit()
                conn.close()
                
                session['authenticated'] = True
                session['role'] = user_role  # Use actual user role from DB
                session['user_id'] = user_id
                session['tenant_id'] = oauth_tenant_id
                session['tenant_name'] = tenant_name
                session['email'] = email
                session['username'] = user_name or user_info.get('name', email)
                
                # Redirect to originally requested URL if stored
                next_url = session.pop('next_url', None)
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('tenant_dashboard', tenant_id=oauth_tenant_id))
            
            # If not in users table, check legacy tenant admin config
            if is_tenant_admin(email, oauth_tenant_id):
                # Get tenant name for session
                cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (oauth_tenant_id,))
                tenant = cursor.fetchone()
                conn.close()
                
                session['authenticated'] = True
                session['role'] = 'tenant_admin'  # Legacy role
                session['tenant_id'] = oauth_tenant_id
                session['tenant_name'] = tenant[0] if tenant else oauth_tenant_id
                session['email'] = email
                session['username'] = user_info.get('name', email)
                
                # Redirect to originally requested URL if stored
                next_url = session.pop('next_url', None)
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('tenant_dashboard', tenant_id=oauth_tenant_id))
            
            # Check if super admin trying to access tenant
            if is_super_admin(email):
                # Get tenant name for session
                cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (oauth_tenant_id,))
                tenant = cursor.fetchone()
                conn.close()
                
                session['authenticated'] = True
                session['role'] = 'super_admin'
                session['email'] = email
                session['username'] = user_info.get('name', email)
                
                if tenant:
                    session['tenant_name'] = tenant[0]
                
                # Super admin can access any tenant
                # Redirect to originally requested URL if stored
                next_url = session.pop('next_url', None)
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('tenant_dashboard', tenant_id=oauth_tenant_id))
            
            # Fall back to checking tenant config
            config = get_tenant_config_from_db(conn, oauth_tenant_id)
            conn.close()
            
            if config:
                # Check if user is authorized for this tenant
                authorized_emails = config.get('authorized_emails', [])
                authorized_domains = config.get('authorized_domains', [])
                
                domain = email.split('@')[1] if '@' in email else None
                
                if email in authorized_emails or (domain and domain in authorized_domains):
                    session['authenticated'] = True
                    session['role'] = 'tenant_user'
                    session['tenant_id'] = oauth_tenant_id
                    session['email'] = email
                    session['username'] = user_info.get('name', email)
                    
                    # Get tenant name
                    conn = get_db_connection()
                    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (oauth_tenant_id,))
                    tenant = cursor.fetchone()
                    conn.close()
                    
                    if tenant:
                        session['tenant_name'] = tenant[0]
                    
                    # Redirect to originally requested URL if stored
                    next_url = session.pop('next_url', None)
                    if next_url:
                        return redirect(next_url)
                    return redirect(url_for('tenant_dashboard', tenant_id=oauth_tenant_id))
            
            # Not authorized for this tenant
            return render_template('login.html', 
                                 error=f'Email {email} is not authorized for this tenant',
                                 tenant_id=oauth_tenant_id)
        
        # Standard super admin flow (no tenant_id in session)
        # Check if super admin
        if is_super_admin(email):
            session['authenticated'] = True
            session['role'] = 'super_admin'
            session['email'] = email
            session['username'] = user_info.get('name', email)
            # Redirect to originally requested URL if stored
            next_url = session.pop('next_url', None)
            if next_url:
                return redirect(next_url)
            return redirect(url_for('index'))
        
        # Check if tenant admin
        tenant_access = is_tenant_admin(email)
        if tenant_access:
            if isinstance(tenant_access, list) and len(tenant_access) == 1:
                # Single tenant access
                tenant_id, tenant_name = tenant_access[0]
                session['authenticated'] = True
                session['role'] = 'tenant_admin'
                session['tenant_id'] = tenant_id
                session['tenant_name'] = tenant_name
                session['email'] = email
                session['username'] = user_info.get('name', email)
                # Redirect to originally requested URL if stored
                next_url = session.pop('next_url', None)
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))
            elif isinstance(tenant_access, list) and len(tenant_access) > 1:
                # Multiple tenant access - let them choose
                session['pre_auth_email'] = email
                session['pre_auth_name'] = user_info.get('name', email)
                session['available_tenants'] = tenant_access
                return render_template('choose_tenant.html', tenants=tenant_access)
        
        # Not authorized
        return render_template('login.html', 
                             error=f'Email {email} is not authorized to access this system',
                             tenant_id=None)
        
    except Exception as e:
        app.logger.error(f"OAuth callback error: {e}")
        oauth_tenant_id = session.pop('oauth_tenant_id', None)
        return render_template('login.html', 
                             error='Authentication failed', 
                             tenant_id=oauth_tenant_id)

# Removed tenant-specific callback - now handled by the centralized callback

@app.route('/auth/select-tenant', methods=['POST'])
def select_tenant():
    """Handle tenant selection for users with multiple tenant access."""
    if not session.get('pre_auth_email'):
        return redirect(url_for('login'))
    
    tenant_id = request.form.get('tenant_id')
    available_tenants = session.get('available_tenants', [])
    
    # Verify the selected tenant is in the available list
    selected_tenant = None
    for tid, tname in available_tenants:
        if tid == tenant_id:
            selected_tenant = (tid, tname)
            break
    
    if not selected_tenant:
        return "Invalid tenant selection", 400
    
    # Set up session
    session['authenticated'] = True
    session['role'] = 'tenant_admin'
    session['tenant_id'] = selected_tenant[0]
    session['tenant_name'] = selected_tenant[1]
    session['email'] = session.pop('pre_auth_email')
    session['username'] = session.pop('pre_auth_name')
    session.pop('available_tenants', None)
    
    return redirect(url_for('tenant_dashboard', tenant_id=selected_tenant[0]))

@app.route('/logout')
def logout():
    """Log out and clear session."""
    # Save tenant_id before clearing session
    tenant_id = session.get('tenant_id')
    is_super_admin = session.get('role') == 'super_admin'
    
    session.clear()
    
    # Redirect to appropriate login page
    if is_super_admin or not tenant_id:
        return redirect(url_for('login'))
    else:
        return redirect(url_for('tenant_login', tenant_id=tenant_id))

# Test mode authentication routes - ONLY FOR AUTOMATED TESTING
@app.route('/test/auth', methods=['POST'])
def test_auth():
    """Test authentication endpoint - bypasses OAuth for automated testing."""
    if not TEST_MODE_ENABLED:
        return "Test mode is not enabled", 404
    
    email = request.form.get('email')
    password = request.form.get('password')
    tenant_id = request.form.get('tenant_id')  # Optional for tenant-specific login
    
    # Check test user credentials
    if email not in TEST_USERS or TEST_USERS[email]['password'] != password:
        if tenant_id:
            return redirect(url_for('tenant_login', tenant_id=tenant_id) + '?error=Invalid+test+credentials')
        return redirect(url_for('login') + '?error=Invalid+test+credentials')
    
    test_user = TEST_USERS[email]
    
    # For super admin test user
    if test_user['role'] == 'super_admin':
        session['authenticated'] = True
        session['role'] = 'super_admin'
        session['email'] = email
        session['username'] = test_user['name']
        return redirect(url_for('index'))
    
    # For tenant users, we need a tenant_id
    if not tenant_id:
        return redirect(url_for('login') + '?error=Tenant+ID+required+for+non-super-admin+test+users')
    
    # Verify tenant exists
    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ? AND is_active = ?", (tenant_id, True))
    tenant = cursor.fetchone()
    
    if not tenant:
        conn.close()
        return redirect(url_for('login') + '?error=Invalid+tenant+ID')
    
    # Set up session for tenant user
    session['authenticated'] = True
    session['role'] = test_user['role']
    session['user_id'] = f"test_{email}"  # Fake user ID for testing
    session['tenant_id'] = tenant_id
    session['tenant_name'] = tenant[0]
    session['email'] = email
    session['username'] = test_user['name']
    
    conn.close()
    return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))

@app.route('/test/login')
def test_login_form():
    """Show test login form for automated testing."""
    if not TEST_MODE_ENABLED:
        return "Test mode is not enabled", 404
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Login - AdCP Admin</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); width: 400px; }
            .warning { background: #ff9800; color: white; padding: 1rem; margin: -2rem -2rem 2rem -2rem; border-radius: 8px 8px 0 0; text-align: center; }
            h1 { color: #333; margin: 0 0 1.5rem 0; }
            .form-group { margin-bottom: 1rem; }
            label { display: block; margin-bottom: 0.5rem; color: #555; }
            input, select { width: 100%; padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; }
            button { background: #4285f4; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 4px; cursor: pointer; width: 100%; }
            button:hover { background: #357ae8; }
            .test-users { margin-top: 2rem; padding: 1rem; background: #f9f9f9; border-radius: 4px; }
            .test-users h3 { margin-top: 0; }
            .test-users code { background: #eee; padding: 0.2rem 0.4rem; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="warning">⚠️ TEST MODE - NOT FOR PRODUCTION USE</div>
            <h1>Test Login</h1>
            <form method="POST" action="/test/auth">
                <div class="form-group">
                    <label>Email:</label>
                    <select name="email" required>
                        <option value="">Select a test user...</option>
                        <option value="test_super_admin@example.com">Test Super Admin</option>
                        <option value="test_tenant_admin@example.com">Test Tenant Admin</option>
                        <option value="test_tenant_user@example.com">Test Tenant User</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Password:</label>
                    <input type="password" name="password" placeholder="test123" required>
                </div>
                <div class="form-group">
                    <label>Tenant ID (optional, required for tenant users):</label>
                    <input type="text" name="tenant_id" placeholder="e.g., tenant_abc123">
                </div>
                <button type="submit">Test Login</button>
            </form>
            <div class="test-users">
                <h3>Available Test Users:</h3>
                <ul>
                    <li><code>test_super_admin@example.com</code> - Full admin access</li>
                    <li><code>test_tenant_admin@example.com</code> - Tenant admin (requires tenant_id)</li>
                    <li><code>test_tenant_user@example.com</code> - Tenant user (requires tenant_id)</li>
                </ul>
                <p>All test users use password: <code>test123</code></p>
            </div>
        </div>
    </body>
    </html>
    '''

# Route removed - using tenant_dashboard as the main route now

@app.route('/health')
def health():
    """Health check endpoint for monitoring."""
    return "OK", 200

@app.route('/')
@require_auth()
def index():
    """Dashboard showing all tenants (super admin) or redirect to tenant page (tenant admin)."""
    # Tenant admins should go directly to their tenant page
    if session.get('role') == 'tenant_admin':
        return redirect(url_for('tenant_dashboard', tenant_id=session.get('tenant_id')))
    
    # Super admins see all tenants
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, is_active, created_at
        FROM tenants
        ORDER BY created_at DESC
    """)
    tenants = []
    for row in cursor.fetchall():
        # Convert datetime if it's a string
        created_at = row[4]
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('T', ' '))
            except:
                pass
        
        tenants.append({
            'tenant_id': row[0],
            'name': row[1],
            'subdomain': row[2],
            'is_active': row[3],
            'created_at': created_at
        })
    conn.close()
    return render_template('index.html', tenants=tenants)

@app.route('/settings')
@require_auth(admin_only=True)
def settings():
    """Superadmin settings page."""
    conn = get_db_connection()
    
    # Get all superadmin config values
    cursor = conn.execute("""
        SELECT config_key, config_value, description
        FROM superadmin_config
        ORDER BY config_key
    """)
    
    config_items = {}
    for row in cursor.fetchall():
        config_items[row[0]] = {
            'value': row[1] if row[1] else '',
            'description': row[2] if row[2] else ''
        }
    
    conn.close()
    return render_template('settings.html', config_items=config_items)

@app.route('/settings/update', methods=['POST'])
@require_auth(admin_only=True)
def update_settings():
    """Update superadmin settings."""
    conn = get_db_connection()
    
    try:
        # Update GAM OAuth settings
        gam_client_id = request.form.get('gam_oauth_client_id', '').strip()
        gam_client_secret = request.form.get('gam_oauth_client_secret', '').strip()
        
        # Update in database
        conn.execute("""
            UPDATE superadmin_config 
            SET config_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE config_key = ?
        """, (gam_client_id, session.get('email'), 'gam_oauth_client_id'))
        
        conn.execute("""
            UPDATE superadmin_config 
            SET config_value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE config_key = ?
        """, (gam_client_secret, session.get('email'), 'gam_oauth_client_secret'))
        
        conn.connection.commit()  # Access the underlying connection
        flash('Settings updated successfully', 'success')
        
    except Exception as e:
        conn.connection.rollback()  # Access the underlying connection
        flash(f'Error updating settings: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('settings'))

@app.route('/tenant/<tenant_id>/manage_old')
@require_auth()
def tenant_detail_old(tenant_id):
    """Show tenant details and configuration."""
    # Check if tenant admin is trying to access another tenant
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only view your own tenant.", 403
    
    conn = get_db_connection()
    
    # Get tenant with all fields
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, is_active, created_at,
               ad_server, max_daily_budget, enable_aee_signals,
               authorized_emails, authorized_domains, slack_webhook_url,
               admin_token, auto_approve_formats, human_review_required,
               slack_audit_webhook_url, hitl_webhook_url, policy_settings
        FROM tenants WHERE tenant_id = ?
    """, (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1],
        'subdomain': row[2],
        'is_active': row[3],
        'created_at': row[4],
        'ad_server': row[5],
        'max_daily_budget': row[6],
        'enable_aee_signals': row[7],
        'authorized_emails': json.loads(row[8]) if row[8] else [],
        'authorized_domains': json.loads(row[9]) if row[9] else [],
        'slack_webhook_url': row[10],
        'admin_token': row[11],
        'auto_approve_formats': json.loads(row[12]) if row[12] else [],
        'human_review_required': row[13],
        'slack_audit_webhook_url': row[14],
        'hitl_webhook_url': row[15],
        'policy_settings': json.loads(row[16]) if row[16] else None
    }
    
    # Get principals with platform mappings
    cursor = conn.execute("""
        SELECT principal_id, name, access_token, created_at, platform_mappings
        FROM principals WHERE tenant_id = ?
        ORDER BY created_at DESC
    """, (tenant_id,))
    principals = []
    for row in cursor.fetchall():
        # Parse platform_mappings JSON
        platform_mappings = row[4]
        if isinstance(platform_mappings, str):
            platform_mappings = json.loads(platform_mappings)
        
        principals.append({
            'principal_id': row[0],
            'name': row[1],
            'access_token': row[2],
            'created_at': row[3],
            'platform_mappings': platform_mappings or {}
        })
    
    # Get products
    cursor = conn.execute("""
        SELECT product_id, name, delivery_type, cpm
        FROM products WHERE tenant_id = ?
    """, (tenant_id,))
    products = []
    for row in cursor.fetchall():
        products.append({
            'product_id': row[0],
            'name': row[1],
            'delivery_type': row[2],
            'cpm': row[3]
        })
    
    # Get operational stats
    active_adapter = tenant['ad_server']  # Now we have a dedicated column for this
    
    # Get adapter configuration if exists
    adapter_config = None
    if active_adapter:
        cursor = conn.execute("""
            SELECT * FROM adapter_config 
            WHERE tenant_id = ? AND adapter_type = ?
        """, (tenant_id, active_adapter))
        adapter_row = cursor.fetchone()
        if adapter_row:
            # Convert row to dict based on adapter type
            if active_adapter == 'google_ad_manager':
                adapter_config = {
                    'network_code': adapter_row[3],  # gam_network_code (after mock_dry_run)
                    'refresh_token': adapter_row[4],  # gam_refresh_token
                    'company_id': adapter_row[5],     # gam_company_id
                    'trafficker_id': adapter_row[6],  # gam_trafficker_id
                    'manual_approval_required': adapter_row[7]  # gam_manual_approval_required
                }
            elif active_adapter == 'mock':
                adapter_config = {
                    'dry_run': adapter_row[2]  # mock_dry_run (position 2)
                }
            # Add other adapters as needed
    
    # Get active media buys count
    cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = ? AND status = 'active'
    """, (tenant_id,))
    active_media_buys = cursor.fetchone()[0]
    
    # Get total spend
    cursor = conn.execute("""
        SELECT SUM(budget) FROM media_buys 
        WHERE tenant_id = ? AND status = 'active'
    """, (tenant_id,))
    total_active_spend = cursor.fetchone()[0] or 0
    
    # Get pending tasks count
    cursor = conn.execute("""
        SELECT COUNT(*) FROM tasks 
        WHERE tenant_id = ? AND status = 'pending'
    """, (tenant_id,))
    pending_tasks = cursor.fetchone()[0]
    
    # Get user count
    cursor = conn.execute("""
        SELECT COUNT(*) FROM users 
        WHERE tenant_id = ? AND is_active = TRUE
    """, (tenant_id,))
    active_users = cursor.fetchone()[0]
    
    conn.close()
    
    # Add operational stats to tenant
    tenant['active_adapter'] = active_adapter
    tenant['active_media_buys'] = active_media_buys
    tenant['total_active_spend'] = total_active_spend
    tenant['pending_tasks'] = pending_tasks
    tenant['active_users'] = active_users
    
    
    # Get the current port from environment
    admin_port = int(os.environ.get('ADMIN_UI_PORT', 8001))
    
    # Calculate tab completion status
    tab_status = {
        'adserver': bool(active_adapter),
        'principals': len(principals) > 0,
        'products': len(products) > 0,
        'formats': False,  # Will check below
        'integrations': True,  # Integrations are optional
        'users': active_users > 0,
        'authorization': True,  # Authorization tab is always complete (set during creation)
        'config': True,  # Config tab is always available
        'tokens': True  # API tokens tab shows principals which we already track
    }
    
    # Check if any creative formats exist
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT COUNT(*) FROM creative_formats 
        WHERE tenant_id = ?
    """, (tenant_id,))
    format_count = cursor.fetchone()[0]
    tab_status['formats'] = format_count > 0
    conn.close()
    
    # Check overall setup completion
    setup_complete = (
        tab_status['adserver'] and 
        tab_status['principals'] and 
        tab_status['products'] and 
        tab_status['formats']
    )
    
    return render_template('tenant_detail.html', 
                         tenant=tenant, 
                         principals=principals,
                         products=products,
                         adapter_config=adapter_config,
                         admin_port=admin_port,
                         tab_status=tab_status,
                         setup_complete=setup_complete)

@app.route('/tenant/<tenant_id>/update', methods=['POST'])
@require_auth()
def update_tenant(tenant_id):
    """Update tenant configuration."""
    # Check access based on role
    if session.get('role') == 'viewer':
        return "Access denied. Viewers cannot update configuration.", 403
        
    # Check if user is trying to update another tenant
    if session.get('role') in ['admin', 'manager', 'tenant_admin'] and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only update your own tenant.", 403
    
    conn = get_db_connection()
    
    try:
        # Get form data for individual fields
        max_daily_budget = request.form.get('max_daily_budget', type=int)
        enable_aee_signals = request.form.get('enable_aee_signals') == 'true'
        human_review_required = request.form.get('human_review_required') == 'true'
        
        # Update individual fields
        conn.execute("""
            UPDATE tenants 
            SET max_daily_budget = ?, 
                enable_aee_signals = ?,
                human_review_required = ?,
                updated_at = ?
            WHERE tenant_id = ?
        """, (max_daily_budget, enable_aee_signals, human_review_required, 
              datetime.now().isoformat(), tenant_id))
        
        conn.connection.commit()
        flash('Configuration updated successfully', 'success')
        conn.close()
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        flash(f"Error updating configuration: {str(e)}", 'error')
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))

@app.route('/tenant/<tenant_id>/update_slack', methods=['POST'])
@require_auth()
def update_slack(tenant_id):
    """Update Slack webhook configuration."""
    # Check if tenant admin is trying to update another tenant
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    try:
        # Validate webhook URLs
        form_data = {
            'slack_webhook_url': request.form.get('slack_webhook_url', '').strip(),
            'slack_audit_webhook_url': request.form.get('slack_audit_webhook_url', '').strip()
        }
        
        # Sanitize form data
        form_data = sanitize_form_data(form_data)
        
        # Validate
        validators = {
            'slack_webhook_url': [FormValidator.validate_webhook_url],
            'slack_audit_webhook_url': [FormValidator.validate_webhook_url]
        }
        
        errors = validate_form_data(form_data, validators)
        if errors:
            for field, error in errors.items():
                flash(f"{field}: {error}", 'error')
            return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))
        
        conn = get_db_connection()
        
        slack_webhook = form_data['slack_webhook_url']
        audit_webhook = form_data['slack_audit_webhook_url']
        
        # Update both slack webhooks in their dedicated fields
        conn.execute("""
            UPDATE tenants 
            SET slack_webhook_url = ?, 
                slack_audit_webhook_url = ?,
                updated_at = ?
            WHERE tenant_id = ?
        """, (slack_webhook if slack_webhook else None, 
              audit_webhook if audit_webhook else None,
              datetime.now().isoformat(), tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        flash('Slack configuration updated successfully', 'success')
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/test_slack', methods=['POST'])
@require_auth()
def test_slack(tenant_id):
    """Test Slack webhook."""
    # Check if tenant admin is trying to test another tenant
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url')
        
        if not webhook_url:
            return jsonify({"success": False, "error": "No webhook URL provided"})
        
        # Send test message
        import requests
        from datetime import datetime
        
        test_message = {
            "text": f"🎉 Test message from AdCP Sales Agent",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Slack Integration Test Successful!"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"This is a test message from tenant *{tenant_id}*\n\nYour Slack integration is working correctly!"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(webhook_url, json=test_message, timeout=10)
        
        if response.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": f"Slack returned status {response.status_code}"})
            
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "Request timed out"})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": str(e)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/create_tenant', methods=['GET', 'POST'])
@require_auth(admin_only=True)
def create_tenant():
    """Create a new tenant (super admin only) - basic setup only."""
    if request.method == 'POST':
        try:
            tenant_name = request.form.get('name')
            tenant_id = request.form.get('tenant_id') or tenant_name.lower().replace(' ', '_')
            subdomain = request.form.get('subdomain') or tenant_id
            
            app.logger.info(f"Creating tenant: name={tenant_name}, id={tenant_id}, subdomain={subdomain}")
            
            # Parse authorization lists
            authorized_emails = [email.strip() for email in request.form.get('authorized_emails', '').split(',') if email.strip()]
            authorized_domains = [domain.strip() for domain in request.form.get('authorized_domains', '').split(',') if domain.strip()]
            
            # Build minimal config for unmigrated fields
            config = {
                "setup_complete": False  # Flag to track if tenant has completed setup
            }
            
            conn = get_db_connection()
            
            # Create tenant with new fields (config column removed)
            conn.execute("""
                INSERT INTO tenants (
                    tenant_id, name, subdomain,
                    created_at, updated_at, is_active,
                    ad_server, max_daily_budget, enable_aee_signals,
                    authorized_emails, authorized_domains,
                    auto_approve_formats, human_review_required,
                    admin_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                tenant_name,
                subdomain,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                True,
                None,  # ad_server - set during setup
                10000,  # max_daily_budget
                True,  # enable_aee_signals
                json.dumps(authorized_emails),  # authorized_emails
                json.dumps(authorized_domains),  # authorized_domains
                json.dumps([]),  # auto_approve_formats
                True,  # human_review_required
                config.get('admin_token', f'admin_{tenant_id}_{secrets.token_hex(16)}')  # admin_token
            ))
            
            app.logger.info(f"Tenant {tenant_id} inserted successfully")
            
            # Create admin principal with access token
            admin_token = secrets.token_urlsafe(32)
            conn.execute("""
                INSERT INTO principals (
                    tenant_id, principal_id, name,
                    platform_mappings, access_token
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                tenant_id,
                f"{tenant_id}_admin",
                f"{tenant_name} Admin",
                json.dumps({}),
                admin_token
            ))
            
            conn.commit()
            conn.close()
            
            flash(f'Tenant "{tenant_name}" created successfully! The publisher should log in and start with the Ad Server Setup tab to complete configuration.', 'success')
            return redirect(url_for('tenant_dashboard', tenant_id=tenant_id))
            
        except Exception as e:
            app.logger.error(f"Error creating tenant: {str(e)}")
            app.logger.error(traceback.format_exc())
            return render_template('create_tenant.html', error=str(e))
    
    return render_template('create_tenant.html')

# New Dashboard Routes (v2)
@app.route('/tenant/<tenant_id>')
@require_auth()
def tenant_dashboard(tenant_id):
    """Show new operational dashboard for tenant."""
    # Check access
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only view your own tenant.", 403
    
    conn = get_db_connection()
    
    # Get tenant basic info
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, is_active, ad_server
        FROM tenants WHERE tenant_id = ?
    """, (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1],
        'subdomain': row[2],
        'is_active': row[3],
        'ad_server': row[4]
    }
    
    # Get metrics
    metrics = {}
    
    # Total revenue (30 days) - using actual budget column
    cursor = conn.execute("""
        SELECT COALESCE(SUM(budget), 0) as total_revenue
        FROM media_buys 
        WHERE tenant_id = %s 
        AND status IN ('active', 'completed')
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    metrics['total_revenue'] = cursor.fetchone()[0] or 0
    
    # Revenue change vs previous period
    cursor = conn.execute("""
        SELECT COALESCE(SUM(budget), 0) as prev_revenue
        FROM media_buys 
        WHERE tenant_id = %s 
        AND status IN ('active', 'completed')
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '60 days'
        AND created_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    prev_revenue = cursor.fetchone()[0] or 0
    if prev_revenue > 0:
        metrics['revenue_change'] = ((metrics['total_revenue'] - prev_revenue) / prev_revenue) * 100
    else:
        metrics['revenue_change'] = 0
    
    # Add absolute value for display
    metrics['revenue_change_abs'] = abs(metrics['revenue_change'])
    
    # Active media buys
    cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = %s AND status = 'active'
    """, (tenant_id,))
    metrics['active_buys'] = cursor.fetchone()[0]
    
    # Pending media buys
    cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = %s AND status = 'pending'
    """, (tenant_id,))
    metrics['pending_buys'] = cursor.fetchone()[0]
    
    # Open tasks (using human_tasks table)
    cursor = conn.execute("""
        SELECT COUNT(*) FROM human_tasks 
        WHERE tenant_id = %s AND status IN ('pending', 'in_progress')
    """, (tenant_id,))
    metrics['open_tasks'] = cursor.fetchone()[0]
    
    # Overdue tasks (simplified - tasks older than 3 days)
    cursor = conn.execute("""
        SELECT COUNT(*) FROM human_tasks 
        WHERE tenant_id = %s 
        AND status IN ('pending', 'in_progress')
        AND created_at < CURRENT_TIMESTAMP - INTERVAL '3 days'
    """, (tenant_id,))
    metrics['overdue_tasks'] = cursor.fetchone()[0]
    
    # Active advertisers (principals with activity in last 30 days)
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT principal_id) 
        FROM media_buys 
        WHERE tenant_id = %s 
        AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    """, (tenant_id,))
    metrics['active_advertisers'] = cursor.fetchone()[0]
    
    # Total advertisers
    cursor = conn.execute("""
        SELECT COUNT(*) FROM principals WHERE tenant_id = %s
    """, (tenant_id,))
    metrics['total_advertisers'] = cursor.fetchone()[0]
    
    # Get recent media buys
    cursor = conn.execute("""
        SELECT 
            mb.media_buy_id,
            mb.principal_id,
            mb.advertiser_name,
            mb.status,
            mb.budget,
            0 as spend,  -- TODO: Calculate actual spend
            mb.created_at
        FROM media_buys mb
        WHERE mb.tenant_id = %s
        ORDER BY mb.created_at DESC
        LIMIT 10
    """, (tenant_id,))
    
    recent_media_buys = []
    for row in cursor.fetchall():
        # Calculate relative time
        created_at = datetime.fromisoformat(row[6].replace('Z', '+00:00')) if row[6] else datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - created_at
        
        if delta.days > 0:
            relative_time = f"{delta.days}d ago"
        elif delta.seconds > 3600:
            relative_time = f"{delta.seconds // 3600}h ago"
        else:
            relative_time = f"{delta.seconds // 60}m ago"
        
        recent_media_buys.append({
            'media_buy_id': row[0],
            'principal_id': row[1],
            'advertiser_name': row[2] or 'Unknown',
            'status': row[3],
            'budget': row[4],
            'spend': row[5],
            'created_at_relative': relative_time
        })
    
    # Get product count
    cursor = conn.execute("""
        SELECT COUNT(*) FROM products WHERE tenant_id = %s
    """, (tenant_id,))
    product_count = cursor.fetchone()[0]
    
    # Get pending tasks (using human_tasks table)
    cursor = conn.execute("""
        SELECT task_type, 
               CASE 
                   WHEN context_data::text != '' AND context_data IS NOT NULL
                   THEN (context_data::json->>'description')::text
                   ELSE task_type
               END as description
        FROM human_tasks 
        WHERE tenant_id = %s AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 5
    """, (tenant_id,))
    
    pending_tasks = []
    for row in cursor.fetchall():
        pending_tasks.append({
            'type': row[0],
            'description': row[1]
        })
    
    # Chart data for revenue by advertiser (last 7 days)
    cursor = conn.execute("""
        SELECT 
            mb.advertiser_name,
            SUM(mb.budget) as revenue
        FROM media_buys mb
        WHERE mb.tenant_id = %s
        AND mb.created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        AND mb.status IN ('active', 'completed')
        GROUP BY mb.advertiser_name
        ORDER BY revenue DESC
        LIMIT 10
    """, (tenant_id,))
    
    chart_labels = []
    chart_data = []
    for row in cursor.fetchall():
        chart_labels.append(row[0] or 'Unknown')
        chart_data.append(float(row[1]))
    
    conn.close()
    
    # Get admin port from environment
    admin_port = os.environ.get('ADMIN_UI_PORT', '8001')
    
    return render_template('tenant_dashboard_v2.html',
                         tenant=tenant,
                         metrics=metrics,
                         recent_media_buys=recent_media_buys,
                         product_count=product_count,
                         pending_tasks=pending_tasks,
                         chart_labels=chart_labels,
                         chart_data=chart_data,
                         admin_port=admin_port)

@app.route('/tenant/<tenant_id>/settings')
@app.route('/tenant/<tenant_id>/settings/<section>')
@require_auth()
def tenant_settings(tenant_id, section=None):
    """Show tenant settings page."""
    # Check access
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only view your own tenant.", 403
    
    conn = get_db_connection()
    
    # Get full tenant info
    cursor = conn.execute("""
        SELECT * FROM tenants WHERE tenant_id = ?
    """, (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    # Convert row to dict
    tenant = dict(zip([col[0] for col in cursor.description], row))
    
    # Parse JSON fields
    if tenant.get('authorized_emails'):
        tenant['authorized_emails'] = json.loads(tenant['authorized_emails']) if isinstance(tenant['authorized_emails'], str) else tenant['authorized_emails']
    if tenant.get('authorized_domains'):
        tenant['authorized_domains'] = json.loads(tenant['authorized_domains']) if isinstance(tenant['authorized_domains'], str) else tenant['authorized_domains']
    
    # Get adapter config if exists
    adapter_config = {}
    if tenant.get('ad_server'):
        # Parse adapter-specific config from tenant config
        try:
            config = json.loads(tenant.get('config', '{}')) if isinstance(tenant.get('config'), str) else tenant.get('config', {})
            adapter_config = config.get('adapters', {}).get(tenant['ad_server'], {})
        except:
            adapter_config = {}
    
    # Get counts
    cursor = conn.execute("SELECT COUNT(*) FROM products WHERE tenant_id = ?", (tenant_id,))
    product_count = cursor.fetchone()[0]
    
    # Products don't have is_active column - all products are considered active
    active_products = product_count
    draft_products = 0
    
    cursor = conn.execute("SELECT COUNT(*) FROM principals WHERE tenant_id = ?", (tenant_id,))
    advertiser_count = cursor.fetchone()[0]
    
    # Use PostgreSQL-compatible syntax (CURRENT_TIMESTAMP - INTERVAL)
    db_config = DatabaseConfig.get_db_config()
    if db_config['type'] == 'postgresql':
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT principal_id) 
            FROM media_buys 
            WHERE tenant_id = %s 
            AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """, (tenant_id,))
    else:
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT principal_id) 
            FROM media_buys 
            WHERE tenant_id = ? 
            AND created_at >= datetime('now', '-30 days')
        """, (tenant_id,))
    active_advertisers = cursor.fetchone()[0]
    
    # Get creative formats (handle boolean properly for PostgreSQL)
    if db_config['type'] == 'postgresql':
        cursor = conn.execute("""
            SELECT format_id, name, width, height,
                   CASE WHEN auto_approve = true THEN 1 ELSE 0 END as auto_approve
            FROM creative_formats 
            WHERE tenant_id = %s OR tenant_id IS NULL
            ORDER BY name
        """, (tenant_id,))
    else:
        cursor = conn.execute("""
            SELECT format_id, name, width, height,
                   CASE WHEN auto_approve = 1 THEN 1 ELSE 0 END as auto_approve
            FROM creative_formats 
            WHERE tenant_id = ? OR tenant_id IS NULL
            ORDER BY name
        """, (tenant_id,))
    
    creative_formats = []
    for row in cursor.fetchall():
        creative_formats.append({
            'id': row[0],
            'name': row[1],
            'dimensions': f"{row[2]}x{row[3]}" if row[2] and row[3] else 'Variable',
            'auto_approve': row[4]
        })
    
    # Format config as JSON for advanced editing
    try:
        config = json.loads(tenant.get('config', '{}')) if isinstance(tenant.get('config'), str) else tenant.get('config', {})
        tenant['config_json'] = json.dumps(config, indent=2)
    except:
        tenant['config_json'] = '{}'
    
    # Get last sync time if GAM
    last_sync_time = None
    if tenant.get('ad_server') == 'google_ad_manager':
        cursor = conn.execute("""
            SELECT MAX(sync_completed_at) 
            FROM gam_inventory_sync 
            WHERE tenant_id = ?
        """, (tenant_id,))
        sync_row = cursor.fetchone()
        if sync_row and sync_row[0]:
            last_sync = datetime.fromisoformat(sync_row[0].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - last_sync
            if delta.days > 0:
                last_sync_time = f"{delta.days} days ago"
            elif delta.seconds > 3600:
                last_sync_time = f"{delta.seconds // 3600} hours ago"
            else:
                last_sync_time = f"{delta.seconds // 60} minutes ago"
    
    conn.close()
    
    # Get admin port from environment
    admin_port = os.environ.get('ADMIN_UI_PORT', '8001')
    
    return render_template('tenant_settings.html',
                         tenant=tenant,
                         adapter_config=adapter_config,
                         product_count=product_count,
                         active_products=active_products,
                         draft_products=draft_products,
                         advertiser_count=advertiser_count,
                         active_advertisers=active_advertisers,
                         creative_formats=creative_formats,
                         last_sync_time=last_sync_time,
                         admin_port=admin_port,
                         section=section)

@app.route('/api/tenant/<tenant_id>/revenue-chart')
@require_auth()
def revenue_chart_api(tenant_id):
    """API endpoint for revenue chart data."""
    period = request.args.get('period', '7d')
    
    # Parse period
    if period == '7d':
        days = 7
    elif period == '30d':
        days = 30
    elif period == '90d':
        days = 90
    else:
        days = 7
    
    conn = get_db_connection()
    
    cursor = conn.execute("""
        SELECT 
            p.name,
            SUM(
                CASE 
                    WHEN mb.config IS NOT NULL AND json_extract(mb.config, '$.budget') IS NOT NULL 
                    THEN CAST(json_extract(mb.config, '$.budget') AS REAL)
                    ELSE 0
                END
            ) as revenue
        FROM media_buys mb
        LEFT JOIN principals p ON mb.principal_id = p.principal_id AND mb.tenant_id = p.tenant_id
        WHERE mb.tenant_id = ?
        AND mb.created_at >= datetime('now', '-' || ? || ' days')
        AND mb.status IN ('active', 'completed')
        GROUP BY p.name
        ORDER BY revenue DESC
        LIMIT 10
    """, (tenant_id, days))
    
    labels = []
    values = []
    for row in cursor.fetchall():
        labels.append(row[0] or 'Unknown')
        values.append(float(row[1]))
    
    conn.close()
    
    return jsonify({
        'labels': labels,
        'values': values
    })

# Settings form handlers
@app.route('/tenant/<tenant_id>/settings/general', methods=['POST'])
@require_auth()
def update_general_settings(tenant_id):
    """Update general tenant settings."""
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    conn = get_db_connection()
    
    # Update tenant
    conn.execute("""
        UPDATE tenants SET
            name = ?,
            max_daily_budget = ?,
            enable_aee_signals = ?,
            human_review_required = ?
        WHERE tenant_id = ?
    """, (
        request.form.get('name'),
        request.form.get('max_daily_budget', type=float),
        'enable_aee_signals' in request.form,
        'human_review_required' in request.form,
        tenant_id
    ))
    
    conn.commit()
    conn.close()
    
    flash('General settings updated successfully', 'success')
    return redirect(url_for('tenant_settings', tenant_id=tenant_id, section='general'))

@app.route('/tenant/<tenant_id>/settings/slack', methods=['POST'])
@require_auth()
def update_slack_settings(tenant_id):
    """Update Slack integration settings."""
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    conn = get_db_connection()
    
    conn.execute("""
        UPDATE tenants SET
            slack_webhook_url = ?,
            slack_audit_webhook_url = ?
        WHERE tenant_id = ?
    """, (
        request.form.get('slack_webhook_url'),
        request.form.get('slack_audit_webhook_url'),
        tenant_id
    ))
    
    conn.commit()
    conn.close()
    
    flash('Slack settings updated successfully', 'success')
    return redirect(url_for('tenant_settings', tenant_id=tenant_id, section='integrations'))

# Targeting Browser Route
@app.route('/tenant/<tenant_id>/targeting')
@require_auth()
def targeting_browser(tenant_id):
    """Display targeting browser page."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    cursor = conn.execute("SELECT tenant_id, name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1]
    }
    conn.close()
    
    return render_template('targeting_browser_simple.html', 
                         tenant=tenant,
                         tenant_id=tenant_id, 
                         tenant_name=row[1])

# Inventory Browser Route
@app.route('/tenant/<tenant_id>/inventory')
@require_auth()
def inventory_browser(tenant_id):
    """Display inventory browser page."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    cursor = conn.execute("SELECT tenant_id, name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1]
    }
    
    # Get inventory type from query param
    inventory_type = request.args.get('type', 'all')
    
    conn.close()
    
    return render_template('inventory_browser.html', 
                         tenant=tenant,
                         tenant_id=tenant_id, 
                         tenant_name=row[1],
                         inventory_type=inventory_type)

# Orders Browser Route
@app.route('/tenant/<tenant_id>/orders')
@require_auth()
def orders_browser(tenant_id):
    """Display GAM orders browser page."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    tenant_name = row[0]
    
    # Get API key for API calls
    cursor = conn.execute(
        "SELECT config_value FROM superadmin_config WHERE config_key = 'api_key'"
    )
    api_key_row = cursor.fetchone()
    api_key = api_key_row[0] if api_key_row else ''
    
    conn.close()
    
    return render_template('orders_browser.html', 
                         tenant_id=tenant_id, 
                         tenant_name=tenant_name,
                         api_key=api_key)

@app.route('/api/tenant/<tenant_id>/sync/orders', methods=['POST'])
@require_auth()
def sync_orders_endpoint(tenant_id):
    """Sync orders and line items from GAM - Session authenticated version."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get tenant and check if GAM is configured
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT ad_server FROM tenants WHERE tenant_id = ?",
            (tenant_id,)
        )
        tenant = cursor.fetchone()
        conn.close()
        
        if not tenant:
            return jsonify({'error': 'Tenant not found'}), 404
        
        if tenant['ad_server'] != 'google_ad_manager':
            return jsonify({'error': 'Only Google Ad Manager sync is supported'}), 400
        
        # Get GAM client
        from gam_helper import get_ad_manager_client_for_tenant
        gam_client = get_ad_manager_client_for_tenant(tenant_id)
        
        # Import and use the orders service
        from gam_orders_service import GAMOrdersService, db_session
        
        # Clean up any existing session
        db_session.remove()
        
        # Create service and perform sync
        service = GAMOrdersService(db_session)
        sync_summary = service.sync_tenant_orders(tenant_id, gam_client)
        
        # Commit changes
        db_session.commit()
        
        return jsonify({
            'status': 'completed',
            'summary': sync_summary,
            'message': f"Successfully synced {sync_summary.get('orders', {}).get('total', 0)} orders"
        })
        
    except Exception as e:
        logger.error(f"Error syncing orders for tenant {tenant_id}: {str(e)}")
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.remove()

# GAM Reporting Route
@app.route('/tenant/<tenant_id>/reporting')
@require_auth()
def gam_reporting_dashboard(tenant_id):
    """Display GAM reporting dashboard."""
    # Verify tenant access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    # Get tenant and check if it's using GAM
    conn = get_db_connection()
    tenant_cursor = conn.execute(
        "SELECT * FROM tenants WHERE tenant_id = ?",
        (tenant_id,)
    )
    tenant = tenant_cursor.fetchone()
    
    if not tenant:
        conn.close()
        return "Tenant not found", 404
    
    # Check if tenant is using Google Ad Manager
    if tenant.get('ad_server') != 'google_ad_manager':
        conn.close()
        return render_template('error.html', 
            error_title="GAM Reporting Not Available",
            error_message=f"This tenant is currently using {tenant.get('ad_server', 'no ad server')}. GAM Reporting is only available for tenants using Google Ad Manager.",
            back_url=f"/tenant/{tenant_id}"
        ), 400
    
    conn.close()
    return render_template('gam_reporting.html', tenant=tenant)

# Sync Status API for Admin UI
@app.route('/api/tenant/<tenant_id>/sync/status')
@require_auth()
def get_tenant_sync_status(tenant_id):
    """Get sync status for a tenant."""
    # Verify tenant access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({'error': 'Access denied'}), 403
    
    conn = get_db_connection()
    
    # Check if tenant exists and uses GAM
    tenant_cursor = conn.execute(
        "SELECT ad_server FROM tenants WHERE tenant_id = ?",
        (tenant_id,)
    )
    tenant = tenant_cursor.fetchone()
    
    if not tenant:
        conn.close()
        return jsonify({'error': 'Tenant not found'}), 404
    
    if tenant.get('ad_server') != 'google_ad_manager':
        conn.close()
        return jsonify({'error': 'Sync only available for GAM tenants'}), 400
    
    # Get latest sync job
    sync_cursor = conn.execute("""
        SELECT started_at, status, summary 
        FROM sync_jobs 
        WHERE tenant_id = ? 
        ORDER BY started_at DESC 
        LIMIT 1
    """, (tenant_id,))
    sync_job = sync_cursor.fetchone()
    
    # Get inventory counts
    inventory_cursor = conn.execute("""
        SELECT 
            COUNT(CASE WHEN inventory_type = 'ad_unit' THEN 1 END) as ad_units,
            COUNT(CASE WHEN inventory_type = 'custom_targeting_key' THEN 1 END) as custom_targeting_keys,
            COUNT(CASE WHEN inventory_type = 'custom_targeting_value' THEN 1 END) as custom_targeting_values,
            COUNT(*) as total
        FROM gam_inventory 
        WHERE tenant_id = ?
    """, (tenant_id,))
    counts = inventory_cursor.fetchone()
    
    conn.close()
    
    response = {
        'last_sync': None,
        'sync_running': False,
        'item_count': counts['total'] if counts else 0,
        'breakdown': None
    }
    
    if sync_job:
        response['last_sync'] = sync_job['started_at']
        response['sync_running'] = sync_job['status'] == 'running'
        
        if counts and counts['total'] > 0:
            response['breakdown'] = {
                'ad_units': counts['ad_units'],
                'custom_targeting_keys': counts['custom_targeting_keys'],
                'custom_targeting_values': counts['custom_targeting_values']
            }
    
    return jsonify(response)

# Trigger Sync API for Admin UI
@app.route('/api/tenant/<tenant_id>/sync/trigger', methods=['POST'])
@require_auth()
def trigger_tenant_sync(tenant_id):
    """Trigger a sync for a GAM tenant."""
    # Verify tenant access  
    if session.get('role') != 'super_admin':
        return jsonify({'error': 'Only super admins can trigger sync'}), 403
    
    conn = get_db_connection()
    
    # Check if tenant exists and uses GAM
    tenant_cursor = conn.execute(
        "SELECT ad_server FROM tenants WHERE tenant_id = ?",
        (tenant_id,)
    )
    tenant = tenant_cursor.fetchone()
    
    if not tenant:
        conn.close()
        return jsonify({'error': 'Tenant not found'}), 404
    
    if tenant.get('ad_server') != 'google_ad_manager':
        conn.close()
        return jsonify({'error': 'Sync only available for GAM tenants'}), 400
    
    try:
        # Create a new sync job
        import uuid
        from datetime import datetime
        
        sync_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO sync_jobs (sync_id, tenant_id, adapter_type, sync_type, status, started_at, triggered_by)
            VALUES (?, ?, 'google_ad_manager', 'manual', 'pending', ?, 'admin_ui')
        """, (sync_id, tenant_id, datetime.utcnow()))
        conn.commit()
        
        # Note: In a real implementation, this would trigger an async job
        # For now, we'll just mark it as pending and let the background worker handle it
        
        conn.close()
        return jsonify({
            'success': True,
            'sync_id': sync_id,
            'message': 'Sync job queued successfully'
        })
        
    except Exception as e:
        conn.close()
        logger.error(f"Error triggering sync for tenant {tenant_id}: {str(e)}")
        return jsonify({'error': 'Failed to trigger sync', 'details': str(e)}), 500

@app.route('/api/tenant/<tenant_id>/orders', methods=['GET'])
@require_auth()
def get_tenant_orders_session(tenant_id):
    """Get orders for a tenant - Session authenticated version."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from gam_orders_service import GAMOrdersService, db_session
        from models import GAMOrder, GAMLineItem
        from sqlalchemy import func
        
        # Remove any existing session to start fresh
        try:
            db_session.remove()
        except Exception:
            pass  # Session might not exist yet
        
        # Get query parameters
        search = request.args.get('search')
        status = request.args.get('status')
        advertiser_id = request.args.get('advertiser_id')
        has_line_items = request.args.get('has_line_items')
        
        # Query orders from database
        query = db_session.query(GAMOrder).filter(GAMOrder.tenant_id == tenant_id)
        
        if search:
            query = query.filter(
                (GAMOrder.name.ilike(f'%{search}%')) |
                (GAMOrder.order_id.ilike(f'%{search}%'))
            )
        
        if status:
            query = query.filter(GAMOrder.status == status)
        
        if advertiser_id:
            query = query.filter(GAMOrder.advertiser_id == advertiser_id)
        
        # Filter by has_line_items using exists subquery
        if has_line_items == 'true':
            query = query.filter(
                db_session.query(GAMLineItem).filter(
                    GAMLineItem.tenant_id == tenant_id,
                    GAMLineItem.order_id == GAMOrder.order_id
                ).exists()
            )
        elif has_line_items == 'false':
            query = query.filter(
                ~db_session.query(GAMLineItem).filter(
                    GAMLineItem.tenant_id == tenant_id,
                    GAMLineItem.order_id == GAMOrder.order_id
                ).exists()
            )
        
        # Order by last modified
        query = query.order_by(GAMOrder.last_modified_date.desc())
        
        orders = query.all()
        
        # Get line item counts and stats for all orders in one query
        line_item_stats = db_session.query(
            GAMLineItem.order_id,
            func.count(GAMLineItem.id).label('count'),
            func.sum(GAMLineItem.stats_impressions).label('total_impressions'),
            func.sum(GAMLineItem.stats_clicks).label('total_clicks')
        ).filter(
            GAMLineItem.tenant_id == tenant_id,
            GAMLineItem.order_id.in_([o.order_id for o in orders]) if orders else []
        ).group_by(GAMLineItem.order_id).all()
        
        # Convert to dict for easy lookup
        stats_dict = {
            row.order_id: {
                'count': row.count,
                'impressions': row.total_impressions or 0,
                'clicks': row.total_clicks or 0
            }
            for row in line_item_stats
        }
        
        # Convert to dict
        result = {
            'orders': [
                {
                    'order_id': o.order_id,
                    'name': o.name,
                    'advertiser_id': o.advertiser_id,
                    'advertiser_name': o.advertiser_name,
                    'status': o.status,
                    'start_date': o.start_date.isoformat() if o.start_date else None,
                    'end_date': o.end_date.isoformat() if o.end_date else None,
                    'line_item_count': stats_dict.get(o.order_id, {}).get('count', 0),
                    'total_impressions_delivered': stats_dict.get(o.order_id, {}).get('impressions', 0),
                    'total_clicks_delivered': stats_dict.get(o.order_id, {}).get('clicks', 0),
                    'last_modified_date': o.last_modified_date.isoformat() if o.last_modified_date else None
                }
                for o in orders
            ],
            'total': len(orders)
        }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error fetching orders: {str(e)}")
        try:
            db_session.rollback()
        except Exception:
            pass  # Session might be in invalid state
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            db_session.remove()
        except Exception:
            pass  # Ensure cleanup doesn't fail

@app.route('/api/tenant/<tenant_id>/orders/<order_id>', methods=['GET'])
@require_auth()
def get_order_details_session(tenant_id, order_id):
    """Get order details - Session authenticated version."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from gam_orders_service import GAMOrdersService, db_session
        from models import GAMOrder, GAMLineItem
        
        db_session.remove()
        
        # Get order
        order = db_session.query(GAMOrder).filter(
            GAMOrder.tenant_id == tenant_id,
            GAMOrder.order_id == order_id
        ).first()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        # Get line items
        line_items = db_session.query(GAMLineItem).filter(
            GAMLineItem.tenant_id == tenant_id,
            GAMLineItem.order_id == order_id
        ).all()
        
        # Calculate delivery metrics
        total_impressions_delivered = sum(li.stats_impressions or 0 for li in line_items)
        total_impressions_goal = sum(li.primary_goal_units or 0 for li in line_items if li.primary_goal_type == 'IMPRESSIONS')
        total_clicks_goal = sum(li.primary_goal_units or 0 for li in line_items if li.primary_goal_type == 'CLICKS')
        
        result = {
            'order': {
                'order_id': order.order_id,
                'name': order.name,
                'advertiser_id': order.advertiser_id,
                'advertiser_name': order.advertiser_name,
                'agency_id': order.agency_id,
                'agency_name': order.agency_name,
                'trafficker_id': order.trafficker_id,
                'trafficker_name': order.trafficker_name,
                'salesperson_id': order.salesperson_id,
                'salesperson_name': order.salesperson_name,
                'status': order.status,
                'start_date': order.start_date.isoformat() if order.start_date else None,
                'end_date': order.end_date.isoformat() if order.end_date else None,
                'unlimited_end_date': order.unlimited_end_date,
                'total_budget': order.total_budget,
                'currency_code': order.currency_code or 'USD',
                'external_order_id': order.external_order_id,
                'po_number': order.po_number,
                'notes': order.notes,
                'last_modified_date': order.last_modified_date.isoformat() if order.last_modified_date else None,
                'total_impressions_delivered': total_impressions_delivered,
                'total_clicks_delivered': sum(li.stats_clicks or 0 for li in line_items),
                'delivery_metrics': {
                    'total_impressions_delivered': total_impressions_delivered,
                    'total_impressions_goal': total_impressions_goal,
                    'total_clicks_delivered': sum(li.stats_clicks or 0 for li in line_items),
                    'total_clicks_goal': total_clicks_goal,
                },
            },
            'line_items': [
                {
                    'line_item_id': li.line_item_id,
                    'name': li.name,
                    'status': li.status,
                    'line_item_type': li.line_item_type,
                    'priority': li.priority,
                    'primary_goal_type': li.primary_goal_type,
                    'primary_goal_units': li.primary_goal_units,
                    'stats_impressions': li.stats_impressions or 0,
                    'stats_clicks': li.stats_clicks or 0,
                    'impressions_delivered': li.stats_impressions or 0,  # Keep for backward compatibility
                    'clicks_delivered': li.stats_clicks or 0,  # Keep for backward compatibility
                    'cost_per_unit': float(li.cost_per_unit) / 1000000 if li.cost_per_unit else None,  # Convert from micros to dollars
                    'delivery_percentage': (li.stats_impressions / li.primary_goal_units * 100) if li.primary_goal_units and li.primary_goal_units > 0 else 0,
                    'start_date': li.start_date.isoformat() if li.start_date else None,
                    'end_date': li.end_date.isoformat() if li.end_date else None,
                }
                for li in line_items
            ]
        }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error fetching order details: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.remove()

# Workflows Dashboard Route
@app.route('/tenant/<tenant_id>/workflows')
@require_auth()
def workflows_dashboard(tenant_id):
    """Display workflows dashboard with media buys, workflow steps, and audit logs."""
    # Verify tenant access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    # Get tenant
    conn = get_db_connection()
    tenant_cursor = conn.execute(
        "SELECT * FROM tenants WHERE tenant_id = ?", 
        (tenant_id,)
    )
    tenant_row = tenant_cursor.fetchone()
    
    if not tenant_row:
        conn.close()
        return "Tenant not found", 404
    
    # PostgreSQL returns JSONB as dict, SQLite as string
    config = tenant_row[3]
    if isinstance(config, str):
        config = json.loads(config)
    
    tenant = {
        'tenant_id': tenant_row[0],
        'name': tenant_row[1],
        'subdomain': tenant_row[2],
        'config': config,
        'created_at': tenant_row[4],
        'updated_at': tenant_row[5],
        'is_active': tenant_row[6]
    }
    
    # Get summary statistics
    from datetime import datetime, timedelta
    today = datetime.now().date()
    
    # Active media buys count
    active_buys_cursor = conn.execute("""
        SELECT COUNT(*) FROM media_buys 
        WHERE tenant_id = ? AND status = 'active'
    """, (tenant_id,))
    active_buys = active_buys_cursor.fetchone()[0]
    
    # Pending tasks count
    pending_tasks_cursor = conn.execute("""
        SELECT COUNT(*) FROM tasks 
        WHERE tenant_id = ? AND status = 'pending'
    """, (tenant_id,))
    pending_tasks = pending_tasks_cursor.fetchone()[0]
    
    # Completed today count
    completed_today_cursor = conn.execute("""
        SELECT COUNT(*) FROM tasks 
        WHERE tenant_id = ? AND status = 'completed' 
        AND DATE(completed_at) = DATE(?)
    """, (tenant_id, today.isoformat()))
    completed_today = completed_today_cursor.fetchone()[0]
    
    # Total active spend
    total_spend_cursor = conn.execute("""
        SELECT SUM(budget) FROM media_buys 
        WHERE tenant_id = ? AND status = 'active'
    """, (tenant_id,))
    total_spend = total_spend_cursor.fetchone()[0] or 0
    
    summary = {
        'active_buys': active_buys,
        'pending_tasks': pending_tasks,
        'completed_today': completed_today,
        'total_spend': total_spend
    }
    
    # Get media buys
    media_buys_cursor = conn.execute("""
        SELECT * FROM media_buys 
        WHERE tenant_id = ? 
        ORDER BY created_at DESC 
        LIMIT 100
    """, (tenant_id,))
    
    media_buys = []
    for row in media_buys_cursor:
        # Handle datetime fields - PostgreSQL returns datetime objects, SQLite returns strings
        created_at = row[11]
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        updated_at = row[12]
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        
        approved_at = row[13]
        if approved_at and isinstance(approved_at, str):
            approved_at = datetime.fromisoformat(approved_at)
        
        media_buys.append({
            'media_buy_id': row[0],
            'tenant_id': row[1],
            'principal_id': row[2],
            'order_name': row[3],
            'advertiser_name': row[4],
            'campaign_objective': row[5],
            'kpi_goal': row[6],
            'budget': row[7],
            'start_date': row[8],
            'end_date': row[9],
            'status': row[10],
            'created_at': created_at,
            'updated_at': updated_at,
            'approved_at': approved_at,
            'approved_by': row[14]
        })
    
    # Get tasks
    tasks_cursor = conn.execute("""
        SELECT * FROM tasks 
        WHERE tenant_id = ? 
        ORDER BY created_at DESC 
        LIMIT 100
    """, (tenant_id,))
    
    tasks = []
    for row in tasks_cursor:
        # Handle datetime fields - PostgreSQL returns datetime objects, SQLite returns strings
        due_date = row[8]
        if due_date and isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date)
        
        completed_at = row[9]
        if completed_at and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        
        created_at = row[12]
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        is_overdue = False
        if due_date and row[6] == 'pending':
            is_overdue = due_date < datetime.now()
        
        # Handle metadata - PostgreSQL returns dict, SQLite returns string
        metadata = row[11]
        if metadata and isinstance(metadata, str):
            metadata = json.loads(metadata)
        elif not metadata:
            metadata = {}
            
        tasks.append({
            'task_id': row[0],
            'tenant_id': row[1],
            'media_buy_id': row[2],
            'task_type': row[3],
            'title': row[4],
            'description': row[5],
            'status': row[6],
            'assigned_to': row[7],
            'due_date': due_date,
            'completed_at': completed_at,
            'completed_by': row[10],
            'metadata': metadata,
            'created_at': created_at,
            'is_overdue': is_overdue
        })
    
    # Get audit logs
    audit_logs_cursor = conn.execute("""
        SELECT * FROM audit_logs 
        WHERE tenant_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 100
    """, (tenant_id,))
    
    audit_logs = []
    for row in audit_logs_cursor:
        # Handle datetime fields - PostgreSQL returns datetime objects, SQLite returns strings
        timestamp = row[2]
        if timestamp and isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        
        audit_logs.append({
            'log_id': row[0],
            'tenant_id': row[1],
            'timestamp': timestamp,
            'operation': row[3],
            'principal_name': row[4],
            'principal_id': row[5],
            'adapter_id': row[6],
            'success': row[7],
            'error_message': row[8],
            'details': row[9]
        })
    
    conn.close()
    
    return render_template('workflows.html', 
                         tenant=tenant,
                         summary=summary,
                         media_buys=media_buys,
                         tasks=tasks,
                         audit_logs=audit_logs)

@app.route('/tenant/<tenant_id>/media-buy/<media_buy_id>/approve')
@require_auth()
def media_buy_approval(tenant_id, media_buy_id):
    """Display media buy approval page with details and dry-run preview."""
    # Verify tenant access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    # Get the media buy details
    buy_cursor = conn.execute("""
        SELECT * FROM media_buys 
        WHERE tenant_id = ? AND media_buy_id = ?
    """, (tenant_id, media_buy_id))
    
    buy_row = buy_cursor.fetchone()
    if not buy_row:
        conn.close()
        return "Media buy not found", 404
    
    # Parse the media buy
    media_buy = {
        'media_buy_id': buy_row[0],
        'tenant_id': buy_row[1],
        'principal_id': buy_row[2],
        'order_name': buy_row[3],
        'advertiser_name': buy_row[4],
        'campaign_objective': buy_row[5],
        'kpi_goal': buy_row[6],
        'budget': buy_row[7],
        'start_date': buy_row[8],
        'end_date': buy_row[9],
        'status': buy_row[10],
        'created_at': buy_row[11] if not isinstance(buy_row[11], str) else datetime.fromisoformat(buy_row[11]),
        'raw_request': json.loads(buy_row[15]) if buy_row[15] and isinstance(buy_row[15], str) else buy_row[15],
        'context_id': buy_row[16] if len(buy_row) > 16 else None
    }
    
    # Get associated human task if exists
    task_cursor = conn.execute("""
        SELECT * FROM human_tasks 
        WHERE media_buy_id = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    """, (media_buy_id,))
    
    task_row = task_cursor.fetchone()
    human_task = None
    if task_row:
        context_data = task_row[8]
        if context_data and isinstance(context_data, str):
            context_data = json.loads(context_data)
        
        human_task = {
            'task_id': task_row[0],
            'task_type': task_row[3],
            'priority': task_row[4],
            'status': task_row[5],
            'operation': task_row[6],
            'error_detail': task_row[7],
            'context_data': context_data or {}
        }
    
    # Get the principal details for adapter info
    principal_cursor = conn.execute("""
        SELECT * FROM principals 
        WHERE tenant_id = ? AND principal_id = ?
    """, (tenant_id, media_buy['principal_id']))
    
    principal_row = principal_cursor.fetchone()
    principal = None
    if principal_row:
        platform_mappings = principal_row[3]
        if isinstance(platform_mappings, str):
            platform_mappings = json.loads(platform_mappings)
        
        principal = {
            'principal_id': principal_row[0],
            'name': principal_row[2],
            'platform_mappings': platform_mappings
        }
    
    # Get the products in this media buy
    products = []
    if media_buy['raw_request'] and 'product_ids' in media_buy['raw_request']:
        product_ids = media_buy['raw_request']['product_ids']
        for product_id in product_ids:
            prod_cursor = conn.execute("""
                SELECT * FROM products 
                WHERE tenant_id = ? AND product_id = ?
            """, (tenant_id, product_id))
            prod_row = prod_cursor.fetchone()
            if prod_row:
                formats = prod_row[3]
                # Debug logging
                app.logger.info(f"Product {product_id} formats value: {formats!r}, type: {type(formats)}")
                
                if formats and isinstance(formats, str) and formats.strip():
                    try:
                        formats = json.loads(formats)
                    except json.JSONDecodeError as e:
                        app.logger.error(f"Failed to parse formats for {product_id}: {e}")
                        formats = []
                elif not formats or (isinstance(formats, str) and not formats.strip()):
                    formats = []
                
                targeting_template = prod_row[4]
                if targeting_template and isinstance(targeting_template, str) and targeting_template.strip():
                    try:
                        targeting_template = json.loads(targeting_template)
                    except json.JSONDecodeError as e:
                        app.logger.error(f"Failed to parse targeting_template for {product_id}: {e}")
                        targeting_template = {}
                elif not targeting_template or (isinstance(targeting_template, str) and not targeting_template.strip()):
                    targeting_template = {}
                
                implementation_config = prod_row[11] if len(prod_row) > 11 else None
                if implementation_config and isinstance(implementation_config, str) and implementation_config.strip():
                    try:
                        implementation_config = json.loads(implementation_config)
                    except json.JSONDecodeError as e:
                        app.logger.error(f"Failed to parse implementation_config for {product_id}: {e}")
                        implementation_config = {}
                elif not implementation_config or (isinstance(implementation_config, str) and not implementation_config.strip()):
                    implementation_config = {}
                
                products.append({
                    'product_id': prod_row[0],
                    'name': prod_row[2],
                    'formats': formats,
                    'targeting_template': targeting_template,
                    'pricing_model': prod_row[5],
                    'base_price': prod_row[6],
                    'min_spend': prod_row[7],
                    'implementation_config': implementation_config
                })
    
    # Prepare dry-run preview (simulate what would happen in GAM)
    dry_run_preview = generate_dry_run_preview(
        media_buy, 
        products, 
        principal,
        human_task
    )
    
    conn.close()
    
    return render_template('media_buy_approval.html',
                         tenant_id=tenant_id,
                         media_buy=media_buy,
                         human_task=human_task,
                         principal=principal,
                         products=products,
                         dry_run_preview=dry_run_preview)

def generate_dry_run_preview(media_buy, products, principal, human_task):
    """Generate a dry-run preview of what would be created in GAM."""
    preview = {
        'order': {
            'name': media_buy['order_name'],
            'advertiser': media_buy['advertiser_name'],
            'budget': media_buy['budget'],
            'start_date': str(media_buy['start_date']),
            'end_date': str(media_buy['end_date'])
        },
        'line_items': []
    }
    
    # Generate preview line items for each product
    for product in products:
        line_item = {
            'name': f"{product['name']} - {media_buy['media_buy_id']}",
            'product_id': product['product_id'],
            'formats': product.get('formats', []),
            'targeting': product.get('targeting_template', {}),
            'pricing_model': product.get('pricing_model', 'CPM'),
            'base_price': product.get('base_price', 0),
            'implementation_notes': []
        }
        
        # Add implementation config details
        if product.get('implementation_config'):
            config = product['implementation_config']
            if 'ad_unit_ids' in config:
                line_item['implementation_notes'].append(
                    f"Will target {len(config['ad_unit_ids'])} ad units"
                )
            if 'placement_ids' in config:
                line_item['implementation_notes'].append(
                    f"Will use {len(config['placement_ids'])} placements"
                )
            if 'custom_targeting' in config:
                line_item['implementation_notes'].append(
                    "Custom targeting will be applied"
                )
        
        preview['line_items'].append(line_item)
    
    # Add any targeting overlay from the request
    if media_buy.get('raw_request') and media_buy['raw_request'].get('targeting_overlay'):
        preview['targeting_overlay'] = media_buy['raw_request']['targeting_overlay']
    
    return preview

# User Management Routes
@app.route('/tenant/<tenant_id>/users')
@require_auth()
def list_users(tenant_id):
    """List users for a tenant."""
    # Check access
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT u.user_id, u.email, u.name, u.role, u.created_at, u.last_login, u.is_active
        FROM users u
        WHERE u.tenant_id = ?
        ORDER BY u.created_at DESC
    """, (tenant_id,))
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'user_id': row[0],
            'email': row[1],
            'name': row[2],
            'role': row[3],
            'created_at': row[4],
            'last_login': row[5],
            'is_active': row[6]
        })
    
    # Get tenant name
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant_name = cursor.fetchone()[0]
    
    conn.close()
    return render_template('users.html', users=users, tenant_id=tenant_id, tenant_name=tenant_name)

@app.route('/tenant/<tenant_id>/users/add', methods=['POST'])
@require_auth()
def add_user(tenant_id):
    """Add a new user to a tenant."""
    # Check access - only admins can add users
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    try:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        email = request.form.get('email')
        name = request.form.get('name')
        role = request.form.get('role', 'viewer')
        
        # Validate role
        if role not in ['admin', 'manager', 'viewer']:
            return "Invalid role", 400
        
        # Check if email already exists
        cursor = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return "User with this email already exists", 400
        
        # Use proper boolean value for PostgreSQL
        conn.execute("""
            INSERT INTO users (user_id, tenant_id, email, name, role, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, tenant_id, email, name, role, datetime.now().isoformat(), True))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('list_users', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/users/<user_id>/toggle', methods=['POST'])
@require_auth()
def toggle_user(tenant_id, user_id):
    """Enable/disable a user."""
    # Check access - only admins can toggle users
    if session.get('role') != 'super_admin':
        if session.get('role') != 'tenant_admin' or session.get('tenant_id') != tenant_id:
            return "Access denied", 403
    
    conn = get_db_connection()
    try:
        # Toggle the is_active status
        conn.execute("""
            UPDATE users 
            SET is_active = NOT is_active
            WHERE user_id = ? AND tenant_id = ?
        """, (user_id, tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('list_users', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/users/<user_id>/update_role', methods=['POST'])
@require_auth()
def update_user_role(tenant_id, user_id):
    """Update a user's role."""
    # Check access - only admins can update roles
    if session.get('role') != 'super_admin':
        if session.get('role') != 'tenant_admin' or session.get('tenant_id') != tenant_id:
            return "Access denied", 403
    
    conn = get_db_connection()
    try:
        new_role = request.form.get('role')
        
        # Validate role
        if new_role not in ['admin', 'manager', 'viewer']:
            return "Invalid role", 400
        
        conn.execute("""
            UPDATE users 
            SET role = ?
            WHERE user_id = ? AND tenant_id = ?
        """, (new_role, user_id, tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('list_users', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/principal/<principal_id>/update_mappings', methods=['POST'])
@require_auth()
def update_principal_mappings(tenant_id, principal_id):
    """Update principal platform mappings."""
    # Check access - only admins and managers can update mappings
    if session.get('role') == 'viewer':
        return "Access denied", 403
        
    if session.get('role') in ['admin', 'manager', 'tenant_admin'] and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    try:
        # Get the form data for platform mappings
        mappings = {}
        
        # Check for common ad server mappings
        if request.form.get('gam_advertiser_id'):
            mappings['gam'] = {
                'advertiser_id': request.form.get('gam_advertiser_id'),
                'network_id': request.form.get('gam_network_id', '')
            }
        
        if request.form.get('kevel_advertiser_id'):
            mappings['kevel'] = {
                'advertiser_id': request.form.get('kevel_advertiser_id')
            }
            
        if request.form.get('triton_advertiser_id'):
            mappings['triton'] = {
                'advertiser_id': request.form.get('triton_advertiser_id')
            }
        
        # Update the principal
        conn.execute("""
            UPDATE principals 
            SET platform_mappings = ?
            WHERE tenant_id = ? AND principal_id = ?
        """, (json.dumps(mappings), tenant_id, principal_id))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id) + '#principals')
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/adapter/<adapter_name>/inventory_schema', methods=['GET'])
@require_auth()
def get_adapter_inventory_schema(tenant_id, adapter_name):
    """Get the inventory configuration schema for a specific adapter."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        # Get tenant config to instantiate adapter
        conn = get_db_connection()
        config_data = get_tenant_config_from_db(conn, tenant_id)
        if not config_data:
            return jsonify({"error": "Tenant not found"}), 404
        # PostgreSQL returns JSONB as dict, SQLite returns string
        tenant_config = config_data if isinstance(config_data, dict) else json.loads(config_data)
        adapter_config = tenant_config.get('adapters', {}).get(adapter_name, {})
        
        if not adapter_config.get('enabled'):
            return jsonify({"error": f"Adapter {adapter_name} is not enabled"}), 400
        
        # Create a dummy principal for schema retrieval
        dummy_principal = Principal(
            tenant_id=tenant_id,
            principal_id="schema_query",
            name="Schema Query",
            access_token="",
            platform_mappings={}
        )
        
        # Import the adapter dynamically
        if adapter_name == 'google_ad_manager':
            from adapters.google_ad_manager import GoogleAdManager
            adapter = GoogleAdManager(adapter_config, dummy_principal, dry_run=True, tenant_id=tenant_id)
        elif adapter_name == 'mock':
            from adapters.mock_ad_server import MockAdServer
            adapter = MockAdServer(adapter_config, dummy_principal, dry_run=True, tenant_id=tenant_id)
        elif adapter_name == 'kevel':
            from adapters.kevel import KevelAdapter
            adapter = KevelAdapter(adapter_config, dummy_principal, dry_run=True, tenant_id=tenant_id)
        elif adapter_name == 'triton':
            from adapters.triton_digital import TritonDigitalAdapter
            adapter = TritonDigitalAdapter(adapter_config, dummy_principal, dry_run=True, tenant_id=tenant_id)
        else:
            return jsonify({"error": f"Unknown adapter: {adapter_name}"}), 400
        
        # Get the inventory schema
        schema = adapter.get_inventory_config_schema()
        
        conn.close()
        return jsonify(schema)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/setup_adapter', methods=['POST'])
@require_auth()
def setup_adapter(tenant_id):
    """Setup or update ad server adapter configuration."""
    # Check access - only admins can setup adapters
    if session.get('role') in ['viewer', 'manager']:
        return "Access denied. Admin privileges required.", 403
        
    if session.get('role') in ['admin', 'tenant_admin'] and session.get('tenant_id') != tenant_id:
        return "Access denied.", 403
    
    conn = get_db_connection()
    try:
        # Get adapter type
        adapter_type = request.form.get('adapter')
        adapter_type_map = {
            'mock': 'mock',
            'gam': 'google_ad_manager',
            'kevel': 'kevel', 
            'triton': 'triton'
        }
        
        if adapter_type not in adapter_type_map:
            return "Invalid adapter type", 400
        
        mapped_adapter = adapter_type_map[adapter_type]
        
        # Update tenant's ad_server field
        conn.execute("""
            UPDATE tenants 
            SET ad_server = ?, updated_at = ?
            WHERE tenant_id = ?
        """, (mapped_adapter, datetime.now().isoformat(), tenant_id))
        
        # Delete any existing adapter config
        conn.execute("""
            DELETE FROM adapter_config WHERE tenant_id = ?
        """, (tenant_id,))
        
        # Insert new adapter configuration
        if adapter_type == 'mock':
            conn.execute("""
                INSERT INTO adapter_config (tenant_id, adapter_type, mock_dry_run)
                VALUES (?, ?, ?)
            """, (tenant_id, mapped_adapter, False))
        
        elif adapter_type == 'gam':
            # Log the form data for debugging
            app.logger.info(f"GAM setup for tenant {tenant_id}")
            app.logger.info(f"Form data: network_code={request.form.get('network_code')}, "
                          f"trafficker_id={request.form.get('trafficker_id')}")
            
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, gam_network_code, gam_refresh_token,
                    gam_company_id, gam_trafficker_id, gam_manual_approval_required
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tenant_id, mapped_adapter, 
                  request.form.get('network_code'),
                  request.form.get('refresh_token'),
                  None,  # company_id is now per-principal, not per-tenant
                  request.form.get('trafficker_id'),
                  False))
        
        elif adapter_type == 'kevel':
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, kevel_network_id, kevel_api_key, 
                    kevel_manual_approval_required
                )
                VALUES (?, ?, ?, ?, ?)
            """, (tenant_id, mapped_adapter,
                  request.form.get('network_id'),
                  request.form.get('api_key'),
                  False))
        
        elif adapter_type == 'triton':
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, triton_station_id, triton_api_key
                )
                VALUES (?, ?, ?, ?)
            """, (tenant_id, mapped_adapter,
                  request.form.get('station_id'),
                  request.form.get('api_key')))
        
        conn.connection.commit()
        conn.close()
        
        flash('Ad server configuration updated successfully!', 'success')
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id) + '#adserver')
    except Exception as e:
        conn.close()
        flash(f'Error updating adapter configuration: {str(e)}', 'error')
        return redirect(url_for('tenant_dashboard', tenant_id=tenant_id) + '#adserver')

@app.route('/tenant/<tenant_id>/principals/create', methods=['GET', 'POST'])
@require_auth()
def create_principal(tenant_id):
    """Create a new principal for a tenant."""
    # Check access - only admins can create principals
    if session.get('role') in ['viewer']:
        return "Access denied. Admin or manager privileges required.", 403
        
    if session.get('role') in ['admin', 'manager', 'tenant_admin'] and session.get('tenant_id') != tenant_id:
        return "Access denied.", 403
    
    # Check if tenant has GAM configured
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT adapter_type 
        FROM adapter_config 
        WHERE tenant_id = ?
    """, (tenant_id,))
    adapter_row = cursor.fetchone()
    has_gam = adapter_row and adapter_row[0] == 'google_ad_manager'
    conn.close()
    
    if request.method == 'POST':
        # Validate form data
        form_data = {
            'principal_id': request.form.get('principal_id', '').strip(),
            'name': request.form.get('name', '').strip(),
            'gam_advertiser_id': request.form.get('gam_advertiser_id', '').strip() if has_gam else None
        }
        
        # Sanitize
        form_data = sanitize_form_data(form_data)
        
        # Validate
        validators = {
            'principal_id': [FormValidator.validate_principal_id],
            'name': [
                lambda v: FormValidator.validate_required(v, "Principal name"),
                lambda v: FormValidator.validate_length(v, min_length=3, max_length=100, field_name="Principal name")
            ]
        }
        
        # If GAM is configured, advertiser ID is required
        if has_gam:
            validators['gam_advertiser_id'] = [
                lambda v: FormValidator.validate_required(v, "GAM Advertiser")
            ]
        
        errors = validate_form_data(form_data, validators)
        if errors:
            return render_template('create_principal.html', 
                                 tenant_id=tenant_id,
                                 errors=errors,
                                 form_data=form_data,
                                 has_gam=has_gam)
        
        conn = get_db_connection()
        try:
            principal_id = form_data['principal_id']
            name = form_data['name']
            
            # Generate a secure access token
            access_token = secrets.token_urlsafe(32)
            
            # Build platform mappings
            platform_mappings = {}
            if has_gam and form_data.get('gam_advertiser_id'):
                platform_mappings['gam_advertiser_id'] = form_data['gam_advertiser_id']
            
            # Create the principal
            conn.execute("""
                INSERT INTO principals (tenant_id, principal_id, name, platform_mappings, access_token)
                VALUES (?, ?, ?, ?, ?)
            """, (tenant_id, principal_id, name, json.dumps(platform_mappings), access_token))
            
            conn.connection.commit()
            conn.close()
            
            return redirect(url_for('tenant_dashboard', tenant_id=tenant_id) + '#principals')
        except Exception as e:
            conn.close()
            return render_template('create_principal.html', 
                                 tenant_id=tenant_id,
                                 error=str(e),
                                 has_gam=has_gam)
    
    return render_template('create_principal.html', tenant_id=tenant_id, has_gam=has_gam)

@app.route('/api/health')
def api_health():
    """API health check endpoint."""
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "healthy"})
    except:
        return jsonify({"status": "unhealthy"}), 500

@app.route('/api/gam/test-connection', methods=['POST'])
@require_auth()
def test_gam_connection():
    """Test GAM connection with refresh token and fetch available resources."""
    try:
        refresh_token = request.json.get('refresh_token')
        if not refresh_token:
            return jsonify({"error": "Refresh token is required"}), 400
        
        # Get OAuth credentials from superadmin config
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT config_key, config_value FROM superadmin_config 
            WHERE config_key IN ('gam_oauth_client_id', 'gam_oauth_client_secret')
        """)
        oauth_config = {}
        for row in cursor.fetchall():
            if row[0] == 'gam_oauth_client_id':
                oauth_config['client_id'] = row[1]
            elif row[0] == 'gam_oauth_client_secret':
                oauth_config['client_secret'] = row[1]
        conn.close()
        
        if not oauth_config.get('client_id') or not oauth_config.get('client_secret'):
            return jsonify({"error": "GAM OAuth credentials not configured in Settings"}), 400
        
        # Test connection using the helper
        from gam_helper import get_ad_manager_client_for_tenant
        
        # Create a temporary tenant-like object with just the refresh token
        class TempConfig:
            def __init__(self, refresh_token):
                self.gam_refresh_token = refresh_token
                self.gam_network_code = "temp"  # Temporary value
        
        temp_config = TempConfig(refresh_token)
        
        # Test by creating credentials and making a simple API call
        from googleads import oauth2, ad_manager
        
        # Create GoogleAds OAuth2 client with refresh token
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            refresh_token=refresh_token
        )
        
        # Test if credentials are valid by trying to refresh
        try:
            # This will attempt to refresh the token
            oauth2_client.Refresh()
        except Exception as e:
            return jsonify({"error": f"Invalid refresh token: {str(e)}"}), 400
        
        # Initialize GAM client to get network info
        # Note: We don't need to specify network_code for getAllNetworks call
        client = ad_manager.AdManagerClient(
            oauth2_client,
            "AdCP-Sales-Agent-Setup"
        )
        
        # Get network service
        network_service = client.GetService('NetworkService', version='v202408')
        
        # Get all networks user has access to
        try:
            # Try to get all networks first
            app.logger.info("Attempting to call getAllNetworks()")
            all_networks = network_service.getAllNetworks()
            app.logger.info(f"getAllNetworks() returned: {all_networks}")
            networks = []
            if all_networks:
                app.logger.info(f"Processing {len(all_networks)} networks")
                for network in all_networks:
                    app.logger.info(f"Network data: {network}")
                    networks.append({
                        "id": network['id'],
                        "displayName": network['displayName'],
                        "networkCode": network['networkCode']
                    })
            else:
                app.logger.info("getAllNetworks() returned empty/None")
        except AttributeError as e:
            # getAllNetworks might not be available, fall back to getCurrentNetwork
            app.logger.info(f"getAllNetworks not available (AttributeError: {e}), falling back to getCurrentNetwork")
            try:
                current_network = network_service.getCurrentNetwork()
                app.logger.info(f"getCurrentNetwork() returned: {current_network}")
                networks = [{
                    "id": current_network['id'],
                    "displayName": current_network['displayName'],
                    "networkCode": current_network['networkCode']
                }]
            except Exception as e:
                app.logger.error(f"Failed to get network info: {e}")
                networks = []
        except Exception as e:
            app.logger.error(f"Failed to get networks: {e}")
            app.logger.exception("Full exception details:")
            networks = []
        
        result = {
            "success": True,
            "message": "Successfully connected to Google Ad Manager",
            "networks": networks
        }
        
        # If we got a network, fetch companies and users
        if networks:
            try:
                # Reinitialize client with network code for subsequent calls
                network_code = networks[0]['networkCode']
                app.logger.info(f"Reinitializing client with network code: {network_code}")
                
                client = ad_manager.AdManagerClient(
                    oauth2_client,
                    "AdCP-Sales-Agent-Setup",
                    network_code=network_code
                )
                
                # Get company service for advertisers
                company_service = client.GetService('CompanyService', version='v202408')
                
                # Build a statement to get advertisers
                from googleads import ad_manager as gam_utils
                statement_builder = gam_utils.StatementBuilder()
                statement_builder.Where('type = :type')
                statement_builder.WithBindVariable('type', 'ADVERTISER')
                statement_builder.Limit(100)
                
                # Get companies
                app.logger.info("Calling getCompaniesByStatement for ADVERTISER companies")
                response = company_service.getCompaniesByStatement(
                    statement_builder.ToStatement()
                )
                app.logger.info(f"getCompaniesByStatement response: {response}")
                
                companies = []
                if response and hasattr(response, 'results'):
                    app.logger.info(f"Found {len(response.results)} companies")
                    for company in response.results:
                        app.logger.info(f"Company: id={company.id}, name={company.name}, type={company.type}")
                        companies.append({
                            "id": company.id,
                            "name": company.name,
                            "type": company.type
                        })
                else:
                    app.logger.info("No companies found in response")
                
                result['companies'] = companies
                
                # Get current user info
                user_service = client.GetService('UserService', version='v202408')
                current_user = user_service.getCurrentUser()
                result['current_user'] = {
                    "id": current_user.id,
                    "name": current_user.name,
                    "email": current_user.email
                }
                
            except Exception as e:
                # It's okay if we can't fetch companies/users
                result['warning'] = f"Connected but couldn't fetch all resources: {str(e)}"
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gam/get-advertisers', methods=['POST'])
@require_auth()
def get_gam_advertisers():
    """Get list of advertisers from GAM for a tenant."""
    try:
        tenant_id = request.json.get('tenant_id')
        if not tenant_id:
            return jsonify({"error": "tenant_id is required"}), 400
        
        # Check access - explicit role and tenant validation
        user_role = session.get('role')
        user_tenant_id = session.get('tenant_id')
        
        if user_role == 'super_admin':
            # Super admin can access any tenant
            pass
        elif user_tenant_id == tenant_id and user_role in ['admin', 'manager', 'tenant_admin']:
            # Tenant-specific roles can only access their own tenant
            pass
        else:
            app.logger.warning(f"Unauthorized GAM advertisers access attempt: role={user_role}, user_tenant={user_tenant_id}, requested_tenant={tenant_id}")
            return jsonify({"error": "Access denied"}), 403
        
        # Get adapter configuration for the tenant
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT gam_refresh_token, gam_network_code
            FROM adapter_config
            WHERE tenant_id = ? AND adapter_type = 'google_ad_manager'
        """, (tenant_id,))
        
        adapter_row = cursor.fetchone()
        if not adapter_row:
            conn.close()
            return jsonify({"error": "GAM not configured for this tenant"}), 400
        
        refresh_token = adapter_row[0]
        network_code = adapter_row[1]
        
        # Get OAuth credentials from superadmin config
        cursor = conn.execute("""
            SELECT config_key, config_value FROM superadmin_config 
            WHERE config_key IN ('gam_oauth_client_id', 'gam_oauth_client_secret')
        """)
        oauth_config = {}
        for row in cursor.fetchall():
            if row[0] == 'gam_oauth_client_id':
                oauth_config['client_id'] = row[1]
            elif row[0] == 'gam_oauth_client_secret':
                oauth_config['client_secret'] = row[1]
        conn.close()
        
        if not oauth_config.get('client_id') or not oauth_config.get('client_secret'):
            return jsonify({"error": "GAM OAuth credentials not configured"}), 400
        
        from googleads import oauth2, ad_manager
        
        # Create OAuth2 client
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            refresh_token=refresh_token
        )
        
        # Initialize GAM client
        client = ad_manager.AdManagerClient(
            oauth2_client,
            "AdCP-Sales-Agent",
            network_code=network_code
        )
        
        # Get company service to fetch advertisers
        company_service = client.GetService('CompanyService', version='v202408')
        
        # Create a statement to get ADVERTISER type companies
        from googleads import ad_manager as gam
        statement_builder = gam.StatementBuilder(version='v202408')
        statement_builder.Where('type = :type')
        statement_builder.WithBindVariable('type', 'ADVERTISER')
        
        advertisers = []
        while True:
            response = company_service.getCompaniesByStatement(
                statement_builder.ToStatement()
            )
            
            if 'results' in response and len(response['results']):
                for company in response['results']:
                    advertisers.append({
                        'id': str(company.id),
                        'name': company.name,
                        'type': company.type,
                        'external_id': getattr(company, 'externalId', None)
                    })
                statement_builder.offset += statement_builder.limit
            else:
                break
        
        return jsonify({"advertisers": advertisers})
        
    except Exception as e:
        # Log detailed error for debugging but return generic message
        app.logger.error(f"GAM advertisers fetch error for tenant {tenant_id}: {str(e)}")
        return jsonify({"error": "Failed to load advertisers from Google Ad Manager"}), 500

@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files."""
    return send_from_directory('static', path)

# Product Management Routes
@app.route('/tenant/<tenant_id>/products')
@require_auth()
def list_products(tenant_id):
    """List products for a tenant."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    # Get tenant name
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    tenant_name = row[0]
    
    # Get tenant config using helper function
    tenant_config = get_tenant_config_from_db(conn, tenant_id)
    
    # Get active adapter from config
    active_adapter = None
    if tenant_config and 'adapters' in tenant_config:
        for adapter_name, adapter_config in tenant_config['adapters'].items():
            if adapter_config.get('enabled'):
                active_adapter = adapter_name
                break
    
    # Get active adapter and its UI endpoint
    adapter_ui_endpoint = None
    if active_adapter:
        # Create dummy principal to get UI endpoint
        dummy_principal = Principal(
            tenant_id=tenant_id,
            principal_id="ui_query",
            name="UI Query",
            access_token="",
            platform_mappings={}
        )
        
        # Get adapter configuration from adapter_config table
        cursor = conn.execute("""
            SELECT mock_dry_run, gam_network_code, gam_refresh_token,
                   kevel_network_id, kevel_api_key
            FROM adapter_config
            WHERE tenant_id = ?
        """, (tenant_id,))
        adapter_row = cursor.fetchone()
        
        try:
            if active_adapter == 'google_ad_manager':
                from adapters.google_ad_manager import GoogleAdManager
                config = {
                    'enabled': True,
                    'network_code': adapter_row[1] if adapter_row else None,
                    'refresh_token': adapter_row[2] if adapter_row else None
                }
                adapter = GoogleAdManager(config, dummy_principal, dry_run=True, tenant_id=tenant_id)
                adapter_ui_endpoint = adapter.get_config_ui_endpoint()
            elif active_adapter == 'mock':
                from adapters.mock_ad_server import MockAdServer
                config = {
                    'enabled': True,
                    'dry_run': adapter_row[0] if adapter_row else False
                }
                adapter = MockAdServer(config, dummy_principal, dry_run=True, tenant_id=tenant_id)
                adapter_ui_endpoint = adapter.get_config_ui_endpoint()
            # Add other adapters as needed
        except Exception as e:
            app.logger.error(f"Error getting adapter UI endpoint: {e}")
            pass
    
    # Get products
    cursor = conn.execute("""
        SELECT product_id, name, description, formats, delivery_type, 
               is_fixed_price, cpm, price_guidance, is_custom, expires_at, countries
        FROM products
        WHERE tenant_id = ?
        ORDER BY product_id
    """, (tenant_id,))
    
    products = []
    for row in cursor.fetchall():
        # Handle PostgreSQL (returns objects) vs SQLite (returns JSON strings)
        formats = row[3] if isinstance(row[3], list) else (json.loads(row[3]) if row[3] else [])
        price_guidance = row[7] if isinstance(row[7], dict) else (json.loads(row[7]) if row[7] else None)
        countries = row[10] if isinstance(row[10], list) else (json.loads(row[10]) if row[10] else None)
        
        products.append({
            'product_id': row[0],
            'name': row[1],
            'description': row[2],
            'formats': formats,
            'delivery_type': row[4],
            'is_fixed_price': row[5],
            'cpm': row[6],
            'price_guidance': price_guidance,
            'is_custom': row[8],
            'expires_at': row[9],
            'countries': countries
        })
    
    conn.close()
    return render_template('products.html', 
                         tenant_id=tenant_id, 
                         tenant_name=tenant_name,
                         products=products,
                         adapter_ui_endpoint=adapter_ui_endpoint)

@app.route('/tenant/<tenant_id>/products/<product_id>/edit', methods=['GET', 'POST'])
@require_auth()
def edit_product_basic(tenant_id, product_id):
    """Edit basic product details."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        try:
            # Update product basic details
            conn.execute("""
                UPDATE products 
                SET name = ?, description = ?, delivery_type = ?, is_fixed_price = ?, cpm = ?, price_guidance = ?
                WHERE tenant_id = ? AND product_id = ?
            """, (
                request.form['name'],
                request.form.get('description', ''),
                request.form.get('delivery_type', 'guaranteed'),
                request.form.get('delivery_type') == 'guaranteed',
                float(request.form.get('cpm', 0)) if request.form.get('delivery_type') == 'guaranteed' else None,
                json.dumps({
                    'min_cpm': float(request.form.get('price_guidance_min', 0)),
                    'max_cpm': float(request.form.get('price_guidance_max', 0))
                }) if request.form.get('delivery_type') != 'guaranteed' else None,
                tenant_id,
                product_id
            ))
            
            conn.connection.commit()
            conn.close()
            
            return redirect(url_for('list_products', tenant_id=tenant_id))
            
        except Exception as e:
            conn.close()
            return render_template('edit_product.html', 
                                 tenant_id=tenant_id,
                                 product=None,
                                 error=str(e))
    
    # GET request - load product
    cursor = conn.execute(
        """SELECT product_id, name, description, formats, delivery_type, 
               is_fixed_price, cpm, price_guidance
        FROM products 
        WHERE tenant_id = ? AND product_id = ?""",
        (tenant_id, product_id)
    )
    product_row = cursor.fetchone()
    
    if not product_row:
        conn.close()
        return "Product not found", 404
    
    # Handle PostgreSQL (returns objects) vs SQLite (returns JSON strings)
    formats = product_row[3] if isinstance(product_row[3], list) else json.loads(product_row[3] or '[]')
    price_guidance = product_row[7] if isinstance(product_row[7], dict) else json.loads(product_row[7] or '{}')
    
    product = {
        'product_id': product_row[0],
        'name': product_row[1],
        'description': product_row[2],
        'formats': formats,
        'delivery_type': product_row[4],
        'is_fixed_price': product_row[5],
        'cpm': product_row[6],
        'price_guidance': price_guidance
    }
    
    conn.close()
    return render_template('edit_product.html', 
                         tenant_id=tenant_id,
                         product=product)

@app.route('/tenant/<tenant_id>/products/add', methods=['GET', 'POST'])
@require_auth()
def add_product(tenant_id):
    """Add a new product."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        try:
            # Check if this is from AI form
            ai_config = request.form.get('ai_config')
            if ai_config:
                # Parse AI-generated configuration
                config = json.loads(ai_config)
                product_id = request.form.get('product_id') or config.get('product_id')
                formats = config.get('formats', [])
                delivery_type = config.get('delivery_type', 'guaranteed')
                cpm = config.get('cpm')
                price_guidance = config.get('price_guidance')
                countries = config.get('countries')
                targeting_template = config.get('targeting_template', {})
                implementation_config = config.get('implementation_config', {})
                
                # Get name and description from form
                name = request.form.get('name')
                description = request.form.get('description')
            else:
                # Regular form submission
                product_id = request.form.get('product_id') or request.form['name'].lower().replace(' ', '_')
                formats = request.form.getlist('formats')
                name = request.form.get('name')
                description = request.form.get('description')
                targeting_template = {}
                implementation_config = {}
            
            # Build implementation config based on adapter
            tenant_config = get_tenant_config_from_db(conn, tenant_id)
            if not tenant_config:
                return jsonify({"error": "Tenant not found"}), 404
            
            # Handle regular form submission fields if not from AI
            if not ai_config:
                # Get selected countries
                countries = request.form.getlist('countries')
                # If "ALL" is selected or no countries selected, set to None (all countries)
                if 'ALL' in countries or not countries:
                    countries = None
                
                # Determine pricing based on delivery type
                delivery_type = request.form.get('delivery_type', 'guaranteed')
                is_fixed_price = delivery_type == 'guaranteed'
                
                # Handle CPM and price guidance
                cpm = None
                price_guidance = None
                
                if is_fixed_price:
                    cpm = float(request.form.get('cpm', 5.0))
                else:
                    # Non-guaranteed: use price guidance
                    min_cpm = request.form.get('price_guidance_min')
                    max_cpm = request.form.get('price_guidance_max')
                    if min_cpm and max_cpm:
                        price_guidance = {
                            'min_cpm': float(min_cpm),
                            'max_cpm': float(max_cpm)
                        }
            else:
                # AI config already has these values
                is_fixed_price = delivery_type == 'guaranteed'
            
            # Insert product
            conn.execute("""
                INSERT INTO products (
                    tenant_id, product_id, name, description,
                    formats, targeting_template, delivery_type,
                    is_fixed_price, cpm, price_guidance, countries, implementation_config
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                product_id,
                name,
                description,
                json.dumps(formats),
                json.dumps(targeting_template),
                delivery_type,
                is_fixed_price,
                cpm,
                json.dumps(price_guidance),
                json.dumps(countries),
                json.dumps(implementation_config)
            ))
            
            conn.connection.commit()
            conn.close()
            
            return redirect(url_for('list_products', tenant_id=tenant_id))
            
        except Exception as e:
            conn.close()
            # Get available formats
            formats = get_creative_formats()
            return render_template('add_product.html', 
                                 tenant_id=tenant_id,
                                 error=str(e),
                                 formats=formats)
    
    # GET request - show form
    conn.close()
    formats = get_creative_formats()
    return render_template('add_product.html', 
                         tenant_id=tenant_id,
                         formats=formats)

@app.route('/tenant/<tenant_id>/products/add/ai', methods=['GET'])
@require_auth()
def add_product_ai_form(tenant_id):
    """Show AI-assisted product creation form."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    return render_template('add_product_ai.html', tenant_id=tenant_id)

@app.route('/tenant/<tenant_id>/products/analyze_ai', methods=['POST'])
@require_auth()
def analyze_product_ai(tenant_id):
    """Analyze product description with AI and return configuration."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        import asyncio
        from ai_product_service import analyze_product_description
        
        data = request.get_json()
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        config = loop.run_until_complete(analyze_product_description(
            tenant_id=tenant_id,
            name=data['name'],
            external_description=data['external_description'],
            internal_details=data.get('internal_details')
        ))
        
        return jsonify({"success": True, "config": config})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/products/bulk', methods=['GET'])
@require_auth()
def bulk_product_upload_form(tenant_id):
    """Show bulk product upload form."""
    # Check access
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    # Get available templates
    from default_products import get_default_products
    templates = get_default_products()
    
    return render_template('bulk_product_upload.html', 
                         tenant_id=tenant_id,
                         templates=templates)

@app.route('/tenant/<tenant_id>/products/bulk/upload', methods=['POST'])
@require_auth()
def bulk_product_upload(tenant_id):
    """Process bulk product upload."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        import csv
        import io
        
        # Check if it's a file upload or JSON data
        if 'file' in request.files:
            file = request.files['file']
            if file.filename.endswith('.csv'):
                # Process CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.DictReader(stream)
                products = list(csv_input)
            else:
                # Assume JSON
                products = json.loads(file.stream.read().decode("UTF8"))
        else:
            # Direct JSON submission
            products = request.get_json().get('products', [])
        
        conn = get_db_connection()
        created_count = 0
        errors = []
        
        for idx, product_data in enumerate(products):
            try:
                # Validate required fields
                if not product_data.get('name'):
                    errors.append(f"Row {idx+1}: Missing product name")
                    continue
                
                # Generate product ID if not provided
                product_id = product_data.get('product_id', product_data['name'].lower().replace(' ', '_'))
                
                # Parse formats (handle comma-separated string or list)
                formats = product_data.get('formats', [])
                if isinstance(formats, str):
                    formats = [f.strip() for f in formats.split(',')]
                
                # Parse countries
                countries = product_data.get('countries')
                if isinstance(countries, str) and countries:
                    countries = [c.strip() for c in countries.split(',')]
                elif not countries:
                    countries = None
                
                # Determine delivery type and pricing
                delivery_type = product_data.get('delivery_type', 'guaranteed')
                cpm = float(product_data.get('cpm', 0)) if product_data.get('cpm') else None
                
                price_guidance_min = None
                price_guidance_max = None
                if delivery_type == 'non_guaranteed' and not cpm:
                    price_guidance_min = float(product_data.get('price_guidance_min', 2.0))
                    price_guidance_max = float(product_data.get('price_guidance_max', 10.0))
                
                # Build targeting template
                targeting_template = {}
                if product_data.get('device_types'):
                    device_types = product_data['device_types']
                    if isinstance(device_types, str):
                        device_types = [d.strip() for d in device_types.split(',')]
                    targeting_template['device_targets'] = {'device_types': device_types}
                
                if countries:
                    targeting_template['geo_targets'] = {'countries': countries}
                
                # Insert product
                conn.execute("""
                    INSERT INTO products (
                        product_id, tenant_id, name, description,
                        creative_formats, delivery_type, cpm,
                        price_guidance_min, price_guidance_max,
                        countries, targeting_template, implementation_config,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_id,
                    tenant_id,
                    product_data['name'],
                    product_data.get('description', ''),
                    json.dumps(formats),
                    delivery_type,
                    cpm,
                    price_guidance_min,
                    price_guidance_max,
                    json.dumps(countries) if countries else None,
                    json.dumps(targeting_template),
                    json.dumps(product_data.get('implementation_config', {})),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                
                created_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx+1}: {str(e)}")
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "created": created_count,
            "errors": errors
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/products/templates', methods=['GET'])
@require_auth()
def get_product_templates(tenant_id):
    """Get product templates for the tenant's industry."""
    try:
        from default_products import get_industry_specific_products
        
        # Get tenant's industry from config
        conn = get_db_connection()
        config = get_tenant_config_from_db(conn, tenant_id)
        conn.close()
        
        if not config:
            return jsonify({"error": "Tenant not found"}), 404
        
        config = config_row[0] if isinstance(config_row[0], dict) else json.loads(config_row[0])
        industry = config.get('industry', 'general')
        
        templates = get_industry_specific_products(industry)
        
        return jsonify({"templates": templates})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/products/templates/browse', methods=['GET'])
@require_auth()
def browse_product_templates(tenant_id):
    """Browse and use product templates."""
    # Check access
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    from default_products import get_default_products, get_industry_specific_products
    
    # Get all available templates
    standard_templates = get_default_products()
    
    # Get industry templates for different industries
    industry_templates = {
        'news': get_industry_specific_products('news'),
        'sports': get_industry_specific_products('sports'),
        'entertainment': get_industry_specific_products('entertainment'),
        'ecommerce': get_industry_specific_products('ecommerce')
    }
    
    # Filter out standard templates from industry lists
    standard_ids = {t['product_id'] for t in standard_templates}
    for industry in industry_templates:
        industry_templates[industry] = [
            t for t in industry_templates[industry] 
            if t['product_id'] not in standard_ids
        ]
    
    # Get creative formats for display
    formats = get_creative_formats()
    
    return render_template('product_templates.html',
                         tenant_id=tenant_id,
                         standard_templates=standard_templates,
                         industry_templates=industry_templates,
                         formats=formats)

@app.route('/tenant/<tenant_id>/products/templates/create', methods=['POST'])
@require_auth()
def create_from_template(tenant_id):
    """Create a product from a template."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        template = data.get('template')
        customizations = data.get('customizations', {})
        
        # Apply customizations to template
        product = template.copy()
        product.update(customizations)
        
        # Ensure unique product ID
        if 'product_id' in customizations:
            product['product_id'] = customizations['product_id']
        else:
            # Generate unique ID
            product['product_id'] = f"{template['product_id']}_{uuid.uuid4().hex[:6]}"
        
        # Insert product
        conn = get_db_connection()
        
        # Check if product ID already exists
        cursor = conn.execute(
            "SELECT product_id FROM products WHERE tenant_id = ? AND product_id = ?",
            (tenant_id, product['product_id'])
        )
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Product ID already exists"}), 400
        
        # Insert the product
        conn.execute("""
            INSERT INTO products (
                product_id, tenant_id, name, description,
                creative_formats, delivery_type, cpm,
                price_guidance_min, price_guidance_max,
                countries, targeting_template, implementation_config,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product['product_id'],
            tenant_id,
            product['name'],
            product.get('description', ''),
            json.dumps(product.get('formats', [])),
            product.get('delivery_type', 'guaranteed'),
            product.get('cpm'),
            product.get('price_guidance', {}).get('min') if not product.get('cpm') else None,
            product.get('price_guidance', {}).get('max') if not product.get('cpm') else None,
            json.dumps(product.get('countries')) if product.get('countries') else None,
            json.dumps(product.get('targeting_template', {})),
            json.dumps(product.get('implementation_config', {})),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "product_id": product['product_id'],
            "redirect_url": url_for('list_products', tenant_id=tenant_id)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Policy Management Routes
@app.route('/tenant/<tenant_id>/policy')
@require_auth()
def policy_settings(tenant_id):
    """View and manage policy settings for the tenant."""
    # Check access
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    # Get tenant info
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant = cursor.fetchone()
    if not tenant:
        conn.close()
        return "Tenant not found", 404
    
    tenant_name = tenant[0]
    
    # Get tenant config using helper function
    config = get_tenant_config_from_db(conn, tenant_id)
    if not config:
        conn.close()
        return "Tenant config not found", 404
    
    # Define default policies that all publishers start with
    default_policies = {
        'enabled': True,
        'require_manual_review': False,
        'default_prohibited_categories': [
            'illegal_content',
            'hate_speech', 
            'violence',
            'adult_content',
            'misleading_health_claims',
            'financial_scams'
        ],
        'default_prohibited_tactics': [
            'targeting_children_under_13',
            'discriminatory_targeting',
            'deceptive_claims',
            'impersonation',
            'privacy_violations'
        ],
        'prohibited_advertisers': [],
        'prohibited_categories': [],
        'prohibited_tactics': []
    }
    
    # Get tenant policy settings, using defaults where not specified
    tenant_policies = config.get('policy_settings', {})
    policy_settings = default_policies.copy()
    policy_settings.update(tenant_policies)
    
    # Get recent policy checks from audit log
    cursor = conn.execute("""
        SELECT timestamp, principal_id, success, details
        FROM audit_logs 
        WHERE tenant_id = ? AND operation = 'policy_check'
        ORDER BY timestamp DESC
        LIMIT 20
    """, (tenant_id,))
    
    recent_checks = []
    for row in cursor.fetchall():
        details = json.loads(row[3]) if row[3] else {}
        recent_checks.append({
            'timestamp': row[0],
            'principal_id': row[1],
            'success': row[2],
            'status': details.get('policy_status', 'unknown'),
            'brief': details.get('brief', ''),
            'reason': details.get('reason', '')
        })
    
    # Get pending policy review tasks
    cursor = conn.execute("""
        SELECT task_id, created_at, details
        FROM tasks
        WHERE tenant_id = ? AND task_type = 'policy_review' AND status = 'pending'
        ORDER BY created_at DESC
    """, (tenant_id,))
    
    pending_reviews = []
    for row in cursor.fetchall():
        details = json.loads(row[2]) if row[2] else {}
        pending_reviews.append({
            'task_id': row[0],
            'created_at': row[1],
            'brief': details.get('brief', ''),
            'advertiser': details.get('promoted_offering', '')
        })
    
    conn.close()
    
    return render_template('policy_settings_comprehensive.html',
                         tenant_id=tenant_id,
                         tenant_name=tenant_name,
                         policy_settings=policy_settings,
                         recent_checks=recent_checks,
                         pending_reviews=pending_reviews)

@app.route('/tenant/<tenant_id>/policy/update', methods=['POST'])
@require_auth()
def update_policy_settings(tenant_id):
    """Update policy settings for the tenant."""
    # Check access - only admins can update policy
    if session.get('role') not in ['super_admin', 'tenant_admin']:
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    try:
        conn = get_db_connection()
        
        # Get current config
        config = get_tenant_config_from_db(conn, tenant_id)
        if not config:
            return jsonify({"error": "Tenant not found"}), 404
        
        # Parse the form data for lists
        def parse_textarea_lines(field_name):
            """Parse textarea input into list of non-empty lines."""
            text = request.form.get(field_name, '')
            return [line.strip() for line in text.strip().split('\n') if line.strip()]
        
        # Update policy settings
        policy_settings = {
            'enabled': request.form.get('enabled') == 'on',
            'require_manual_review': request.form.get('require_manual_review') == 'on',
            'prohibited_advertisers': parse_textarea_lines('prohibited_advertisers'),
            'prohibited_categories': parse_textarea_lines('prohibited_categories'),
            'prohibited_tactics': parse_textarea_lines('prohibited_tactics'),
            # Keep default policies (they don't change from form)
            'default_prohibited_categories': config.get('policy_settings', {}).get('default_prohibited_categories', [
                'illegal_content',
                'hate_speech', 
                'violence',
                'adult_content',
                'misleading_health_claims',
                'financial_scams'
            ]),
            'default_prohibited_tactics': config.get('policy_settings', {}).get('default_prohibited_tactics', [
                'targeting_children_under_13',
                'discriminatory_targeting',
                'deceptive_claims',
                'impersonation',
                'privacy_violations'
            ])
        }
        
        config['policy_settings'] = policy_settings
        
        # Update database
        conn.execute("""
            UPDATE tenants 
            SET config = ?
            WHERE tenant_id = ?
        """, (json.dumps(config), tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('policy_settings', tenant_id=tenant_id))
        
    except Exception as e:
        return f"Error: {e}", 400

@app.route('/tenant/<tenant_id>/policy/rules', methods=['GET', 'POST'])
@require_auth()
def manage_policy_rules(tenant_id):
    """Redirect old policy rules URL to new comprehensive policy settings page."""
    return redirect(url_for('policy_settings', tenant_id=tenant_id))

@app.route('/tenant/<tenant_id>/policy/review/<task_id>', methods=['GET', 'POST'])
@require_auth()
def review_policy_task(tenant_id, task_id):
    """Review and approve/reject a policy review task."""
    # Check access
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            review_notes = request.form.get('review_notes', '')
            
            if action not in ['approve', 'reject']:
                return "Invalid action", 400
            
            # Update task status
            new_status = 'approved' if action == 'approve' else 'rejected'
            
            # Get task details
            cursor = conn.execute("""
                SELECT details FROM tasks
                WHERE tenant_id = ? AND task_id = ?
            """, (tenant_id, task_id))
            
            row = cursor.fetchone()
            if not row:
                conn.close()
                return "Task not found", 404
            
            details = json.loads(row[0]) if row[0] else {}
            details['review_notes'] = review_notes
            details['reviewed_by'] = session.get('email', 'unknown')
            details['reviewed_at'] = datetime.utcnow().isoformat()
            
            conn.execute("""
                UPDATE tasks
                SET status = ?, details = ?, completed_at = CURRENT_TIMESTAMP
                WHERE tenant_id = ? AND task_id = ?
            """, (new_status, json.dumps(details), tenant_id, task_id))
            
            # Log the review
            audit_logger = AuditLogger(conn)
            audit_logger.log(
                operation='policy_review',
                tenant_id=tenant_id,
                principal_id=details.get('principal_id'),
                success=True,
                details={
                    'task_id': task_id,
                    'action': action,
                    'reviewer': session.get('email', 'unknown')
                }
            )
            
            conn.connection.commit()
            conn.close()
            
            return redirect(url_for('policy_settings', tenant_id=tenant_id))
            
        except Exception as e:
            conn.close()
            return f"Error: {e}", 400
    
    # GET: Show review form
    cursor = conn.execute("""
        SELECT t.created_at, t.details, tn.name
        FROM tasks t
        JOIN tenants tn ON t.tenant_id = tn.tenant_id
        WHERE t.tenant_id = ? AND t.task_id = ? AND t.task_type = 'policy_review'
    """, (tenant_id, task_id))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Task not found", 404
    
    created_at, details_str, tenant_name = row
    details = json.loads(details_str) if details_str else {}
    
    conn.close()
    
    return render_template('policy_review.html',
                         tenant_id=tenant_id,
                         tenant_name=tenant_name,
                         task_id=task_id,
                         created_at=created_at,
                         details=details)

def get_creative_formats():
    """Get all creative formats from the database."""
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT format_id, name, type, description, width, height, duration_seconds
        FROM creative_formats
        WHERE is_standard = true
        ORDER BY type, name
    """)
    
    formats = []
    for row in cursor.fetchall():
        format_info = {
            'format_id': row[0],
            'name': row[1],
            'type': row[2],
            'description': row[3]
        }
        if row[4] and row[5]:  # width and height for display
            format_info['dimensions'] = f"{row[4]}x{row[5]}"
        elif row[6]:  # duration for video
            format_info['duration'] = f"{row[6]}s"
        formats.append(format_info)
    
    conn.close()
    return formats

# Creative Format Management Routes
@app.route('/tenant/<tenant_id>/creative-formats')
@require_auth()
def list_creative_formats(tenant_id):
    """List creative formats (both standard and custom)."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    conn = get_db_connection()
    
    # Get tenant name
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant_row = cursor.fetchone()
    if not tenant_row:
        conn.close()
        return "Tenant not found", 404
    
    tenant_name = tenant_row[0]
    
    # Get all formats (standard + custom for this tenant)
    cursor = conn.execute("""
        SELECT format_id, name, type, description, width, height, 
               duration_seconds, is_standard, source_url, created_at
        FROM creative_formats
        WHERE tenant_id IS NULL OR tenant_id = ?
        ORDER BY is_standard DESC, type, name
    """, (tenant_id,))
    
    formats = []
    for row in cursor.fetchall():
        format_info = {
            'format_id': row[0],
            'name': row[1],
            'type': row[2],
            'description': row[3],
            'is_standard': row[7],
            'source_url': row[8],
            'created_at': row[9]
        }
        
        # Add dimensions or duration
        if row[4] and row[5]:  # width and height
            format_info['dimensions'] = f"{row[4]}x{row[5]}"
        elif row[6]:  # duration
            format_info['duration'] = f"{row[6]}s"
            
        formats.append(format_info)
    
    conn.close()
    
    return render_template('creative_formats.html',
                         tenant_id=tenant_id,
                         tenant_name=tenant_name,
                         formats=formats)

@app.route('/tenant/<tenant_id>/creative-formats/add/ai', methods=['GET'])
@require_auth()
def add_creative_format_ai(tenant_id):
    """Show AI-assisted creative format discovery form."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    return render_template('add_creative_format_ai.html', tenant_id=tenant_id)

@app.route('/tenant/<tenant_id>/creative-formats/analyze', methods=['POST'])
@require_auth()
def analyze_creative_format(tenant_id):
    """Analyze creative format with AI."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        import asyncio
        from ai_creative_format_service import discover_creative_format
        
        data = request.get_json()
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        format_data = loop.run_until_complete(discover_creative_format(
            tenant_id=tenant_id,
            name=data['name'],
            description=data.get('description'),
            url=data.get('url'),
            type_hint=data.get('type_hint')
        ))
        
        return jsonify({"success": True, "format": format_data})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/save', methods=['POST'])
@require_auth()
def save_creative_format(tenant_id):
    """Save a creative format to the database."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        format_data = data['format']
        
        conn = get_db_connection()
        
        # Check if format ID already exists
        cursor = conn.execute(
            "SELECT format_id FROM creative_formats WHERE format_id = ?",
            (format_data['format_id'],)
        )
        
        if cursor.fetchone():
            # Update existing
            conn.execute("""
                UPDATE creative_formats
                SET name = ?, type = ?, description = ?, width = ?, height = ?,
                    duration_seconds = ?, max_file_size_kb = ?, specs = ?,
                    source_url = ?
                WHERE format_id = ?
            """, (
                format_data['name'],
                format_data['type'],
                format_data['description'],
                format_data.get('width'),
                format_data.get('height'),
                format_data.get('duration_seconds'),
                format_data.get('max_file_size_kb'),
                format_data.get('specs', '{}'),
                format_data.get('source_url'),
                format_data['format_id']
            ))
        else:
            # Insert new
            conn.execute("""
                INSERT INTO creative_formats (
                    format_id, tenant_id, name, type, description,
                    width, height, duration_seconds, max_file_size_kb,
                    specs, is_standard, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                format_data['format_id'],
                format_data.get('tenant_id'),
                format_data['name'],
                format_data['type'],
                format_data['description'],
                format_data.get('width'),
                format_data.get('height'),
                format_data.get('duration_seconds'),
                format_data.get('max_file_size_kb'),
                format_data.get('specs', '{}'),
                format_data.get('is_standard', False),
                format_data.get('source_url')
            ))
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/sync-standard', methods=['POST'])
@require_auth()
def sync_standard_formats(tenant_id):
    """Sync standard formats from adcontextprotocol.org."""
    # Super admin only
    if session.get('role') != 'super_admin':
        return jsonify({"error": "Access denied"}), 403
    
    try:
        import asyncio
        from ai_creative_format_service import sync_standard_formats as sync_formats
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        count = loop.run_until_complete(sync_formats())
        
        return jsonify({"success": True, "count": count})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/discover', methods=['POST'])
@require_auth()
def discover_formats_from_url(tenant_id):
    """Discover multiple creative formats from a URL."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        import asyncio
        from ai_creative_format_service import AICreativeFormatService
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        service = AICreativeFormatService()
        formats = loop.run_until_complete(service.discover_format_from_url(url))
        
        # Convert FormatSpecification objects to dicts for JSON response
        format_data = []
        for fmt in formats:
            format_data.append({
                "format_id": fmt.format_id,
                "name": fmt.name,
                "type": fmt.type,
                "description": fmt.description,
                "width": fmt.width,
                "height": fmt.height,
                "duration_seconds": fmt.duration_seconds,
                "max_file_size_kb": fmt.max_file_size_kb,
                "specs": fmt.specs or {},
                "extends": fmt.extends,  # Include the extends field
                "source_url": fmt.source_url
            })
        
        return jsonify({"success": True, "formats": format_data})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/save-multiple', methods=['POST'])
@require_auth()
def save_discovered_formats(tenant_id):
    """Save multiple discovered creative formats to the database."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        formats = data.get('formats', [])
        
        if not formats:
            return jsonify({"error": "No formats provided"}), 400
        
        conn = get_db_connection()
        saved_count = 0
        
        for format_data in formats:
            # Generate a unique format_id if needed
            base_format_id = format_data.get('format_id', f"{format_data['type']}_{format_data['name'].lower().replace(' ', '_')}")
            format_id = base_format_id
            counter = 1
            
            # Ensure format_id is unique
            while True:
                cursor = conn.execute(
                    "SELECT format_id FROM creative_formats WHERE format_id = ?",
                    (format_id,)
                )
                if not cursor.fetchone():
                    break
                format_id = f"{base_format_id}_{counter}"
                counter += 1
            
            # Insert new format
            conn.execute("""
                INSERT INTO creative_formats (
                    format_id, tenant_id, name, type, description,
                    width, height, duration_seconds, max_file_size_kb,
                    specs, is_standard, source_url, extends
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                format_id,
                tenant_id,  # Custom formats belong to the tenant
                format_data['name'],
                format_data['type'],
                format_data.get('description', ''),
                format_data.get('width'),
                format_data.get('height'),
                format_data.get('duration_seconds'),
                format_data.get('max_file_size_kb'),
                json.dumps(format_data.get('specs', {})),
                False,  # Custom formats are not standard
                format_data.get('source_url'),
                format_data.get('extends')  # Include the extends field
            ))
            saved_count += 1
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({"success": True, "saved_count": saved_count})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/<format_id>')
@require_auth()
def get_creative_format(tenant_id, format_id):
    """Get a specific creative format for editing."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        abort(403)
    
    conn = get_db_connection()
    cursor = conn.execute("""
        SELECT format_id, name, type, description, width, height,
               duration_seconds, max_file_size_kb, specs, is_standard, source_url
        FROM creative_formats
        WHERE format_id = ? AND (tenant_id = ? OR is_standard = TRUE)
    """, (format_id, tenant_id))
    
    format_data = cursor.fetchone()
    conn.close()
    
    if not format_data:
        abort(404)
    
    # Convert to dict
    format_dict = dict(format_data)
    if format_dict['specs']:
        format_dict['specs'] = json.loads(format_dict['specs']) if isinstance(format_dict['specs'], str) else format_dict['specs']
    
    return jsonify(format_dict)

@app.route('/tenant/<tenant_id>/creative-formats/<format_id>/edit', methods=['GET'])
@require_auth()
def edit_creative_format_page(tenant_id, format_id):
    """Display the edit creative format page."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        abort(403)
    
    # Get tenant info
    conn = get_db_connection()
    cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant = cursor.fetchone()
    
    if not tenant:
        abort(404)
    
    # Get creative format
    cursor = conn.execute("""
        SELECT format_id, name, type, description, width, height,
               duration_seconds, max_file_size_kb, specs, is_standard, source_url
        FROM creative_formats
        WHERE format_id = ? AND (tenant_id = ? OR is_standard = TRUE)
    """, (format_id, tenant_id))
    
    format_data = cursor.fetchone()
    conn.close()
    
    if not format_data:
        abort(404)
    
    # Don't allow editing standard formats
    if format_data['is_standard']:
        flash('Standard formats cannot be edited', 'error')
        return redirect(url_for('creative_formats', tenant_id=tenant_id))
    
    # Convert to dict and parse specs
    format_dict = dict(format_data)
    if format_dict['specs']:
        format_dict['specs'] = json.loads(format_dict['specs']) if isinstance(format_dict['specs'], str) else format_dict['specs']
    
    return render_template('edit_creative_format.html',
                         tenant_id=tenant_id,
                         tenant_name=tenant['name'],
                         format=format_dict)

@app.route('/tenant/<tenant_id>/creative-formats/<format_id>/update', methods=['POST'])
@require_auth()
def update_creative_format(tenant_id, format_id):
    """Update a creative format."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({"error": "Name is required"}), 400
        
        conn = get_db_connection()
        
        # Check if format exists and is editable
        cursor = conn.execute("""
            SELECT is_standard FROM creative_formats
            WHERE format_id = ? AND tenant_id = ?
        """, (format_id, tenant_id))
        
        format_info = cursor.fetchone()
        if not format_info:
            return jsonify({"error": "Format not found"}), 404
        
        if format_info['is_standard']:
            return jsonify({"error": "Cannot edit standard formats"}), 400
        
        # Update the format
        specs = json.dumps(data.get('specs', {})) if data.get('specs') else None
        
        conn.execute("""
            UPDATE creative_formats
            SET name = ?, description = ?, width = ?, height = ?,
                duration_seconds = ?, max_file_size_kb = ?, specs = ?,
                source_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE format_id = ? AND tenant_id = ?
        """, (
            data['name'],
            data.get('description'),
            data.get('width'),
            data.get('height'),
            data.get('duration_seconds'),
            data.get('max_file_size_kb'),
            specs,
            data.get('source_url'),
            format_id,
            tenant_id
        ))
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/creative-formats/<format_id>/delete', methods=['POST'])
@require_auth()
def delete_creative_format(tenant_id, format_id):
    """Delete a creative format."""
    # Check access
    if session.get('role') != 'super_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        conn = get_db_connection()
        
        # Check if format exists and is editable
        cursor = conn.execute("""
            SELECT is_standard FROM creative_formats
            WHERE format_id = ? AND tenant_id = ?
        """, (format_id, tenant_id))
        
        format_info = cursor.fetchone()
        if not format_info:
            return jsonify({"error": "Format not found"}), 404
        
        if format_info['is_standard']:
            return jsonify({"error": "Cannot delete standard formats"}), 400
        
        # Check if format is used in any products
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM products
            WHERE tenant_id = ? AND formats LIKE ?
        """, (tenant_id, f'%{format_id}%'))
        
        result = cursor.fetchone()
        if result['count'] > 0:
            return jsonify({"error": f"Cannot delete format - it is used by {result['count']} product(s)"}), 400
        
        # Delete the format
        conn.execute("""
            DELETE FROM creative_formats
            WHERE format_id = ? AND tenant_id = ?
        """, (format_id, tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tenant/<tenant_id>/products/suggestions', methods=['GET'])
@require_auth()
def get_product_suggestions(tenant_id):
    """API endpoint to get product suggestions based on industry and criteria."""
    try:
        from default_products import get_industry_specific_products, get_default_products
        
        # Get query parameters
        industry = request.args.get('industry')
        include_standard = request.args.get('include_standard', 'true').lower() == 'true'
        delivery_type = request.args.get('delivery_type')  # 'guaranteed', 'non_guaranteed', or None for all
        max_cpm = request.args.get('max_cpm', type=float)
        formats = request.args.getlist('formats')  # Can specify multiple format IDs
        
        # Get suggestions
        suggestions = []
        
        # Get industry-specific products if industry specified
        if industry:
            industry_products = get_industry_specific_products(industry)
            suggestions.extend(industry_products)
        elif include_standard:
            # If no industry specified but standard requested, get default products
            suggestions.extend(get_default_products())
        
        # Filter suggestions based on criteria
        filtered_suggestions = []
        for product in suggestions:
            # Filter by delivery type
            if delivery_type and product.get('delivery_type') != delivery_type:
                continue
            
            # Filter by max CPM
            if max_cpm:
                if product.get('cpm') and product['cpm'] > max_cpm:
                    continue
                elif product.get('price_guidance'):
                    if product['price_guidance']['min'] > max_cpm:
                        continue
            
            # Filter by formats
            if formats:
                product_formats = set(product.get('formats', []))
                requested_formats = set(formats)
                if not product_formats.intersection(requested_formats):
                    continue
            
            filtered_suggestions.append(product)
        
        # Sort suggestions by relevance
        # Prioritize: 1) Industry-specific, 2) Lower CPM, 3) More formats
        def sort_key(product):
            is_industry_specific = product['product_id'] not in [p['product_id'] for p in get_default_products()]
            avg_cpm = product.get('cpm', 0) or (product.get('price_guidance', {}).get('min', 0) + product.get('price_guidance', {}).get('max', 0)) / 2
            format_count = len(product.get('formats', []))
            return (-int(is_industry_specific), avg_cpm, -format_count)
        
        filtered_suggestions.sort(key=sort_key)
        
        # Check existing products to mark which are already created
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT product_id FROM products WHERE tenant_id = ?",
            (tenant_id,)
        )
        existing_ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        # Add metadata to suggestions
        for suggestion in filtered_suggestions:
            suggestion['already_exists'] = suggestion['product_id'] in existing_ids
            suggestion['is_industry_specific'] = suggestion['product_id'] not in [p['product_id'] for p in get_default_products()]
            
            # Calculate match score (0-100)
            score = 100
            if delivery_type and suggestion.get('delivery_type') == delivery_type:
                score += 20
            if formats:
                matching_formats = len(set(suggestion.get('formats', [])).intersection(set(formats)))
                score += matching_formats * 10
            if industry and suggestion['is_industry_specific']:
                score += 30
            
            suggestion['match_score'] = min(score, 100)
        
        return jsonify({
            "suggestions": filtered_suggestions,
            "total_count": len(filtered_suggestions),
            "criteria": {
                "industry": industry,
                "delivery_type": delivery_type,
                "max_cpm": max_cpm,
                "formats": formats
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tenant/<tenant_id>/products/quick-create', methods=['POST'])
@require_auth()
def quick_create_products(tenant_id):
    """Quick create multiple products from suggestions."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({"error": "No product IDs provided"}), 400
        
        from default_products import get_industry_specific_products, get_default_products
        
        # Get all available templates
        all_templates = get_default_products()
        # Add industry templates
        for industry in ['news', 'sports', 'entertainment', 'ecommerce']:
            all_templates.extend(get_industry_specific_products(industry))
        
        # Create a map for quick lookup
        template_map = {t['product_id']: t for t in all_templates}
        
        conn = get_db_connection()
        created = []
        errors = []
        
        for product_id in product_ids:
            if product_id not in template_map:
                errors.append(f"Template not found: {product_id}")
                continue
            
            template = template_map[product_id]
            
            try:
                # Check if already exists
                cursor = conn.execute(
                    "SELECT product_id FROM products WHERE tenant_id = ? AND product_id = ?",
                    (tenant_id, product_id)
                )
                if cursor.fetchone():
                    errors.append(f"Product already exists: {product_id}")
                    continue
                
                # Insert product
                conn.execute("""
                    INSERT INTO products (
                        product_id, tenant_id, name, description,
                        creative_formats, delivery_type, cpm,
                        price_guidance_min, price_guidance_max,
                        countries, targeting_template, implementation_config,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    template['product_id'],
                    tenant_id,
                    template['name'],
                    template.get('description', ''),
                    json.dumps(template.get('formats', [])),
                    template.get('delivery_type', 'guaranteed'),
                    template.get('cpm'),
                    template.get('price_guidance', {}).get('min') if not template.get('cpm') else None,
                    template.get('price_guidance', {}).get('max') if not template.get('cpm') else None,
                    json.dumps(template.get('countries')) if template.get('countries') else None,
                    json.dumps(template.get('targeting_template', {})),
                    json.dumps(template.get('implementation_config', {})),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                
                created.append(product_id)
                
            except Exception as e:
                errors.append(f"Failed to create {product_id}: {str(e)}")
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "created": created,
            "errors": errors,
            "created_count": len(created)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/products/setup-wizard')
@require_auth()
def product_setup_wizard(tenant_id):
    """Show product setup wizard for new tenants."""
    # Check access
    if session.get('role') == 'viewer':
        return "Access denied", 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied", 403
    
    return render_template('product_setup_wizard.html', tenant_id=tenant_id)

@app.route('/tenant/<tenant_id>/check-inventory-sync')
@require_auth()
def check_inventory_sync(tenant_id):
    """Check if GAM inventory has been synced for this tenant."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        from models import GAMInventory
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from db_config import DatabaseConfig
        
        # Create database session
        engine = create_engine(DatabaseConfig.get_connection_string())
        Session = sessionmaker(bind=engine)
        
        # Use context manager for automatic cleanup
        with Session() as db_session:
            # Check if any inventory exists for this tenant
            inventory_count = db_session.query(GAMInventory).filter(
                GAMInventory.tenant_id == tenant_id
            ).count()
            
            has_inventory = inventory_count > 0
            
            # Get last sync time if available
            last_sync = None
            if has_inventory:
                latest = db_session.query(GAMInventory).filter(
                    GAMInventory.tenant_id == tenant_id
                ).order_by(GAMInventory.created_at.desc()).first()
                if latest and latest.created_at:
                    last_sync = latest.created_at.isoformat()
            
            return jsonify({
                "has_inventory": has_inventory,
                "inventory_count": inventory_count,
                "last_sync": last_sync
            })
            
    except Exception as e:
        app.logger.error(f"Error checking inventory sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/tenant/<tenant_id>/analyze-ad-server')
@require_auth()
def analyze_ad_server_inventory(tenant_id):
    """Analyze ad server to discover audiences, formats, and placements."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        conn = get_db_connection()
        
        # Get tenant config to determine adapter
        config = get_tenant_config_from_db(conn, tenant_id)
        if not config:
            return jsonify({"error": "Tenant not found"}), 404
        
        # Find enabled adapter
        adapter_type = None
        adapter_config = None
        for adapter, cfg in config.get('adapters', {}).items():
            if cfg.get('enabled'):
                adapter_type = adapter
                adapter_config = cfg
                break
        
        if not adapter_type:
            # Return mock data if no adapter configured
            return jsonify({
                "audiences": [
                    {"id": "tech_enthusiasts", "name": "Tech Enthusiasts", "size": 1200000},
                    {"id": "sports_fans", "name": "Sports Fans", "size": 800000}
                ],
                "formats": [],
                "placements": [
                    {"id": "homepage_hero", "name": "Homepage Hero", "sizes": ["970x250", "728x90"]}
                ]
            })
        
        # Get a principal for API calls
        cursor = conn.execute(
            "SELECT principal_id, name, access_token, platform_mappings FROM principals WHERE tenant_id = ? LIMIT 1",
            (tenant_id,)
        )
        principal_row = cursor.fetchone()
        conn.close()
        
        if not principal_row:
            return jsonify({"error": "No principal found for tenant"}), 404
        
        # Create principal object
        from schemas import Principal
        mappings = principal_row[3] if isinstance(principal_row[3], dict) else json.loads(principal_row[3])
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=principal_row[0],
            name=principal_row[1],
            access_token=principal_row[2],
            platform_mappings=mappings
        )
        
        # Get adapter instance
        from adapters import get_adapter_class
        adapter_class = get_adapter_class(adapter_type)
        app.logger.info(f"Creating adapter for tenant_id={tenant_id}, adapter_type={adapter_type}")
        adapter = adapter_class(
            config=adapter_config,
            principal=principal,
            dry_run=True,
            tenant_id=tenant_id
        )
        
        # Query ad server inventory
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        inventory = loop.run_until_complete(adapter.get_available_inventory())
        
        # Debug logging
        app.logger.info(f"Inventory returned: audiences={len(inventory.get('audiences', []))}, "
                       f"key_values={len(inventory.get('key_values', []))}, "
                       f"placements={len(inventory.get('placements', []))}")
        
        # Process and return relevant data
        response_data = {
            "audiences": inventory.get("audiences", []),
            "formats": inventory.get("creative_specs", []),
            "placements": inventory.get("placements", []),
            "key_values": inventory.get("key_values", []),
            "properties": inventory.get("properties", {})
        }
        app.logger.info(f"Returning response with {len(response_data['key_values'])} key_values")
        return jsonify(response_data)
        
    except Exception as e:
        error_detail = traceback.format_exc()
        logger.error(f"Error analyzing ad server: {e}\n{error_detail}")
        app.logger.error(f"Full error details: {error_detail}")
        
        # Return error details for debugging
        return jsonify({
            "error": str(e),
            "audiences": [],
            "formats": [],
            "placements": [],
            "key_values": [],
            "properties": {"error_occurred": True}
        })

@app.route('/tenant/<tenant_id>/products/create-bulk', methods=['POST'])
@require_auth()
def create_products_bulk(tenant_id):
    """Create multiple products from wizard suggestions."""
    # Check access
    if session.get('role') == 'viewer':
        return jsonify({"error": "Access denied"}), 403
    
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return jsonify({"error": "Access denied"}), 403
    
    try:
        data = request.get_json()
        products = data.get('products', [])
        
        print(f"Received request to create {len(products)} products")
        print(f"Products data: {json.dumps(products, indent=2)}")
        
        if not products:
            return jsonify({"error": "No products provided"}), 400
        
        conn = get_db_connection()
        created_count = 0
        errors = []
        
        for product in products:
            try:
                # Generate unique product ID if needed
                product_id = product.get('product_id')
                if not product_id:
                    product_id = product['name'].lower().replace(' ', '_').replace('-', '_')
                    product_id = f"{product_id}_{uuid.uuid4().hex[:6]}"
                
                print(f"Creating product: {product_id} - {product.get('name')}")
                
                # Build price guidance
                price_guidance = None
                if product.get('price_guidance'):
                    price_guidance = json.dumps(product['price_guidance'])
                
                # Determine if fixed price based on whether CPM is provided
                is_fixed_price = product.get('cpm') is not None
                
                # Insert product
                conn.execute("""
                    INSERT INTO products (
                        product_id, tenant_id, name, description,
                        formats, delivery_type, is_fixed_price, cpm,
                        price_guidance,
                        countries, targeting_template, implementation_config
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_id,
                    tenant_id,
                    product['name'],
                    product.get('description', ''),
                    json.dumps(product.get('formats', [])),
                    product.get('delivery_type', 'non_guaranteed'),
                    is_fixed_price,
                    product.get('cpm'),
                    price_guidance,
                    json.dumps(product.get('countries')) if product.get('countries') else None,
                    json.dumps(product.get('targeting_template', {})),
                    json.dumps(product.get('implementation_config', {}))
                ))
                
                created_count += 1
                print(f"Successfully created product {product_id}, total count: {created_count}")
                
            except Exception as e:
                print(f"Error creating product: {e}")
                errors.append(f"Failed to create {product.get('name', 'product')}: {str(e)}")
        
        conn.connection.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "created_count": created_count,
            "errors": errors
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================
# GAM Line Item Viewer
# ========================

def get_custom_targeting_mappings(tenant_id=None):
    """Get custom targeting mappings for a tenant.
    
    In production, this would fetch from GAM CustomTargetingService.
    For now, returns mock data that can be configured per tenant.
    """
    # TODO: Store these in database or fetch from GAM API
    # Could be cached in Redis/memory for performance
    
    # Default mappings for header bidding (common across many publishers)
    default_key_mappings = {
        "13748922": "hb_pb",
        "14095946": "hb_source", 
        "14094596": "hb_format",
        # Add more common keys as needed
    }
    
    default_value_mappings = {
        "448589710493": "0.01",
        "448946107548": "freestar",
        "448946356517": "prebid",
        "448946353802": "video",
        # Add more common values as needed
    }
    
    # In production, could override with tenant-specific mappings
    # tenant_mappings = get_tenant_custom_mappings(tenant_id)
    # if tenant_mappings:
    #     key_mappings.update(tenant_mappings['keys'])
    #     value_mappings.update(tenant_mappings['values'])
    
    return default_key_mappings, default_value_mappings

def translate_custom_targeting(custom_targeting_node, tenant_id=None):
    """Translate GAM custom targeting structure to readable format."""
    if not custom_targeting_node:
        return None
    
    # Get mappings (could be tenant-specific in future)
    key_mappings, value_mappings = get_custom_targeting_mappings(tenant_id)
    
    def translate_node(node):
        if not node:
            return None
            
        if 'logicalOperator' in node:
            # This is a group node with AND/OR logic
            operator = node['logicalOperator'].lower()
            children = []
            if 'children' in node and node['children']:
                for child in node['children']:
                    translated_child = translate_node(child)
                    if translated_child:
                        children.append(translated_child)
            
            if len(children) == 1:
                return children[0]
            elif len(children) > 1:
                return {operator: children}
            return None
            
        elif 'keyId' in node:
            # This is a key-value targeting node
            key_id = str(node['keyId'])
            key_name = key_mappings.get(key_id, f"key_{key_id}")
            
            operator = node.get('operator', 'IS')
            value_ids = node.get('valueIds', [])
            
            # Translate value IDs to names
            values = []
            for value_id in value_ids:
                value_name = value_mappings.get(str(value_id), str(value_id))
                values.append(value_name)
            
            if operator == 'IS':
                return {"key": key_name, "in": values}
            elif operator == 'IS_NOT':
                return {"key": key_name, "not_in": values}
            else:
                return {"key": key_name, "operator": operator, "values": values}
                
        return None
    
    return translate_node(custom_targeting_node)

@app.route('/api/tenant/<tenant_id>/gam/custom-targeting-keys')
@require_auth()
def get_custom_targeting_keys(tenant_id):
    """Fetch custom targeting keys and values for display."""
    try:
        # Get the mappings using the centralized function
        key_mappings, value_mappings = get_custom_targeting_mappings(tenant_id)
        
        # Transform to the expected API format
        formatted_keys = {}
        for key_id, key_name in key_mappings.items():
            # Generate display names from the key names
            display_name = key_name.replace('_', ' ').replace('hb ', 'Header Bidding ').title()
            formatted_keys[key_id] = {
                "name": key_name,
                "displayName": display_name
            }
        
        formatted_values = {}
        for value_id, value_name in value_mappings.items():
            # Format display names for values
            display_name = value_name
            if value_name.replace('.', '').isdigit():
                display_name = f"${value_name}"  # Format as currency if numeric
            else:
                display_name = value_name.title()  # Capitalize for names
            
            formatted_values[value_id] = {
                "name": value_name,
                "displayName": display_name
            }
        
        return jsonify({
            "keys": formatted_keys,
            "values": formatted_values
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tenant/<tenant_id>/gam/line-item/<line_item_id>')
@require_auth()
def get_gam_line_item(tenant_id, line_item_id):
    """Fetch detailed line item data from GAM."""
    try:
        # Validate tenant_id format
        if not tenant_id or not isinstance(tenant_id, str):
            return jsonify({'error': 'Invalid tenant ID'}), 400
            
        # Validate line_item_id is numeric and follows GAM ID format
        if not line_item_id or not str(line_item_id).isdigit():
            return jsonify({'error': 'Line item ID must be a numeric value'}), 400
            
        try:
            line_item_id_int = int(line_item_id)
            if line_item_id_int <= 0:
                return jsonify({'error': 'Line item ID must be a positive number'}), 400
            # GAM line item IDs are typically 8+ digits
            if len(str(line_item_id_int)) < 8:
                return jsonify({'error': 'Invalid GAM line item ID format (must be at least 8 digits)'}), 400
        except (ValueError, TypeError) as e:
            app.logger.error(f"Invalid line item ID format: {line_item_id} - {str(e)}")
            return jsonify({'error': 'Line item ID must be a valid number'}), 400
        
        # Get the tenant's GAM configuration
        conn = get_db_connection()
        cursor = conn.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            conn.close()
            return jsonify({'error': 'Tenant not found'}), 404
        
        tenant_config = get_tenant_config_from_db(conn, tenant_id)
        conn.close()
        gam_config = tenant_config.get('adapters', {}).get('google_ad_manager', {})
        
        if not gam_config.get('enabled'):
            return jsonify({'error': 'GAM not enabled for this tenant'}), 400
        
        # Check if we're in dry-run mode (no refresh token means dry-run)
        is_dry_run = not gam_config.get('refresh_token')
        
        if is_dry_run:
            # Fetch from database in dry-run mode
            from models import GAMLineItem, GAMOrder
            from gam_orders_service import db_session
            
            db_session.remove()
            
            # Get line item from database
            line_item = db_session.query(GAMLineItem).filter(
                GAMLineItem.tenant_id == tenant_id,
                GAMLineItem.line_item_id == line_item_id
            ).first()
            
            if not line_item:
                db_session.remove()
                return jsonify({'error': 'Line item not found in database'}), 404
            
            # Get the associated order
            order = db_session.query(GAMOrder).filter(
                GAMOrder.tenant_id == tenant_id,
                GAMOrder.order_id == line_item.order_id
            ).first()
            
            # Build response from database data
            line_item_data = {
                'id': line_item.line_item_id,
                'name': line_item.name,
                'orderId': line_item.order_id,
                'status': line_item.status,
                'lineItemType': line_item.line_item_type,
                'priority': line_item.priority,
                'startDateTime': line_item.start_date.isoformat() if line_item.start_date else None,
                'endDateTime': line_item.end_date.isoformat() if line_item.end_date else None,
                'unlimitedEndDateTime': line_item.unlimited_end_date,
                'costType': line_item.cost_type,
                'costPerUnit': {'currencyCode': 'USD', 'microAmount': int((line_item.cost_per_unit or 0) * 1000000)} if line_item.cost_per_unit else None,
                'primaryGoal': {
                    'goalType': line_item.goal_type,
                    'unitType': line_item.primary_goal_type,
                    'units': line_item.primary_goal_units
                } if line_item.primary_goal_units else None,
                'stats': {
                    'impressionsDelivered': line_item.stats_impressions or 0,
                    'clicksDelivered': line_item.stats_clicks or 0,
                    'ctr': line_item.stats_ctr or 0,
                    'videoCompletionsDelivered': line_item.stats_video_completions or 0,
                    'videoStartsDelivered': line_item.stats_video_starts or 0,
                    'viewableImpressionsDelivered': line_item.stats_viewable_impressions or 0
                },
                'targeting': line_item.targeting or {},
                'creativePlaceholders': line_item.creative_placeholders or [],
                'frequencyCaps': line_item.frequency_caps or [],
                'deliveryRateType': line_item.delivery_rate_type,
                'deliveryIndicator': {'type': line_item.delivery_indicator_type} if line_item.delivery_indicator_type else None,
                'lastModifiedDateTime': line_item.last_modified_date.isoformat() if line_item.last_modified_date else None
            }
            
            order_data = {
                'id': order.order_id,
                'name': order.name,
                'advertiserId': order.advertiser_id,
                'advertiserName': order.advertiser_name,
                'traffickerId': order.trafficker_id,
                'trafficklerName': order.trafficker_name,
                'status': order.status,
                'startDateTime': order.start_date.isoformat() if order.start_date else None,
                'endDateTime': order.end_date.isoformat() if order.end_date else None,
                'totalBudget': {'currencyCode': order.currency_code or 'USD', 'microAmount': int((order.total_budget or 0) * 1000000)} if order.total_budget else None,
                'externalOrderId': order.external_order_id,
                'poNumber': order.po_number,
                'notes': order.notes
            } if order else None
            
            result = {
                'line_item': line_item_data,
                'order': order_data,
                'creatives': [],  # Would need to fetch from creative associations
                'creative_associations': [],
                'inventory_details': {},
                'media_product_json': convert_line_item_to_product_json(line_item_data, [])
            }
            
            db_session.remove()
            return jsonify(result)
        
        # Original code for non-dry-run mode
        # Get GAM client using the helper
        from gam_helper import get_ad_manager_client_for_tenant
        from googleads import ad_manager
        from zeep.helpers import serialize_object
        
        try:
            client = get_ad_manager_client_for_tenant(tenant_id)
        except Exception as e:
            return jsonify({'error': f'Failed to connect to GAM: {str(e)}'}), 500
        
        # Fetch the line item
        line_item_service = client.GetService('LineItemService')
        statement = (ad_manager.StatementBuilder(version='v202411')
                    .Where('id = :lineItemId')
                    .WithBindVariable('lineItemId', line_item_id_int)
                    .Limit(1))
        
        response = line_item_service.getLineItemsByStatement(statement.ToStatement())
        
        # Check if response has results (SOAP object, not dict)
        if not hasattr(response, 'results') or not response.results or len(response.results) == 0:
            return jsonify({'error': 'Line item not found'}), 404
        
        # Serialize the SOAP object to dict
        line_item = serialize_object(response.results[0])
        
        # Fetch the associated order
        order_service = client.GetService('OrderService')
        order_statement = (ad_manager.StatementBuilder(version='v202411')
                          .Where('id = :orderId')
                          .WithBindVariable('orderId', line_item['orderId'])
                          .Limit(1))
        order_response = order_service.getOrdersByStatement(order_statement.ToStatement())
        order = serialize_object(order_response.results[0]) if hasattr(order_response, 'results') and order_response.results else None
        
        # Fetch associated creatives
        lica_service = client.GetService('LineItemCreativeAssociationService')
        lica_statement = (ad_manager.StatementBuilder(version='v202411')
                         .Where('lineItemId = :lineItemId')
                         .WithBindVariable('lineItemId', line_item_id_int))
        lica_response = lica_service.getLineItemCreativeAssociationsByStatement(lica_statement.ToStatement())
        creative_associations = serialize_object(lica_response.results) if hasattr(lica_response, 'results') and lica_response.results else []
        
        # Fetch creative details if any associations exist
        creatives = []
        if creative_associations:
            creative_service = client.GetService('CreativeService')
            creative_ids = [lica['creativeId'] for lica in creative_associations]
            creative_statement = (ad_manager.StatementBuilder(version='v202411')
                                 .Where('id IN (:creativeIds)')
                                 .WithBindVariable('creativeIds', creative_ids))
            creative_response = creative_service.getCreativesByStatement(creative_statement.ToStatement())
            creatives = serialize_object(creative_response.results) if hasattr(creative_response, 'results') and creative_response.results else []
        
        # Fetch targeted inventory details (ad units and placements)
        inventory_details = {}
        
        # Fetch ad unit details if targeted
        if (line_item.get('targeting', {}).get('inventoryTargeting', {}).get('targetedAdUnits')):
            try:
                ad_unit_service = client.GetService('InventoryService')
                targeted_units = line_item['targeting']['inventoryTargeting']['targetedAdUnits']
                ad_unit_ids = [unit['adUnitId'] for unit in targeted_units]
                
                # Batch fetch ad units
                if ad_unit_ids:
                    ad_unit_statement = (ad_manager.StatementBuilder(version='v202411')
                                       .Where('id IN (:adUnitIds)')
                                       .WithBindVariable('adUnitIds', ad_unit_ids))
                    ad_unit_response = ad_unit_service.getAdUnitsByStatement(ad_unit_statement.ToStatement())
                    
                    if hasattr(ad_unit_response, 'results') and ad_unit_response.results:
                        ad_units_data = serialize_object(ad_unit_response.results)
                        # Create a mapping of ad unit ID to details including hierarchy
                        inventory_details['ad_units'] = {}
                        for ad_unit in ad_units_data:
                            # Build the full path from root to this ad unit
                            path_names = []
                            if ad_unit.get('parentPath'):
                                for path_unit in ad_unit['parentPath']:
                                    path_names.append(path_unit.get('name', 'Unknown'))
                            path_names.append(ad_unit.get('name', 'Unknown'))
                            
                            inventory_details['ad_units'][ad_unit['id']] = {
                                'id': ad_unit['id'],
                                'name': ad_unit.get('name', 'Unknown'),
                                'fullPath': ' > '.join(path_names),
                                'parentId': ad_unit.get('parentId'),
                                'status': ad_unit.get('status', 'ACTIVE'),
                                'adUnitCode': ad_unit.get('adUnitCode', '')
                            }
            except Exception as e:
                app.logger.warning(f"Failed to fetch ad unit details: {str(e)}")
                inventory_details['ad_units'] = {}
        
        # Fetch placement details if targeted
        if (line_item.get('targeting', {}).get('inventoryTargeting', {}).get('targetedPlacementIds')):
            try:
                placement_service = client.GetService('PlacementService')
                placement_ids = line_item['targeting']['inventoryTargeting']['targetedPlacementIds']
                
                if placement_ids:
                    placement_statement = (ad_manager.StatementBuilder(version='v202411')
                                         .Where('id IN (:placementIds)')
                                         .WithBindVariable('placementIds', placement_ids))
                    placement_response = placement_service.getPlacementsByStatement(placement_statement.ToStatement())
                    
                    if hasattr(placement_response, 'results') and placement_response.results:
                        placements_data = serialize_object(placement_response.results)
                        inventory_details['placements'] = {}
                        for placement in placements_data:
                            # Get the ad units in this placement
                            ad_unit_ids_in_placement = placement.get('targetedAdUnitIds', [])
                            inventory_details['placements'][placement['id']] = {
                                'id': placement['id'],
                                'name': placement.get('name', 'Unknown'),
                                'description': placement.get('description', ''),
                                'status': placement.get('status', 'ACTIVE'),
                                'targetedAdUnitIds': ad_unit_ids_in_placement,
                                'isAdSenseTargetingEnabled': placement.get('isAdSenseTargetingEnabled', False)
                            }
            except Exception as e:
                app.logger.warning(f"Failed to fetch placement details: {str(e)}")
                inventory_details['placements'] = {}
        
        # Data is already serialized above, just assign
        line_item_data = line_item
        order_data = order
        creatives_data = creatives
        
        # Build the comprehensive response
        result = {
            'line_item': line_item_data,
            'order': order_data,
            'creatives': creatives_data,
            'creative_associations': creative_associations if isinstance(creative_associations, list) else [],
            'inventory_details': inventory_details,  # Add the new inventory details
            # Convert to our internal media product JSON format
            'media_product_json': convert_line_item_to_product_json(line_item_data, creatives_data)
        }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error fetching GAM line item: {str(e)}")
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/tenant/<tenant_id>/gam/line-item/<line_item_id>')
@require_auth()
def view_gam_line_item(tenant_id, line_item_id):
    """View GAM line item details."""
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant = cursor.fetchone()
    conn.close()
    
    if not tenant:
        flash('Tenant not found', 'danger')
        return redirect(url_for('index'))
    
    return render_template('gam_line_item_viewer.html',
                          tenant=tenant,
                          tenant_id=tenant_id,
                          line_item_id=line_item_id,
                          user_email=session.get('user_email', 'Unknown'))

def extract_targeting_overlay(targeting):
    """Extract targeting overlay from GAM targeting object."""
    targeting_overlay = {}
    
    # Geographic targeting
    if targeting.get('geoTargeting'):
        geo = targeting['geoTargeting']
        if geo.get('targetedLocations'):
            countries = []
            for loc in geo['targetedLocations']:
                if loc.get('type', '').upper() == 'COUNTRY':
                    # Map common country names to ISO codes
                    display_name = loc.get('displayName', '')
                    if display_name == 'United States' or loc.get('id') == 2840:
                        countries.append('US')
                    elif display_name == 'Canada' or loc.get('id') == 2124:
                        countries.append('CA')
                    elif display_name == 'United Kingdom' or loc.get('id') == 2826:
                        countries.append('GB')
                    else:
                        countries.append(display_name or str(loc.get('id')))
            if countries:
                targeting_overlay['geo_country_any_of'] = countries
        
        if geo.get('excludedLocations'):
            excluded_countries = [loc.get('displayName', loc.get('id')) 
                                for loc in geo['excludedLocations'] 
                                if loc.get('type', '').upper() == 'COUNTRY']
            if excluded_countries:
                targeting_overlay['geo_country_none_of'] = excluded_countries
    
    # Device targeting
    if targeting.get('technologyTargeting'):
        tech = targeting['technologyTargeting']
        if tech.get('deviceCategoryTargeting'):
            devices = tech['deviceCategoryTargeting'].get('targetedDeviceCategories', [])
            device_types = []
            for device in devices:
                # GAM device category IDs
                if device.get('id') == 30000:  # Desktop
                    device_types.append('desktop')
                elif device.get('id') == 30001:  # Tablet
                    device_types.append('tablet')
                elif device.get('id') == 30002:  # Mobile
                    device_types.append('mobile')
            if device_types:
                targeting_overlay['device_type_any_of'] = device_types
    
    # Custom targeting (key-value pairs)
    if targeting.get('customTargeting'):
        custom = targeting['customTargeting']
        key_value_pairs = {}
        # TODO: Parse custom targeting tree structure if needed
        targeting_overlay['key_value_pairs'] = key_value_pairs
    
    return targeting_overlay

def extract_frequency_caps(line_item):
    """Extract frequency caps and convert to suppress_minutes."""
    if not line_item.get('frequencyCaps'):
        return None
    
    # Convert frequency caps to suppress_minutes
    for cap in line_item['frequencyCaps']:
        if cap.get('timeUnit') == 'MINUTE' and cap.get('numTimeUnits'):
            return cap['numTimeUnits']
        elif cap.get('timeUnit') == 'HOUR' and cap.get('numTimeUnits'):
            return cap['numTimeUnits'] * 60
        elif cap.get('timeUnit') == 'DAY' and cap.get('numTimeUnits'):
            return cap['numTimeUnits'] * 60 * 24
    return None

def extract_creative_formats(line_item, creatives):
    """Extract creative formats from line item and creatives."""
    formats = []
    seen_formats = set()
    
    # Extract from creative placeholders
    if line_item.get('creativePlaceholders'):
        for placeholder in line_item['creativePlaceholders']:
            size = placeholder.get('size')
            if size:
                width = size.get('width', 0)
                height = size.get('height', 0)
                format_id = f"display_{width}x{height}"
                if format_id not in seen_formats:
                    formats.append({
                        'id': format_id,
                        'display_name': f"Display {width}x{height}",
                        'creative_type': 'display',
                        'width': width,
                        'height': height
                    })
                    seen_formats.add(format_id)
    
    # Also check actual creatives
    for creative in creatives:
        if creative.get('size'):
            width = creative['size'].get('width', 0)
            height = creative['size'].get('height', 0)
            
            # Determine format type based on creative type
            format_type = 'display'
            if 'VideoCreative' in creative.get('Creative.Type', ''):
                format_type = 'video'
                format_id = f"video_{width}x{height}"
            elif 'AudioCreative' in creative.get('Creative.Type', ''):
                format_type = 'audio'
                format_id = f"audio"
            else:
                format_id = f"display_{width}x{height}"
            
            if format_id not in seen_formats:
                formats.append({
                    'id': format_id,
                    'display_name': f"{format_type.title()} {width}x{height}" if format_type != 'audio' else 'Audio',
                    'creative_type': format_type,
                    'width': width,
                    'height': height
                })
                seen_formats.add(format_id)
    
    return formats

def convert_line_item_to_product_json(line_item, creatives):
    """Convert GAM line item to our internal media product JSON format."""
    # Extract targeting information
    targeting = line_item.get('targeting', {})
    targeting_overlay = extract_targeting_overlay(targeting)
    
    # Add dayparting if present
    if targeting.get('dayPartTargeting'):
        daypart = targeting['dayPartTargeting']
        if daypart.get('dayParts'):
            schedules = []
            for dp in daypart['dayParts']:
                schedule = {
                    'days': [dp.get('dayOfWeek')],
                    'start_hour': dp.get('startTime', {}).get('hour', 0),
                    'end_hour': dp.get('endTime', {}).get('hour', 23)
                }
                schedules.append(schedule)
            
            if schedules:
                targeting_overlay['dayparting'] = {
                    'timezone': daypart.get('timeZone', 'America/New_York'),
                    'schedules': schedules
                }
    
    # Add frequency cap if present
    suppress_minutes = extract_frequency_caps(line_item)
    if suppress_minutes:
        targeting_overlay['frequency_cap'] = {
            'suppress_minutes': suppress_minutes,
            'scope': 'media_buy'
        }
    
    # Extract creative formats
    formats = extract_creative_formats(line_item, creatives)
    
    # Translate custom targeting to human-readable format
    key_value_targeting = None
    if targeting.get('customTargeting'):
        key_value_targeting = translate_custom_targeting(targeting['customTargeting'])
    
    # Build the product JSON
    product_json = {
        'product_id': f'gam_line_item_{line_item.get("id")}',
        'name': line_item.get('name', 'Unknown'),
        'description': f'GAM Line Item: {line_item.get("name", "")}',
        'formats': formats,
        'delivery_type': 'guaranteed' if line_item.get('lineItemType') == 'STANDARD' else 'non_guaranteed',
        'is_fixed_price': line_item.get('costType') == 'CPM',
        'cpm': float(line_item.get('costPerUnit', {}).get('microAmount', 0)) / 1000000.0 if line_item.get('costPerUnit') else None,
        'targeting_overlay': targeting_overlay,
        'implementation_config': {
            'gam': {
                'line_item_id': line_item.get('id'),
                'order_id': line_item.get('orderId'),
                'line_item_type': line_item.get('lineItemType'),
                'priority': line_item.get('priority'),
                'delivery_rate_type': line_item.get('deliveryRateType'),
                'status': line_item.get('status'),
                'start_datetime': line_item.get('startDateTime'),
                'end_datetime': line_item.get('endDateTime'),
                'units_bought': line_item.get('unitsBought'),
                'cost_type': line_item.get('costType'),
                'cost_per_unit': float(line_item.get('costPerUnit', {}).get('microAmount', 0)) / 1000000.0 if line_item.get('costPerUnit') else None,
                'discount_type': line_item.get('discountType'),
                'allow_overbook': line_item.get('allowOverbook', False),
                # Add human-readable key-value targeting
                'key_value_targeting': key_value_targeting,
                # Add creative sizes in simple format
                'creative_sizes': [
                    {'width': p.get('size', {}).get('width'), 'height': p.get('size', {}).get('height')}
                    for p in line_item.get('creativePlaceholders', [])
                    if p.get('size')
                ],
                # Add ad units if present
                'ad_units': [
                    au.get('adUnitId') 
                    for au in targeting.get('inventoryTargeting', {}).get('targetedAdUnits', [])
                ] if targeting.get('inventoryTargeting', {}).get('targetedAdUnits') else []
            }
        }
    }
    
    return product_json

# Function to register adapter routes
def register_adapter_routes():
    """Register UI routes from all available adapters."""
    try:
        print("Starting adapter route registration...")
        # Get all enabled adapters across all tenants
        conn = get_db_connection()
        cursor = conn.execute("SELECT tenant_id, ad_server FROM tenants WHERE ad_server IS NOT NULL")
        
        registered_adapters = set()
        for row in cursor.fetchall():
            tenant_id = row[0]
            ad_server = row[1]
            print(f"Processing tenant {tenant_id} with adapter {ad_server}")
            
            tenant_config = get_tenant_config_from_db(conn, tenant_id)
            if not tenant_config:
                continue
                
            adapters_config = tenant_config.get('adapters', {})
            
            for adapter_name, adapter_config in adapters_config.items():
                if adapter_config.get('enabled') and adapter_name not in registered_adapters:
                    # Create a dummy principal for route registration
                    dummy_principal = Principal(
                        tenant_id="system",
                        principal_id="route_registration",
                        name="Route Registration",
                        access_token="",
                        platform_mappings={}
                    )
                    
                    # Import and register adapter routes
                    try:
                        if adapter_name == 'google_ad_manager':
                            print(f"Registering routes for {adapter_name}")
                            print(f"Adapter config: {adapter_config}")
                            from adapters.google_ad_manager import GoogleAdManager
                            adapter = GoogleAdManager(adapter_config, dummy_principal, dry_run=True, tenant_id="system")
                            adapter.register_ui_routes(app)
                            registered_adapters.add(adapter_name)
                        elif adapter_name == 'mock':
                            print(f"Registering routes for {adapter_name}")
                            from adapters.mock_ad_server import MockAdServer
                            adapter = MockAdServer(adapter_config, dummy_principal, dry_run=True, tenant_id="system")
                            adapter.register_ui_routes(app)
                            registered_adapters.add(adapter_name)
                        elif adapter_name == 'kevel':
                            from adapters.kevel import KevelAdapter
                            adapter = KevelAdapter(adapter_config, dummy_principal, dry_run=True)
                            if hasattr(adapter, 'register_ui_routes'):
                                adapter.register_ui_routes(app)
                                registered_adapters.add(adapter_name)
                        # Add other adapters as they implement UI routes
                    except Exception as e:
                        print(f"Warning: Failed to register routes for {adapter_name}: {e}")
        
        conn.close()
        print(f"Registered UI routes for adapters: {', '.join(registered_adapters)}")
        
    except Exception as e:
        print(f"Warning: Failed to register adapter routes: {e}")
        traceback.print_exc()

# Register adapter routes at module level
register_adapter_routes()

# Register GAM inventory endpoints at module level
register_inventory_endpoints(app)

# WebSocket event handlers for activity feed
@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    tenant_id = request.args.get('tenant_id')
    if not tenant_id:
        return False  # Reject connection
    
    # Join the room for this tenant
    join_room(f'tenant_{tenant_id}')
    app.logger.info(f"WebSocket connected for tenant {tenant_id}")
    
    # Send recent activities from activity_feed
    if tenant_id in activity_feed.recent_activities:
        for activity in activity_feed.recent_activities[tenant_id]:
            emit('activity', activity)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    tenant_id = request.args.get('tenant_id')
    if tenant_id:
        leave_room(f'tenant_{tenant_id}')
        app.logger.info(f"WebSocket disconnected for tenant {tenant_id}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """Handle subscription to a tenant's activity feed."""
    tenant_id = data.get('tenant_id')
    if tenant_id:
        join_room(f'tenant_{tenant_id}')
        emit('subscribed', {'tenant_id': tenant_id})
        
        # Send recent activities
        if tenant_id in activity_feed.recent_activities:
            for activity in activity_feed.recent_activities[tenant_id]:
                emit('activity', activity)

# Function to broadcast activities from activity_feed to WebSocket clients
def broadcast_activity_to_websocket(tenant_id: str, activity: dict):
    """Broadcast activity to WebSocket clients in a tenant room."""
    socketio.emit('activity', activity, room=f'tenant_{tenant_id}')

# Register a callback with activity_feed to broadcast to WebSocket
# Note: This is a simplified integration since activity_feed uses asyncio
# In production, you might want to use a message queue or event system
activity_feed.broadcast_to_websocket = broadcast_activity_to_websocket

if __name__ == '__main__':
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("ERROR: Google OAuth credentials not found!")
        print("\nPlease provide OAuth credentials using one of these methods:")
        print("1. Place your client_secret_*.json file in the project root")
        print("2. Set GOOGLE_OAUTH_CREDENTIALS_FILE=/path/to/credentials.json")
        print("3. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
        print("\nTo obtain credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create OAuth 2.0 credentials for a Web application")
        print("3. Add redirect URI: http://localhost:8001/auth/google/callback")
        print("4. Download the JSON file")
        exit(1)
    
# ============== MCP Protocol Testing Routes (Super Admin Only) ==============

@app.route('/test-simple')
def test_simple():
    """Simple test page - no auth required for debugging."""
    return render_template('test_mcp_simple.html')

@app.route('/mcp-test')
@require_auth(admin_only=True)
def mcp_test():
    """MCP protocol testing interface for super admins."""
    # Get all tenants and their principals
    conn = get_db_connection()
    
    # Get tenants
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain
        FROM tenants
        WHERE is_active = true
        ORDER BY name
    """)
    tenants = []
    for row in cursor.fetchall():
        tenants.append({
            'tenant_id': row[0],
            'name': row[1],
            'subdomain': row[2]
        })
    
    # Get all principals with their tenant info
    cursor = conn.execute("""
        SELECT p.principal_id, p.name, p.tenant_id, p.access_token, t.name as tenant_name
        FROM principals p
        JOIN tenants t ON p.tenant_id = t.tenant_id
        WHERE t.is_active = true
        ORDER BY t.name, p.name
    """)
    principals = []
    for row in cursor.fetchall():
        principals.append({
            'principal_id': row[0],
            'name': row[1],
            'tenant_id': row[2],
            'access_token': row[3],
            'tenant_name': row[4]
        })
    
    conn.close()
    
    # Get server URL - use correct port from environment
    server_port = int(os.environ.get('ADCP_SALES_PORT', 8005))
    server_url = f"http://localhost:{server_port}/mcp/"
    
    return render_template('mcp_test.html',
                         tenants=tenants,
                         principals=principals,
                         server_url=server_url)

@app.route('/api/mcp-test/call', methods=['POST'])
def mcp_test_call():
    """Make an MCP call using the official client."""
    # For debugging, temporarily allow unauthenticated access if a special header is present
    if request.headers.get('X-Debug-Mode') == 'test':
        # Allow debugging without auth
        pass
    else:
        # Check authentication manually for API endpoint to return JSON on failure
        if not session.get('authenticated'):
            return jsonify({'success': False, 'error': 'Authentication required. Please login again.'}), 401
        if session.get('role') != 'super_admin':
            return jsonify({'success': False, 'error': 'Super admin access required.'}), 403
    
    try:
        import asyncio
        from fastmcp.client import Client
        from fastmcp.client.transports import StreamableHttpTransport
        
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
            
        tool_name = data.get('tool')
        tool_params = data.get('params', {})
        access_token = data.get('access_token')
        # If the server URL is localhost, replace with internal Docker service name
        server_url = data.get('server_url', 'http://adcp-server:8080/mcp/')
        if 'localhost:8005' in server_url:
            server_url = server_url.replace('localhost:8005', 'adcp-server:8080')
        elif 'localhost:8080' in server_url:
            server_url = server_url.replace('localhost:8080', 'adcp-server:8080')
        
        if not tool_name or not access_token:
            return jsonify({'success': False, 'error': 'Missing required parameters: tool and access_token'}), 400
        
        # Look up the tenant for this token
        conn = get_db_connection()
        cursor = conn.execute(
            "SELECT tenant_id FROM principals WHERE access_token = ?",
            (access_token,)
        )
        row = cursor.fetchone()
        conn.close()
        
        tenant_id = row[0] if row else 'default'
        
        # Set up headers for authentication
        # Include tenant header for proper principal resolution
        headers = {
            "x-adcp-auth": access_token,
            "x-adcp-tenant": tenant_id
        }
        
        # Log for debugging
        app.logger.info(f"MCP Test Call - Tool: {tool_name}, Server: {server_url}, Token: {access_token[:20]}...")
        
        async def make_call():
            """Make the actual MCP call."""
            transport = StreamableHttpTransport(server_url, headers=headers)
            
            async with Client(transport) as client:
                try:
                    # Some tools expect params wrapped in 'req' key, others don't
                    # Tools without req parameter: get_targeting_capabilities
                    tools_without_req = ['get_targeting_capabilities']
                    
                    if tool_name in tools_without_req:
                        arguments = tool_params or {}
                    else:
                        # Most tools have a single parameter named 'req'
                        arguments = {"req": tool_params} if tool_params else {"req": {}}
                    
                    app.logger.info(f"Calling tool {tool_name} with arguments: {arguments}")
                    result = await client.call_tool(tool_name, arguments)
                    
                    # Convert result to dict if it's a pydantic model or handle TextContent
                    if hasattr(result, 'model_dump'):
                        return {'success': True, 'result': result.model_dump()}
                    else:
                        # Handle various FastMCP response types
                        import json as json_module
                        
                        # Check if it's a CallToolResult object
                        if hasattr(result, 'structured_content'):
                            # Use the structured_content which is already parsed
                            content = result.structured_content
                            # Remove implementation_config from products (security - proprietary data)
                            if isinstance(content, dict) and 'products' in content:
                                for product in content.get('products', []):
                                    if isinstance(product, dict) and 'implementation_config' in product:
                                        del product['implementation_config']
                            return {'success': True, 'result': content}
                        elif hasattr(result, 'data') and hasattr(result.data, 'model_dump'):
                            # Use the data field if it has model_dump
                            return {'success': True, 'result': result.data.model_dump()}
                        elif hasattr(result, 'content'):
                            # Handle content field which might be a list of TextContent
                            if isinstance(result.content, list) and len(result.content) > 0:
                                first_item = result.content[0]
                                if hasattr(first_item, 'text'):
                                    try:
                                        parsed_result = json_module.loads(first_item.text)
                                        return {'success': True, 'result': parsed_result}
                                    except:
                                        return {'success': True, 'result': first_item.text}
                        
                        # Check if result itself has text attribute
                        if hasattr(result, 'text'):
                            try:
                                parsed_result = json_module.loads(result.text)
                                return {'success': True, 'result': parsed_result}
                            except:
                                return {'success': True, 'result': result.text}
                        
                        # Fallback to string representation
                        return {'success': True, 'result': str(result)}
                        
                except Exception as e:
                    app.logger.error(f"MCP call error: {str(e)}")
                    return {'success': False, 'error': str(e), 'error_type': type(e).__name__}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(make_call())
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Event loop error: {str(e)}")
            return jsonify({'success': False, 'error': f'Event loop error: {str(e)}'}), 500
        finally:
            loop.close()
            
    except ImportError as e:
        app.logger.error(f"Import error in mcp_test_call: {str(e)}")
        return jsonify({'success': False, 'error': f'Import error: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in mcp_test_call: {str(e)}")
        return jsonify({'success': False, 'error': f'Unexpected error: {str(e)}'}), 500

    
    # Run server
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))  # Match OAuth redirect URI
    # Debug mode off for production
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    
    print(f"DEBUG: FLASK_DEBUG={os.environ.get('FLASK_DEBUG')}, debug={debug}")
    print(f"Starting Admin UI with Google OAuth and WebSocket support on port {port}")
    print(f"Redirect URI should be: http://localhost:{port}/auth/google/callback")
    
    if not SUPER_ADMIN_EMAILS and not SUPER_ADMIN_DOMAINS:
        print("\nWARNING: No super admin emails or domains configured!")
        print("Set SUPER_ADMIN_EMAILS='email1@example.com,email2@example.com' or")
        print("Set SUPER_ADMIN_DOMAINS='example.com,company.com' in environment variables")
    
    # Use socketio.run instead of app.run to enable WebSocket support
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)