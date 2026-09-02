"""Structural guard: the storyboard seams are the only expressible route.

Two seams own resolution for the storyboard audit chain:

* ``storyboard_spec.adcp_home()`` — where the pinned AdCP tree lives
  ($ADCP_HOME, then the in-repo release bundle, then a personal clone).
* ``storyboard_spec.pinned_version()`` — which version that is, read from the
  INSTALLED SDK via ``adcp.get_adcp_spec_version()``.

Both existed before this guard and adoption was by convention, which is why
every review round on #1858 found another site that had missed them: modules
that built ``~/projects/adcp`` by hand (so they resolved a tree at whatever
revision one developer last fetched, and skipped in CI), and generators that
typed the version into strings they publish (so a repin would have them assert a
version the code is not on).

This guard makes the raw shapes inexpressible inside the chain. It is the
"ban the raw pattern" mechanism CLAUDE.md documents and 70+ sibling guards
already use.

Deliberately AST-based, not grep-based. 14 lines under scripts/ and tests/
mention ``projects/adcp`` in prose — module docstrings and comments explaining
what the resolver does, several written while fixing exactly this class. A grep
guard reddens on all of them; an AST guard sees only constructions.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── Assertion 1: nothing outside the resolver builds a personal-clone path ────

# The resolver itself. Its last-resort fallback IS the personal clone, which is
# the documented third choice in adcp_home()'s resolution order.
_RESOLVER = Path("scripts/audit/storyboard_spec.py")

# Exempt, with the reason, because a name list without one rots into an
# allowlist nobody can re-derive:
#
#   adcp_schemas_pinned/_refresh.py reads its source with
#       git -C <clone> show <PINNED_SHA>:static/schemas/source/<rel>
#   which needs a GIT REPOSITORY at a commit. The release bundle is an extracted
#   tarball: no history, and a different layout (schemas/ at the root, versus the
#   clone's static/schemas/source/). adcp_home() cannot serve it however it is
#   called, and the module already degrades to GitHub raw at the pinned SHA
#   rather than failing closed.
_CLONE_EXEMPT = {Path("tests/fixtures/adcp_schemas_pinned/_refresh.py")}


# The clone path has more than one spelling, and a guard that catches only the
# spelling the last author happened to use is the vacuity this whole change set
# exists to remove. Each spelling below was tested against the matcher; the one
# it cannot see is named in the docstring rather than left for someone to find.
_CLONE_SEGMENTS = ("projects", "adcp")
_CLONE_TEXT = "~/projects/adcp"


def _is_home_call(node: ast.AST) -> bool:
    """``Path.home()`` — or ``Path("~").expanduser()``, which is the same place.

    The second spelling reaches the home directory without ever calling
    ``home()``, so matching on the method name alone misses it.
    """
    if not isinstance(node, ast.Call):
        return False
    if getattr(node.func, "attr", "") == "home":
        return True
    if getattr(node.func, "attr", "") in {"expanduser", "expandvars"}:
        base = getattr(node.func, "value", None)
        return isinstance(base, ast.Call) and any(
            isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("~") for a in base.args
        )
    return False


def _segments_name_the_clone(parts: list[str]) -> bool:
    """True whether the clone is spelled as two segments or one.

    ``/ "projects" / "adcp"`` and ``/ "projects/adcp"`` denote the same path;
    a matcher that only understands the first is a matcher for one author's
    habit. Neither form may match ``adcp-req``, a different repository.
    """
    if tuple(parts[:2]) == _CLONE_SEGMENTS:
        return True
    joined = "/".join(_CLONE_SEGMENTS)
    return any(p == joined or p.startswith(joined + "/") for p in parts)


def _home_clone_chain(node: ast.AST) -> bool:
    """``Path.home() / "projects" / "adcp"``, at any depth and any spacing.

    Matches the FULL segment pair on purpose. ``Path.home() / "projects"`` alone
    also matches scripts/compile_bdd.py, whose target is ``adcp-req`` — a
    different repository with its own $ADCP_REQ_PATH override. Banning that would
    force a third exemption for a site that is not this seam's business.
    """
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
        return False
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
        if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
            parts.append(cur.right.value)
        cur = cur.left
    parts.reverse()
    return _segments_name_the_clone(parts) and _is_home_call(cur)


def _home_clone_joinpath(node: ast.AST) -> bool:
    """``Path.home().joinpath("projects", "adcp")`` and ``.joinpath("projects/adcp")``."""
    if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "joinpath":
        return False
    if not _is_home_call(getattr(node.func, "value", None)):
        return False
    args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return tuple(args[:2]) == _CLONE_SEGMENTS or any("/".join(_CLONE_SEGMENTS) in a for a in args)


def _clone_string_literal(node: ast.AST) -> bool:
    """``Path("~/projects/adcp")`` / ``os.path.expanduser("~/projects/adcp")``.

    These never build a chain, so the two matchers above cannot see them.

    Flags the string only where it is USED AS A PATH — an argument to ``Path()``
    or to an ``expanduser``/``expandvars`` call. Flagging the bare constant
    reddens on prose instead: 11 module docstrings and error messages name
    ``~/projects/adcp`` to explain what the resolver does, and several were
    written while fixing this very class. Prose describing the clone is not a
    site that resolves one.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # Both spellings: `Path(...)` and `pathlib.Path(...)`. The repo uses the
    # qualified form in 19 places, so an ast.Name-only check is a real gap, not
    # a theoretical one.
    is_path_ctor = (isinstance(func, ast.Name) and func.id == "Path") or (
        isinstance(func, ast.Attribute) and func.attr == "Path"
    )
    is_expanduser = isinstance(func, ast.Attribute) and func.attr in {"expanduser", "expandvars"}
    if not (is_path_ctor or is_expanduser):
        return False
    return any(isinstance(a, ast.Constant) and isinstance(a.value, str) and _CLONE_TEXT in a.value for a in node.args)


