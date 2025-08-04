"""Configuration loader for multi-tenant setup - Version 2 using database fields."""

import os
import json
from typing import Dict, Any, Optional
from contextvars import ContextVar
from db_config import get_db_connection

# Thread-safe tenant context
current_tenant: ContextVar[Optional[Dict[str, Any]]] = ContextVar('current_tenant', default=None)

def get_current_tenant() -> Dict[str, Any]:
    """Get current tenant from context."""
    tenant = current_tenant.get()
    if not tenant:
        # Fallback for CLI/testing - use default tenant
        tenant = get_default_tenant()
        if not tenant:
            raise RuntimeError("No tenant in context and no default tenant found")
    return tenant

def get_default_tenant() -> Optional[Dict[str, Any]]:
    """Get the default tenant for CLI/testing."""
    try:
        conn = get_db_connection()
        
        # Get first active tenant or specific default
        cursor = conn.execute("""
            SELECT t.tenant_id, t.name, t.subdomain, t.ad_server, 
                   t.max_daily_budget, t.enable_aee_signals,
                   t.authorized_emails, t.authorized_domains,
                   t.slack_webhook_url, t.admin_token,
                   t.auto_approve_formats, t.human_review_required,
                   ac.adapter_type, ac.mock_dry_run,
                   ac.gam_network_code, ac.gam_refresh_token,
                   ac.gam_company_id, ac.gam_trafficker_id,
                   ac.gam_manual_approval_required,
                   ac.kevel_network_id, ac.kevel_api_key,
                   ac.kevel_manual_approval_required,
                   ac.triton_station_id, ac.triton_api_key
            FROM tenants t
            LEFT JOIN adapter_config ac ON t.tenant_id = ac.tenant_id
            WHERE t.is_active = ? 
            ORDER BY 
                CASE WHEN t.tenant_id = 'default' THEN 0 ELSE 1 END,
                t.created_at 
            LIMIT 1
        """, (True,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'tenant_id': row[0],
                'name': row[1],
                'subdomain': row[2],
                'ad_server': row[3],
                'max_daily_budget': row[4],
                'enable_aee_signals': row[5],
                'authorized_emails': json.loads(row[6]) if row[6] else [],
                'authorized_domains': json.loads(row[7]) if row[7] else [],
                'slack_webhook_url': row[8],
                'admin_token': row[9],
                'auto_approve_formats': json.loads(row[10]) if row[10] else [],
                'human_review_required': row[11],
                'adapter_config': build_adapter_config(row)
            }
        return None
    except Exception as e:
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise

def build_adapter_config(row) -> Dict[str, Any]:
    """Build adapter configuration from database row."""
    if not row[12]:  # adapter_type
        return {}
    
    adapter_type = row[12]
    config = {
        'adapter_type': adapter_type,
        'enabled': True
    }
    
    if adapter_type == 'mock':
        config['dry_run'] = row[13] or False
        
    elif adapter_type == 'google_ad_manager':
        config.update({
            'network_code': row[14],
            'refresh_token': row[15],
            'company_id': row[16],
            'trafficker_id': row[17],
            'manual_approval_required': row[18] or False
        })
        
    elif adapter_type == 'kevel':
        config.update({
            'network_id': row[19],
            'api_key': row[20],
            'manual_approval_required': row[21] or False
        })
        
    elif adapter_type == 'triton':
        config.update({
            'station_id': row[22],
            'api_key': row[23]
        })
    
    return config

def load_config() -> Dict[str, Any]:
    """
    Load configuration from current tenant.
    
    This version uses the new database fields instead of the config JSON.
    """
    tenant = get_current_tenant()
    
    # Build config dict for backward compatibility
    config = {
        'features': {
            'max_daily_budget': tenant['max_daily_budget'],
            'enable_aee_signals': tenant['enable_aee_signals']
        },
        'creative_engine': {
            'auto_approve_formats': tenant['auto_approve_formats'],
            'human_review_required': tenant['human_review_required']
        },
        'admin_token': tenant['admin_token']
    }
    
    # Add authorization settings if present
    if tenant['authorized_emails']:
        config['authorized_emails'] = tenant['authorized_emails']
    if tenant['authorized_domains']:
        config['authorized_domains'] = tenant['authorized_domains']
    
    # Add Slack integration if configured
    if tenant['slack_webhook_url']:
        config['integrations'] = {
            'slack': {
                'webhook_url': tenant['slack_webhook_url']
            }
        }
    
    # Add adapter configuration
    if tenant['ad_server'] and tenant['adapter_config']:
        adapter_config = tenant['adapter_config'].copy()
        adapter_config['enabled'] = True
        config['adapters'] = {
            tenant['ad_server']: adapter_config
        }
        
        # Also set ad_server for backward compatibility
        config['ad_server'] = {
            'adapter': tenant['ad_server'],
            **adapter_config
        }
    
    # Apply environment variable overrides (for development/testing)
    if gemini_key := os.environ.get('GEMINI_API_KEY'):
        config['gemini_api_key'] = gemini_key
    
    # System-level overrides
    if dry_run := os.environ.get('ADCP_DRY_RUN'):
        config['dry_run'] = dry_run.lower() == 'true'
    
    return config

def get_tenant_config(key: str, default=None):
    """Get config value for current tenant."""
    tenant = get_current_tenant()
    
    # Map common keys to new structure
    key_map = {
        'features.max_daily_budget': 'max_daily_budget',
        'features.enable_aee_signals': 'enable_aee_signals',
        'creative_engine.auto_approve_formats': 'auto_approve_formats',
        'creative_engine.human_review_required': 'human_review_required',
        'admin_token': 'admin_token',
        'authorized_emails': 'authorized_emails',
        'authorized_domains': 'authorized_domains'
    }
    
    # Check if it's a mapped key
    if key in key_map:
        return tenant.get(key_map[key], default)
    
    # For adapter-specific keys
    if key.startswith('adapters.'):
        parts = key.split('.')
        if len(parts) >= 3 and tenant.get('ad_server') == parts[1]:
            adapter_key = '.'.join(parts[2:])
            if adapter_key in tenant.get('adapter_config', {}):
                return tenant['adapter_config'][adapter_key]
    
    # For nested config keys (backward compatibility)
    config = load_config()
    keys = key.split('.')
    value = config
    
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    
    return value

def get_adapter_config_for_principal(principal) -> Dict[str, Any]:
    """
    Get adapter configuration for a principal's tenant.
    
    This is used by the adapter instantiation code.
    """
    tenant = get_current_tenant()
    
    if not tenant['ad_server'] or not tenant['adapter_config']:
        # Default to mock if no adapter configured
        return {
            'adapter_type': 'mock',
            'enabled': True,
            'dry_run': False
        }
    
    return tenant['adapter_config']