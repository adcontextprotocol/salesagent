"""The A2A dispatch map, read out of the server source.

``skill_handlers`` is a function-local inside ``_handle_explicit_skill``, so it cannot be
imported -- and constructing ``AdCPRequestHandler`` to reach it would pull in the whole
server. Parsing is the only way to read it, and the obligation every caller has is about
what the map DECLARES anyway.

Shared rather than copied: two guards need this read -- the one that grades skill names
against the pinned spec, and the one that grades the tool registry against A2A dispatch --
and a second copy is a second thing to fix when the map moves.
"""

import ast
from pathlib import Path

A2A_SERVER = Path("src/a2a_server/adcp_a2a_server.py")


def registered_skill_names() -> set[str]:
    """The keys of the ``skill_handlers`` map."""
    tree = ast.parse(A2A_SERVER.read_text(), filename=str(A2A_SERVER))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "skill_handlers" and isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("skill_handlers map not found — this guard is reading the wrong shape")
