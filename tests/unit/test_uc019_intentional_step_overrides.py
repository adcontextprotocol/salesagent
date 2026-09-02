"""The UC-019 step overrides are a named set, not a sentence.

``tests/bdd/test_uc019_query_media_buys.py`` imports its domain steps at module
scope rather than through conftest's global registration, because the module
deliberately redefines a handful of generic step texts. Registering them globally
would hand those redefinitions to every other UC.

The count lived in prose ("intentionally redefines 8 generic step texts"), which
made a ninth invisible: it would simply be redefined, scoped to UC-019, and nothing
would say so. The shadowed-step guard cannot see these either — it scans globally
REGISTERED plugins, and local registration is the whole point of the arrangement.

So the set is pinned here. Adding an override fails this test and asks for a
decision; the exclusion itself stays deliberate and correct.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_UC019_STEPS = _REPO / "tests" / "bdd" / "steps" / "domain" / "uc019_query_media_buys.py"
_GENERIC_STEPS = _REPO / "tests" / "bdd" / "steps" / "generic"

# Verified at the commit that pinned them: UC-019 answers these eight sentences
# itself because its responses carry sandbox/validation shapes the generic steps
# do not model.
INTENTIONAL_OVERRIDES = frozenset(
    {
        "the error should be a real validation error, not simulated",
        'the error should include a "suggestion" field',
        "the error should include a suggestion for how to fix the issue",
        "the request targets a production account",
        "the request targets a sandbox account",
        "the response should include sandbox equals true",
        "the response should indicate a validation error",
        "the response should not include a sandbox field",
    }
)


def _step_texts(path: Path) -> set[str]:
    """Every Gherkin sentence a module registers, including ``parsers.parse`` forms."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in {"given", "when", "then"}:
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
                elif isinstance(arg, ast.Call):  # parsers.parse("...")
                    for inner in arg.args:
                        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                            found.add(inner.value)
    return found


@pytest.mark.arch_guard
def test_uc019_overrides_exactly_the_pinned_set() -> None:
    uc019 = _step_texts(_UC019_STEPS)
    generic: set[str] = set()
    for module in _GENERIC_STEPS.rglob("*.py"):
        generic |= _step_texts(module)

    assert uc019, "read zero steps from the UC-019 module — the reader is broken, not green"
    assert generic, "read zero generic steps — the reader is broken, not green"

    actual = uc019 & generic
    added = sorted(actual - INTENTIONAL_OVERRIDES)
    removed = sorted(INTENTIONAL_OVERRIDES - actual)
    assert not added and not removed, (
        "UC-019's set of generic-step overrides changed.\n"
        f"  newly overriding ({len(added)}): {added}\n"
        f"  no longer overriding ({len(removed)}): {removed}\n"
        "Each override is scoped to UC-019 and invisible to the shadowed-step guard, "
        "so it needs a deliberate decision rather than a silent redefinition."
    )
