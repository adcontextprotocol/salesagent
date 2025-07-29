#!/usr/bin/env python3
"""Simple web UI for managing AdCP Sales Agent tenants."""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import secrets
import json
from datetime import datetime
from functools import wraps
import os
from db_config import get_db_connection

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Auth configuration
SUPER_ADMIN_PASSWORD = os.environ.get('ADMIN_UI_PASSWORD', 'admin')

def require_auth(admin_only=False):
    """Decorator for authentication. 
    admin_only=True requires super admin access.
    admin_only=False allows both super admin and tenant admin access.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('authenticated'):
                return redirect(url_for('login'))
            
            # Check if super admin is required but user is tenant admin
            if admin_only and session.get('role') != 'super_admin':
                return "Access denied. Super admin required.", 403
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        # Check super admin login
        if username == 'admin' and password == SUPER_ADMIN_PASSWORD:
            session['authenticated'] = True
            session['role'] = 'super_admin'
            session['username'] = 'admin'
            return redirect(url_for('index'))
        
        # Check tenant admin login
        conn = get_db_connection()
        cursor = conn.execute("""
            SELECT tenant_id, name, config
            FROM tenants
            WHERE tenant_id = ? AND is_active = ?
        """, (username, True))
        
        tenant = cursor.fetchone()
        if tenant:
            # PostgreSQL returns JSONB as dict, SQLite as string
            config = tenant[2]
            if isinstance(config, str):
                config = json.loads(config)
            
            admin_token = config.get('admin_token', '')
            if admin_token and password == admin_token:
                session['authenticated'] = True
                session['role'] = 'tenant_admin'
                session['tenant_id'] = tenant[0]
                session['tenant_name'] = tenant[1]
                session['username'] = username
                conn.close()
                # Redirect tenant admins to their tenant page
                return redirect(url_for('tenant_detail', tenant_id=tenant[0]))
        
        conn.close()
        return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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

@app.route('/tenant/<tenant_id>')
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
    
    # Get principals
    cursor = conn.execute("""
        SELECT principal_id, name, access_token, created_at
        FROM principals WHERE tenant_id = ?
        ORDER BY created_at DESC
    """, (tenant_id,))
    principals = []
    for row in cursor.fetchall():
        principals.append({
            'principal_id': row[0],
            'name': row[1],
            'access_token': row[2],
            'created_at': row[3]
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
    
    conn.close()
    return render_template('tenant_detail.html', 
                         tenant=tenant, 
                         principals=principals,
                         products=products)

@app.route('/tenant/<tenant_id>/update', methods=['POST'])
@require_auth()
def update_tenant(tenant_id):
    """Update tenant configuration."""
    # Check if tenant admin is trying to update another tenant
    if session.get('role') == 'tenant_admin' and session.get('tenant_id') != tenant_id:
        return "Access denied. You can only update your own tenant.", 403
    
    conn = get_db_connection()
    
    try:
        config = json.loads(request.form.get('config'))
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
                "admin_token": secrets.token_urlsafe(32)
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
    
    # Run server
    port = int(os.environ.get('ADMIN_UI_PORT', 8081))
    # Debug mode off for production
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)