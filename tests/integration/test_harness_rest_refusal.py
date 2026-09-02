"""A transport the harness cannot dispatch must refuse loudly, not dispatch something else.

``MediaBuyCreateListEnv`` routes ``req=GetMediaBuysRequest`` to the get_media_buys
dispatch on IMPL/A2A/MCP, but declares no REST body of its own — so a REST list
request falls through to ``MediaBuyCreateEnv.build_rest_body``, a *create*-shaped
builder. There is no get_media_buys REST route to fall through to: ``src/routes/api_v1.py``
exposes only ``POST /media-buys`` (create), ``PUT /media-buys/{id}`` (update) and
``POST /media-buys/delivery``.

What the inherited create builder does with a list request today, measured at HEAD
629230123 — and deliberately NOT what these tests assert, because both arms are
accidents rather than a contract:

  * ``req=`` arm: ``AttributeError: 'GetMediaBuysRequest' object has no attribute
    'packages'``, raised inside ``_restore_creative_ids`` (media_buy_create.py:54
    via :406) — an obscure crash in a create-only helper, not a refusal.
  * flat-kwargs arm: builds ``{"media_buy_ids": [...], "idempotency_key": ...}`` and
    POSTs it, create-SHAPED, to the create collection ``/api/v1/media-buys``.

The obligation these tests grade is the refusal itself, and — the part that is easy
to get wrong — that the refusal SURVIVES to the caller. Two launderers sit between
the raise and the report:

  (a) ``tests/bdd/conftest.py:103-105`` converts any ``NotImplementedError`` raised
      in a BDD call phase into ``report.outcome = "skipped"`` + ``wasxfail``. A
      NotImplementedError refusal is therefore a silent shrink of the test matrix.
  (b) ``RestDispatcher.dispatch`` (dispatchers.py:151-181) wraps the whole in-process
      REST dispatch — INCLUDING ``env.build_rest_body`` — in ``except Exception ->
      TransportResult(error=exc)``. An ``Exception``-derived refusal comes back as an
      error-shaped result, indistinguishable from a production error response, so any
      Then step that only checks "an error was returned" goes GREEN on the harness
      refusing to dispatch.

``pytest.fail(..., pytrace=False)`` raises ``_pytest.outcomes.Failed``, whose MRO is
``(Failed, OutcomeException, BaseException)``: it is not an ``Exception`` (escapes (b))
and not a ``NotImplementedError`` (escapes (a)). ``test_weaker_refusal_dialects_are_swallowed``
below is the mechanical demonstration, against the real dispatcher.

Scope note, stated rather than faked: launderer (a) is graded here by the type
property only, not end to end. UC-019 is in ``_NO_REST_UC_TAG_PREFIXES``
(tests/bdd/conftest.py:2833), so its scenarios are parametrized a2a+mcp and the REST
arm never runs under BDD at all — no BDD test reaches this seam, and driving the
``pytest_runtest_makereport`` hook for real would need a nested pytest run rather than
a test. The integration pin in this file is the grading path for the seam; the BDD
conftest hook does not apply to it.

GH #1941 (review finding F18); precedent for shape: tests/integration/test_harness_wire_response.py
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.schemas._base import GetMediaBuysRequest, UpdateMediaBuyRequest
from tests.harness.media_buy_create_list import MediaBuyCreateListEnv
from tests.harness.media_buy_create_update_list import MediaBuyCreateUpdateListEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.mark.requires_db
class TestUnroutedRestDispatchRefuses:
    """The un-routed REST arm of the create+list env refuses instead of dispatching."""

    def test_rest_list_request_refuses_through_call_via(self, integration_db):
        """A REST get_media_buys call raises out of ``call_via``, it does not return a result.

        Driven through ``env.call_via(Transport.REST, ...)`` — the whole dispatch — and
        NOT through a direct ``build_rest_body()`` call. A direct-call pin passes while
        launderer (b) still eats the refusal one call-frame over, which is greening the
        cited test while the disease persists.

        ``pytest.raises`` is what mechanically locks the dialect: downgrade the refusal
        to ``NotImplementedError`` or ``AssertionError`` and ``RestDispatcher`` swallows
        it into an error-shaped ``TransportResult``, nothing propagates, and this test
        reddens with DID NOT RAISE.

        The message must name what refused and why, so the reader of a failing run does
        not have to re-derive the route table: the tool and the transport.
        """
        with MediaBuyCreateListEnv() as env:
            with pytest.raises(pytest.fail.Exception) as excinfo:
                env.call_via(Transport.REST, req=GetMediaBuysRequest(media_buy_ids=["mb_absent"]))

        message = str(excinfo.value)
        assert "get_media_buys" in message, f"refusal does not name the tool it refused: {message!r}"
        assert "REST" in message or "rest" in message, f"refusal does not name the transport: {message!r}"

    def test_refusal_escapes_both_launderers_by_type(self):
        """The refusal type is outside the reach of both launderers on the dispatch path.

        This is the property the choice of ``pytest.fail`` rests on, pinned so a future
        "simplification" back to ``NotImplementedError`` (which re-arms both) cannot pass
        silently. Launderer (b) is additionally demonstrated end-to-end against the real
        dispatcher in ``test_weaker_refusal_dialects_are_swallowed``.
        """
        failed = pytest.fail.Exception
        assert not issubclass(failed, Exception), (
            f"{failed.__name__} is an Exception subclass — RestDispatcher's "
            "`except Exception` (dispatchers.py:180) would swallow the refusal into an "
            "error-shaped TransportResult"
        )
        assert not issubclass(failed, NotImplementedError), (
            f"{failed.__name__} is a NotImplementedError subclass — tests/bdd/conftest.py:103-105 "
            "would convert the refusal into skipped + wasxfail"
        )
        assert issubclass(failed, BaseException)


class _RefusalDialectEnv(MediaBuyCreateListEnv):
    """A create+list env whose REST body builder refuses in a configurable dialect."""

    refusal: Any = None

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        raise self.refusal


@pytest.mark.requires_db
class TestRefusalDialectSurvivesTheDispatcher:
    """Why the dialect is ``pytest.fail`` and not the ``_outcome_helpers`` AssertionError."""

    @pytest.mark.parametrize(
        "refusal",
        [
            pytest.param(NotImplementedError("REST get_media_buys is not routed"), id="not-implemented-error"),
            pytest.param(AssertionError("REST get_media_buys is not routed"), id="assertion-error"),
        ],
    )
    def test_weaker_refusal_dialects_are_swallowed(self, integration_db, refusal):
        """An ``Exception``-derived refusal returns as an error-shaped result, not a raise.

        The refusal becomes ``TransportResult(error=...)`` — the same shape a real
        production error response produces — so a Then step asserting only "an error was
        returned" cannot tell "the seller rejected the request" from "the harness declined
        to dispatch". That is the launderer the pin above exists to route around, measured
        here against the production ``RestDispatcher`` rather than argued.
        """
        env_class = type("_Dialect", (_RefusalDialectEnv,), {"refusal": refusal})
        with env_class() as env:
            result = env.call_via(Transport.REST, req=GetMediaBuysRequest(media_buy_ids=["mb_absent"]))

        assert result.is_error, "expected the dispatcher to have swallowed the refusal into an error result"
        assert result.error is refusal
        assert result.wire_error_envelope is None, (
            "a swallowed harness refusal carries no wire envelope — it never reached the server, "
            "which is exactly why it is indistinguishable from a transport-level production failure"
        )

    def test_the_chosen_dialect_propagates(self, integration_db):
        """The same env, refusing via ``pytest.fail``, raises out of the dispatcher."""
        env_class = type("_Dialect", (_RefusalDialectEnv,), {})

        def _refuse() -> None:
            pytest.fail("REST get_media_buys is not routed", pytrace=False)

        with env_class() as env:
            env.build_rest_body = lambda **kwargs: _refuse()  # type: ignore[method-assign]
            with pytest.raises(pytest.fail.Exception):
                env.call_via(Transport.REST, req=GetMediaBuysRequest(media_buy_ids=["mb_absent"]))


@pytest.mark.requires_db
class TestNonListRestRoutingIsPreserved:
    """The non-list arm must delegate via ``super()``, not by naming a parent class.

    ``MediaBuyCreateUpdateListEnv.__mro__`` is [CreateUpdateList, CreateList,
    ListDispatchMixin, DualEnv, CreateEnv, IntegrationEnv, BaseTestEnv], so
    ``build_rest_body`` resolves to ``MediaBuyDualEnv.build_rest_body`` — the stateful
    create-vs-update router. A refusal override on ``MediaBuyCreateListEnv`` that fell
    back to ``MediaBuyCreateEnv.build_rest_body`` explicitly instead of
    ``super().build_rest_body(**kwargs)`` would skip that router: updates would build a
    create-shaped body and POST the collection.
    """

    def test_update_request_still_routes_to_the_update_body_and_endpoint(self):
        env = MediaBuyCreateUpdateListEnv()
        req = UpdateMediaBuyRequest(media_buy_id="mb_seeded", paused=True)

        body = env.build_rest_body(req=req)

        assert "media_buy_id" not in body, (
            "update REST body still carries media_buy_id — build_rest_body did not reach "
            "MediaBuyDualEnv._build_update_rest_body, so super() delegation was bypassed"
        )
        assert body["paused"] is True
        assert env.REST_ENDPOINT == "/api/v1/media-buys/mb_seeded"
        assert env.REST_METHOD == "put"

    def test_create_request_still_routes_to_the_create_collection(self):
        env = MediaBuyCreateUpdateListEnv()
        body = env.build_rest_body(
            brand={"domain": "testbrand.com"},
            packages=[{"product_id": "prod_1", "budget": 1000, "pricing_option_id": "po_1"}],
        )

        assert body["brand"] == {"domain": "testbrand.com"}
        assert env.REST_ENDPOINT == "/api/v1/media-buys"
        assert env.REST_METHOD == "post"
