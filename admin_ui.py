#!/usr/bin/env python3
"""Admin UI with Google OAuth2 authentication."""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory, g
import secrets
import json
import os
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps
from authlib.integrations.flask_client import OAuth
from db_config import get_db_connection
from validation import FormValidator, validate_form_data, sanitize_form_data

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.logger.setLevel(logging.INFO)

# Import schemas after Flask app is created
from schemas import Principal

# Import and register super admin API blueprint
from superadmin_api import superadmin_api
app.register_blueprint(superadmin_api)

# Import and register sync API blueprint
from sync_api import sync_api
app.register_blueprint(sync_api, url_prefix='/api/sync')

# Import GAM inventory service for targeting browser
from gam_inventory_service import GAMInventoryService, create_inventory_endpoints as register_inventory_endpoints, SessionLocal, db_session

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
                return redirect(url_for('tenant_detail', tenant_id=oauth_tenant_id))
            
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
                return redirect(url_for('tenant_detail', tenant_id=oauth_tenant_id))
            
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
                return redirect(url_for('tenant_detail', tenant_id=oauth_tenant_id))
            
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
                    return redirect(url_for('tenant_detail', tenant_id=oauth_tenant_id))
            
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
                return redirect(url_for('tenant_detail', tenant_id=tenant_id))
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
    
    return redirect(url_for('tenant_detail', tenant_id=selected_tenant[0]))

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
    return redirect(url_for('tenant_detail', tenant_id=tenant_id))

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

@app.route('/tenant/<tenant_id>')
def tenant_root(tenant_id):
    """Redirect to tenant login if not authenticated."""
    if session.get('authenticated'):
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))
    return redirect(url_for('tenant_login', tenant_id=tenant_id))

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
        return redirect(url_for('tenant_detail', tenant_id=session.get('tenant_id')))
    
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

