"""Super Admin API for tenant management - Using direct SQL queries."""

from flask import Blueprint, request, jsonify
from functools import wraps
import secrets
import json
import uuid
from datetime import datetime
from database_session import get_db_session
from models import SuperadminConfig, Tenant, Principal
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
        with get_db_session() as db_session:
            config = db_session.query(SuperadminConfig).filter_by(
                config_key='superadmin_api_key'
            ).first()
            
            if not config or not config.config_value:
                logger.error("Superadmin API key not configured in database")
                return jsonify({'error': 'API not configured'}), 503
            
            if api_key != config.config_value:
                logger.warning(f"Invalid superadmin API key attempted: {api_key[:8]}...")
                return jsonify({'error': 'Invalid API key'}), 401
            
            return f(*args, **kwargs)
    
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
    from models import AdapterConfig
    from sqlalchemy import func
    
    with get_db_session() as db_session:
        try:
            # Query with left join and group by
            tenants_query = (
                db_session.query(
                    Tenant.tenant_id,
                    Tenant.name,
                    Tenant.subdomain,
                    Tenant.is_active,
                    Tenant.billing_plan,
                    Tenant.ad_server,
                    Tenant.created_at,
                    func.count(AdapterConfig.tenant_id).label('has_adapter')
                )
                .outerjoin(AdapterConfig, Tenant.tenant_id == AdapterConfig.tenant_id)
                .group_by(Tenant.tenant_id)
                .order_by(Tenant.created_at.desc())
            )
            
            results = []
            for row in tenants_query:
                results.append({
                    'tenant_id': row.tenant_id,
                    'name': row.name,
                    'subdomain': row.subdomain,
                    'is_active': bool(row.is_active),
                    'billing_plan': row.billing_plan,
                    'ad_server': row.ad_server,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'adapter_configured': bool(row.has_adapter)
                })
            
            return jsonify({
                'tenants': results,
                'count': len(results)
            })
            
        except Exception as e:
            logger.error(f"Error listing tenants: {str(e)}")
            return jsonify({'error': 'Failed to list tenants'}), 500


@superadmin_api.route('/tenants', methods=['POST'])
@require_superadmin_api_key
def create_tenant():
    """Create a new tenant."""
    from models import AdapterConfig
    from datetime import timezone
    
    with get_db_session() as db_session:
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
        
            # Create tenant
            new_tenant = Tenant(
                tenant_id=tenant_id,
                name=data['name'],
                subdomain=data['subdomain'],
                ad_server=data['ad_server'],
                is_active=data.get('is_active', True),
                billing_plan=data.get('billing_plan', 'standard'),
                billing_contact=data.get('billing_contact'),
                max_daily_budget=data.get('max_daily_budget', 10000),
                enable_aee_signals=data.get('enable_aee_signals', True),
                authorized_emails=json.dumps(data.get('authorized_emails', [])),
                authorized_domains=json.dumps(data.get('authorized_domains', [])),
                slack_webhook_url=data.get('slack_webhook_url'),
                slack_audit_webhook_url=data.get('slack_audit_webhook_url'),
                hitl_webhook_url=data.get('hitl_webhook_url'),
                admin_token=admin_token,
                auto_approve_formats=json.dumps(data.get('auto_approve_formats', ['display_300x250'])),
                human_review_required=data.get('human_review_required', True),
                policy_settings=json.dumps(data.get('policy_settings', {})),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db_session.add(new_tenant)
        
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
    with get_db_session() as db_session:
        try:
            # Get tenant details
            tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
            
            if not tenant:
                return jsonify({'error': 'Tenant not found'}), 404
            
            result = {
                'tenant_id': tenant.tenant_id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'is_active': bool(tenant.is_active),
                'billing_plan': tenant.billing_plan,
                'billing_contact': tenant.billing_contact,
                'ad_server': tenant.ad_server,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
                'settings': {
                    'max_daily_budget': tenant.max_daily_budget,
                    'enable_aee_signals': bool(tenant.enable_aee_signals),
                    'authorized_emails': json.loads(tenant.authorized_emails) if tenant.authorized_emails else [],
                    'authorized_domains': json.loads(tenant.authorized_domains) if tenant.authorized_domains else [],
                    'slack_webhook_url': tenant.slack_webhook_url,
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
    from datetime import timezone
    
    with get_db_session() as db_session:
        try:
            # Check if API key already exists
            existing_config = db_session.query(SuperadminConfig).filter_by(
                config_key='superadmin_api_key'
            ).first()
            
            if existing_config:
                return jsonify({'error': 'API key already initialized'}), 409
            
            # Generate new API key
            api_key = f"sk-{secrets.token_urlsafe(32)}"
            
            # Store in database
            new_config = SuperadminConfig(
                config_key='superadmin_api_key',
                config_value=api_key,
                description='Super admin API key for tenant management',
                updated_at=datetime.now(timezone.utc),
                updated_by='system'
            )
            db_session.add(new_config)
            db_session.commit()
            
            return jsonify({
                'message': 'Super admin API key initialized',
                'api_key': api_key,
                'warning': 'Save this key securely. It cannot be retrieved again.'
            }), 201
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error initializing API key: {str(e)}")
            return jsonify({'error': 'Failed to initialize API key'}), 500