"""Super Admin API for tenant management - Using direct SQL queries."""

from flask import Blueprint, request, jsonify
from functools import wraps
import secrets
import json
import uuid
from datetime import datetime
from db_config import get_db_connection
import logging

logger = logging.getLogger(__name__)

# Create Blueprint
superadmin_api = Blueprint('superadmin_api', __name__, url_prefix='/api/v1/superadmin')


def require_superadmin_api_key(f):
    """Decorator to require super admin API key for access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-Superadmin-API-Key')
        
        if not api_key:
            return jsonify({'error': 'Missing API key'}), 401
        
        # Get the stored API key from database
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                "SELECT config_value FROM superadmin_config WHERE config_key = ?",
                ('superadmin_api_key',)
            )
            result = cursor.fetchone()
            
            if not result or not result[0]:
                logger.error("Superadmin API key not configured in database")
                return jsonify({'error': 'API not configured'}), 503
            
            if api_key != result[0]:
                logger.warning(f"Invalid superadmin API key attempted: {api_key[:8]}...")
                return jsonify({'error': 'Invalid API key'}), 401
            
            return f(*args, **kwargs)
        finally:
            conn.close()
    
    return decorated_function


@superadmin_api.route('/health', methods=['GET'])
@require_superadmin_api_key
def health_check():
    """Health check endpoint for the super admin API."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })


