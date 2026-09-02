"""Shared parser for line-based known-failures ledger files.

One nodeid-equivalent identifier per line, ``#``-prefixed comments and blank
lines dropped. Used by every ledger loader + its lock test (e.g.
``tests/bdd/e2e_rest_known_failures.txt`` and
``tests/storyboard/known_failures.txt``) so the parse logic has exactly one
implementation instead of being copy-pasted per ledger.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit import storyboard_spec


def load_ledger_nodeids(path: Path) -> frozenset[str]:
    """Parse a line-based known-failures ledger file into a frozenset of ids.

    The line scan lives in :func:`storyboard_spec.parse_ledger_lines` — the ONE
    scan shared with the bracket-grammar ledger loader. This supplies the
    identity grammar: a nodeid ledger line IS its identifier, so the only thing
    that can reject one is emptiness, which the shared scan already drops.
    """
    return frozenset(storyboard_spec.parse_ledger_lines(path, grammar=lambda line: line))
