"""Unit tests for F-03: task management tools require authenticated principal.

Covers the vulnerability where list_tasks / get_task_status / complete_task accepted
requests that had a resolved tenant (via localhost fallback) but no principal_id.
An unauthenticated caller could read or mutate workflow task state.

The fix: all three functions enforce an authenticated principal via
require_principal_id (after the tenant check), which raises AdCPAuthenticationError
when principal_id is missing.
"""

import pytest

from src.core.exceptions import AdCPAuthenticationError, AdCPNotFoundError, AdCPTaskNotFoundError
from src.core.resolved_identity import ResolvedIdentity

# Every protocol field travels on the request now. Dispatch goes through the shared boundary
# -- the one path MCP, A2A and REST take -- so this grades the auth gate every buyer hits.
from src.core.schemas import CompleteTaskRequest, GetTaskStatusRequest, ListTasksRequest
from src.core.tools._boundary import invoke_tool


def _identity_no_principal() -> ResolvedIdentity:
    """Simulate the localhost tenant-fallback case: tenant is resolved, principal is not."""
    return ResolvedIdentity(
        principal_id=None,
        tenant={"tenant_id": "test-tenant", "name": "Test"},
        protocol="mcp",
    )


def _identity_with_principal() -> ResolvedIdentity:
    """Fully authenticated identity."""
    return ResolvedIdentity(
        principal_id="principal-abc",
        tenant={"tenant_id": "test-tenant", "name": "Test"},
        protocol="mcp",
    )


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_no_principal_raises_auth_error() -> None:
    """list_tasks must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        await invoke_tool("list_tasks", ListTasksRequest(), _identity_no_principal())


@pytest.mark.asyncio
async def test_list_tasks_no_identity_raises_auth_error() -> None:
    """list_tasks must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool("list_tasks", ListTasksRequest(), None)


# ---------------------------------------------------------------------------
# get_task_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_no_principal_raises_auth_error() -> None:
    """get_task_status must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        await invoke_tool("get_task_status", GetTaskStatusRequest(task_id="step-123"), _identity_no_principal())


@pytest.mark.asyncio
async def test_get_task_no_identity_raises_auth_error() -> None:
    """get_task_status must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool("get_task_status", GetTaskStatusRequest(task_id="step-123"), None)


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_task_no_principal_raises_auth_error() -> None:
    """complete_task must reject identity that has tenant but no principal_id."""
    with pytest.raises(AdCPAuthenticationError) as exc_info:
        await invoke_tool(
            "complete_task", CompleteTaskRequest(task_id="step-123", status="completed"), _identity_no_principal()
        )


@pytest.mark.asyncio
async def test_complete_task_no_identity_raises_auth_error() -> None:
    """complete_task must reject a completely missing identity."""
    with pytest.raises(AdCPAuthenticationError):
        await invoke_tool("complete_task", CompleteTaskRequest(task_id="step-123", status="completed"), None)


# ---------------------------------------------------------------------------
# Regression: authenticated identity is not affected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tasks_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""
    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.count_by_tenant.return_value = 0
    mock_uow.return_value.__enter__.return_value.workflows.list_by_tenant.return_value = []
    mock_uow.return_value.__enter__.return_value.workflows.get_mappings_for_steps.return_value = {}

    result = await invoke_tool("list_tasks", ListTasksRequest(), _identity_with_principal())

    assert result.tasks == []
    # The count moved inside query_summary, where list-tasks-response.json declares it.
    assert result.query_summary.total_matching == 0


@pytest.mark.asyncio
async def test_get_task_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""

    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.get_by_step_id_or_raise.side_effect = AdCPTaskNotFoundError()

    with pytest.raises(AdCPNotFoundError) as _ei:
        await invoke_tool("get_task_status", GetTaskStatusRequest(task_id="step-999"), _identity_with_principal())
    # The old pattern matched the AUTHORED sentence; the sentence is the
    # code's table entry now, so assert it exactly.


@pytest.mark.asyncio
async def test_complete_task_authenticated_proceeds_past_auth_check(
    mocker: pytest.FixtureRequest,
) -> None:
    """Authenticated identity must pass the auth check and proceed to DB access."""

    mock_uow = mocker.patch("src.core.tools.task_management.WorkflowUoW")
    mock_uow.return_value.__enter__.return_value.workflows.get_by_step_id_or_raise.side_effect = AdCPTaskNotFoundError()

    with pytest.raises(AdCPNotFoundError) as _ei:
        # status is REQUIRED by the DTO and typed Literal["completed", "failed"], so the
        # request cannot be built without one -- the rejection is the model's, not a
        # second check inside the impl.
        await invoke_tool(
            "complete_task",
            CompleteTaskRequest(task_id="step-999", status="completed"),
            _identity_with_principal(),
        )
    # The old pattern matched the AUTHORED sentence; the sentence is the
    # code's table entry now, so assert it exactly.
