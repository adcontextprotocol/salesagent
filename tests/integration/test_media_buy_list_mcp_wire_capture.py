"""``MediaBuyListEnv`` must actually capture the MCP wire it declares.

This env was the last one in ``tests/harness/`` still dispatching through
``_run_mcp_wrapper``, which calls the UNDECORATED module function. The
``with_error_logging`` decorator is applied at registration time
(``src/core/main.py:348``), so the wrapper path never raises ``AdCPToolError``,
never stashes an envelope, and the dispatcher captures ``None`` — while the env
goes on declaring ``has_wire=True``.

That combination is one the harness itself calls a bug and raises on loudly
(``tests/harness/transport.py``), so it cannot be left to a BDD scenario to
notice: the two live UC-019 ``[mcp]`` scenarios pass at HEAD through the
documented typed-exception fallback, which is precisely the weak grading this
pins. The obligation is a harness-contract one, so it is graded here, through
the public ``call_via`` surface — the same way
``test_request_validation_suggestion_parity.py`` pins its own.
"""

import pytest

from tests.harness.media_buy_list import MediaBuyListEnv
from tests.harness.transport import Transport


@pytest.mark.requires_db
class TestMediaBuyListMcpWireCapture:
    def test_an_mcp_rejection_exposes_the_two_layer_wire_envelope(self, integration_db):
        """The rejection a real MCP buyer receives, not one rebuilt from the exception.

        Asserted on the envelope's SHAPE. ``is not None`` would pass on any dict,
        including one a builder regenerated — the substitution this whole lane
        exists to make impossible.

        The message is pydantic's, not ``_impl``'s, and that is the point:
        FastMCP's ``TypeAdapter`` rejects the enum at the schema boundary before
        ``_impl`` runs, and ``RequestCompatMiddleware`` translates that into the
        two-layer error. A buyer calling this tool over MCP gets exactly this.
        Grading ``_impl``'s wording here would grade a rejection no MCP client
        ever sees.
        """
        from tests.factories import PrincipalFactory, TenantFactory

        with MediaBuyListEnv(tenant_id="t1", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="t1")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            result = env.call_via(Transport.MCP, status_filter="not_a_status")

        assert result.is_error, f"expected a rejection, got payload: {result.payload!r}"
        result.assert_wire_error("VALIDATION_ERROR", recovery="correctable", require_suggestion=True)

        adcp_error = result.wire_error_envelope["adcp_error"]
        assert adcp_error["field"].startswith("status_filter"), (
            f"the rejection must name the field the buyer got wrong, got {adcp_error['field']!r}"
        )
        assert "pending_creatives" in adcp_error["message"], (
            f"the rejection must tell the buyer which values ARE valid, got {adcp_error['message']!r}"
        )

    def test_a_successful_mcp_call_exposes_the_wire_response_it_declares(self, integration_db):
        """``has_wire=True`` is a promise about the success path too.

        The env declared it and delivered ``None``. Grading only the error path
        would leave the declared-but-uncaptured success wire with no grader at
        all, which is the same defect wearing the other face.
        """
        from tests.factories import PrincipalFactory, TenantFactory

        with MediaBuyListEnv(tenant_id="t1", principal_id="p1") as env:
            tenant = TenantFactory(tenant_id="t1")
            PrincipalFactory(tenant=tenant, principal_id="p1")
            result = env.call_via(Transport.MCP)

        assert not result.is_error, f"expected success, got error: {result.error!r}"
        assert result.wire_response is not None, (
            "MediaBuyListEnv declares has_wire=True, so a successful MCP dispatch must "
            "carry the wire response it promised, not None"
        )
        assert "media_buys" in result.wire_response
