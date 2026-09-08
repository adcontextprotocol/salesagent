"""CLAUDE.md's egress example must be callable against the real seam.

Pattern #9's ``# CORRECT`` fence is the canonical copy-target for the one seam
that owns this repo's most-recurring security defect. It was
``asend("POST", url, json=payload)`` -- a ``TypeError``, because ``method`` is
keyword-only, so the example passed ``"POST"`` as the URL. Anyone following it
got a traceback; anyone skimming it learned the wrong call shape for the seam
that exists to stop SSRF.

Nothing bound it. Prose about a signature goes stale the moment the signature
moves, and there is no doctest configuration or fence parser anywhere in this
repo to notice.

This does not re-check the seam's design. It resolves the callable the fence's
own import names and asks Python whether the fence's call would bind --
``inspect.signature`` doing the arity resolution, not a rule written here.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
SEAM_IMPORT = "from src.core.security.outbound_http import"


def _egress_example_fence() -> str:
    """The body of the CLAUDE.md python fence that imports the seam.

    Anchored on the import rather than on the prose around it. A comment
    naming the example is editorial and moves whenever the pattern is
    reworded; the import is the thing the example exists to demonstrate, so
    binding to it keeps this test pointed at the example through a rewrite.
    """
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert SEAM_IMPORT in text, (
        f"CLAUDE.md no longer contains a python fence importing the seam ({SEAM_IMPORT!r}). "
        "Either the example was removed and this test is pointed at nothing, or the seam's "
        "import path changed -- both make this binding vacuous."
    )
    start = text.index(SEAM_IMPORT)
    end = text.index("```", start)
    return text[start:end]


def test_the_correct_fence_call_binds_against_the_real_signature() -> None:
    fence = _egress_example_fence()
    tree = ast.parse(fence)

    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert imports, "the fence no longer imports the seam, so there is nothing to resolve it against"
    module = importlib.import_module(imports[0].module)

    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert calls, "the fence no longer calls anything"

    for call in calls:
        fn = getattr(module, call.func.id, None)
        assert fn is not None, (
            f"the fence calls {call.func.id!r}, which does not exist in {imports[0].module} -- "
            "the example names a function the seam does not export"
        )
        signature = inspect.signature(fn)
        positional = [ast.unparse(a) for a in call.args]
        keywords = {kw.arg: ast.unparse(kw.value) for kw in call.keywords if kw.arg}
        try:
            signature.bind_partial(*positional, **keywords)
        except TypeError as exc:
            raise AssertionError(
                f"CLAUDE.md's Pattern #9 CORRECT example does not bind against "
                f"{call.func.id}{signature}: {exc}. The canonical copy-target for the egress "
                f"seam raises TypeError as written."
            ) from exc
