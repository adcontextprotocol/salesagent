from .base_page import BasePage
from playwright.async_api import Page
from typing import List, Dict

class TenantPage(BasePage):
    """Tenant management page object model."""
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        
        # Selectors
        self.create_tenant_button = 'a:has-text("Create New Tenant")'
        self.tenant_name_input = 'input[name="name"]'
        self.subdomain_input = 'input[name="subdomain"]'
        self.billing_plan_select = 'select[name="billing_plan"]'
        self.adapter_checkboxes = 'input[name="adapters"]'
        self.submit_button = 'button[type="submit"]'
        self.tenant_list = '.tenant-list'
        self.tenant_row = '.tenant-row'
        self.success_message = '.success-message'
        self.error_message = '.error-message'
        
    async def goto_tenants(self) -> None:
        """Navigate to tenants page."""
        await self.navigate_to("/")
    
    async def click_create_tenant(self) -> None:
        """Click create tenant button."""
        await self.click(self.create_tenant_button)
    
    async def fill_tenant_form(self, name: str, subdomain: str, billing_plan: str = "standard") -> None:
        """Fill tenant creation form."""
        await self.fill(self.tenant_name_input, name)
        await self.fill(self.subdomain_input, subdomain)
        await self.select_option(self.billing_plan_select, billing_plan)
    
    async def select_adapters(self, adapters: List[str]) -> None:
        """Select adapters for tenant."""
        for adapter in adapters:
            checkbox = f'input[name="adapters"][value="{adapter}"]'
            await self.page.check(checkbox)
    
    async def submit_form(self) -> None:
        """Submit the form."""
        await self.click(self.submit_button)
    
    async def get_tenant_list(self) -> List[Dict[str, str]]:
        """Get list of all tenants."""
        await self.wait_for_element(self.tenant_list)
        tenants = []
        rows = await self.page.query_selector_all(self.tenant_row)
        
        for row in rows:
            name = await row.query_selector('.tenant-name').text_content()
            subdomain = await row.query_selector('.tenant-subdomain').text_content()
            status = await row.query_selector('.tenant-status').text_content()
            tenants.append({
                'name': name.strip(),
                'subdomain': subdomain.strip(),
                'status': status.strip()
            })
        
        return tenants
    
    async def click_tenant(self, tenant_name: str) -> None:
        """Click on a specific tenant."""
        tenant_link = f'a:has-text("{tenant_name}")'
        await self.click(tenant_link)
    
    async def wait_for_success_message(self) -> str:
        """Wait for and return success message."""
        await self.wait_for_element(self.success_message)
        return await self.get_text(self.success_message)
    
    async def get_error_message(self) -> str:
        """Get error message if present."""
        if await self.is_visible(self.error_message):
            return await self.get_text(self.error_message)
        return ""