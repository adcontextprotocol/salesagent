"""MCP ``context`` handling for the account tools.

The MCP wrappers in ``accounts.py`` take ``context`` as a separate kwarg, because
that is how FastMCP dispatches tool parameters:
``list_accounts(account=..., ctx=..., context=ContextObject(...))``.

Two levels are covered, deliberately:

* ``TestMCPContextThroughRealPipeline`` — dispatch by tool name through the real
  FastMCP client and assert the response carries the context back. This is the
  path a buyer actually uses, middleware chain and TypeAdapter coercion included.
* ``TestMCPContextDirectCalls`` — call the wrapper directly with ``context`` as a
  separate kwarg, covering the wrapper's own parameter handling.

Historical note: this file used to assert, via an instrumented copy of the
wrapper handed to ``BaseTestEnv._run_mcp_wrapper``, that a
``if context is not None`` merge branch fired. That premise expired twice over —
the branch no longer exists (``list_accounts`` forwards ``context`` straight into
``ListAccountsRequest``), and ``_run_mcp_wrapper`` itself is deleted
because it bypassed the FastMCP pipeline.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from adcp.types import ContextObject
from fastmcp.server.context import Context

from src.core.schemas.account import (
    ListAccountsRequest,
    ListAccountsResponse,
    SyncAccountsResponse,
)
from tests.bdd.steps._outcome_helpers import require_payload
from tests.harness.account_list import AccountListEnv
from tests.harness.account_sync import AccountSyncEnv

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestMCPContextThroughRealPipeline:
    """``context`` survives the REAL FastMCP dispatch, not just a direct wrapper call."""

    def test_mcp_pipeline_forwards_context_to_the_response(self, integration_db):
        """A context sent through Client(mcp) comes back on the response.

        Replaces an instrumented-branch test that handed an instrumented copy of
        the wrapper to ``BaseTestEnv._run_mcp_wrapper`` and asserted a
        ``merge_branch_entered`` flag. Two things made that unsound:

        * It graded the TEST'S OWN wrapper. The flag was set by the instrumented
          function's ``if context is not None`` check, so it proved the harness
          had passed the kwarg -- never that production did anything with it.
        * Its premise had expired. The docstring claimed ``_run_mcp_wrapper``
          "skips the merge branch entirely", while the assertion asserting the
          branch DID fire passed. And ``list_accounts`` has no merge branch left
          to skip: it forwards ``context=context`` straight into
          ``ListAccountsRequest`` (accounts.py:318-327).

        What matters is the OBSERVABLE outcome through the pipeline a buyer
        actually uses, so that is what this asserts: dispatch by tool name
        through the real FastMCP client, and the response carries the context
        back. That also exercises the middleware chain and TypeAdapter coercion
        the bypass skipped -- strictly more of production than the flag ever did.

        The sibling ``TestMCPContextDirectCalls`` keeps covering the wrapper
        called directly with ``context`` as a separate kwarg, so no coverage is
        lost by dropping the instrumentation.
        """
        from tests.factories import (
            AccountFactory,
            AgentAccountAccessFactory,
            PrincipalFactory,
            TenantFactory,
        )

        with AccountListEnv(tenant_id="merge_t1", principal_id="merge_agent") as env:
            tenant = TenantFactory(tenant_id="merge_t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="merge_agent")
            acc = AccountFactory(tenant=tenant, account_id="acc_merge_1")
            AgentAccountAccessFactory(tenant_id=tenant.tenant_id, principal=principal, account=acc)
            env._commit_factory_data()

            response = env.call_mcp(context=ContextObject.model_validate({"channel": "merge-test"}))

        assert response.context is not None, "FastMCP dispatch dropped the request context entirely"
        assert response.context.channel == "merge-test"


class TestMCPContextDirectCalls:
    """Verify MCP wrappers work correctly when called the production way (direct calls)."""

    def test_list_accounts_mcp_context_as_separate_kwarg(self, integration_db):
        """MCP list_accounts forwards context when passed as separate kwarg.

        Calls the wrapper directly with context as a separate kwarg,
        exercising lines 226-231 in accounts.py.
        """
        from src.core.tools.accounts import list_accounts
        from tests.factories import (
            AccountFactory,
            AgentAccountAccessFactory,
            PrincipalFactory,
            TenantFactory,
        )

        with AccountListEnv(tenant_id="mcp_ctx_t1", principal_id="mcp_ctx_agent") as env:
            tenant = TenantFactory(tenant_id="mcp_ctx_t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="mcp_ctx_agent")
            acc = AccountFactory(tenant=tenant, account_id="acc_mcp_ctx_1", name="Ctx Test")
            AgentAccountAccessFactory(tenant_id=tenant.tenant_id, principal=principal, account=acc)
            env._commit_factory_data()

            context_obj = ContextObject.model_validate({"channel": "mcp-test"})

            from tests.harness.transport import Transport

            mcp_identity = env.identity_for(Transport.MCP)
            mock_ctx = MagicMock(spec=Context)
            mock_ctx.get_state = AsyncMock(return_value=mcp_identity)

            tool_result = asyncio.run(list_accounts(ctx=mock_ctx, context=context_obj))
            response = ListAccountsResponse(**tool_result.structured_content)

        assert response.context is not None
        assert response.context.channel == "mcp-test"

    def test_sync_accounts_mcp_context_as_separate_kwarg(self, integration_db):
        """MCP sync_accounts forwards context when passed as separate kwarg.

        Exercises lines 689-694 in accounts.py.
        """
        from src.core.tools.accounts import sync_accounts
        from tests.factories.request import fresh_idempotency_key

        with AccountSyncEnv(tenant_id="mcp_sync_ctx_t1", principal_id="mcp_sync_ctx_agent") as env:
            env.setup_default_data()

            context_obj = ContextObject.model_validate({"channel": "sync-mcp-test"})

            from tests.harness.transport import Transport

            mcp_identity = env.identity_for(Transport.MCP)
            mock_ctx = MagicMock(spec=Context)
            mock_ctx.get_state = AsyncMock(return_value=mcp_identity)

            tool_result = asyncio.run(
                sync_accounts(
                    accounts=[{"brand": {"domain": "ctx-sync.com"}, "operator": "ctx-sync.com", "billing": "operator"}],
                    # Required by sync-accounts-request.json 3.1.1 (prkv.86). This scenario
                    # grades the context ECHO on a SUCCESSFUL sync, so the request has to be
                    # one the boundary accepts — a refusal never reaches the echo.
                    idempotency_key=fresh_idempotency_key(),
                    ctx=mock_ctx,
                    context=context_obj,
                )
            )
            response = SyncAccountsResponse(**tool_result.structured_content)

        assert response.context is not None
        assert response.context.channel == "sync-mcp-test"


class TestBDDTransportBypass:
    """Demonstrate that BDD step when_request_with_context bypasses transport for list_accounts."""

    def test_list_accounts_context_through_dispatch(self, integration_db):
        """list_accounts with context should go through dispatch_request, not _impl directly.

        The BDD step when_request_with_context calls _list_accounts_impl
        directly for list_accounts, bypassing transport dispatch. This means
        the MCP/A2A/REST transports are never tested for list_accounts context echo.

        This test verifies that dispatch_request works correctly for list_accounts
        with context, proving the BDD step SHOULD use it.
        """
        from tests.bdd.steps.generic._dispatch import dispatch_request
        from tests.factories import (
            AccountFactory,
            AgentAccountAccessFactory,
            PrincipalFactory,
            TenantFactory,
        )

        with AccountListEnv(tenant_id="bdd_disp_t1", principal_id="bdd_disp_agent") as env:
            tenant = TenantFactory(tenant_id="bdd_disp_t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="bdd_disp_agent")
            acc = AccountFactory(tenant=tenant, account_id="acc_disp_1")
            AgentAccountAccessFactory(tenant_id=tenant.tenant_id, principal=principal, account=acc)

            context_obj = ContextObject.model_validate({"channel": "dispatch-test"})
            req = ListAccountsRequest(context=context_obj)

            # Simulate what the BDD step SHOULD do (but doesn't for list_accounts):
            # dispatch through a wire transport. IMPL was dropped from BDD dispatch
            # (#1417), so this exercises the MCP wire path for context echo.
            bdd_ctx = {"env": env, "transport": "mcp"}
            dispatch_request(bdd_ctx, req=req)

            # The dispatch result, not a copy of it: dispatch_request stashes the
            # TransportResult and the payload is read through the shared accessor.
            response = require_payload(bdd_ctx)

        assert response.context is not None
        assert response.context.channel == "dispatch-test"
