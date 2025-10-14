# Issue: Remove Protocol Fields from Requests and Add Conversation Context (MCP/A2A Parity)

## Summary

Complete the protocol envelope migration by removing protocol fields from request models and adding conversation context support, creating parity between MCP and A2A transports.

## Background

AdCP PR #113 removes protocol metadata from domain schemas, moving it to transport layer envelopes. We've completed response model cleanup (see #XXX), but requests still have protocol fields and our implementation functions lack conversation context that A2A provides.

## Current Problems

### 1. Protocol Fields in Request Models
Request models contain protocol fields that should be handled by transport wrappers:

```python
class ListAuthorizedPropertiesRequest(AdCPBaseModel):
    adcp_version: str = Field(default="1.0.0", ...)  # ❌ Protocol field
    tags: list[str] | None = Field(None, ...)        # ✅ Domain field
```

**Why this is wrong:**
- Protocol version negotiation should happen at transport layer
- Domain logic shouldn't care about protocol version
- Creates coupling between business logic and protocol concerns

### 2. No Conversation Context in Implementation Functions
A2A provides conversation history via `Task.history` (array of messages), but our MCP implementation doesn't provide equivalent context:

**A2A provides:**
```python
Task(
    id="task_123",
    contextId="ctx_abc",  # Protocol: groups related tasks
    history=[             # Domain: conversation context!
        Message(role="user", parts=[...]),
        Message(role="agent", parts=[...]),
    ],
    ...
)
```

**Our _impl functions receive:**
```python
def _get_products_impl(
    promoted_offering: str | None,
    brief: str,
    # ❌ NO conversation history - can't understand context!
) -> GetProductsResponse:
```

**Impact:**
- Can't provide context-aware responses
- MCP and A2A behave differently (no parity)
- Loss of conversational intelligence

## Proposed Solution

### 1. Remove Protocol Fields from Requests

**Files to update:**
- `src/core/schemas.py`: Remove `adcp_version` from `ListAuthorizedPropertiesRequest`
- Check all other request models for protocol fields

**Example:**
```python
# BEFORE
class ListAuthorizedPropertiesRequest(AdCPBaseModel):
    adcp_version: str = Field(default="1.0.0", ...)  # Remove this
    tags: list[str] | None = Field(None, ...)

# AFTER
class ListAuthorizedPropertiesRequest(AdCPBaseModel):
    tags: list[str] | None = Field(None, ...)  # Domain fields only
```

### 2. Add Conversation Context System

**Create new context models:**
```python
# src/core/conversation_context.py

class ConversationMessage(BaseModel):
    """Single message in conversation history."""
    role: Literal["user", "agent"]
    content: str  # Combined text from all parts
    timestamp: datetime
    metadata: dict[str, Any] | None = None

class ConversationContext(BaseModel):
    """Conversation context passed to implementation functions.

    Provides conversation history for context-aware responses.
    Populated by transport layer (MCP/A2A) from protocol envelopes.
    """
    history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Previous messages in this conversation"
    )
    context_id: str | None = Field(
        None,
        description="Protocol-level context ID (for tracking, not business logic)"
    )

    def get_last_user_message(self) -> str | None:
        """Helper: Get last message from user."""
        for msg in reversed(self.history):
            if msg.role == "user":
                return msg.content
        return None

    def get_conversation_summary(self, max_messages: int = 5) -> str:
        """Helper: Get recent conversation as text."""
        recent = self.history[-max_messages:] if len(self.history) > max_messages else self.history
        return "\n".join([f"{msg.role}: {msg.content}" for msg in recent])
```

### 3. Update Implementation Function Signatures

**Pattern for all _impl functions:**
```python
def _get_products_impl(
    # Domain request parameters
    promoted_offering: str | None,
    brief: str,
    # NEW: Conversation context
    conversation_context: ConversationContext | None = None,
) -> GetProductsResponse:
    """Implementation with conversation context.

    Args:
        promoted_offering: What is being advertised
        brief: Campaign brief
        conversation_context: Conversation history for context-aware responses
    """
    # Can now use conversation history!
    if conversation_context and conversation_context.history:
        # Understand what user asked before
        previous_queries = [msg.content for msg in conversation_context.history if msg.role == "user"]
        logger.info(f"User has made {len(previous_queries)} previous queries")

    # Rest of implementation...
```

**Functions to update:**
- `_get_products_impl`
- `_create_media_buy_impl`
- `_update_media_buy_impl`
- `_sync_creatives_impl`
- `_list_creatives_impl`
- `_list_creative_formats_impl`
- `_get_media_buy_delivery_impl`
- `_update_performance_index_impl`

### 4. Update Transport Layers