def _names_the_clone(node: ast.AST) -> bool:
    return _home_clone_chain(node) or _home_clone_joinpath(node) or _clone_string_literal(node)


def _python_files() -> list[Path]:
    return sorted(
        p for root in ("scripts", "tests") for p in (REPO_ROOT / root).rglob("*.py") if "__pycache__" not in p.parts
    )


def test_no_personal_clone_construction_outside_the_resolver() -> None:
    """Only adcp_home() may name a personal clone; everyone else calls it.

    Covers eight spellings, each verified against this matcher by a fixture
    below: the ``/`` chain canonical, with extra spacing, at greater depth, and
    with the segments fused into one string (``/ "projects/adcp"``); a base of
    ``Path.home()`` or of ``Path("~").expanduser()``; ``joinpath`` with either
    segment form; and a ``"~/projects/adcp"`` string passed to ``Path()`` or to
    an ``expanduser`` call. It deliberately does NOT match ``adcp-req``, a
    different repository.

    KNOWN BLIND SPOT, one class, stated rather than discovered later: anything
    bound through a NAME before use. A chain split across statements
    (``p = Path.home() / "projects"`` then ``p / "adcp"``), or the path text
    hoisted to a constant (``_C = "~/projects/adcp"`` then ``Path(_C)``), is
    invisible here — seeing either needs dataflow, not a syntax match. No site
    is written either way. If one appears the fix is to inline the value, not to
    grow this guard into a dataflow analysis it cannot maintain.
    """
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT)
        if rel == _RESOLVER or rel in _CLONE_EXEMPT:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if _names_the_clone(node):
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], (
        "these sites build a path to a personal ~/projects/adcp clone instead of calling "
        "storyboard_spec.adcp_home(). A clone sits at whatever revision its owner last fetched, "
        "so neither CI nor another contributor reproduces it:\n  " + "\n  ".join(offenders)
    )


_CLONE_SPELLINGS = {
    "chain canonical": ('x = Path.home() / "projects" / "adcp"', True),
    "chain extra spacing": ('x = Path.home()  /  "projects"  /  "adcp"', True),
    "chain deeper": ('x = Path.home() / "projects" / "adcp" / "dist"', True),
    "chain fused segment": ('x = Path.home() / "projects/adcp"', True),
    "base Path('~').expanduser()": ('x = Path("~").expanduser() / "projects" / "adcp"', True),
    "joinpath two segments": ('x = Path.home().joinpath("projects", "adcp")', True),
    "joinpath fused segment": ('x = Path.home().joinpath("projects/adcp")', True),
    "Path(str).expanduser()": ('x = Path("~/projects/adcp").expanduser()', True),
    "os.path.expanduser(str)": ('x = os.path.expanduser("~/projects/adcp")', True),
    "pathlib.Path(str) qualified": ('x = pathlib.Path("~/projects/adcp")', True),
    # adcp-req is a DIFFERENT repository with its own $ADCP_REQ_PATH override.
    # Matching it would force an exemption for a site this seam does not own.
    "adcp-req segments": ('x = Path.home() / "projects" / "adcp-req"', False),
    "adcp-req fused": ('x = Path.home() / "projects/adcp-req"', False),
    # Prose naming the clone is not a site that resolves one.
    "prose in a string": ('x = "see ~/projects/adcp for the clone"', False),
}


def test_clone_matcher_sees_every_spelling_it_claims() -> None:
    """Pins the matcher's reach, so widening it later cannot silently narrow it."""
    wrong = {
        name: f"expected caught={expected}, got {not expected}"
        for name, (src, expected) in _CLONE_SPELLINGS.items()
        if any(_names_the_clone(node) for node in ast.walk(ast.parse(src))) is not expected
    }
    assert wrong == {}, f"the clone matcher disagrees with its own docstring: {wrong}"


def test_clone_matcher_cannot_see_a_split_chain() -> None:
    """Pins the ONE documented blind spot, so it stays documented.

    Seeing ``p = Path.home() / "projects"`` then ``p / "adcp"`` needs dataflow,
    not a syntax match. No site is written that way. If this test ever fails,
    someone taught the matcher dataflow — update the docstring, do not delete
    this test.
    """
    for src in (
        'p = Path.home() / "projects"\nx = p / "adcp"',  # chain split across statements
        '_C = "~/projects/adcp"\nx = Path(_C)',  # path text hoisted to a constant
    ):
        assert not any(_names_the_clone(node) for node in ast.walk(ast.parse(src))), src
