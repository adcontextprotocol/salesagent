import pytest
from playwright.async_api import Page
from ..pages.tenant_page import TenantPage
from ..utils.auth_helper import AuthHelper
from ..utils.test_data import TestDataGenerator, TestConstants

class TestTenantManagement:
    """Test tenant management functionality."""
    
    @pytest.mark.asyncio
    async def test_create_tenant(self, page: Page, base_url: str):
        """Test creating a new tenant."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        
        # Navigate to tenants page
        await tenant_page.goto_tenants()
        
        # Click create tenant
        await tenant_page.click_create_tenant()
        
        # Generate test data
        tenant_name = TestDataGenerator.generate_tenant_name()
        subdomain = TestDataGenerator.generate_subdomain()
        
        # Fill form
        await tenant_page.fill_tenant_form(
            name=tenant_name,
            subdomain=subdomain,
            billing_plan="standard"
        )
        
        # Select adapters
        await tenant_page.select_adapters(["mock", "google_ad_manager"])
        
        # Submit form
        await tenant_page.submit_form()
        
        # Verify success
        success_msg = await tenant_page.wait_for_success_message()
        assert TestConstants.SUCCESS_MESSAGES["tenant_created"] in success_msg
        
        # Verify tenant appears in list
        tenants = await tenant_page.get_tenant_list()
        assert any(t['name'] == tenant_name for t in tenants)
    
    @pytest.mark.asyncio
    async def test_view_tenant_details(self, page: Page, base_url: str):
        """Test viewing tenant details."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        
        # Navigate to tenants page
        await tenant_page.goto_tenants()
        
        # Get first tenant from list
        tenants = await tenant_page.get_tenant_list()
        assert len(tenants) > 0
        
        first_tenant = tenants[0]
        
        # Click on tenant
        await tenant_page.click_tenant(first_tenant['name'])
        
        # Verify on tenant detail page
        await page.wait_for_url(f"**/tenant/**")
        
        # Verify tenant information displayed
        assert await page.is_visible('h2:has-text("Tenant Details")')
        assert first_tenant['name'] in await page.content()
    
    @pytest.mark.asyncio
    async def test_create_principal(self, page: Page, base_url: str):
        """Test creating a principal (advertiser) for a tenant."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        # Navigate to first tenant
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        
        tenants = await tenant_page.get_tenant_list()
        assert len(tenants) > 0
        
        await tenant_page.click_tenant(tenants[0]['name'])
        
        # Click create principal
        await page.click('a:has-text("Create Principal")')
        
        # Generate principal data
        principal_data = TestDataGenerator.generate_principal_data()
        
        # Fill principal form
        await page.fill('input[name="name"]', principal_data['name'])
        await page.fill('input[name="email"]', principal_data['email'])
        
        # Submit
        await page.click('button[type="submit"]')
        
        # Verify success
        await page.wait_for_selector('.success-message')
        
        # Verify principal appears in list
        assert principal_data['name'] in await page.content()
    
    @pytest.mark.asyncio
    async def test_duplicate_subdomain_error(self, page: Page, base_url: str):
        """Test error handling for duplicate subdomain."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        
        # Get existing tenant subdomain
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No existing tenants to test duplicate subdomain")
        
        existing_subdomain = tenants[0]['subdomain']
        
        # Try to create tenant with duplicate subdomain
        await tenant_page.click_create_tenant()
        
        await tenant_page.fill_tenant_form(
            name=TestDataGenerator.generate_tenant_name(),
            subdomain=existing_subdomain,  # Duplicate
            billing_plan="standard"
        )
        
        await tenant_page.submit_form()
        
        # Verify error message
        error_msg = await tenant_page.get_error_message()
        assert TestConstants.ERROR_MESSAGES["duplicate_entry"] in error_msg
    
    @pytest.mark.asyncio
    async def test_tenant_search_filter(self, page: Page, base_url: str):
        """Test searching/filtering tenants."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        
        # Get all tenants
        all_tenants = await tenant_page.get_tenant_list()
        
        if len(all_tenants) < 2:
            pytest.skip("Need at least 2 tenants for search test")
        
        # Search for specific tenant
        search_term = all_tenants[0]['name'][:5]  # First 5 chars
        await page.fill('input[name="search"]', search_term)
        await page.press('input[name="search"]', 'Enter')
        
        # Wait for filtered results
        await page.wait_for_timeout(1000)
        
        # Get filtered results
        filtered_tenants = await tenant_page.get_tenant_list()
        
        # Verify filtering worked
        assert len(filtered_tenants) < len(all_tenants)
        for tenant in filtered_tenants:
            assert search_term.lower() in tenant['name'].lower()