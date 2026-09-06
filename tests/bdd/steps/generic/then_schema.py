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
from tests.helpers.response_schemas import response_schema_ref, response_validator


def _assert_compliant(ctx: dict, tool: str, branch: str | None) -> None:
    wire = wire_dict(ctx)
    errors = sorted(response_validator(tool, branch).iter_errors(wire), key=lambda e: list(e.absolute_path))
    if errors:
        where = f"{tool} {branch}" if branch else tool
        detail = "\n".join(f"  at {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors)
        raise AssertionError(
            f"the response does not comply with the {where} spec "
            f"({response_schema_ref(tool)}):\n{detail}"
        )


@then(parsers.parse("the response is compliant with the {tool} spec"))
def then_response_compliant(ctx: dict, tool: str) -> None:
    """Grade the response the buyer received against the tool's pinned schema.

    The scenario names the TOOL, never a schema file. A filename in a feature
    file is a second spelling of "which tool is this scenario exercising", and
    the two drift silently — a scenario whose When changed keeps asserting the
    old contract and still passes.

    For a tool whose response branches, this refuses and names the branches: a
    whole-``oneOf`` check passes against the ERROR branch when the scenario
    meant success, which grades the opposite of what it says.
    """
    _assert_compliant(ctx, tool, None)


@then(parsers.parse("the response is compliant with the {tool} {branch} spec"))
def then_response_compliant_branch(ctx: dict, tool: str, branch: str) -> None:
    """Grade the response against ONE branch of a branching response.

    ``success``, ``error`` and ``submitted`` are the spec's own words, read from
    the schema's ``oneOf`` titles (``CreateMediaBuySuccess`` -> ``success``), so
    the vocabulary a scenario may use is the vocabulary the pin defines.
    """
    _assert_compliant(ctx, tool, branch)


#: ``the response should be schema-valid against <file>`` is DELETED. It named a
#: schema file, which is a second spelling of "which tool is this scenario
#: exercising" — and the two drift, silently, because a scenario whose When
#: changes keeps asserting the old contract and still passes. All 20 uses across
#: nine feature files now name the tool instead.


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
