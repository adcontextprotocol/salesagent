"""Structural guard: an enum-valued thing is compared to a MEMBER, never to text.

The disease, stated once: *code answers "which one is this?" by comparing against
a string literal.* The spelling then becomes every caller's problem, and callers
disagree — ``order_approval_service`` compared lowercase ``"bearer"`` while
``protocol_webhook_service`` compared spec-cased ``"Bearer"``, so the same stored
row authenticated on one path and silently did not on the other. The egress seam
had the same shape at ``scheme == "HMAC-SHA256"``: the branch that decides whether
a webhook is SIGNED, where a typo downgrades delivery to unsigned rather than
failing.

A mistyped MEMBER does not resolve. A mistyped LITERAL takes the wrong branch in
silence. That asymmetry is the whole rule.

**Why a guard and not just mypy.** ``strict_equality`` (enabled in ``mypy.ini``)
catches the plain-``Enum``-vs-``str`` case, because those types do not overlap.
It cannot catch ``StrEnum``, whose members ARE strings, so the comparison is
perfectly legal and silently spelling-dependent — and ``AuthenticationScheme``,
the enum this started with, is a ``StrEnum``. It also cannot catch ``x.value ==
"..."``, which compares two genuine ``str`` values. Those two shapes are what
this scans for; the two mechanisms are complementary, not redundant.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    SCHEME_LITERAL_CASINGS,
    assert_detector_catches_ast_snippets,
    assert_guard_vocabulary_contains,
    assert_violations_match_allowlist,
    parse_module,
    rel,
    repo_root,
    src_python_files,
)

# Scheme spellings, in the casings that have actually appeared in this codebase.
# The point of the guard is precisely that these disagree with each other.
_SCHEME_LITERALS = SCHEME_LITERAL_CASINGS


def test_every_pinned_scheme_is_covered_by_the_literals_this_guard_matches() -> None:
    """Every value of the pinned enum appears here, in at least its own casing.

    The point of the guard is that a scheme must be compared as an enum, not as
    a string -- so the set of strings it recognises has to track the enum. A pin
    bump adding a third scheme would otherwise leave that scheme quietly
    uncovered: comparisons against it would be exactly the defect this guard
    exists to catch, and the guard would not see them.

    Containment, not derivation: the casing VARIANTS are deliberately hand-held
    (the whole point is catching a wrong casing), so this asserts the canonical
    value is present rather than regenerating the set from the enum.
    """
    from adcp.types import AuthenticationScheme

    assert_guard_vocabulary_contains(
        {member.value for member in AuthenticationScheme},
        set(_SCHEME_LITERALS),
        why=(
            "A pinned AuthenticationScheme value is not in _SCHEME_LITERALS, so a comparison "
            "against it is invisible to this guard. Add the value and its plausible casings -- "
            "the pin moved and the guard did not."
        ),
    )


# Files permitted to still compare a scheme literal. Shrink-only.
#
# ``src/core/utils/mcp_client.py`` — JUSTIFIED FALSE POSITIVE, not debt. Its
# ``auth_type == "bearer"`` picks a header for an OUTBOUND call to another MCP
# server, and its sibling value is ``"api_key"`` — a different vocabulary that
# merely shares the word "Bearer". Forcing the AdCP enum onto it would assert a
# relationship that does not exist. (``src/core/auth.py`` parses the INBOUND
# ``Authorization: Bearer`` header for the same reason, but uses ``.startswith``,
# so it never matches this detector.)
#
# ``src/admin/blueprints/principals.py`` was here as DEBT, with the note that its
# ``auth_type == "hmac_sha256"`` was the smaller half of the defect and that
# converting the route to register through the gate would fix both at once. That
# is what happened (#1802): the route now goes
# ``accept_push_notification_primitives`` -> ``PushNotificationConfigRepository``
# and constructs no ORM model, and the form's option value is rendered from
# ``AuthenticationScheme`` so no spelling is written by hand. Entry removed —
# this list only shrinks.
_ALLOWLIST: set[tuple[str, ...]] = {
    ("src/core/utils/mcp_client.py",),
}


def _string_constants(node: ast.expr) -> list[str]:
    """String constants directly in *node*, including inside a tuple/list/set."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return [s for element in node.elts for s in _string_constants(element)]
    return []


def _constants_in_pattern(pattern: ast.pattern) -> list[str]:
    """String constants used as a match-case value pattern."""
    if isinstance(pattern, ast.MatchValue):
        return _string_constants(pattern.value)
    if isinstance(pattern, ast.MatchOr):
        return [s for alt in pattern.patterns for s in _constants_in_pattern(alt)]
    return []


def _find_violations(tree: ast.Module) -> list[int]:
    """Line numbers where a scheme literal is compared or matched against."""
    violations: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            compared = [s for operand in [node.left, *node.comparators] for s in _string_constants(operand)]
        elif isinstance(node, ast.match_case):
            compared = _constants_in_pattern(node.pattern)
        else:
            continue
        if any(literal in _SCHEME_LITERALS for literal in compared):
            violations.append(getattr(node, "lineno", 0) or node.pattern.lineno)
    return violations


def test_no_scheme_literal_comparisons():
    """No module decides an auth scheme by comparing against text."""
    repo = repo_root()
    found: set[tuple[str, ...]] = set()
    detail: list[str] = []
    for path in src_python_files(repo):
        lines = _find_violations(parse_module(path))
        if lines:
            found.add((rel(path),))
            detail.extend(f"  {rel(path)}:{line}" for line in sorted(lines))

    assert_violations_match_allowlist(
        found,
        _ALLOWLIST,
        fix_hint=(
            "Compare against an AuthenticationScheme member, not a string:\n"
            "    if scheme == AuthenticationScheme.HMAC_SHA256:   # not scheme == 'HMAC-SHA256'\n"
            "A mistyped member fails to resolve; a mistyped literal silently takes the wrong "
            "branch — and for HMAC that means delivering UNSIGNED.\n"
            "Sites found:\n" + "\n".join(sorted(detail))
        ),
    )


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("equality", "if scheme == 'HMAC-SHA256':\n    sign()\n"),
        ("lowercase equality", "if auth_type == 'bearer':\n    header()\n"),
        ("membership", "if scheme in ('Bearer', 'Basic'):\n    header()\n"),
        ("match case", "match scheme:\n    case 'Bearer':\n        header()\n"),
        ("match or-pattern", "match scheme:\n    case 'Bearer' | 'Basic':\n        header()\n"),
        ("dot-value", "if scheme.value == 'HMAC-SHA256':\n    sign()\n"),
    ],
)
def test_the_detector_catches_known_bad(label, source):
    """The guard must actually fire — a drained detector passes silently."""
    assert_detector_catches_ast_snippets(_find_violations, snippets={label: source})


def test_the_enum_member_form_is_not_flagged():
    """The prescribed fix must pass, or the guard would forbid its own remedy."""
    good = "if scheme == AuthenticationScheme.HMAC_SHA256:\n    sign()\n"
    assert not _find_violations(ast.parse(good)), "the guard flags the form it tells callers to use"
