#!/usr/bin/env python3
"""Admin UI with Google OAuth2 authentication."""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory, g
import secrets
import json
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from authlib.integrations.flask_client import OAuth
from db_config import get_db_connection
from validation import FormValidator, validate_form_data, sanitize_form_data

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Import schemas after Flask app is created
from schemas import Principal

# Configure for being mounted at different paths
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
TEST_USERS = {
    'test_super_admin@example.com': {
        'name': 'Test Super Admin',
        'role': 'super_admin',
        'password': 'test123'  # Simple password for testing only
    },
    'test_tenant_admin@example.com': {
        'name': 'Test Tenant Admin', 
        'role': 'tenant_admin',
        'password': 'test123'
    },
    'test_tenant_user@example.com': {
        'name': 'Test Tenant User',
        'role': 'tenant_user', 
        'password': 'test123'
    }
}

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

def is_super_admin(email):
    """Check if email is authorized as super admin."""
    # Check explicit email list
    if email in SUPER_ADMIN_EMAILS:
        return True
    
    # Check domain
    domain = email.split('@')[1] if '@' in email else ''
    if domain and domain in SUPER_ADMIN_DOMAINS:
        return True
    
    return False

def is_tenant_admin(email, tenant_id=None):
    """Check if email is authorized for a specific tenant."""
    conn = get_db_connection()
    
    if tenant_id:
        # Check specific tenant
        cursor = conn.execute("""
            SELECT config
            FROM tenants
            WHERE tenant_id = ? AND is_active = ?
        """, (tenant_id, True))
        
        tenant = cursor.fetchone()
        if tenant:
            config = tenant[0]
            if isinstance(config, str):
                config = json.loads(config)
            
            # Check authorized emails
            authorized_emails = config.get('authorized_emails', [])
            if email in authorized_emails:
                conn.close()
                return True
            
            # Check authorized domains
            authorized_domains = config.get('authorized_domains', [])
            domain = email.split('@')[1] if '@' in email else ''
            if domain and domain in authorized_domains:
                conn.close()
                return True
    else:
        # Check all tenants to find which one(s) this email can access
        cursor = conn.execute("""
            SELECT tenant_id, name, config
            FROM tenants
            WHERE is_active = ?
        """, (True,))
        
        authorized_tenants = []
        for row in cursor.fetchall():
            tenant_id = row[0]
            tenant_name = row[1]
            config = row[2]
            if isinstance(config, str):
                config = json.loads(config)
            
            # Check authorized emails
            authorized_emails = config.get('authorized_emails', [])
            if email in authorized_emails:
                authorized_tenants.append((tenant_id, tenant_name))
                continue
            
            # Check authorized domains
            authorized_domains = config.get('authorized_domains', [])
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
    redirect_uri = url_for('tenant_google_callback', tenant_id=tenant_id, _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback for super admin."""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            return redirect(url_for('login'))
        
        email = user_info.get('email')
        if not email:
            return render_template('login.html', error='No email address provided by Google', tenant_id=None)
        
        # Check if super admin
        if is_super_admin(email):
            session['authenticated'] = True
            session['role'] = 'super_admin'
            session['email'] = email
            session['username'] = user_info.get('name', email)
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
        return render_template('login.html', error='Authentication failed', tenant_id=None)

@app.route('/tenant/<tenant_id>/auth/google/callback')
def tenant_google_callback(tenant_id):
    """Handle Google OAuth callback for specific tenant."""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            return redirect(url_for('tenant_login', tenant_id=tenant_id))
        
        email = user_info.get('email')
        if not email:
            return render_template('login.html', 
                                 error='No email address provided by Google',
                                 tenant_id=tenant_id)
        
        # First check if user is in the users table for this tenant
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT u.user_id, u.role, u.name, t.name as tenant_name, u.is_active
            FROM users u
            JOIN tenants t ON u.tenant_id = t.tenant_id
            WHERE u.email = ? AND u.tenant_id = ?
        """, (email, tenant_id))
        user_row = cursor.fetchone()
        
        # Update last login if user exists
        if user_row:
            user_id, user_role, user_name, tenant_name, is_active = user_row
            
            if not is_active:
                conn.close()
                return render_template('login.html', 
                                     error='Your account has been disabled',
                                     tenant_id=tenant_id)
            
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
            session['tenant_id'] = tenant_id
            session['tenant_name'] = tenant_name
            session['email'] = email
            session['username'] = user_name or user_info.get('name', email)
            session.pop('oauth_tenant_id', None)  # Clean up
            
            return redirect(url_for('tenant_detail', tenant_id=tenant_id))
        
        # If not in users table, check legacy tenant admin config
        if is_tenant_admin(email, tenant_id):
            # Get tenant name for session
            cursor = conn.execute("SELECT name FROM tenants WHERE tenant_id = ?", (tenant_id,))
            tenant = cursor.fetchone()
            conn.close()
            
            session['authenticated'] = True
            session['role'] = 'tenant_admin'  # Legacy role
            session['tenant_id'] = tenant_id
            session['tenant_name'] = tenant[0] if tenant else tenant_id
            session['email'] = email
            session['username'] = user_info.get('name', email)
            session.pop('oauth_tenant_id', None)  # Clean up
            
            return redirect(url_for('tenant_detail', tenant_id=tenant_id))
        
        conn.close()
        
        # Check if super admin trying to access tenant
        if is_super_admin(email):
            session['authenticated'] = True
            session['role'] = 'super_admin'
            session['email'] = email
            session['username'] = user_info.get('name', email)
            session.pop('oauth_tenant_id', None)  # Clean up
            
            # Super admin can access any tenant
            return redirect(url_for('tenant_detail', tenant_id=tenant_id))
        
        # Not authorized for this tenant
        return render_template('login.html', 
                             error=f'Email {email} is not authorized to access this tenant',
                             tenant_id=tenant_id)
        
    except Exception as e:
        app.logger.error(f"OAuth callback error: {e}")
        return render_template('login.html', 
                             error='Authentication failed',
                             tenant_id=tenant_id)

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
                    <input type="password" name="password" value="test123" required>
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