@app.route('/tenant/<tenant_id>/manage')
@require_auth()
def tenant_detail(tenant_id):
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
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        flash(f"Error updating configuration: {str(e)}", 'error')
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))

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
            return redirect(url_for('tenant_detail', tenant_id=tenant_id))
        
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
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))
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
            
            # Parse authorization lists
            authorized_emails = [email.strip() for email in request.form.get('authorized_emails', '').split(',') if email.strip()]
            authorized_domains = [domain.strip() for domain in request.form.get('authorized_domains', '').split(',') if domain.strip()]
            
            # Build minimal config for unmigrated fields
            config = {
                "setup_complete": False  # Flag to track if tenant has completed setup
            }
            
            conn = get_db_connection()
            
            # Create tenant with new fields
            conn.execute("""
                INSERT INTO tenants (
                    tenant_id, name, subdomain, config,
                    created_at, updated_at, is_active,
                    ad_server, max_daily_budget, enable_aee_signals,
                    authorized_emails, authorized_domains,
                    auto_approve_formats, human_review_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                tenant_name,
                subdomain,
                json.dumps(config),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                True,
                None,  # ad_server - set during setup
                10000,  # max_daily_budget
                True,  # enable_aee_signals
                json.dumps(authorized_emails),  # authorized_emails
                json.dumps(authorized_domains),  # authorized_domains
                json.dumps([]),  # auto_approve_formats
                True  # human_review_required
            ))
            
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
            return redirect(url_for('tenant_detail', tenant_id=tenant_id))
            
        except Exception as e:
            return render_template('create_tenant.html', error=str(e))
    
    return render_template('create_tenant.html')

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
    api_key = api_key_row['config_value'] if api_key_row else ''
    
    conn.close()
    
    return render_template('orders_browser.html', 
                         tenant_id=tenant_id, 
                         tenant_name=tenant_name,
                         api_key=api_key)

# Operations Dashboard Route
@app.route('/tenant/<tenant_id>/operations')
@require_auth()
def operations_dashboard(tenant_id):
    """Display operations dashboard with media buys, tasks, and audit logs."""
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
            'created_at': datetime.fromisoformat(row[11]) if row[11] else None,
            'updated_at': datetime.fromisoformat(row[12]) if row[12] else None,
            'approved_at': datetime.fromisoformat(row[13]) if row[13] else None,
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
        due_date = datetime.fromisoformat(row[8]) if row[8] else None
        is_overdue = False
        if due_date and row[6] == 'pending':
            is_overdue = due_date < datetime.now()
            
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
            'completed_at': datetime.fromisoformat(row[9]) if row[9] else None,
            'completed_by': row[10],
            'metadata': json.loads(row[11]) if row[11] else {},
            'created_at': datetime.fromisoformat(row[12]) if row[12] else None,
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
        audit_logs.append({
            'log_id': row[0],
            'tenant_id': row[1],
            'timestamp': datetime.fromisoformat(row[2]) if row[2] else None,
            'operation': row[3],
            'principal_name': row[4],
            'principal_id': row[5],
            'adapter_id': row[6],
            'success': row[7],
            'error_message': row[8],
            'details': row[9]
        })
    
    conn.close()
    
    return render_template('operations.html', 
                         tenant=tenant,
                         summary=summary,
                         media_buys=media_buys,
                         tasks=tasks,
                         audit_logs=audit_logs)

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
        
        return redirect(url_for('tenant_detail', tenant_id=tenant_id) + '#principals')
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
                          f"company_id={request.form.get('company_id')}, "
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
                  request.form.get('company_id'),
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
        return redirect(url_for('tenant_detail', tenant_id=tenant_id) + '#adserver')
    except Exception as e:
        conn.close()
        flash(f'Error updating adapter configuration: {str(e)}', 'error')
        return redirect(url_for('tenant_detail', tenant_id=tenant_id) + '#adserver')

@app.route('/tenant/<tenant_id>/principals/create', methods=['GET', 'POST'])
@require_auth()
def create_principal(tenant_id):
    """Create a new principal for a tenant."""
    # Check access - only admins can create principals
    if session.get('role') in ['viewer']:
        return "Access denied. Admin or manager privileges required.", 403
        
    if session.get('role') in ['admin', 'manager', 'tenant_admin'] and session.get('tenant_id') != tenant_id:
        return "Access denied.", 403
    
    if request.method == 'POST':
        # Validate form data
        form_data = {
            'principal_id': request.form.get('principal_id', '').strip(),
            'name': request.form.get('name', '').strip()
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
        
        errors = validate_form_data(form_data, validators)
        if errors:
            return render_template('create_principal.html', 
                                 tenant_id=tenant_id,
                                 errors=errors,
                                 form_data=form_data)
        
        conn = get_db_connection()
        try:
            principal_id = form_data['principal_id']
            name = form_data['name']
            
            # Generate a secure access token
            access_token = secrets.token_urlsafe(32)
            
            # Create the principal
            conn.execute("""
                INSERT INTO principals (tenant_id, principal_id, name, platform_mappings, access_token)
                VALUES (?, ?, ?, ?, ?)
            """, (tenant_id, principal_id, name, json.dumps({}), access_token))
            
            conn.connection.commit()
            conn.close()
            
            return redirect(url_for('tenant_detail', tenant_id=tenant_id) + '#principals')
        except Exception as e:
            conn.close()
            return render_template('create_principal.html', 
                                 tenant_id=tenant_id,
                                 error=str(e))
    
    return render_template('create_principal.html', tenant_id=tenant_id)

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
    
    # Get tenant and config
    cursor = conn.execute("SELECT name, config FROM tenants WHERE tenant_id = ?", (tenant_id,))
    row = cursor.fetchone()
    tenant_name = row[0]
    config_data = row[1]
    # PostgreSQL returns JSONB as dict, SQLite returns string
    tenant_config = config_data if isinstance(config_data, dict) else json.loads(config_data)
    
    # Get active adapter and its UI endpoint
    adapter_ui_endpoint = None
    adapters = tenant_config.get('adapters', {})
    for adapter_name, config in adapters.items():
        if config.get('enabled'):
            # Create dummy principal to get UI endpoint
            dummy_principal = Principal(
                tenant_id=tenant_id,
                principal_id="ui_query",
                name="UI Query",
                access_token="",
                platform_mappings={}
            )
            
            try:
                if adapter_name == 'google_ad_manager':
                    from adapters.google_ad_manager import GoogleAdManager
                    adapter = GoogleAdManager(config, dummy_principal, dry_run=True, tenant_id=tenant_id)
                    adapter_ui_endpoint = adapter.get_config_ui_endpoint()
                elif adapter_name == 'mock':
                    from adapters.mock_ad_server import MockAdServer
                    adapter = MockAdServer(config, dummy_principal, dry_run=True, tenant_id=tenant_id)
                    adapter_ui_endpoint = adapter.get_config_ui_endpoint()
                # Add other adapters as needed
            except:
                pass
            break
    
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
    
    # Get tenant info and config
    cursor = conn.execute("SELECT name, config FROM tenants WHERE tenant_id = ?", (tenant_id,))
    tenant = cursor.fetchone()
    if not tenant:
        conn.close()
        return "Tenant not found", 404
    
    tenant_name, config_str = tenant
    config = parse_json_config(config_str)
    
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
        
        # Process and return relevant data
        return jsonify({
            "audiences": inventory.get("audiences", []),
            "formats": inventory.get("creative_specs", []),
            "placements": inventory.get("placements", [])
        })
        
    except Exception as e:
        logger.error(f"Error analyzing ad server: {e}")
        # Return mock data on error
        return jsonify({
            "audiences": [
                {"id": "general", "name": "General Audience", "size": 5000000}
            ],
            "formats": [],
            "placements": []
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

@app.route('/api/tenant/<tenant_id>/gam/line-item/<line_item_id>')
@require_auth()
def get_gam_line_item(tenant_id, line_item_id):
    """Fetch detailed line item data from GAM."""
    try:
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
        
        # Get GAM client using the helper
        from gam_helper import get_ad_manager_client_for_tenant
        client = get_ad_manager_client_for_tenant(tenant_id)
        
        # Fetch the line item
        line_item_service = client.GetService('LineItemService')
        statement = (client.new_statement_builder()
                    .where('id = :lineItemId')
                    .with_bind_variable('lineItemId', int(line_item_id))
                    .limit(1))
        
        response = line_item_service.getLineItemsByStatement(statement.to_statement())
        
        if not response.get('results'):
            return jsonify({'error': 'Line item not found'}), 404
        
        line_item = response['results'][0]
        
        # Fetch the associated order
        order_service = client.GetService('OrderService')
        order_statement = (client.new_statement_builder()
                          .where('id = :orderId')
                          .with_bind_variable('orderId', line_item['orderId'])
                          .limit(1))
        order_response = order_service.getOrdersByStatement(order_statement.to_statement())
        order = order_response['results'][0] if order_response.get('results') else None
        
        # Fetch associated creatives
        lica_service = client.GetService('LineItemCreativeAssociationService')
        lica_statement = (client.new_statement_builder()
                         .where('lineItemId = :lineItemId')
                         .with_bind_variable('lineItemId', int(line_item_id)))
        lica_response = lica_service.getLineItemCreativeAssociationsByStatement(lica_statement.to_statement())
        creative_associations = lica_response.get('results', [])
        
        # Fetch creative details if any associations exist
        creatives = []
        if creative_associations:
            creative_service = client.GetService('CreativeService')
            creative_ids = [lica['creativeId'] for lica in creative_associations]
            creative_statement = (client.new_statement_builder()
                                 .where('id IN (:creativeIds)')
                                 .with_bind_variable('creativeIds', creative_ids))
            creative_response = creative_service.getCreativesByStatement(creative_statement.to_statement())
            creatives = creative_response.get('results', [])
        
        # Convert to JSON-serializable format
        from zeep.helpers import serialize_object
        line_item_data = serialize_object(line_item)
        order_data = serialize_object(order) if order else None
        creatives_data = [serialize_object(c) for c in creatives]
        
        # Build the comprehensive response
        result = {
            'line_item': line_item_data,
            'order': order_data,
            'creatives': creatives_data,
            'creative_associations': [serialize_object(ca) for ca in creative_associations],
            # Convert to our internal media product JSON format
            'media_product_json': convert_line_item_to_product_json(line_item_data, creatives_data)
        }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error fetching GAM line item: {str(e)}")
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

def convert_line_item_to_product_json(line_item, creatives):
    """Convert GAM line item to our internal media product JSON format."""
    # Extract targeting information
    targeting = line_item.get('targeting', {})
    
    # Build targeting overlay
    targeting_overlay = {}
    
    # Geographic targeting
    if targeting.get('geoTargeting'):
        geo = targeting['geoTargeting']
        if geo.get('targetedLocations'):
            countries = [loc.get('displayName', loc.get('id')) 
                        for loc in geo['targetedLocations'] 
                        if loc.get('type') == 'Country']
            if countries:
                targeting_overlay['geo_country_any_of'] = countries
        
        if geo.get('excludedLocations'):
            excluded_countries = [loc.get('displayName', loc.get('id')) 
                                for loc in geo['excludedLocations'] 
                                if loc.get('type') == 'Country']
            if excluded_countries:
                targeting_overlay['geo_country_none_of'] = excluded_countries
    
    # Device targeting
    if targeting.get('technologyTargeting'):
        tech = targeting['technologyTargeting']
        if tech.get('deviceCategoryTargeting'):
            devices = tech['deviceCategoryTargeting'].get('targetedDeviceCategories', [])
            device_types = []
            for device in devices:
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
        
        # Parse custom criteria - this is complex in GAM
        if custom.get('children'):
            for child in custom['children']:
                if child.get('keyId') and child.get('valueIds'):
                    # We'd need to look up the actual key/value names
                    # For now, just store the IDs
                    key_value_pairs[f'key_{child["keyId"]}'] = [f'value_{vid}' for vid in child['valueIds']]
        
        if key_value_pairs:
            targeting_overlay['key_value_pairs'] = key_value_pairs
    
    # Dayparting
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
    
    # Frequency cap
    if line_item.get('frequencyCaps'):
        freq_caps = line_item['frequencyCaps']
        if freq_caps:
            # Take the first frequency cap
            cap = freq_caps[0]
            if cap.get('maxImpressions') and cap.get('numTimeUnits'):
                # Convert to minutes
                time_unit = cap.get('timeUnit')
                num_units = cap.get('numTimeUnits', 1)
                
                minutes = num_units
                if time_unit == 'HOUR':
                    minutes = num_units * 60
                elif time_unit == 'DAY':
                    minutes = num_units * 60 * 24
                elif time_unit == 'WEEK':
                    minutes = num_units * 60 * 24 * 7
                
                targeting_overlay['frequency_cap'] = {
                    'suppress_minutes': minutes,
                    'scope': 'media_buy'
                }
    
    # Extract creative formats
    formats = []
    for creative in creatives:
        format_type = 'display'  # Default
        if creative.get('size'):
            size = creative['size']
            width = size.get('width', 0)
            height = size.get('height', 0)
            
            # Determine format based on creative type and size
            if 'VideoCreative' in creative.get('Creative.Type', ''):
                format_type = 'video'
            elif 'AudioCreative' in creative.get('Creative.Type', ''):
                format_type = 'audio'
            
            format_dict = {
                'format_id': f'{format_type}_{width}x{height}',
                'name': f'{format_type.title()} {width}x{height}',
                'type': format_type,
                'dimensions': {'width': width, 'height': height}
            }
            
            if format_dict not in formats:
                formats.append(format_dict)
    
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
                'creative_placeholders': line_item.get('creativePlaceholders', []),
                'status': line_item.get('status'),
                'start_datetime': line_item.get('startDateTime'),
                'end_datetime': line_item.get('endDateTime'),
                'units_bought': line_item.get('unitsBought'),
                'cost_type': line_item.get('costType'),
                'discount_type': line_item.get('discountType'),
                'allow_overbook': line_item.get('allowOverbook', False)
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
        import traceback
        print(f"Warning: Failed to register adapter routes: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    
    # Register adapter routes
    register_adapter_routes()
    
    # Register GAM inventory endpoints
    register_inventory_endpoints(app, db_session)
    
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
    
    # Run server
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))  # Match OAuth redirect URI
    # Debug mode off for production
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    
    print(f"DEBUG: FLASK_DEBUG={os.environ.get('FLASK_DEBUG')}, debug={debug}")
    print(f"Starting Admin UI with Google OAuth on port {port}")
    print(f"Redirect URI should be: http://localhost:{port}/auth/google/callback")
    
    if not SUPER_ADMIN_EMAILS and not SUPER_ADMIN_DOMAINS:
        print("\nWARNING: No super admin emails or domains configured!")
        print("Set SUPER_ADMIN_EMAILS='email1@example.com,email2@example.com' or")
        print("Set SUPER_ADMIN_DOMAINS='example.com,company.com' in environment variables")
    
    app.run(host='0.0.0.0', port=port, debug=debug)