@superadmin_api.route('/tenants', methods=['GET'])
@require_superadmin_api_key
def list_tenants():
    """List all tenants."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT t.tenant_id, t.name, t.subdomain, t.is_active, 
                   t.billing_plan, t.ad_server, t.created_at,
                   COUNT(ac.tenant_id) as has_adapter
            FROM tenants t
            LEFT JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
            GROUP BY t.tenant_id
            ORDER BY t.created_at DESC
        """)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'tenant_id': row[0],
                'name': row[1],
                'subdomain': row[2],
                'is_active': bool(row[3]),
                'billing_plan': row[4],
                'ad_server': row[5],
                'created_at': row[6] if row[6] else None,
                'adapter_configured': bool(row[7])
            })
        
        return jsonify({
            'tenants': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error listing tenants: {str(e)}")
        return jsonify({'error': 'Failed to list tenants'}), 500
    finally:
        conn.close()


@superadmin_api.route('/tenants', methods=['POST'])
@require_superadmin_api_key
def create_tenant():
    """Create a new tenant."""
    conn = get_db_connection()
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'subdomain', 'ad_server']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Generate tenant ID
        tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
        admin_token = secrets.token_urlsafe(32)
        
        # Create tenant - using parameterized query for safety
        conn.execute("""
            INSERT INTO tenants (
                tenant_id, name, subdomain, ad_server, is_active,
                billing_plan, billing_contact, max_daily_budget,
                enable_aee_signals, authorized_emails, authorized_domains,
                slack_webhook_url, slack_audit_webhook_url, hitl_webhook_url,
                admin_token, auto_approve_formats, human_review_required,
                policy_settings, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant_id,
            data['name'],
            data['subdomain'],
            data['ad_server'],
            data.get('is_active', True),
            data.get('billing_plan', 'standard'),
            data.get('billing_contact'),
            data.get('max_daily_budget', 10000),
            data.get('enable_aee_signals', True),
            json.dumps(data.get('authorized_emails', [])),
            json.dumps(data.get('authorized_domains', [])),
            data.get('slack_webhook_url'),
            data.get('slack_audit_webhook_url'),
            data.get('hitl_webhook_url'),
            admin_token,
            json.dumps(data.get('auto_approve_formats', ['display_300x250'])),
            data.get('human_review_required', True),
            json.dumps(data.get('policy_settings', {})),
            datetime.utcnow(),
            datetime.utcnow()
        ))
        
        # Create adapter config
        adapter_type = data['ad_server']
        
        # Insert adapter config with appropriate fields based on type
        if adapter_type == 'google_ad_manager':
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, gam_network_code, gam_refresh_token,
                    gam_company_id, gam_trafficker_id, gam_manual_approval_required,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                adapter_type,
                data.get('gam_network_code'),
                data.get('gam_refresh_token'),
                data.get('gam_company_id'),
                data.get('gam_trafficker_id'),
                data.get('gam_manual_approval_required', False),
                datetime.utcnow(),
                datetime.utcnow()
            ))
        elif adapter_type == 'kevel':
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, kevel_network_id, kevel_api_key,
                    kevel_manual_approval_required, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                adapter_type,
                data.get('kevel_network_id'),
                data.get('kevel_api_key'),
                data.get('kevel_manual_approval_required', False),
                datetime.utcnow(),
                datetime.utcnow()
            ))
        elif adapter_type == 'triton':
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, triton_station_id, triton_api_key,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                adapter_type,
                data.get('triton_station_id'),
                data.get('triton_api_key'),
                datetime.utcnow(),
                datetime.utcnow()
            ))
        else:  # mock or other
            conn.execute("""
                INSERT INTO adapter_config (
                    tenant_id, adapter_type, mock_dry_run, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                tenant_id,
                adapter_type,
                data.get('mock_dry_run', False),
                datetime.utcnow(),
                datetime.utcnow()
            ))
        
        # Create default principal if requested
        principal_token = None
        if data.get('create_default_principal', True):
            principal_id = f"principal_{uuid.uuid4().hex[:8]}"
            principal_token = secrets.token_urlsafe(32)
            
            conn.execute("""
                INSERT INTO principals (
                    tenant_id, principal_id, name, platform_mappings,
                    access_token, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tenant_id,
                principal_id,
                f"{data['name']} Default Principal",
                json.dumps({}),
                principal_token,
                datetime.utcnow()
            ))
        
        conn.connection.commit()
        
        result = {
            'tenant_id': tenant_id,
            'name': data['name'],
            'subdomain': data['subdomain'],
            'admin_token': admin_token,
            'admin_ui_url': f"http://{data['subdomain']}.localhost:8001/tenant/{tenant_id}"
        }
        
        if principal_token:
            result['default_principal_token'] = principal_token
        
        return jsonify(result), 201
        
    except Exception as e:
        # Note: DatabaseConnection doesn't support rollback
        # Changes are not committed unless we explicitly call commit()
        if 'UNIQUE constraint failed: tenants.subdomain' in str(e):
            return jsonify({'error': 'Subdomain already exists'}), 409
        logger.error(f"Error creating tenant: {str(e)}")
        return jsonify({'error': f'Failed to create tenant: {str(e)}'}), 500
    finally:
        conn.close()


@superadmin_api.route('/tenants/<tenant_id>', methods=['GET'])
@require_superadmin_api_key
def get_tenant(tenant_id):
    """Get details for a specific tenant."""
    conn = get_db_connection()
    try:
        # Get tenant details
        cursor = conn.execute("""
            SELECT tenant_id, name, subdomain, is_active, billing_plan,
                   billing_contact, ad_server, created_at, updated_at,
                   max_daily_budget, enable_aee_signals, authorized_emails,
                   authorized_domains, slack_webhook_url, slack_audit_webhook_url,
                   hitl_webhook_url, auto_approve_formats, human_review_required,
                   policy_settings
            FROM tenants
            WHERE tenant_id = ?
        """, (tenant_id,))
        
        tenant = cursor.fetchone()
        if not tenant:
            return jsonify({'error': 'Tenant not found'}), 404
        
        result = {
            'tenant_id': tenant[0],
            'name': tenant[1],
            'subdomain': tenant[2],
            'is_active': bool(tenant[3]),
            'billing_plan': tenant[4],
            'billing_contact': tenant[5],
            'ad_server': tenant[6],
            'created_at': tenant[7],
            'updated_at': tenant[8],
            'settings': {
                'max_daily_budget': tenant[9],
                'enable_aee_signals': bool(tenant[10]),
                'authorized_emails': json.loads(tenant[11]) if tenant[11] else [],
                'authorized_domains': json.loads(tenant[12]) if tenant[12] else [],
                'slack_webhook_url': tenant[13],
                'slack_audit_webhook_url': tenant[14],
                'hitl_webhook_url': tenant[15],
                'auto_approve_formats': json.loads(tenant[16]) if tenant[16] else [],
                'human_review_required': bool(tenant[17]),
                'policy_settings': json.loads(tenant[18]) if tenant[18] else {}
            }
        }
        
        # Get adapter config
        cursor = conn.execute("""
            SELECT adapter_type, created_at, gam_network_code, gam_refresh_token,
                   gam_company_id, gam_trafficker_id, gam_manual_approval_required,
                   kevel_network_id, kevel_api_key, kevel_manual_approval_required,
                   triton_station_id, triton_api_key, mock_dry_run
            FROM adapter_config
            WHERE tenant_id = ?
        """, (tenant_id,))
        
        adapter = cursor.fetchone()
        if adapter:
            adapter_data = {
                'adapter_type': adapter[0],
                'created_at': adapter[1]
            }
            
            if adapter[0] == 'google_ad_manager':
                adapter_data.update({
                    'gam_network_code': adapter[2],
                    'has_refresh_token': bool(adapter[3]),
                    'gam_company_id': adapter[4],
                    'gam_trafficker_id': adapter[5],
                    'gam_manual_approval_required': bool(adapter[6])
                })
            elif adapter[0] == 'kevel':
                adapter_data.update({
                    'kevel_network_id': adapter[7],
                    'has_api_key': bool(adapter[8]),
                    'kevel_manual_approval_required': bool(adapter[9])
                })
            elif adapter[0] == 'triton':
                adapter_data.update({
                    'triton_station_id': adapter[10],
                    'has_api_key': bool(adapter[11])
                })
            elif adapter[0] == 'mock':
                adapter_data.update({
                    'mock_dry_run': bool(adapter[12])
                })
            
            result['adapter_config'] = adapter_data
        
        # Get principals count
        cursor = conn.execute(
            "SELECT COUNT(*) FROM principals WHERE tenant_id = ?",
            (tenant_id,)
        )
        result['principals_count'] = cursor.fetchone()[0]
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting tenant {tenant_id}: {str(e)}")
        return jsonify({'error': 'Failed to get tenant'}), 500
    finally:
        conn.close()


@superadmin_api.route('/tenants/<tenant_id>', methods=['PUT'])
@require_superadmin_api_key
def update_tenant(tenant_id):
    """Update a tenant."""
    conn = get_db_connection()
    try:
        # Check if tenant exists
        cursor = conn.execute(
            "SELECT tenant_id FROM tenants WHERE tenant_id = ?",
            (tenant_id,)
        )
        if not cursor.fetchone():
            return jsonify({'error': 'Tenant not found'}), 404
        
        data = request.get_json()
        
        # Build update query dynamically based on provided fields
        update_fields = []
        params = []
        
        # Basic fields
        if 'name' in data:
            update_fields.append('name = ?')
            params.append(data['name'])
        if 'is_active' in data:
            update_fields.append('is_active = ?')
            params.append(data['is_active'])
        if 'billing_plan' in data:
            update_fields.append('billing_plan = ?')
            params.append(data['billing_plan'])
        if 'billing_contact' in data:
            update_fields.append('billing_contact = ?')
            params.append(data['billing_contact'])
        
        # Settings fields
        if 'max_daily_budget' in data:
            update_fields.append('max_daily_budget = ?')
            params.append(data['max_daily_budget'])
        if 'enable_aee_signals' in data:
            update_fields.append('enable_aee_signals = ?')
            params.append(data['enable_aee_signals'])
        if 'authorized_emails' in data:
            update_fields.append('authorized_emails = ?')
            params.append(json.dumps(data['authorized_emails']))
        if 'authorized_domains' in data:
            update_fields.append('authorized_domains = ?')
            params.append(json.dumps(data['authorized_domains']))
        if 'slack_webhook_url' in data:
            update_fields.append('slack_webhook_url = ?')
            params.append(data['slack_webhook_url'])
        if 'slack_audit_webhook_url' in data:
            update_fields.append('slack_audit_webhook_url = ?')
            params.append(data['slack_audit_webhook_url'])
        if 'hitl_webhook_url' in data:
            update_fields.append('hitl_webhook_url = ?')
            params.append(data['hitl_webhook_url'])
        if 'auto_approve_formats' in data:
            update_fields.append('auto_approve_formats = ?')
            params.append(json.dumps(data['auto_approve_formats']))
        if 'human_review_required' in data:
            update_fields.append('human_review_required = ?')
            params.append(data['human_review_required'])
        if 'policy_settings' in data:
            update_fields.append('policy_settings = ?')
            params.append(json.dumps(data['policy_settings']))
        
        # Always update the updated_at timestamp
        update_fields.append('updated_at = ?')
        params.append(datetime.utcnow())
        
        # Add tenant_id to params
        params.append(tenant_id)
        
        if update_fields:
            query = f"UPDATE tenants SET {', '.join(update_fields)} WHERE tenant_id = ?"
            conn.execute(query, params)
        
        # Update adapter config if provided
        if 'adapter_config' in data:
            adapter_data = data['adapter_config']
            
            # Get current adapter type
            cursor = conn.execute(
                "SELECT adapter_type FROM adapter_config WHERE tenant_id = ?",
                (tenant_id,)
            )
            result = cursor.fetchone()
            
            if result:
                adapter_type = result[0]
                update_fields = []
                params = []
                
                if adapter_type == 'google_ad_manager':
                    if 'gam_network_code' in adapter_data:
                        update_fields.append('gam_network_code = ?')
                        params.append(adapter_data['gam_network_code'])
                    if 'gam_refresh_token' in adapter_data:
                        update_fields.append('gam_refresh_token = ?')
                        params.append(adapter_data['gam_refresh_token'])
                    if 'gam_company_id' in adapter_data:
                        update_fields.append('gam_company_id = ?')
                        params.append(adapter_data['gam_company_id'])
                    if 'gam_trafficker_id' in adapter_data:
                        update_fields.append('gam_trafficker_id = ?')
                        params.append(adapter_data['gam_trafficker_id'])
                    if 'gam_manual_approval_required' in adapter_data:
                        update_fields.append('gam_manual_approval_required = ?')
                        params.append(adapter_data['gam_manual_approval_required'])
                
                elif adapter_type == 'kevel':
                    if 'kevel_network_id' in adapter_data:
                        update_fields.append('kevel_network_id = ?')
                        params.append(adapter_data['kevel_network_id'])
                    if 'kevel_api_key' in adapter_data:
                        update_fields.append('kevel_api_key = ?')
                        params.append(adapter_data['kevel_api_key'])
                    if 'kevel_manual_approval_required' in adapter_data:
                        update_fields.append('kevel_manual_approval_required = ?')
                        params.append(adapter_data['kevel_manual_approval_required'])
                
                elif adapter_type == 'triton':
                    if 'triton_station_id' in adapter_data:
                        update_fields.append('triton_station_id = ?')
                        params.append(adapter_data['triton_station_id'])
                    if 'triton_api_key' in adapter_data:
                        update_fields.append('triton_api_key = ?')
                        params.append(adapter_data['triton_api_key'])
                
                elif adapter_type == 'mock':
                    if 'mock_dry_run' in adapter_data:
                        update_fields.append('mock_dry_run = ?')
                        params.append(adapter_data['mock_dry_run'])
                
                if update_fields:
                    update_fields.append('updated_at = ?')
                    params.append(datetime.utcnow())
                    params.append(tenant_id)
                    
                    query = f"UPDATE adapter_config SET {', '.join(update_fields)} WHERE tenant_id = ?"
                    conn.execute(query, params)
        
        conn.connection.commit()
        
        # Get updated timestamp
        cursor = conn.execute(
            "SELECT name, updated_at FROM tenants WHERE tenant_id = ?",
            (tenant_id,)
        )
        result = cursor.fetchone()
        
        return jsonify({
            'tenant_id': tenant_id,
            'name': result[0],
            'updated_at': result[1]
        })
        
    except Exception as e:
        # Note: DatabaseConnection doesn't support rollback
        # Changes are not committed unless we explicitly call commit()
        logger.error(f"Error updating tenant {tenant_id}: {str(e)}")
        return jsonify({'error': f'Failed to update tenant: {str(e)}'}), 500
    finally:
        conn.close()


@superadmin_api.route('/tenants/<tenant_id>', methods=['DELETE'])
@require_superadmin_api_key
def delete_tenant(tenant_id):
    """Delete a tenant (soft delete by default)."""
    conn = get_db_connection()
    try:
        # Check if tenant exists
        cursor = conn.execute(
            "SELECT tenant_id FROM tenants WHERE tenant_id = ?",
            (tenant_id,)
        )
        if not cursor.fetchone():
            return jsonify({'error': 'Tenant not found'}), 404
        
        # Soft delete by default
        hard_delete = request.args.get('hard_delete', 'false').lower() == 'true'
        
        if hard_delete:
            # Delete related records first due to foreign key constraints
            conn.execute("DELETE FROM adapter_config WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM principals WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM products WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM media_buys WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM tasks WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM audit_logs WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM users WHERE tenant_id = ?", (tenant_id,))
            
            # Finally delete the tenant
            conn.execute("DELETE FROM tenants WHERE tenant_id = ?", (tenant_id,))
            message = f'Tenant {tenant_id} permanently deleted'
        else:
            # Just mark as inactive
            conn.execute(
                "UPDATE tenants SET is_active = ?, updated_at = ? WHERE tenant_id = ?",
                (False, datetime.utcnow(), tenant_id)
            )
            message = f'Tenant {tenant_id} deactivated'
        
        conn.connection.commit()
        
        return jsonify({
            'message': message,
            'tenant_id': tenant_id
        })
        
    except Exception as e:
        # Note: DatabaseConnection doesn't support rollback
        # Changes are not committed unless we explicitly call commit()
        logger.error(f"Error deleting tenant {tenant_id}: {str(e)}")
        return jsonify({'error': f'Failed to delete tenant: {str(e)}'}), 500
    finally:
        conn.close()


@superadmin_api.route('/init-api-key', methods=['POST'])
def initialize_api_key():
    """Initialize the super admin API key (can only be done once)."""
    conn = get_db_connection()
    try:
        # Check if API key already exists
        cursor = conn.execute(
            "SELECT config_value FROM superadmin_config WHERE config_key = ?",
            ('superadmin_api_key',)
        )
        
        if cursor.fetchone():
            return jsonify({'error': 'API key already initialized'}), 409
        
        # Generate new API key
        api_key = f"sk-{secrets.token_urlsafe(32)}"
        
        # Store in database
        conn.execute("""
            INSERT INTO superadmin_config (
                config_key, config_value, description, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            'superadmin_api_key',
            api_key,
            'Super admin API key for tenant management',
            datetime.utcnow(),
            'system'
        ))
        
        conn.connection.commit()
        
        return jsonify({
            'message': 'Super admin API key initialized',
            'api_key': api_key,
            'warning': 'Save this key securely. It cannot be retrieved again.'
        }), 201
        
    except Exception as e:
        # Note: DatabaseConnection doesn't support rollback
        # Changes are not committed unless we explicitly call commit()
        logger.error(f"Error initializing API key: {str(e)}")
        return jsonify({'error': 'Failed to initialize API key'}), 500
    finally:
        conn.close()