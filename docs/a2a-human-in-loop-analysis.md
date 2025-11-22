# A2A Human-in-the-Loop Pattern Analysis

**Status**: Analysis complete, implementation gaps identified
**Date**: 2025-01-21
**Reference**: [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)

## Executive Summary

The A2A protocol has **first-class support** for human-in-the-loop patterns through the `input_required` state and multi-turn message interactions. Our current implementation partially supports this through the `pending_approval` status in media buys, but we need to align with A2A's standard patterns.

## A2A Specification Requirements

### 1. Task States for Human Approval

**From A2A Spec:**
- `input_required`: Task needs external input (human approval, additional data)
- `submitted`: Task submitted for external processing (approval queue)
- `working`: Task actively processing
- `completed`: Task successfully finished
- `failed`: Task failed with error
- `canceled`: Task was canceled
- `rejected`: Task was explicitly rejected

**Our Current Usage:**
- ✅ `working`: Used for tasks in progress
- ✅ `completed`: Used for successful completion
- ✅ `failed`: Used for protocol/system errors
- ✅ `canceled`: Used in cancel handler
- ✅ `submitted`: Used when creatives are "pending_review"
- ❌ `input_required`: **NOT USED** - Gap identified
- ❌ `rejected`: **NOT USED** - Gap identified

### 2. Signaling Need for Approval

**A2A Pattern:**
```python
# Agent transitions task to input_required state
task.status = TaskStatus(
    state=TaskState.input_required,
    message="Media buy requires manual approval. Please review and approve."
)
```

**Our Current Pattern:**
```python
# We use internal "pending_approval" string status in database
pending_buy = MediaBuy(
    status="pending_approval",  # Internal DB status
    ...
)

# But we return AdCP status "pending_activation" to client
# And don't use A2A TaskState.input_required
```

**Gap:** We don't expose the approval requirement through A2A task state

### 3. Resuming After Approval

**A2A Pattern:**
```python
# Client sends new message with same taskId and contextId
await client.send_message(
    task_id=original_task_id,      # Same task
    context_id=original_context_id, # Same conversation
    message=ApprovalResponse(approved=True)
)
```

**Our Current Pattern:**
- Approval happens through Admin UI, not A2A message
- No mechanism to resume task via A2A after approval
- Manual approval updates database directly

**Gap:** No A2A-based approval resumption flow

### 4. Fields for Approval Workflows

**A2A Spec Fields:**
- `TaskStatus.message`: Human-readable context ("Awaiting approval", "Please review...")
- `Task.contextId`: Maintains conversation continuity
- `Task.history`: Full interaction sequence
- `Task.metadata`: Custom data for approval tracking

**Our Current Usage:**
- ✅ `TaskStatus.message`: Not currently used for approval messages
- ✅ `Task.contextId`: Used in all tasks
- ❌ `Task.history`: Not populated
- ✅ `Task.metadata`: Contains skill_name, tenant_id, principal_id

**Gap:** Not using TaskStatus.message for approval notifications

### 5. Push Notifications for Approvals

**A2A Pattern:**
```python
# Client registers webhook
push_notification_config = PushNotificationConfig(
    url="https://client.example.com/webhooks/a2a",
    authentication={"schemes": ["HMAC-SHA256"], "credentials": "secret"},
)

# Server sends TaskStatusUpdateEvent when state changes
event = TaskStatusUpdateEvent(
    task_id=task_id,
    state="input_required",
    message="Media buy requires approval"
)
```

**Our Current Implementation:**
- ✅ We support PushNotificationConfig registration (database model + A2A integration)
- ✅ We send webhooks via `_send_protocol_webhook()` after task completion
- ✅ Webhooks sent for "completed" state (line 867 in adcp_a2a_server.py)
- ✅ Webhooks sent for "failed" state (line 899 in adcp_a2a_server.py)
- ✅ Webhooks sent for "submitted" state (creatives pending review)
- ❌ We don't send webhooks for "input_required" state transitions

