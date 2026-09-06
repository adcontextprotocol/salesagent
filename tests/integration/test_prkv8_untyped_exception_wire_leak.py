"""Reproduction for #1587: raw exception text reaching the buyer-facing wire.

An untyped exception raised inside a dispatched skill's business logic is
normalized to a wire-safe ``AdCPSalesAgentError`` by ``adcp_error_for()``
(src/core/exceptions.py) — the single chokepoint used by all three transport
boundaries (A2A, MCP, REST). Its final fallback branch,
``return AdCPSalesAgentError(str(exc) or type(exc).__name__)``, uses the raw exception's
``str()`` as the buyer-facing ``message`` verbatim: whatever internal detail
the exception happened to carry (a DB DSN, a stack fragment, an upstream
response body) lands directly in the wire's two-layer error envelope.

AdCP 3.1.1 transport-errors.mdx, Security Considerations, is a MUST-NOT list
covering exactly this: credentials, SQL, hostnames, stack traces, upstream
responses must never reach the buyer.
"""

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# A distinctive, plainly-internal-looking payload — if this string appears
# anywhere in the wire envelope, the raw exception leaked.
_SECRET_MARKER = "postgres://admin:s3cr3t-prkv8@10.0.0.5:5432/prod_shadow"


def _assert_no_leak(envelope: dict, label: str) -> None:
    assert envelope is not None, f"no wire envelope captured on {label}"
    rendered = str(envelope)
    assert _SECRET_MARKER not in rendered, f"raw exception text leaked into the {label} wire envelope: {rendered!r}"


@pytest.mark.parametrize("transport", [Transport.A2A, Transport.MCP, Transport.REST], ids=lambda t: t.value)
class TestUntypedExceptionDoesNotLeakOntoWire:
    """An untyped exception inside a dispatched skill must not put its own
    text on the buyer-facing wire, on any transport.

    Uses ``env.inject_untyped_exception()`` (added by prkv.18, the harness
    capability this test originally motivated but hand-rolled around — see
    prkv.18's codebase-scan disposition table). It patches the skill's
    ``_impl`` directly (real dispatch through A2A skill routing / the MCP
    tool pipeline / the REST route, only the innermost business-logic call is
    mocked) and, for REST specifically, sets
    ``env.REST_RAISE_SERVER_EXCEPTIONS = False`` as an INSTANCE attribute so
    ``get_rest_client()`` observes the real
    ``@app.exception_handler(Exception)`` catch-all response instead of
    Starlette's ``ServerErrorMiddleware`` re-raising into the test (see
    ``BaseTestEnv.inject_untyped_exception``'s docstring for why the default
    ``TestClient(app)`` can't observe this path)."""

    def test_no_raw_exception_text_in_wire_envelope(self, integration_db, transport):
        with ProductEnv(tenant_id="prkv8-leak", principal_id="prkv8-principal") as env:
            tenant = TenantFactory(tenant_id="prkv8-leak", subdomain="prkv8-leak")
            PrincipalFactory(tenant=tenant, principal_id="prkv8-principal")

            env.inject_untyped_exception(RuntimeError(_SECRET_MARKER))
            result = env.call_via(transport, brief="video ads")

            assert result.is_error, f"expected an error result on {transport.value}, got {result.payload!r}"
            _assert_no_leak(result.wire_error_envelope, transport.value)


class TestInternalErrorForDoesNotLeakOntoWire:
    """Separate obligation: adcp_a2a_server.py's ``_internal_error_for()`` (the
    ticket's literal WHERE) builds the top-level A2A JSON-RPC ``error.message``
    field independently of ``adcp_error_for()`` — it is reachable only
    from NON-skill A2A boundary failures (``on_message_send``'s outer
    fallthrough, and the push-notification-config JSON-RPC methods), never from
    a dispatched skill's own per-invocation catch (that goes through
    ``_build_failed_skill_result`` instead, covered by the class above).
    Mutation-verified: this test does NOT fail if only
    ``adcp_error_for()``'s fix is reverted — it exercises the OTHER
    mechanism specifically, by raising during identity resolution, which runs
    inside ``on_message_send``'s outer try/except, before skill dispatch."""

    def test_no_raw_exception_text_in_internal_error_message(self, integration_db):
        import asyncio

        from a2a.server.routes.common import ServerCallContext
        from a2a.types import SendMessageRequest

        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler, InternalError
        from tests.utils.a2a_helpers import create_a2a_message_with_skill

        handler = AdCPRequestHandler()
        # get_products is in DISCOVERY_SKILLS (no auth required), so on_message_send
        # still calls _resolve_a2a_identity(None, require_valid_token=False, ...)
        # even with no auth token presented -- the simplest way to raise inside the
        # outer try/except, before the skill-dispatch loop's own catch takes over.
        handler._get_auth_token = lambda *a, **kw: None  # type: ignore[assignment]
        handler._resolve_a2a_identity = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError(_SECRET_MARKER))  # type: ignore[assignment]

        message = create_a2a_message_with_skill(skill_name="get_products", parameters={"brief": "video ads"})
        params = SendMessageRequest(message=message)

        with pytest.raises(InternalError) as exc_info:
            asyncio.run(handler.on_message_send(params, ServerCallContext()))

        raised = exc_info.value
        assert _SECRET_MARKER not in str(raised.message), (
            f"raw exception text leaked into InternalError.message: {raised.message!r}"
        )
        # The safe two-layer envelope must still be present in data= -- this fix
        # must not regress the one channel that WAS already safe.
        envelope = raised.data
        _assert_no_leak(envelope, "a2a InternalError.data")
        assert envelope.get("adcp_error", {}).get("code"), f"expected a code in InternalError.data: {envelope!r}"
