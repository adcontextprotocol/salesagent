"""
Example integration code for Scope3 application to use the Super Admin API.

This demonstrates how the main Scope3 app would:
1. Handle OAuth flow to get GAM credentials
2. Create a new tenant via the Super Admin API
3. Redirect the user to their provisioned tenant
"""

import os
import requests
import secrets
from typing import Dict, Optional
from urllib.parse import quote


class AdCPTenantManager:
    """Manager for creating and managing AdCP tenants from Scope3 app."""
    
    def __init__(self, api_base_url: str, api_key: str):
        """
        Initialize the tenant manager.
        
        Args:
            api_base_url: Base URL of the AdCP Sales Agent (e.g., https://adcp.example.com)
            api_key: Super admin API key
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-Superadmin-API-Key': api_key,
            'Content-Type': 'application/json'
        }
    
    def create_gam_tenant(self, 
                         company_name: str,
                         refresh_token: str,
                         network_code: Optional[str] = None,
                         user_email: Optional[str] = None,
                         company_id: Optional[str] = None,
                         trafficker_id: Optional[str] = None) -> Dict:
        """
        Create a new tenant with Google Ad Manager configuration.
        
        Args:
            company_name: Name of the publisher company
            refresh_token: OAuth refresh token from GAM OAuth flow
            network_code: Optional GAM network code (can be set later in UI)
            user_email: Optional email of the user who will admin this tenant
            company_id: Optional GAM company ID
            trafficker_id: Optional GAM trafficker ID
            
        Returns:
            Dict containing tenant details including admin UI URL
        """
        # Generate a subdomain from company name
        subdomain = self._generate_subdomain(company_name)
        
        # Prepare tenant data - minimal required fields
        tenant_data = {
            "name": company_name,
            "subdomain": subdomain,
            "ad_server": "google_ad_manager",
            "gam_refresh_token": refresh_token,
            "billing_plan": "standard",
            "create_default_principal": True
        }
        
        # Add optional fields if provided
        if network_code:
            tenant_data["gam_network_code"] = network_code
            
        if user_email:
            tenant_data["authorized_emails"] = [user_email]
            # Extract domain from email for authorization
            email_domain = user_email.split('@')[1]
            tenant_data["authorized_domains"] = [email_domain]
        
        if company_id:
            tenant_data["gam_company_id"] = company_id
        if trafficker_id:
            tenant_data["gam_trafficker_id"] = trafficker_id
        
        # Create tenant via API
        response = requests.post(
            f"{self.api_base_url}/api/v1/superadmin/tenants",
            headers=self.headers,
            json=tenant_data
        )
        
        if response.status_code != 201:
            raise Exception(f"Failed to create tenant: {response.status_code} - {response.text}")
        
        return response.json()
    
    def create_minimal_gam_tenant(self, company_name: str, refresh_token: str) -> Dict:
        """
        Create a minimal GAM tenant with just the refresh token.
        The publisher can configure everything else in the Admin UI.
        
        Args:
            company_name: Name of the publisher company
            refresh_token: OAuth refresh token from GAM OAuth flow
            
        Returns:
            Dict containing tenant details including admin UI URL
        """
        return self.create_gam_tenant(
            company_name=company_name,
            refresh_token=refresh_token
        )
    
    def get_tenant_status(self, tenant_id: str) -> Dict:
        """Check the status of a tenant."""
        response = requests.get(
            f"{self.api_base_url}/api/v1/superadmin/tenants/{tenant_id}",
            headers=self.headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get tenant: {response.status_code} - {response.text}")
        
        return response.json()
    
    def update_gam_refresh_token(self, tenant_id: str, new_refresh_token: str) -> Dict:
        """Update the GAM refresh token for a tenant (e.g., after re-auth)."""
        update_data = {
            "adapter_config": {
                "gam_refresh_token": new_refresh_token
            }
        }
        
        response = requests.put(
            f"{self.api_base_url}/api/v1/superadmin/tenants/{tenant_id}",
            headers=self.headers,
            json=update_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to update tenant: {response.status_code} - {response.text}")
        
        return response.json()
    
    def _generate_subdomain(self, company_name: str) -> str:
        """Generate a valid subdomain from company name."""
        # Simple implementation - in production, ensure uniqueness
        subdomain = company_name.lower()
        subdomain = ''.join(c if c.isalnum() else '-' for c in subdomain)
        subdomain = subdomain.strip('-')[:20]  # Max 20 chars
        
        # Add random suffix to ensure uniqueness
        subdomain = f"{subdomain}-{secrets.token_hex(3)}"
        
        return subdomain


# Example 1: Minimal setup - let publisher configure in Admin UI
def handle_gam_oauth_callback_minimal(request):
    """
    Minimal OAuth callback - just capture refresh token.
    Publisher will configure network code and other settings in Admin UI.
    """
    # 1. Exchange authorization code for tokens
    oauth_tokens = exchange_auth_code_for_tokens(request.args.get('code'))
    refresh_token = oauth_tokens['refresh_token']
    
    # 2. Create AdCP tenant with minimal info
    tenant_manager = AdCPTenantManager(
        api_base_url=os.environ['ADCP_SERVER_URL'],
        api_key=os.environ['ADCP_SUPERADMIN_API_KEY']
    )
    
    try:
        tenant = tenant_manager.create_minimal_gam_tenant(
            company_name=request.form.get('company_name'),
            refresh_token=refresh_token
        )
        
        # 3. Store tenant info in your database
        save_tenant_to_db(
            scope3_account_id=request.user.account_id,
            adcp_tenant_id=tenant['tenant_id'],
            adcp_principal_token=tenant['default_principal_token'],
            admin_ui_url=tenant['admin_ui_url']
        )
        
        # 4. Redirect user to their AdCP admin UI to complete setup
        return redirect(tenant['admin_ui_url'])
        
    except Exception as e:
        return render_template('error.html', error=str(e))


# Example 2: Full setup - configure everything via API
def handle_gam_oauth_callback_full(request):
    """
    Full OAuth callback - capture all details and configure via API.
    This would be in your Scope3 app's OAuth callback handler.
    """
    # 1. Exchange authorization code for tokens
    # (Implementation depends on your OAuth library)
    oauth_tokens = exchange_auth_code_for_tokens(request.args.get('code'))
    refresh_token = oauth_tokens['refresh_token']
    
    # 2. Get user info and GAM network details
    user_info = get_user_info_from_oauth(oauth_tokens['access_token'])
    gam_info = get_gam_network_info(oauth_tokens['access_token'])
    
    # 3. Create AdCP tenant
    tenant_manager = AdCPTenantManager(
        api_base_url=os.environ['ADCP_SERVER_URL'],
        api_key=os.environ['ADCP_SUPERADMIN_API_KEY']
    )
    
    try:
        tenant = tenant_manager.create_gam_tenant(
            company_name=request.form.get('company_name'),
            refresh_token=refresh_token,
            network_code=gam_info['network_code'],
            user_email=user_info['email'],
            company_id=gam_info.get('company_id'),
            trafficker_id=gam_info.get('trafficker_id')
        )
        
        # 4. Store tenant info in your database
        save_tenant_to_db(
            scope3_account_id=request.user.account_id,
            adcp_tenant_id=tenant['tenant_id'],
            adcp_principal_token=tenant['default_principal_token'],
            admin_ui_url=tenant['admin_ui_url']
        )
        
        # 5. Redirect user to their AdCP admin UI
        return redirect(tenant['admin_ui_url'])
        
    except Exception as e:
        # Handle error appropriately
        return render_template('error.html', error=str(e))


# Example: Periodic token refresh job
def refresh_gam_tokens_job():
    """
    Background job to refresh GAM tokens before they expire.
    Run this periodically (e.g., daily) to keep tokens fresh.
    """
    tenant_manager = AdCPTenantManager(
        api_base_url=os.environ['ADCP_SERVER_URL'],
        api_key=os.environ['ADCP_SUPERADMIN_API_KEY']
    )
    
    # Get all tenants with GAM from your database
    tenants = get_all_gam_tenants_from_db()
    
    for tenant in tenants:
        try:
            # Check if token needs refresh (implement your logic)
            if needs_token_refresh(tenant.last_refreshed):
                # Use Google OAuth library to refresh the token
                new_tokens = refresh_google_tokens(tenant.current_refresh_token)
                
                # Update in AdCP
                tenant_manager.update_gam_refresh_token(
                    tenant_id=tenant.adcp_tenant_id,
                    new_refresh_token=new_tokens['refresh_token']
                )
                
                # Update in your database
                update_tenant_tokens(tenant.id, new_tokens)
                
        except Exception as e:
            # Log error and continue with next tenant
            log_error(f"Failed to refresh token for tenant {tenant.id}: {e}")


# Helper functions (implement based on your stack)
def exchange_auth_code_for_tokens(auth_code: str) -> Dict:
    """Exchange OAuth authorization code for tokens."""
    # Implementation depends on your OAuth library
    pass

def get_user_info_from_oauth(access_token: str) -> Dict:
    """Get user info using OAuth access token."""
    # Implementation depends on your OAuth library
    pass

def get_gam_network_info(access_token: str) -> Dict:
    """Get GAM network info using OAuth access token."""
    # Use Google Ads API to get network details
    pass

def save_tenant_to_db(scope3_account_id: str, adcp_tenant_id: str, 
                     adcp_principal_token: str, admin_ui_url: str):
    """Save AdCP tenant info to Scope3 database."""
    # Implementation depends on your database/ORM
    pass

def get_all_gam_tenants_from_db():
    """Get all tenants using GAM from database."""
    # Implementation depends on your database/ORM
    pass

def needs_token_refresh(last_refreshed) -> bool:
    """Check if token needs refreshing."""
    # Google OAuth tokens typically last 1 hour
    # Refresh tokens don't expire but it's good to rotate them
    pass

def refresh_google_tokens(refresh_token: str) -> Dict:
    """Refresh Google OAuth tokens."""
    # Implementation depends on your OAuth library
    pass

def update_tenant_tokens(tenant_id: str, new_tokens: Dict):
    """Update tenant tokens in database."""
    # Implementation depends on your database/ORM
    pass

def log_error(message: str):
    """Log error message."""
    # Implementation depends on your logging setup
    pass