"""Guard: every egress refusal raised by the seam carries ``field``.

``OutboundRequestBlocked`` carries a message that says nothing about the cause,
on purpose (AdCP 3.1.1, ``building/by-layer/L1/security.mdx`` point 6: do not
echo fetch errors back to the party that supplied the URL). Where the refused URL
came from the BUYER's request, ``error.field`` is therefore the only channel that
can name which of their inputs to fix, and a refusal path that forgets to pass
the caller's ``field=`` hands them a correctable error they cannot act on — which
fails silently, because the envelope is still well-formed and every existing test
still passes.

Not every call site surfaces the refusal that way. A site whose URL is OPERATOR
configuration — a registered agent endpoint, a vendor host — re-maps it to
CONFIGURATION_ERROR / terminal instead (see
``src/core/helpers/outbound_error_mapping.py``), because the buyer did not choose
that address and cannot correct it. That is a call-site decision about whose URL
it is; this guard is about the seam always CARRYING the field, so either
disposition remains possible.

The seam has three refusal sites today, all inside
``EgressPolicy.resolve_for_dial`` (scheme, the SDK's ``SSRFValidationError``,
and the shared supplement-range predicate) and all carry it. This guard is
about the next one somebody adds later: a body-size pre-check, a method
allowlist, a new SDK refusal. It fails that change at ``make quality`` rather
than at a buyer.

What it cannot check, stated plainly so nobody mistakes its silence for proof:
whether a CALL SITE passes a ``field`` when it should. That is semantic — only
the call site knows whether its URL came from the caller's request payload — and
the seam refuses to guess (see ``_checked_field``). This guard covers the half
that is mechanical.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    iter_call_expressions,
    parse_module,
    repo_root,
)

SEAM_FILE = "src/core/security/egress/policy.py"
REFUSAL_CLASS = "OutboundRequestBlocked"


FIX_HINT = (
    f"Every {REFUSAL_CLASS} must be raised with field=<the caller's field>. The refusal message is "
    "deliberately opaque, so field is the only thing that tells a buyer which input to fix; a path "
    "that omits it produces a correctable error nobody can correct."
)


def find_fieldless_refusals(tree: ast.Module) -> list[int]:
    """Line numbers where ``OutboundRequestBlocked`` is constructed without ``field=``.

    Construction, not ``raise``: ``_blocked`` builds the exception and returns it
    for the caller to raise, so keying on ``ast.Raise`` would miss exactly the
    path that already exists.
    """
    return [
        node.lineno
        for node in iter_call_expressions(tree, name=REFUSAL_CLASS)
        if not any(kw.arg == "field" for kw in node.keywords)
    ]


class TestRefusalCarriesField:
    """The seam's own refusal paths all carry the buyer-facing field."""

    @pytest.mark.arch_guard
    def test_seam_raises_no_fieldless_refusal(self):
        """No construction of the refusal in the seam omits ``field=``."""
        seam = repo_root() / SEAM_FILE
        violations = find_fieldless_refusals(parse_module(seam))
        assert not violations, f"{SEAM_FILE} lines {violations} raise {REFUSAL_CLASS} without field=. {FIX_HINT}"

    @pytest.mark.arch_guard
    def test_the_seam_actually_raises_this_exception(self):
        """The guard is pointed at a file that really refuses — not a stale path.

        A guard whose subject moved would pass forever by scanning nothing. This
        asserts the seam still constructs the refusal at all, so the check above
        is known to be scanning something real.
        """
        seam = repo_root() / SEAM_FILE
        constructions = [node.lineno for node in iter_call_expressions(parse_module(seam), name=REFUSAL_CLASS)]
        assert len(constructions) >= 2, (
            f"expected the seam's scheme and address refusal paths to construct {REFUSAL_CLASS}, "
            f"found {len(constructions)} — has the seam moved?"
        )


class TestGuardDetector:
    """The guard's own correctness, on synthetic sources."""

    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        """A refusal built without ``field=`` is reported, however it is spelled."""
        assert_detector_catches_ast_snippets(
            find_fieldless_refusals,
            snippets={
                "bare raise": "raise OutboundRequestBlocked(_BLOCKED_MESSAGE)\n",
                "returned for a caller to raise": (
                    "def _blocked(exc):\n    return OutboundRequestBlocked(_BLOCKED_MESSAGE)\n"
                ),
                "qualified name": "raise outbound_http.OutboundRequestBlocked('nope')\n",
                "other kwargs but no field": "raise OutboundRequestBlocked(_BLOCKED_MESSAGE, details={'a': 1})\n",
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("field passed through", "raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)\n"),
            ("field passed literally", "raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field='a.b')\n"),
            ("field explicitly none", "raise OutboundRequestBlocked(_BLOCKED_MESSAGE, field=None)\n"),
            (
                "returned with field",
                "def _blocked(exc, field):\n    return OutboundRequestBlocked(_BLOCKED_MESSAGE, field=field)\n",
            ),
            ("a different exception", "raise OutboundDeliveryFailed(attempts=3, http_status=None)\n"),
            ("catching, not raising", "try:\n    pass\nexcept OutboundRequestBlocked:\n    pass\n"),
        ],
    )
    def test_detector_ignores_correct_forms(self, label, source):
        """Carrying the field — or not being this exception at all — is not a violation."""
        assert find_fieldless_refusals(ast.parse(source)) == [], f"false positive on {label}"

    @pytest.mark.arch_guard
    def test_field_none_is_deliberately_allowed(self):
        """``field=None`` passes, and that is the intended reading, not an oversight.

        Most refusals legitimately have no field: an operator-configured endpoint
        or a stored URL never appeared in a caller's request payload, so there is
        no JSONPath-lite path to name. What the guard bans is a path that cannot
        carry one at all — omitting the parameter, rather than passing nothing.
        """
        assert find_fieldless_refusals(ast.parse("raise OutboundRequestBlocked('x', field=None)\n")) == []
        assert find_fieldless_refusals(ast.parse("raise OutboundRequestBlocked('x')\n")) == [1]
