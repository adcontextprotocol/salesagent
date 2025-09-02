"""Simplified context object for MCP tools.

This module provides a clean context abstraction for tools, similar to how A2A
handles context automatically. Tools receive a ToolContext with all necessary
information without needing to manage protocol details.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    """Simplified context passed to MCP tools.

    This mirrors the A2A approach where handlers receive rich context automatically.
    The MCP wrapper handles all protocol details and provides this clean interface.
    """

    # Core identifiers
    context_id: str = Field(description="Unique conversation/session ID")
    tenant_id: str = Field(description="Tenant identifier")
    principal_id: str = Field(description="Principal (advertiser) identifier")

    # Conversation state
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list, description="Previous messages in this conversation"
    )

    # Request metadata
    tool_name: str = Field(description="Name of the tool being called")
    request_timestamp: datetime = Field(description="When this request was made")

    # Optional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")

    # Testing context (if applicable)
    testing_context: dict[str, Any] | None = Field(
        default=None, description="Testing hooks context (dry-run, mock-time, etc.)"
    )

    # Workflow tracking
    workflow_id: str | None = Field(default=None, description="Associated workflow ID if part of a workflow")

    def is_async_operation(self) -> bool:
        """Check if this is an async operation requiring persistent context."""
        return self.workflow_id is not None

    def get_test_header(self, header_name: str) -> str | None:
        """Get a testing header value if present."""
        if not self.testing_context:
            return None
        return self.testing_context.get(header_name)

    def add_to_history(self, message: dict[str, Any]) -> None:
        """Add a message to the conversation history."""
        self.conversation_history.append({**message, "timestamp": datetime.now(UTC).isoformat()})
