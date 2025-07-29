#!/usr/bin/env python3
"""Admin UI with Google OAuth2 authentication."""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import secrets
import json
import os
import uuid
from datetime import datetime
from functools import wraps
from authlib.integrations.flask_client import OAuth
from db_config import get_db_connection

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

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

# Load Google OAuth credentials
# First check environment variable, then look for any client_secret*.json file
oauth_creds_file = os.environ.get('GOOGLE_OAUTH_CREDENTIALS_FILE')

if not oauth_creds_file:
    # Look for any client_secret*.json file in the current directory
    import glob
    creds_files = glob.glob('client_secret*.json')
    if creds_files:
        oauth_creds_file = creds_files[0]

if oauth_creds_file and os.path.exists(oauth_creds_file):
    with open(oauth_creds_file) as f:
        creds = json.load(f)
        GOOGLE_CLIENT_ID = creds['web']['client_id']
        GOOGLE_CLIENT_SECRET = creds['web']['client_secret']
else:
    # Try environment variables as fallback
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# Super admin configuration from environment or config
SUPER_ADMIN_EMAILS = os.environ.get('SUPER_ADMIN_EMAILS', '').split(',') if os.environ.get('SUPER_ADMIN_EMAILS') else []
SUPER_ADMIN_DOMAINS = os.environ.get('SUPER_ADMIN_DOMAINS', '').split(',') if os.environ.get('SUPER_ADMIN_DOMAINS') else []

# Default super admin config if none provided
if not SUPER_ADMIN_EMAILS and not SUPER_ADMIN_DOMAINS:
    # You should set these via environment variables in production
    SUPER_ADMIN_EMAILS = []  # e.g., ['admin@example.com']
    SUPER_ADMIN_DOMAINS = []  # e.g., ['example.com']

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
    return render_template('login.html', tenant_id=None)

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
        
    return render_template('login.html', tenant_id=tenant_id, tenant_name=tenant[0])

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
        SELECT tenant_id, name, subdomain, is_active, billing_plan, created_at
        FROM tenants
        ORDER BY created_at DESC
    """)
    tenants = []
    for row in cursor.fetchall():
        # Convert datetime if it's a string
        created_at = row[5]
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
            'billing_plan': row[4],
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
        SELECT tenant_id, name, subdomain, config, is_active, billing_plan, created_at
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
        'billing_plan': row[5],
        'created_at': row[6]
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
    
    return render_template('tenant_detail.html', 
                         tenant=tenant, 
                         principals=principals,
                         products=products,
                         config_for_editing=config_for_editing)

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
        config = json.loads(request.form.get('config'))
        
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
        # Get current config
        conn = get_db_connection()
        cursor = conn.execute("SELECT config FROM tenants WHERE tenant_id = ?", (tenant_id,))
        config = cursor.fetchone()[0]
        if isinstance(config, str):
            config = json.loads(config)
        
        # Update Slack webhooks in features
        if 'features' not in config:
            config['features'] = {}
        
        slack_webhook = request.form.get('slack_webhook_url', '').strip()
        audit_webhook = request.form.get('slack_audit_webhook_url', '').strip()
        
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
                            "text": f"Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
    """Create a new tenant (super admin only)."""
    if request.method == 'POST':
        try:
            tenant_id = request.form['tenant_id'] or request.form['name'].lower().replace(' ', '_')
            subdomain = request.form['subdomain'] or tenant_id
            
            # Build config
            config = {
                "adapters": {},
                "creative_engine": {
                    "auto_approve_formats": ["display_300x250", "display_728x90"],
                    "human_review_required": request.form.get('human_review') == 'on'
                },
                "features": {
                    "max_daily_budget": int(request.form.get('max_daily_budget', 10000)),
                    "enable_aee_signals": request.form.get('enable_aee') == 'on'
                },
                "authorized_emails": [email.strip() for email in request.form.get('authorized_emails', '').split(',') if email.strip()],
                "authorized_domains": [domain.strip() for domain in request.form.get('authorized_domains', '').split(',') if domain.strip()]
            }
            
            # Add adapter config
            adapter = request.form.get('adapter')
            if adapter == 'mock':
                config['adapters']['mock'] = {'enabled': True}
            elif adapter == 'google_ad_manager':
                config['adapters']['google_ad_manager'] = {
                    'enabled': True,
                    'network_code': request.form.get('gam_network_code'),
                    'company_id': request.form.get('gam_company_id')
                }
            elif adapter == 'kevel':
                config['adapters']['kevel'] = {
                    'enabled': True,
                    'network_id': request.form.get('kevel_network_id'),
                    'api_key': request.form.get('kevel_api_key')
                }
            
            conn = get_db_connection()
            
            # Create tenant
            conn.execute("""
                INSERT INTO tenants (
                    tenant_id, name, subdomain, config,
                    created_at, updated_at, is_active, billing_plan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                request.form['name'],
                subdomain,
                json.dumps(config),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                True,
                request.form.get('billing_plan', 'standard')
            ))
            
            # Create admin principal
            admin_token = secrets.token_urlsafe(32)
            conn.execute("""
                INSERT INTO principals (
                    tenant_id, principal_id, name,
                    platform_mappings, access_token
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                tenant_id,
                f"{tenant_id}_admin",
                f"{request.form['name']} Admin",
                json.dumps({}),
                admin_token
            ))
            
            conn.connection.commit()
            conn.close()
            
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
        conn = get_db_connection()
        try:
            principal_id = request.form.get('principal_id')
            name = request.form.get('name')
            
            # Validate principal_id format
            if not principal_id or not principal_id.replace('_', '').isalnum():
                return render_template('create_principal.html', 
                                     tenant_id=tenant_id,
                                     error="Principal ID must contain only letters, numbers, and underscores")
            
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
    
    # Run server
    port = int(os.environ.get('ADMIN_UI_PORT', 8001))  # Match OAuth redirect URI
    # Debug mode off for production
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"Starting Admin UI with Google OAuth on port {port}")
    print(f"Redirect URI should be: http://localhost:{port}/auth/google/callback")
    
    if not SUPER_ADMIN_EMAILS and not SUPER_ADMIN_DOMAINS:
        print("\nWARNING: No super admin emails or domains configured!")
        print("Set SUPER_ADMIN_EMAILS='email1@example.com,email2@example.com' or")
        print("Set SUPER_ADMIN_DOMAINS='example.com,company.com' in environment variables")
    
    app.run(host='0.0.0.0', port=port, debug=debug)