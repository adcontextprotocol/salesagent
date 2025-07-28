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
    conn = get_db_connection()
    
    # Get first active tenant or specific default
    cursor = conn.execute("""
        SELECT tenant_id, name, subdomain, config 
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
            'config': json.loads(row[3])
        }
    return None

def load_config() -> Dict[str, Any]:
    """
    Load configuration from current tenant.
    
    For backward compatibility, this returns config in the old format.
    In multi-tenant mode, config comes from database.
    """
    tenant = get_current_tenant()
    config = tenant['config'].copy()
    
    # Map tenant config to old format for compatibility
    if 'adapters' in config:
        # Extract primary adapter
        for adapter_name, adapter_config in config['adapters'].items():
            if adapter_config.get('enabled'):
                config['ad_server'] = {
                    'adapter': adapter_name,
                    **adapter_config
                }
                break
    
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
    
    # Navigate nested config
    keys = key.split('.')
    value = tenant['config']
    
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    
    return value

def set_current_tenant(tenant_dict: Dict[str, Any]):
    """Set the current tenant context."""
    current_tenant.set(tenant_dict)

def get_secret(key: str, default: str = None) -> str:
    """Get a secret from environment or config."""
    return os.environ.get(key, default)