**Gap:** We send webhooks after tasks complete, but not when they transition to "input_required" state (which we don't currently use). If we implement "input_required" state, we should also send webhooks at that transition point to notify clients that approval is needed.

## Current Implementation Analysis

### What We Do Well

1. **Database State Management**: We properly track `pending_approval` status
2. **Admin UI Approval Flow**: Working manual approval through UI
3. **AdCP Status Mapping**: Correctly map to `pending_activation` status
4. **Webhook Infrastructure**: Full webhook support with PushNotificationConfig registration and delivery
5. **Task Completion Webhooks**: Send webhooks for completed, failed, and submitted states

### What's Missing for A2A Alignment

1. **No `input_required` State**: Don't use A2A's standard approval state
2. **No A2A Resume Flow**: Can't approve via A2A message
3. **No Intermediate State Webhooks**: Don't send webhooks when tasks transition to "input_required" (though we do send them for completed/failed/submitted)
4. **No TaskStatus.message**: Don't provide human context in task status

## Recommended Implementation

### Phase 1: Use `input_required` State (High Priority)

**When media buy requires approval:**
```python
# src/a2a_server/adcp_a2a_server.py
if requires_manual_approval:
    task.status = TaskStatus(
        state=TaskState.input_required,
        message=f"Media buy {media_buy_id} requires manual approval. "
                f"Budget: ${total_budget:,.2f}, Duration: {duration_days} days. "
                f"Please approve via Admin UI or send approval message."
    )

    # Send webhook notification
    await self._send_protocol_webhook(
        task,
        status="input_required",
        message="Approval required for media buy"
    )
```

### Phase 2: A2A Approval Messages (Medium Priority)

**Support approval via A2A:**
```python
# Client can send approval message
{
    "method": "message/send",
    "params": {
        "taskId": "task-123",
        "contextId": "ctx-456",
        "message": {
            "parts": [{
                "kind": "data",
                "data": {
                    "action": "approve",
                    "media_buy_id": "mb-789",
                    "approved": true,
                    "notes": "Budget approved"
                }
            }]
        }
    }
}

# Server processes approval and resumes
task.status = TaskStatus(state=TaskState.working)
# ... execute adapter.create_campaign()
task.status = TaskStatus(state=TaskState.completed)
```

### Phase 3: Enhanced Webhook Notifications (Medium Priority)

**Extend webhook support:**
```python
# Send webhooks for all state changes
WEBHOOK_STATES = ["completed", "failed", "input_required", "submitted", "rejected"]

for state in WEBHOOK_STATES:
    if task.status.state == state:
        await self._send_protocol_webhook(task, status=state)
```

## Testing Requirements

### Test Coverage Needed

1. **State Transition Tests**:
   - Test `input_required` state for manual approval
   - Test `submitted` state for creative review
   - Test `rejected` state for denied approvals

2. **Webhook Tests**:
   - Test webhook sent when task enters `input_required`
   - Test webhook payload includes approval context
   - Test webhook authentication (HMAC-SHA256)

3. **Resume Flow Tests**:
   - Test approval message resuming task
   - Test rejection message failing task
   - Test taskId and contextId continuity

4. **Message Field Tests**:
   - Test TaskStatus.message provides human context
   - Test message includes budget, duration, advertiser
   - Test message includes action URL for Admin UI

## Compliance Status

| Requirement | Current Status | Gap | Priority |
|-------------|---------------|-----|----------|
| Use `input_required` state | ❌ Not implemented | Critical - breaks ADK/A2A client expectations | High |
| Use `submitted` state | ✅ Partial - only for creatives | Should extend to other submission flows | Medium |
| Support approval messages | ❌ Not implemented | Limits A2A-native workflow | Medium |
| Send task completion webhooks | ✅ Implemented for completed/failed/submitted | None - works as expected | - |
| Send intermediate state webhooks | ❌ Not sent for input_required | Would need if we implement input_required state | High |
| Provide TaskStatus.message | ❌ Not implemented | Missing human context | High |
| Use Task.history | ❌ Not implemented | Limits debugging/audit | Low |
| Support `rejected` state | ❌ Not implemented | Can't signal explicit rejection | Medium |

## Impact on ADK Integration

**ADK clients expect:**
1. Tasks requiring approval to use `input_required` state
2. Webhook notifications when approval needed
3. Ability to approve via A2A message (future)
4. Human-readable context in TaskStatus.message

**Current Status:**
- ✅ Webhook infrastructure works well for task completion
- ✅ Clients get notified when tasks complete or fail
- ❌ Clients don't get notified when approval is needed (we don't use input_required state)
- ❌ Must poll or check Admin UI manually for approval status
- ⚠️ If we implement input_required state, we'd need to add webhooks for that transition too

## Recommendations

### Immediate Actions (Before Merging Current PR)

1. ✅ Document the gap (this document)
2. ⚠️ Consider adding `input_required` state usage
3. ⚠️ Consider adding approval webhook notifications
4. ✅ Add tests for future approval patterns

### Future Work (Separate PR)

1. Implement `input_required` state for manual approvals
2. Add webhook notifications for approval requests
3. Support A2A approval messages (multi-turn)
4. Add TaskStatus.message for human context
5. Implement `rejected` state for denied approvals

## References

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A Human-in-Loop Validation Pattern](https://medium.com/@visrow/google-a2a-protocol-human-in-loop-validation-with-java-dc1a86680cde)
- Current implementation: `src/core/tools/media_buy_create.py`
- A2A server: `src/a2a_server/adcp_a2a_server.py`
- Database model: `src/core/database/models.py` (MediaBuy.status)

## Conclusion

Our implementation has **solid webhook infrastructure** and handles task completion well, but doesn't fully align with A2A's **standard patterns for approval workflows**. The key gaps are:

1. Not using `input_required` state (critical for ADK compatibility)
2. Not sending webhooks when approval is needed (we do send them for completion/failure)
3. Not supporting A2A-based approval messages (future consideration)

**Webhook Status:** Our webhook implementation is solid - we successfully send notifications for completed, failed, and submitted states. The gap is that we don't use `input_required` state in the first place, so there's no intermediate state to send webhooks for.

These should be addressed in a follow-up PR to ensure full A2A/ADK compliance for approval workflows.