@app.route('/tenant/<tenant_id>/manage')
@require_auth()
def tenant_detail(tenant_id):
    """Show tenant details and configuration."""
    # Check if tenant admin is trying to access another tenant
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only view your own tenant.", 403
    
    conn = get_db_connection()
    
    # Get tenant
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, config, is_active, created_at
        FROM tenants WHERE tenant_id = ?
    """, (tenant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Tenant not found", 404
    
    # PostgreSQL returns JSONB as dict, SQLite as string
    config = row[3]
    if isinstance(config, str):
        config = json.loads(config)
    
    tenant = {
        'tenant_id': row[0],
        'name': row[1],
        'subdomain': row[2],
        'config': config,
        'is_active': row[4],
        'created_at': row[5]
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
    active_adapter = None
    for adapter_name, adapter_config in config.get('adapters', {}).items():
        if adapter_config.get('enabled'):
            active_adapter = adapter_name
            break
    
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
    
    # For the configuration tab, create a version without adapters
    config_for_editing = config.copy()
    if 'adapters' in config_for_editing:
        del config_for_editing['adapters']
    
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
                         config_for_editing=config_for_editing,
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
    
    # Validate JSON configuration
    config_json = request.form.get('config', '').strip()
    
    # Validate JSON
    json_error = FormValidator.validate_json(config_json)
    if json_error:
        flash(f"Configuration error: {json_error}", 'error')
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))
    
    conn = get_db_connection()
    
    try:
        config = json.loads(config_json)
        
        # Get current config to preserve certain settings
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        current_config = cursor.fetchone()[0]
        if isinstance(current_config, str):
            current_config = json.loads(current_config)
        
        # Always preserve adapter settings (managed via Ad Server Setup tab)
        if 'adapters' in current_config:
            config['adapters'] = current_config['adapters']
        
        # Preserve OAuth settings if not super admin
        if session.get('role') != 'super_admin':
            # Preserve authorization settings
            config['authorized_emails'] = current_config.get('authorized_emails', [])
            config['authorized_domains'] = current_config.get('authorized_domains', [])
        
        conn.execute("""
            UPDATE tenants 
            SET config = ?, updated_at = ?
            WHERE tenant_id = ?
        """, (json.dumps(config), datetime.now().isoformat(), tenant_id))
        conn.connection.commit()
        conn.close()
        return redirect(url_for('tenant_detail', tenant_id=tenant_id))
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

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
        
        # Get current config
        conn = get_db_connection()
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        config = cursor.fetchone()[0]
        if isinstance(config, str):
            config = json.loads(config)
        
        # Update Slack webhooks in features
        if 'features' not in config:
            config['features'] = {}
        
        slack_webhook = form_data['slack_webhook_url']
        audit_webhook = form_data['slack_audit_webhook_url']
        
        if slack_webhook:
            config['features']['slack_webhook_url'] = slack_webhook
        elif 'slack_webhook_url' in config['features']:
            del config['features']['slack_webhook_url']
            
        if audit_webhook:
            config['features']['slack_audit_webhook_url'] = audit_webhook
        elif 'slack_audit_webhook_url' in config['features']:
            del config['features']['slack_audit_webhook_url']
        
        # Save updated config
        conn.execute("""
            UPDATE tenants 
            SET config = ?, updated_at = ?
            WHERE tenant_id = ?
        """, (json.dumps(config), datetime.now().isoformat(), tenant_id))
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
            
            # Build minimal config - tenant will complete setup later
            config = {
                "adapters": {},
                "creative_engine": {
                    "auto_approve_formats": [],
                    "human_review_required": True
                },
                "features": {
                    "max_daily_budget": 10000,
                    "enable_aee_signals": True
                },
                "authorized_emails": authorized_emails,
                "authorized_domains": authorized_domains,
                "setup_complete": False  # Flag to track if tenant has completed setup
            }
            
            conn = get_db_connection()
            
            # Create tenant
            conn.execute("""
                INSERT INTO tenants (
                    tenant_id, name, subdomain, config,
                    created_at, updated_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                tenant_name,
                subdomain,
                json.dumps(config),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                True
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
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Tenant not found"}), 404
        
        config_data = row[0]
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
        # Get current config
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        config = cursor.fetchone()[0]
        if isinstance(config, str):
            config = json.loads(config)
        
        # Get adapter type
        adapter_type = request.form.get('adapter')
        if adapter_type not in ['mock', 'gam', 'kevel', 'triton']:
            return "Invalid adapter type", 400
        
        # Reset all adapters to disabled
        if 'adapters' not in config:
            config['adapters'] = {}
        
        for adapter in config['adapters']:
            config['adapters'][adapter]['enabled'] = False
        
        # Configure the selected adapter
        if adapter_type == 'mock':
            config['adapters']['mock'] = {
                'enabled': True,
                'dry_run': False
            }
        
        elif adapter_type == 'gam':
            config['adapters']['gam'] = {
                'enabled': True,
                'network_id': request.form.get('network_id'),
                'credentials': json.loads(request.form.get('credentials', '{}')),
                'api_version': 'v202411'
            }
        
        elif adapter_type == 'kevel':
            config['adapters']['kevel'] = {
                'enabled': True,
                'network_id': request.form.get('network_id'),
                'api_key': request.form.get('api_key')
            }
        
        elif adapter_type == 'triton':
            config['adapters']['triton'] = {
                'enabled': True,
                'station_id': request.form.get('station_id'),
                'api_key': request.form.get('api_key')
            }
        
        # Update the tenant config
        conn.execute("""
            UPDATE tenants 
            SET config = ?, updated_at = ?
            WHERE tenant_id = ?
        """, (json.dumps(config), datetime.now().isoformat(), tenant_id))
        
        conn.connection.commit()
        conn.close()
        
        return redirect(url_for('tenant_detail', tenant_id=tenant_id) + '#adserver')
    except Exception as e:
        conn.close()
        return f"Error: {e}", 400

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
def health():
    """Health check endpoint."""
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "healthy"})
    except:
        return jsonify({"status": "unhealthy"}), 500

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
            cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
            config_data = cursor.fetchone()[0]
            # PostgreSQL returns JSONB as dict, SQLite returns string
            tenant_config = config_data if isinstance(config_data, dict) else json.loads(config_data)
            
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
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        config_row = cursor.fetchone()
        conn.close()
        
        if not config_row:
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
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        config_row = cursor.fetchone()
        if not config_row:
            return jsonify({"error": "Tenant not found"}), 404
        
        config = config_row[0] if isinstance(config_row[0], dict) else json.loads(config_row[0])
        
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

# Function to register adapter routes
def register_adapter_routes():
    """Register UI routes from all available adapters."""
    try:
        print("Starting adapter route registration...")
        # Get all enabled adapters across all tenants
        conn = get_db_connection()
        cursor = conn.execute("SELECT config FROM tenants")
        
        registered_adapters = set()
        for row in cursor.fetchall():
            print(f"Processing row: {type(row)}")
            # Handle both tuple (PostgreSQL) and Row object (SQLite)
            config_data = row[0] if isinstance(row, tuple) else row['config']
            print(f"Config data type: {type(config_data)}")
            # PostgreSQL returns JSONB as dict, SQLite returns string
            tenant_config = config_data if isinstance(config_data, dict) else json.loads(config_data)
            print(f"Tenant config type: {type(tenant_config)}")
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