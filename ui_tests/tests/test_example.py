"""
Example test file demonstrating UI test patterns.
This file shows best practices for writing UI tests.
"""

import pytest
from playwright.async_api import Page
from ..pages.login_page import LoginPage
from ..pages.tenant_page import TenantPage
from ..utils.auth_helper import AuthHelper
from ..utils.test_data import TestDataGenerator, TestConstants

# Mark entire class with smoke marker
@pytest.mark.smoke
class TestExampleWorkflow:
    """Example test workflow demonstrating common patterns."""
    
    @pytest.mark.asyncio
    async def test_complete_tenant_creation_workflow(self, page: Page, base_url: str):
        """
        Test complete workflow: login → create tenant → verify.
        This demonstrates a full end-to-end test.
        """
        # Step 1: Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        assert await AuthHelper.is_authenticated(page)
        
        # Step 2: Navigate to tenant management
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        
        # Step 3: Create new tenant
        await tenant_page.click_create_tenant()
        
        # Generate unique test data
        tenant_data = {
            "name": TestDataGenerator.generate_tenant_name(),
            "subdomain": TestDataGenerator.generate_subdomain(),
            "billing_plan": "standard"
        }
        
        # Fill and submit form
        await tenant_page.fill_tenant_form(**tenant_data)
        await tenant_page.select_adapters(["mock"])
        await tenant_page.submit_form()
        
        # Step 4: Verify success
        success_msg = await tenant_page.wait_for_success_message()
        assert TestConstants.SUCCESS_MESSAGES["tenant_created"] in success_msg
        
        # Step 5: Verify tenant in list
        tenants = await tenant_page.get_tenant_list()
        created_tenant = next((t for t in tenants if t['name'] == tenant_data['name']), None)
        assert created_tenant is not None
        assert created_tenant['subdomain'] == tenant_data['subdomain']
    
    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_error_handling_example(self, page: Page, base_url: str):
        """
        Example of testing error scenarios.
        Shows how to verify error messages and states.
        """
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        await tenant_page.click_create_tenant()
        
        # Submit empty form to trigger validation
        await tenant_page.submit_form()
        
        # Verify error message appears
        error_msg = await tenant_page.get_error_message()
        assert error_msg != ""
        assert "required" in error_msg.lower()
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("billing_plan", ["basic", "standard", "enterprise"])
    async def test_parameterized_example(self, page: Page, base_url: str, billing_plan: str):
        """
        Example of parameterized testing.
        This test runs once for each billing plan.
        """
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        await tenant_page.click_create_tenant()
        
        # Test each billing plan
        await tenant_page.fill_tenant_form(
            name=f"Test {billing_plan} Tenant",
            subdomain=f"test-{billing_plan}",
            billing_plan=billing_plan
        )
        
        # Verify billing plan is selected
        selected = await page.input_value('select[name="billing_plan"]')
        assert selected == billing_plan


@pytest.mark.slow
class TestSlowOperations:
    """Example of tests marked as slow."""
    
    @pytest.mark.asyncio
    async def test_large_data_load(self, page: Page, base_url: str):
        """
        Example of testing with large datasets.
        Marked as slow to exclude from quick test runs.
        """
        await AuthHelper.login_as_admin(page, base_url)
        
        # Simulate testing with large data
        # This would typically involve:
        # - Loading many records
        # - Testing pagination
        # - Verifying performance
        
        # For demo purposes, just wait
        await page.wait_for_timeout(2000)
        assert True  # Replace with actual assertions


class TestDebugExamples:
    """Examples showing debugging techniques."""
    
    @pytest.mark.asyncio
    async def test_with_screenshot_example(self, page: Page, base_url: str, screenshot_on_failure):
        """
        Example showing how screenshots are taken on failure.
        The screenshot_on_failure fixture handles this automatically.
        """
        await page.goto(base_url)
        
        # This would fail and trigger a screenshot
        # assert False, "Intentional failure for screenshot demo"
        
        # Instead, let's show a passing test
        assert await page.title() != ""
    
    @pytest.mark.asyncio
    async def test_wait_strategies(self, page: Page, base_url: str):
        """
        Example showing different wait strategies.
        """
        await page.goto(base_url)
        
        # Wait for specific element
        await page.wait_for_selector('body', state='visible')
        
        # Wait for network idle
        await page.wait_for_load_state('networkidle')
        
        # Wait for specific URL
        if "/login" in await page.url:
            await page.wait_for_url("**/login")
        
        # Wait for JavaScript execution
        await page.wait_for_function("() => document.readyState === 'complete'")
        
        assert True  # Test passes if all waits succeed