**MCP Layer (src/core/main.py):**
```python
@mcp.tool
async def get_products(
    promoted_offering: str | None = None,
    brief: str = "",
    context: Context = None,
) -> GetProductsResponse:
    """MCP tool wrapper - extracts conversation context."""

    # Extract conversation history from MCP Context
    conversation_context = _extract_mcp_conversation_context(context)

    # Call shared implementation with context
    return _get_products_impl(
        promoted_offering=promoted_offering,
        brief=brief,
        conversation_context=conversation_context,
    )

def _extract_mcp_conversation_context(context: Context | None) -> ConversationContext | None:
    """Extract conversation history from MCP Context.

    FastMCP may provide conversation history via context metadata.
    Map MCP conversation format to our ConversationContext.
    """
    if not context or not hasattr(context, 'meta'):
        return None

    # TODO: Determine how FastMCP provides conversation history
    # May need FastMCP library update or custom extraction
    history = []

    # Extract from context.meta or context-specific storage
    # ...

    return ConversationContext(history=history)
```

**A2A Layer (src/core/tools.py or src/a2a_server/):**
```python
def get_products_raw(
    promoted_offering: str | None = None,
    brief: str = "",
    task_context: dict | None = None,  # A2A Task object
) -> GetProductsResponse:
    """A2A raw function wrapper - extracts conversation context."""

    # Extract conversation history from A2A Task.history
    conversation_context = _extract_a2a_conversation_context(task_context)

    # Call shared implementation with context
    from src.core.main import _get_products_impl
    return _get_products_impl(
        promoted_offering=promoted_offering,
        brief=brief,
        conversation_context=conversation_context,
    )

def _extract_a2a_conversation_context(task_context: dict | None) -> ConversationContext | None:
    """Extract conversation history from A2A Task object.

    A2A provides Task.history as array of Message objects.
    Map A2A Message format to our ConversationContext.
    """
    if not task_context or 'history' not in task_context:
        return None

    history = []
    for msg in task_context.get('history', []):
        # A2A Message: {role: "user"|"agent", parts: [{text: "..."}]}
        content = " ".join(part.get('text', '') for part in msg.get('parts', []))
        history.append(ConversationMessage(
            role=msg.get('role'),
            content=content,
            timestamp=datetime.now(UTC),  # Or extract from msg if available
        ))

    return ConversationContext(
        history=history,
        context_id=task_context.get('contextId'),
    )
```

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create `src/core/conversation_context.py` with `ConversationContext` and `ConversationMessage` models
- [ ] Add unit tests for context models

### Phase 2: Remove Protocol Fields
- [ ] Remove `adcp_version` from `ListAuthorizedPropertiesRequest`
- [ ] Audit all request models for other protocol fields
- [ ] Update tests that use protocol fields in requests

### Phase 3: Add Context to Implementations
- [ ] Update all `_impl` function signatures to accept `ConversationContext`
- [ ] Update MCP tool wrappers to extract and pass context
- [ ] Update A2A raw functions to extract and pass context
- [ ] Add context extraction helpers for both MCP and A2A

### Phase 4: Testing
- [ ] Unit tests: Verify context extraction from MCP
- [ ] Unit tests: Verify context extraction from A2A
- [ ] Integration tests: Verify context flows through both protocols
- [ ] E2E tests: Verify conversation context works in real scenarios

### Phase 5: Documentation
- [ ] Update architecture docs explaining context flow
- [ ] Add examples of using conversation context in implementations
- [ ] Document MCP/A2A parity achievement

## Benefits

1. **MCP/A2A Parity**: Both protocols provide same conversation context
2. **Context-Aware Responses**: Can reference previous conversation turns
3. **Clean Separation**: Protocol fields handled by transport layer only
4. **AdCP PR #113 Compliance**: Complete migration to protocol envelope pattern
5. **Extensibility**: Easy to add more context types in future

## Related Work

- **Prerequisite**: #XXX (Protocol Field Removal from Responses) - COMPLETED
- **Follows**: AdCP PR #113 pattern (domain/protocol separation)
- **Enables**: Context-aware AI responses, multi-turn conversations

## Success Criteria

- [ ] No protocol fields in any request models
- [ ] All `_impl` functions receive `ConversationContext`
- [ ] MCP and A2A both provide conversation history
- [ ] Tests verify context flows correctly
- [ ] Documentation updated

## Open Questions

1. How does FastMCP provide conversation history? Need to check FastMCP library.
2. Should we store conversation history in database for persistence?
3. Do we need conversation pruning/summarization for long conversations?

## Implementation Notes

- This is a **non-breaking change** if we make `conversation_context` optional
- Can implement incrementally (one function at a time)
- Should coordinate with FastMCP maintainers on conversation history support
