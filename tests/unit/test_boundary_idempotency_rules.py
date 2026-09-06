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

import pytest
from pydantic import BaseModel

from src.core.schemas import CreateMediaBuyResult, CreateMediaBuySuccess, SyncCreativesResponse
from src.core.tools._boundary import (
    _cacheable_body,
    _is_error_result,
    _is_task_envelope,
    _response_model_for,
    _spec_declares_idempotency_key,
)
from src.core.tools.registry import TOOLS


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

    Most implementations raise, and a raise never reaches the save. ``create_media_buy`` is
    the exception that makes this a real check: it RETURNS a failure for an adapter
    rejection, so without a status check the boundary would store it and replay that failure
    for the whole TTL.
    """

    @pytest.mark.parametrize("status", ["failed", "rejected", "canceled", "unknown"])
    def test_a_failed_protocol_status_is_an_error(self, status: str) -> None:
        assert _is_error_result(_success_result(status)) is True

    @pytest.mark.parametrize("status", ["completed", "submitted"])
    def test_a_successful_protocol_status_is_not(self, status: str) -> None:
        assert _is_error_result(_success_result(status)) is False

    def test_a_response_with_no_protocol_status_is_not_an_error(self) -> None:
        """A plain response is not a task envelope; if its work failed, it raised."""
        assert _is_error_result(SyncCreativesResponse(creatives=[])) is False


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


class TestAKeyIsHonouredOnlyWhereTheSpecDeclaresOne:
    """Rule 1, and the reading recorded at ``_spec_declares_idempotency_key``.

    A pure-read task whose pinned schema declares no ``idempotency_key`` owes TOLERANCE of an
    unknown property, not the replay contract. ``ListAccountsRequest`` carries such a field
    locally, documented at its declaration as "not a spec field"; honouring it would turn
    every ``list_accounts`` call into a database write.
    """

    #: The pinned schemas that declare the key. Cross-checked against the SDK's own
    #: ``adcp._idempotency.IDEMPOTENT_TASKS`` by the test below, so this literal cannot
    #: quietly drift from the vocabulary it claims to name.
    EXPECTED = {"create_media_buy", "update_media_buy", "sync_creatives", "sync_accounts"}

    def test_exactly_the_mutating_tools_are_keyed(self) -> None:
        keyed = {name for name, spec in TOOLS.items() if _spec_declares_idempotency_key(spec.dto)}
        assert keyed == self.EXPECTED

    def test_the_sdk_agrees_about_which_tools_those_are(self) -> None:
        """The SDK is a cross-check, never the authority -- but it should not disagree."""
        from adcp._idempotency import IDEMPOTENT_TASKS

        assert self.EXPECTED <= IDEMPOTENT_TASKS

    def test_a_locally_added_field_does_not_enrol_a_read(self) -> None:
        """``list_accounts`` declares the field and is still not keyed. That IS the rule."""
        dto = TOOLS["list_accounts"].dto
        assert "idempotency_key" in dto.model_fields, (
            "precondition: this test is about a DTO that declares the field locally; if the "
            "declaration is gone the test no longer grades anything and should be deleted"
        )
        assert _spec_declares_idempotency_key(dto) is False


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
