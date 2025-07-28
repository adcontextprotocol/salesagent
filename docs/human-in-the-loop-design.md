# Human-in-the-Loop Task Queue System Design

## Overview

The Human-in-the-Loop (HITL) task queue system provides a mechanism for operations that require human intervention. This includes creative approvals, permission-restricted operations, compliance reviews, and manual configuration steps.

## Task Types

### 1. Creative Approval
- **Trigger**: Creative uploaded in non-auto-approved format
- **Actor**: Creative review team
- **Resolution**: Approve/reject creative with feedback

### 2. Permission Exception
- **Trigger**: Ad server API returns permission denied
- **Actor**: Ad operations team  
- **Resolution**: Manual operation completion or permission grant

### 3. Configuration Required
- **Trigger**: Missing adapter configuration or credentials
- **Actor**: Technical operations
- **Resolution**: Update configuration and retry

### 4. Compliance Review
- **Trigger**: Targeting or creative flagged for review
- **Actor**: Compliance team
- **Resolution**: Approve/reject with modifications

## Task States

```
pending → assigned → in_progress → completed/failed
                  ↓
              escalated
```

## Schema Design

### Task Model
```python
class HumanTask(BaseModel):
    task_id: str
    task_type: str  # creative_approval, permission_exception, etc.
    principal_id: str
    adapter_name: Optional[str]
    status: str  # pending, assigned, in_progress, completed, failed, escalated
    priority: str  # low, medium, high, urgent
    
    # Context
    media_buy_id: Optional[str]
    creative_id: Optional[str]
    operation: Optional[str]
    error_detail: Optional[str]
    
    # Assignment
    assigned_to: Optional[str]
    assigned_at: Optional[datetime]
    
    # Timing
    created_at: datetime
    updated_at: datetime
    due_by: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Resolution
    resolution: Optional[str]  # approved, rejected, completed, cannot_complete
    resolution_detail: Optional[str]
    resolved_by: Optional[str]
```

## API Tools

### create_human_task
Creates a new task requiring human intervention.

### get_pending_tasks
Retrieves tasks awaiting assignment or completion.

### assign_task
Assigns a task to a human operator.

### complete_task
Marks a task as completed with resolution details.

## Integration Points

### 1. Creative Engine
```python
# In MockCreativeEngine.evaluate_creative()
if creative.format_id not in self.auto_approve_formats:
    task = create_human_task(
        task_type="creative_approval",
        principal_id=self.principal.principal_id,
        creative_id=creative.creative_id,
        priority="medium"
    )
    return EvaluateCreativeResponse(
        approval_status="pending_review",
        detail=f"Task {task.task_id} created for manual review"
    )
```

### 2. Ad Server Adapters
```python
# In adapter operations
try:
    response = gam_api.create_line_item(...)
except PermissionError as e:
    task = create_human_task(
        task_type="permission_exception",
        adapter_name="google_ad_manager",
        media_buy_id=media_buy_id,
        operation="create_line_item",
        error_detail=str(e),
        priority="high"
    )
    return CreateMediaBuyResponse(
        status="pending_manual",
        detail=f"Task {task.task_id} created for manual operation"
    )
```

### 3. Webhook Notifications
```python
# Notify external systems when tasks are created
def send_task_notification(task: HumanTask):
    if task.priority in ["high", "urgent"]:
        webhook_url = config.get("hitl_webhook_url")
        if webhook_url:
            requests.post(webhook_url, json={
                "task_id": task.task_id,
                "type": task.task_type,
                "priority": task.priority,
                "detail": task.error_detail
            })
```

## Implementation Strategy

1. **Phase 1**: Core task queue with creative approval integration
2. **Phase 2**: Ad server permission exceptions
3. **Phase 3**: Webhook notifications and external integrations
4. **Phase 4**: SLA tracking and escalation rules

## Security Considerations

- Tasks contain sensitive operation context
- Access control based on task type and principal
- Audit logging for all task state changes
- PII masking in task details

## Monitoring

### Metrics
- Tasks by type and status
- Average resolution time by type
- Overdue tasks
- Escalation rate

### Alerts
- High priority task created
- Task overdue (based on SLA)
- High volume of failed operations

## Future Enhancements

1. **Automated Retry**: Retry operations after manual resolution
2. **Batch Operations**: Group similar tasks for efficiency  
3. **Machine Learning**: Predict task outcomes and auto-route
4. **Integration Hub**: Connect to ticketing systems (Jira, ServiceNow)