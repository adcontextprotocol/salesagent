"""Generic Then steps that grade a response against the pinned AdCP schema.

``the response should be schema-valid against <file>`` lived at module scope in
tests/bdd/test_uc018_list_creatives.py, so only UC-018 could use it. Moving it here
is correct on its own merits — it overrides no generic text, so unlike the eight
deliberately module-scoped UC-019 steps there is nothing to keep it local.

It was NOT, however, why the UC-019 scenario was dormant, and this docstring used
to say it was. Measured: ``-k freshly`` reported ``2 xfailed`` with
``Step definition not found: Given "the buyer captured a media_buy_id from a
successful create_media_buy response"``. The blocker was the missing ``Given`` —
moving this ``Then`` would not have woken the scenario. That ``Given`` now exists
(``steps/domain/uc019_query_media_buys.py``), which is what actually woke it.

Grades the REAL WIRE. When a dispatcher stashed ``ctx["wire_response"]`` (REST's
HTTP body, MCP's structured_content, A2A's artifact DataPart) that is the document
a buyer actually receives, and validating it catches transport-framing regressions
that a re-serialized typed payload cannot.

Both steps read through ``wire_dict``, which RAISES when a real-wire transport
stashed nothing, rather than quietly re-serializing the typed payload. The
difference is the whole point: ``status`` is a model field with a default, so a
re-serialized payload carries it whether or not the envelope ever reached the
wire — an instrument that reports success precisely where it could not observe
what it was asked to grade. This module is registered globally, and that fallback
fired on ``then_envelope_status``, the step grading the obligation GH #1900 owns.

No ``exclude_none``: stripping literal nulls would mask exactly the regression
class a wire reader exists to catch, and ``confirmed_at`` reaches the wire as an
explicit null under the required-nullable contract.
"""

from __future__ import annotations

from pytest_bdd import parsers, then

from tests.bdd.steps._outcome_helpers import wire_dict
from tests.helpers.pinned_schema import validate_against_pinned_schema


@then(parsers.parse("the response should be schema-valid against {schema_file}"))
def then_response_schema_valid(ctx: dict, schema_file: str) -> None:
    """Assert the response validates against the pinned AdCP schema."""
    validate_against_pinned_schema(schema_file, wire_dict(ctx))


@then(parsers.parse("the response envelope carries status {expected_status}"))
def then_envelope_status(ctx: dict, expected_status: str) -> None:
    """Assert the protocol envelope's spec-required ``status`` is on the response.

    Scoped to the envelope rather than full-document validity on purpose: this is
    the obligation GH #1900 owns, and it is gradeable on any response whose schema
    composes core/protocol-envelope.json, independently of whether that response's
    domain body is complete.

    Parameterized on the status rather than hard-coding ``completed``: an exact-text
    step means the next scenario that needs a different terminal status has to invent
    a second sentence for the same obligation, which is how one obligation ends up
    with several phrasings and only one of them graded.
    """
    document = wire_dict(ctx)
    assert "status" in document, (
        f"AdCP 3.1.1 core/protocol-envelope.json marks 'status' REQUIRED on every task "
        f"response envelope, but the response carries only {sorted(document)}"
    )
    assert document["status"] == expected_status, (
        f"expected the envelope to report status {expected_status!r}, got {document['status']!r}"
    )
