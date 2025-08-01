from .base_page import BasePage
from playwright.async_api import Page
from typing import List, Dict, Optional

class OperationsPage(BasePage):
    """Operations dashboard page object model."""
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        
        # Selectors
        self.operations_link = 'a:has-text("Operations")'
        self.summary_cards = '.metric-card'
        self.active_campaigns_count = '#active-campaigns-count'
        self.total_spend = '#total-spend'
        self.pending_approvals = '#pending-approvals-count'
        
        # Filters
        self.status_filter = 'select[name="status"]'
        self.principal_filter = 'select[name="principal"]'
        self.date_from = 'input[name="date_from"]'
        self.date_to = 'input[name="date_to"]'
        self.apply_filters_button = 'button:has-text("Apply Filters")'
        self.clear_filters_button = 'button:has-text("Clear")'
        
        # Tables
        self.media_buys_table = '#media-buys-table'
        self.tasks_table = '#tasks-table'
        self.audit_logs_table = '#audit-logs-table'
        
        # Table rows
        self.media_buy_row = 'tr.media-buy-row'
        self.task_row = 'tr.task-row'
        self.audit_log_row = 'tr.audit-log-row'
        
    async def goto_operations(self, tenant_id: str) -> None:
        """Navigate to operations dashboard for a tenant."""
        await self.navigate_to(f"/operations/{tenant_id}")
    
    async def get_summary_metrics(self) -> Dict[str, str]:
        """Get summary metrics from dashboard."""
        metrics = {}
        
        # Wait for metrics to load
        await self.wait_for_element(self.active_campaigns_count)
        
        metrics['active_campaigns'] = await self.get_text(self.active_campaigns_count)
        metrics['total_spend'] = await self.get_text(self.total_spend)
        metrics['pending_approvals'] = await self.get_text(self.pending_approvals)
        
        return metrics
    
    async def apply_filters(self, status: Optional[str] = None, 
                           principal: Optional[str] = None,
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> None:
        """Apply filters to the operations view."""
        if status:
            await self.select_option(self.status_filter, status)
        
        if principal:
            await self.select_option(self.principal_filter, principal)
        
        if date_from:
            await self.fill(self.date_from, date_from)
        
        if date_to:
            await self.fill(self.date_to, date_to)
        
        await self.click(self.apply_filters_button)
        await self.wait_for_load()
    
    async def clear_filters(self) -> None:
        """Clear all filters."""
        await self.click(self.clear_filters_button)
        await self.wait_for_load()
    
    async def get_media_buys(self) -> List[Dict[str, str]]:
        """Get list of media buys from table."""
        media_buys = []
        rows = await self.page.query_selector_all(self.media_buy_row)
        
        for row in rows:
            buy_id = await row.query_selector('.buy-id').text_content()
            principal = await row.query_selector('.principal').text_content()
            status = await row.query_selector('.status').text_content()
            budget = await row.query_selector('.budget').text_content()
            dates = await row.query_selector('.dates').text_content()
            
            media_buys.append({
                'id': buy_id.strip(),
                'principal': principal.strip(),
                'status': status.strip(),
                'budget': budget.strip(),
                'dates': dates.strip()
            })
        
        return media_buys
    
    async def get_tasks(self) -> List[Dict[str, str]]:
        """Get list of tasks from table."""
        tasks = []
        rows = await self.page.query_selector_all(self.task_row)
        
        for row in rows:
            task_id = await row.query_selector('.task-id').text_content()
            task_type = await row.query_selector('.task-type').text_content()
            status = await row.query_selector('.status').text_content()
            created = await row.query_selector('.created').text_content()
            
            tasks.append({
                'id': task_id.strip(),
                'type': task_type.strip(),
                'status': status.strip(),
                'created': created.strip()
            })
        
        return tasks
    
    async def click_media_buy(self, buy_id: str) -> None:
        """Click on a specific media buy."""
        buy_link = f'a:has-text("{buy_id}")'
        await self.click(buy_link)
    
    async def approve_task(self, task_id: str) -> None:
        """Approve a pending task."""
        approve_button = f'button[data-task-id="{task_id}"][data-action="approve"]'
        await self.click(approve_button)
        await self.wait_for_response("**/approve_task")
    
    async def reject_task(self, task_id: str) -> None:
        """Reject a pending task."""
        reject_button = f'button[data-task-id="{task_id}"][data-action="reject"]'
        await self.click(reject_button)
        await self.wait_for_response("**/reject_task")