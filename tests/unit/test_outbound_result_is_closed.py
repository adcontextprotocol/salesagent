"""``OutboundResult`` is closed over its own fields — no httpx type reaches a caller.

The seam returns a value object, not a borrowed ``httpx.Response``. A caller
holding the response could reach through to any attribute on it, including a
body that has already been streamed and closed, which is the leak this shape
exists to close.

Why these two asserts and not an AST guard: a ``result.response`` read anywhere
under ``src/`` is now a mypy error, so the reach-through is unrepresentable
rather than merely absent — which is what let the 247-line scanning guard that
used to live here retire. But mypy only rejects it while the field is genuinely
gone: re-add ``response`` to the dataclass and the whole repo type-checks clean
again, with every consumer reach-through representable once more. These asserts
are what keep that coverage unconditional, so they outlived the guard that
carried them.
"""

from __future__ import annotations

import dataclasses

from src.core.security import outbound_http


def test_outbound_result_declares_no_response_field() -> None:
    field_names = {f.name for f in dataclasses.fields(outbound_http.OutboundResult)}
    assert "response" not in field_names, (
        f"OutboundResult declares a 'response' field again ({sorted(field_names)}). "
        "A caller holding it can reach through to any httpx.Response attribute, and "
        "mypy stops rejecting every reach-through under src/ the moment this field "
        "exists — this assertion is the only thing standing between the two."
    )


def test_attach_body_does_not_exist() -> None:
    assert not hasattr(outbound_http, "_attach_body"), (
        "_attach_body exists again on src.core.security.outbound_http. It existed only to "
        "poke httpx.Response._content so a reach-through's .text/.json() kept working on a "
        "streamed-then-closed body; OutboundResult surfaces content directly, so its return "
        "means the borrowed-response shape is back."
    )
