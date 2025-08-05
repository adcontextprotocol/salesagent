"""Helper functions for Google Ad Manager OAuth integration."""

from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleads import ad_manager
from database import db_session
from models import Tenant, AdapterConfig, SuperadminConfig
import logging

logger = logging.getLogger(__name__)


def get_ad_manager_client_for_tenant(tenant_id: str) -> Optional[ad_manager.AdManagerClient]:
    """
    Get a Google Ad Manager client for a specific tenant using OAuth credentials.
    
    This function:
    1. Retrieves the tenant's GAM configuration (network code, refresh token, etc.)
    2. Gets the OAuth client credentials from superadmin config
    3. Creates OAuth2 credentials using the refresh token
    4. Returns an initialized AdManagerClient
    
    Args:
        tenant_id: The tenant ID to get the client for
        
    Returns:
        An initialized Google Ad Manager client, or None if configuration is missing
        
    Raises:
        ValueError: If required configuration is missing
        Exception: If OAuth token refresh fails
    """
    # Get tenant and adapter config
    tenant = db_session.query(Tenant).filter_by(tenant_id=tenant_id).first()
    if not tenant:
        raise ValueError(f"Tenant {tenant_id} not found")
    
    if tenant.ad_server != 'google_ad_manager':
        raise ValueError(f"Tenant {tenant_id} is not configured for Google Ad Manager (using {tenant.ad_server})")
    
    adapter_config = db_session.query(AdapterConfig).filter_by(tenant_id=tenant_id).first()
    if not adapter_config:
        raise ValueError(f"No adapter configuration found for tenant {tenant_id}")
    
    # Validate required GAM fields
    if not adapter_config.gam_network_code:
        raise ValueError(f"GAM network code not configured for tenant {tenant_id}")
    if not adapter_config.gam_refresh_token:
        raise ValueError(f"GAM refresh token not configured for tenant {tenant_id}")
    
    # Get OAuth client credentials from superadmin config
    client_id_config = db_session.query(SuperadminConfig).filter_by(config_key='gam_oauth_client_id').first()
    client_secret_config = db_session.query(SuperadminConfig).filter_by(config_key='gam_oauth_client_secret').first()
    
    if not client_id_config or not client_id_config.config_value:
        raise ValueError("GAM OAuth Client ID not configured in superadmin settings")
    if not client_secret_config or not client_secret_config.config_value:
        raise ValueError("GAM OAuth Client Secret not configured in superadmin settings")
    
    try:
        # Create OAuth2 credentials
        credentials = Credentials(
            None,  # No access token yet
            refresh_token=adapter_config.gam_refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id_config.config_value,
            client_secret=client_secret_config.config_value,
            scopes=['https://www.googleapis.com/auth/dfp']
        )
        
        # Refresh the access token if needed
        if not credentials.valid:
            logger.info(f"Refreshing access token for tenant {tenant_id}")
            credentials.refresh(Request())
        
        # Create and return the Ad Manager client
        client = ad_manager.AdManagerClient(
            credentials,
            adapter_config.gam_network_code,
            application_name=f"AdCP-Sales-Agent-{tenant.name}"
        )
        
        logger.info(f"Successfully created GAM client for tenant {tenant_id} (network: {adapter_config.gam_network_code})")
        return client
        
    except Exception as e:
        logger.error(f"Failed to create GAM client for tenant {tenant_id}: {str(e)}")
        raise


def test_gam_connection(tenant_id: str) -> dict:
    """
    Test the GAM connection for a tenant by making a simple API call.
    
    Args:
        tenant_id: The tenant ID to test
        
    Returns:
        A dict with 'success' boolean and 'message' string
    """
    try:
        client = get_ad_manager_client_for_tenant(tenant_id)
        if not client:
            return {'success': False, 'message': 'Failed to create GAM client'}
        
        # Try to get the network information as a test
        network_service = client.GetService('NetworkService')
        network = network_service.getCurrentNetwork()
        
        return {
            'success': True,
            'message': f'Successfully connected to GAM network: {network["displayName"]} (ID: {network["id"]})'
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'GAM connection test failed: {str(e)}'
        }


def get_gam_config_for_tenant(tenant_id: str) -> Optional[dict]:
    """
    Get the GAM configuration for a tenant.
    
    Args:
        tenant_id: The tenant ID
        
    Returns:
        A dict with GAM configuration, or None if not configured
    """
    adapter_config = db_session.query(AdapterConfig).filter_by(
        tenant_id=tenant_id,
        adapter_type='google_ad_manager'
    ).first()
    
    if not adapter_config:
        return None
    
    return {
        'network_code': adapter_config.gam_network_code,
        'has_refresh_token': bool(adapter_config.gam_refresh_token),
        'company_id': adapter_config.gam_company_id,
        'trafficker_id': adapter_config.gam_trafficker_id,
        'manual_approval_required': adapter_config.gam_manual_approval_required
    }