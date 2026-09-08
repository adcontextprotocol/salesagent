"""Guard: no second hostname blocklist exists outside the egress package.

The real blocklist -- cloud-metadata hostnames, Docker-internal aliases,
localhost -- lives in exactly one place: src/core/security/egress/policy.py's
_BLOCKED_HOSTNAMES. TID251 (ruff-egress.toml) cannot see a hostname-set
LITERAL the way it sees an import -- constructing {"metadata.google.internal",
...} is not an import statement -- so this AST scan is the backstop TID251's
own mechanism structurally cannot cover (GH #1589).
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_guard_vocabulary_contains,
    parse_module,
    repo_root,
    scan_src,
)

# Two of the real blocklist's members (egress/policy.py's _BLOCKED_HOSTNAMES)
# -- named directly in the plan text -- are the sentinels: a set/frozenset
# literal containing either is presumptively a SECOND hostname blocklist.
_SENTINEL_HOSTNAMES = frozenset({"metadata.google.internal", "host.docker.internal"})


def test_the_sentinels_are_still_members_of_the_real_blocklist() -> None:
    """The sentinels are a SUBSET of production's blocklist, not a copy of it.

    Without this the guard is silent about the thing it exists to protect. Its
    detector matches two hostname strings; if production's ``_BLOCKED_HOSTNAMES``
    quietly stopped containing ``metadata.google.internal``, every scan here
    would keep passing while the address the whole #1589 lane is about became
    dialable. The constant above pins the guard's own vocabulary; this pins it
    to production's.

    Containment, deliberately not derivation: computing the sentinels FROM the
    blocklist would make the detector track whatever production happens to say,
    which is the opposite of a guard.
    """
    from src.core.security.egress.policy import _BLOCKED_HOSTNAMES

    assert_guard_vocabulary_contains(
        set(_SENTINEL_HOSTNAMES),
        set(_BLOCKED_HOSTNAMES),
        why=(
            "Sentinel hostname(s) are no longer in the production blocklist "
            "(src/core/security/egress/policy.py::_BLOCKED_HOSTNAMES). Either the blocklist lost "
            "an address it must refuse, or the sentinels are stale -- the first is a security "
            "regression, the second makes this guard scan for strings production no longer uses."
        ),
    )


_EGRESS_PACKAGE_PREFIX = "src/core/security/egress/"


def _literal_elements(node: ast.AST) -> list[ast.expr] | None:
    """The element list of a set/frozenset/set(...) construction, or None."""
    if isinstance(node, ast.Set):
        return node.elts
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("frozenset", "set")
        and node.args
        and isinstance(node.args[0], (ast.Set, ast.List, ast.Tuple))
    ):
        return node.args[0].elts
    return None


def find_hostname_blocklist_violations(tree: ast.Module) -> list[int]:
    """Line numbers of set/frozenset literals containing a blocklist sentinel."""
    violations = []
    for node in ast.walk(tree):
        elements = _literal_elements(node)
        if elements is None:
            continue
        strings = {el.value for el in elements if isinstance(el, ast.Constant) and isinstance(el.value, str)}
        if strings & _SENTINEL_HOSTNAMES:
            violations.append(node.lineno)
    return sorted(violations)


def _scan_src_outside_egress() -> dict[str, list[int]]:
    """Violations outside the egress package, which legitimately owns this logic.

    ``scan_src`` raises if NO file under the prefix is flagged — a scope boundary
    that excludes nothing is a boundary that would silently permit the first
    violation to appear there.
    """
    return scan_src(find_hostname_blocklist_violations, skip_prefixes=(_EGRESS_PACKAGE_PREFIX,))


class TestNoHostnameBlocklistDuplication:
    @pytest.mark.arch_guard
    def test_no_second_blocklist_outside_egress(self):
        offenders = _scan_src_outside_egress()
        assert not offenders, (
            "A hostname blocklist (containing a sentinel from the real one, "
            "src/core/security/egress/policy.py's _BLOCKED_HOSTNAMES) was found "
            f"outside the egress package: {offenders}. Address classification "
            "belongs to the egress package alone (GH #1589)."
        )


class TestHostnameBlocklistDetector:
    @pytest.mark.arch_guard
    def test_detector_catches_known_bad(self):
        assert_detector_catches_ast_snippets(
            find_hostname_blocklist_violations,
            snippets={
                "frozenset literal": ('BLOCKED = frozenset({"metadata.google.internal", "evil.example"})\n'),
                "bare set literal": '_HOSTS = {"host.docker.internal"}\n',
                "set() call": 'x = set(["metadata.google.internal"])\n',
                "list arg to frozenset": 'x = frozenset(["host.docker.internal", "other"])\n',
            },
        )

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("unrelated string set", 'X = frozenset({"apple", "banana"})\n'),
            ("non-sentinel hostname set", 'X = frozenset({"example.com", "other.example"})\n'),
            ("sentinel as a bare string, not in a set", 'X = "metadata.google.internal"\n'),
        ],
    )
    def test_detector_ignores_non_violations(self, label, source):
        assert find_hostname_blocklist_violations(ast.parse(source)) == [], f"false positive on {label}"

    @pytest.mark.arch_guard
    def test_real_blocklist_is_excluded_by_package_prefix(self):
        """egress/policy.py legitimately contains the sentinels -- excluded by being IN the package, not a per-file exemption."""
        repo = repo_root()
        real_file = repo / "src/core/security/egress/policy.py"
        assert find_hostname_blocklist_violations(parse_module(real_file)) != [], (
            "expected the real _BLOCKED_HOSTNAMES to trip the raw detector (non-vacuity); "
            "the package-prefix exclusion in _scan_src_outside_egress is what suppresses it"
        )
        assert "src/core/security/egress/policy.py" not in _scan_src_outside_egress()
