import pytest
from playwright.async_api import Page
from ..pages.operations_page import OperationsPage
from ..pages.tenant_page import TenantPage
from ..utils.auth_helper import AuthHelper
from ..utils.test_data import TestDataGenerator, TestConstants
from datetime import datetime, timedelta

class TestOperationsDashboard:
    """Test operations dashboard functionality."""
    
    @pytest.mark.asyncio
    async def test_operations_dashboard_loads(self, page: Page, base_url: str):
        """Test that operations dashboard loads correctly."""
        # Login as admin
        await AuthHelper.login_as_admin(page, base_url)
        
        # Get first tenant
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available for testing")
        
        # Navigate to operations for first tenant
        tenant_id = tenants[0]['subdomain']  # Assuming subdomain is used as ID
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenant_id)
        
        # Verify dashboard loaded
        assert await page.is_visible('h2:has-text("Operations Dashboard")')
        
        # Verify summary metrics loaded
        metrics = await ops_page.get_summary_metrics()
        assert 'active_campaigns' in metrics
        assert 'total_spend' in metrics
        assert 'pending_approvals' in metrics
    
    @pytest.mark.asyncio
    async def test_media_buys_table(self, page: Page, base_url: str):
        """Test media buys table functionality."""
        # Login and navigate to operations
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available")
        
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenants[0]['subdomain'])
        
        # Check media buys table
        media_buys = await ops_page.get_media_buys()
        
        # If there are media buys, verify table structure
        if len(media_buys) > 0:
            first_buy = media_buys[0]
            assert 'id' in first_buy
            assert 'principal' in first_buy
            assert 'status' in first_buy
            assert 'budget' in first_buy
            assert 'dates' in first_buy
    
    @pytest.mark.asyncio
    async def test_filter_by_status(self, page: Page, base_url: str):
        """Test filtering operations by status."""
        # Login and navigate to operations
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available")
        
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenants[0]['subdomain'])
        
        # Get all media buys
        all_buys = await ops_page.get_media_buys()
        
        if len(all_buys) < 2:
            pytest.skip("Not enough media buys to test filtering")
        
        # Apply status filter
        await ops_page.apply_filters(status="active")
        
        # Get filtered results
        filtered_buys = await ops_page.get_media_buys()
        
        # Verify all results have active status
        for buy in filtered_buys:
            assert buy['status'].lower() == 'active'
        
        # Clear filters
        await ops_page.clear_filters()
        
        # Verify all results returned
        cleared_buys = await ops_page.get_media_buys()
        assert len(cleared_buys) >= len(filtered_buys)
    
    @pytest.mark.asyncio
    async def test_date_range_filter(self, page: Page, base_url: str):
        """Test filtering by date range."""
        # Login and navigate to operations
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available")
        
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenants[0]['subdomain'])
        
        # Set date range filter
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        
        await ops_page.apply_filters(date_from=date_from, date_to=date_to)
        
        # Verify filter applied (page should reload/update)
        await page.wait_for_timeout(1000)
        
        # Check that date inputs retain values
        assert await page.input_value('input[name="date_from"]') == date_from
        assert await page.input_value('input[name="date_to"]') == date_to
    
    @pytest.mark.asyncio
    async def test_task_approval(self, page: Page, base_url: str):
        """Test approving a pending task."""
        # Login and navigate to operations
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available")
        
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenants[0]['subdomain'])
        
        # Get tasks
        tasks = await ops_page.get_tasks()
        
        # Find pending task
        pending_tasks = [t for t in tasks if t['status'].lower() == 'pending']
        
        if len(pending_tasks) == 0:
            pytest.skip("No pending tasks to approve")
        
        # Approve first pending task
        task_id = pending_tasks[0]['id']
        await ops_page.approve_task(task_id)
        
        # Verify success message or status update
        await page.wait_for_selector('.success-message')
        
        # Refresh and verify task status changed
        await page.reload()
        updated_tasks = await ops_page.get_tasks()
        
        # Find the task we approved
        approved_task = next((t for t in updated_tasks if t['id'] == task_id), None)
        if approved_task:
            assert approved_task['status'].lower() != 'pending'
    
    @pytest.mark.asyncio
    async def test_audit_logs_display(self, page: Page, base_url: str):
        """Test audit logs display."""
        # Login and navigate to operations
        await AuthHelper.login_as_admin(page, base_url)
        
        tenant_page = TenantPage(page, base_url)
        await tenant_page.goto_tenants()
        tenants = await tenant_page.get_tenant_list()
        
        if len(tenants) == 0:
            pytest.skip("No tenants available")
        
        ops_page = OperationsPage(page, base_url)
        await ops_page.goto_operations(tenants[0]['subdomain'])
        
        # Check if audit logs section exists
        assert await page.is_visible('#audit-logs-table')
        
        # Verify audit log entries if any exist
        audit_rows = await page.query_selector_all('.audit-log-row')
        
        if len(audit_rows) > 0:
            # Verify first log entry has expected fields
            first_row = audit_rows[0]
            assert await first_row.query_selector('.timestamp') is not None
            assert await first_row.query_selector('.operation') is not None
            assert await first_row.query_selector('.principal') is not None
            assert await first_row.query_selector('.status') is not None