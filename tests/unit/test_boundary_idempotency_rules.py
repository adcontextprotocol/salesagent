"""The boundary's idempotency decisions, graded directly.

``src/core/tools/_boundary.py`` is the one path from a validated request to a response, and
four of its decisions are pure functions of a model or a result. They are exercised
end-to-end by the integration suite against a real database; this module grades them where
they are decided, so a regression names the rule it broke instead of surfacing as a replay
that did not happen three layers away.

Each rule cites the pinned prose it comes from: ``docs/building/by-layer/L1/security.mdx``,
"Idempotency", in the adcontextprotocol/adcp repo at the version this repo pins.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from src.core.schemas import CreateMediaBuyResult, CreateMediaBuySuccess, SyncCreativesResponse
from src.core.tools._boundary import (
    _cacheable_body,
    _is_task_envelope,
    _response_model_for,
    invoke,
)
from src.core.tools.registry import TOOLS
from tests.factories.principal import PrincipalFactory


def _success_result(status: str = "completed") -> CreateMediaBuyResult:
    return CreateMediaBuyResult(
        status=status,
        response=CreateMediaBuySuccess(
            media_buy_id="mb_1",
            packages=[],
            status="completed",
            confirmed_at="2026-03-01T00:00:00Z",
            revision=1,
        ),
    )


class TestOnlySuccessesAreCached:
    """Rule 3: "Only successful responses are cached. On any error ... the key is not stored."

    Graded through the boundary rather than on a predicate, because the rule is enforced by
    CONTROL FLOW now: every implementation raises on failure, and a raise never reaches the
    save. There is no status inspection left to test.

    This used to grade ``_is_error_result``, a predicate that read the protocol status off a
    returned result. It existed for ONE caller -- ``create_media_buy`` returned a result
    carrying ``status="failed"`` for an adapter rejection instead of raising. That site raises
    like every other failure path now, so the predicate is deleted and the rule holds because
    caching a failure is no longer expressible.
    """

    def test_a_raising_implementation_stores_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The raise propagates and the save is never reached."""
        # Patched where the boundary BINDS them, not where they are defined: _boundary does
        # `from src.core.idempotency_replay import cache_success`, so patching the source
        # module renames something the boundary never consults.
        saved: list[object] = []
        monkeypatch.setattr("src.core.tools._boundary.cache_success", lambda **kwargs: saved.append(kwargs))
        monkeypatch.setattr("src.core.tools._boundary.lookup_cached_replay", lambda **kwargs: None)
        monkeypatch.setattr("src.core.tools._boundary.maybe_evict_expired", lambda tenant_id: None)
        # This one IS imported inside invoke(), so the source module is the right target.
        # Account resolution reads the database and is not what this rule grades.
        monkeypatch.setattr(
            "src.core.transport_helpers.enrich_identity_with_account",
            lambda identity, account: identity,
        )

        class Boom(Exception):
            pass

        def failing_impl(req: object, identity: object) -> object:
            raise Boom("the adapter rejected it")

        req = TOOLS["sync_creatives"].dto.model_validate(
            {
                "creatives": [
                    {
                        "creative_id": "cr-1",
                        "name": "c",
                        "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "x"},
                        "assets": {},
                    }
                ],
                "account": {"account_id": "acct-1"},
                "idempotency_key": "k-0123456789abcdef",
            }
        )
        identity = PrincipalFactory.make_identity(tenant_id="t1", principal_id="p1")

        with pytest.raises(Boom):
            asyncio.run(invoke("sync_creatives", failing_impl, req, identity))

        assert saved == [], "a failure reached the idempotency store"


class TestTheStoredShapeIsTheInverseOfTheLoadedOne:
    """Rule 2: the seller stores "the inner response payload (not the protocol envelope)".

    ``IdempotencyAttemptRepository.record_success`` writes ``{"status": <protocol status>,
    "response": <domain response>}``. Storing the wrapper instead would put the status in
    twice, in two vocabularies -- and a create awaiting approval, whose protocol status is
    ``submitted``, would replay as whatever the domain response happened to say.
    """

    def test_a_task_envelope_stores_its_domain_response(self) -> None:
        result = _success_result()
        assert _cacheable_body(result) is result.response

    def test_a_plain_response_stores_itself(self) -> None:
        response = SyncCreativesResponse(creatives=[])
        assert _cacheable_body(response) is response

    def test_envelope_detection_reads_the_model_not_a_list_of_tools(self) -> None:
        assert _is_task_envelope(CreateMediaBuyResult) is True
        assert _is_task_envelope(SyncCreativesResponse) is False

    def test_a_non_model_is_not_an_envelope(self) -> None:
        """Guards the success path: a raise here would lose the answer to completed work."""
        assert _is_task_envelope(dict) is False


class TestTheResponseModelIsReadOffTheImplementation:
    """The cache can only revive an envelope it can name a type for."""

    def test_every_registered_tool_declares_a_model_return(self) -> None:
        missing = sorted(name for name, spec in TOOLS.items() if _response_model_for(spec.impl) is None)
        assert missing == [], (
            f"{missing} declare no BaseModel return annotation, so a cached response for them "
            f"can never be revived and every retry re-executes silently"
        )

    def test_an_unreadable_callable_degrades_to_no_model(self) -> None:
        """A raise here would turn an un-annotatable callable into a failed request."""

        class NotAModel:
            pass

        def unannotated(req, identity=None):  # noqa: ANN001, ANN202
            return None

        def wrong_return(req: BaseModel, identity: None = None) -> NotAModel:
            return NotAModel()

        assert _response_model_for(unannotated) is None
        assert _response_model_for(wrong_return) is None
