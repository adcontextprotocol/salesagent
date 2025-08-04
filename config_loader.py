"""Configuration loader for multi-tenant setup."""

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
        
        # Get first active tenant or specific default with all fields
        cursor = conn.execute("""
            SELECT tenant_id, name, subdomain, ad_server, max_daily_budget,
                   enable_aee_signals, authorized_emails, authorized_domains,
                   slack_webhook_url, admin_token, auto_approve_formats,
                   human_review_required, slack_audit_webhook_url, hitl_webhook_url,
                   policy_settings
            FROM tenants 
            WHERE is_active = ? 
            ORDER BY 
                CASE WHEN tenant_id = 'default' THEN 0 ELSE 1 END,
                created_at 
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
                'slack_audit_webhook_url': row[12],
                'hitl_webhook_url': row[13],
                'policy_settings': json.loads(row[14]) if row[14] else None
            }
        return None
    except Exception as e:
        # If table doesn't exist or other DB errors, return None
        if "no such table" in str(e) or "does not exist" in str(e):
            return None
        raise

def load_config() -> Dict[str, Any]:
    """
    Load configuration from current tenant.
    
    For backward compatibility, this returns config in the old format.
    In multi-tenant mode, config comes from database.
    """
    tenant = get_current_tenant()
    
    # Build config from tenant fields
    config = {
        'ad_server': {'adapter': tenant.get('ad_server', 'mock'), 'enabled': True},
        'creative_engine': {
            'auto_approve_formats': tenant.get('auto_approve_formats', []),
            'human_review_required': tenant.get('human_review_required', True)
        },
        'features': {
            'max_daily_budget': tenant.get('max_daily_budget', 10000),
            'enable_aee_signals': tenant.get('enable_aee_signals', True),
            'slack_webhook_url': tenant.get('slack_webhook_url'),
            'slack_audit_webhook_url': tenant.get('slack_audit_webhook_url'),
            'hitl_webhook_url': tenant.get('hitl_webhook_url')
        },
        'admin_token': tenant.get('admin_token'),
        'dry_run': False
    }
    
    # Add policy settings if present
    if tenant.get('policy_settings'):
        config['policy_settings'] = tenant['policy_settings']
    
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
    
    # Check if it's a top-level tenant field
    if key in tenant:
        return tenant[key]
    
    # Otherwise return default
    return default

def set_current_tenant(tenant_dict: Dict[str, Any]):
    """Set the current tenant context."""
    current_tenant.set(tenant_dict)

def get_secret(key: str, default: str = None) -> str:
    """Get a secret from environment or config."""
    return os.environ.get(key, default)