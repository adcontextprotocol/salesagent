"""The storyboard guards must not be able to switch themselves off silently.

Finding 8 (#1858 round 6). Measured on the branch before this module existed::

    ADCP_HOME=/nonexistent uv run pytest tests/unit/test_architecture_*.py
    -> 670 passed, 25 skipped, exit 0

Twenty-five guards across seven modules disabled themselves and the run was
green. Every engine surveyed for prior art (Semgrep, ast-grep, ESLint, CodeQL,
ArchUnit) has the same hole in a *scan* and closes it the same way: a rule that
observed nothing is caught by a TEST, never by the scan. ArchUnit went further
and made the empty subject set a failure by default in 0.23.0, calling out this
exact scenario -- a renamed package leaving a rule that "will now always
evaluate successfully without any reported error [but] does not check any
classes at all anymore".

This module is that test, for the one subject the storyboard guards share.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.unit import _storyboard_guard_env as env

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The modules whose tests are gated on the pinned bundle. Adding one is a
#: reviewed edit: it is the set this module proves is really running.
BUNDLE_GATED_MODULES = frozenset(
    {
        "test_architecture_storyboard_check_index_liveness.py",
        "test_architecture_storyboard_check_inventory.py",
        "test_architecture_storyboard_controller_divergence.py",
        "test_architecture_storyboard_gate_schema_oracle.py",
        "test_architecture_storyboard_ledger.py",
        "test_architecture_storyboard_spec.py",
        "test_architecture_storyboard_wireability.py",
    }
)


def test_a_misconfigured_adcp_home_fails_instead_of_skipping(monkeypatch):
    """The regression test for the 25-silent-skips measurement.

    ``$ADCP_HOME`` pointing at a tree that does not resolve is never a
    legitimate state -- it is a misconfiguration, and the worst possible answer
    is for every gated guard to quietly stop.
    """
    monkeypatch.setenv(env.ADCP_HOME_ENV_VAR, "/nonexistent-adcp-tree")

    with pytest.raises(RuntimeError) as excinfo:
        env._resolve()

    message = str(excinfo.value)
    assert "/nonexistent-adcp-tree" in message, message
    assert "silently disable" in message, message


def test_the_in_repo_bundle_resolves_without_an_override(monkeypatch):
    """With no override, resolution uses the pinned in-repo bundle or nothing.

    Never a maintainer's personal clone: ``adcp_home()``'s third candidate
    (``~/projects/adcp``) is deliberately not consulted here. During the
    origin/main merge it silently retargeted a fresh worktree to an unrelated
    checkout and produced 39 phantom ledger failures.
    """
    monkeypatch.delenv(env.ADCP_HOME_ENV_VAR, raising=False)

    home, dist = env._resolve()

    if home is None:
        assert dist is None
        return
    assert home.is_dir(), home
    assert dist is not None and dist.is_dir(), dist
    assert str(home).startswith(str(REPO_ROOT)), (
        f"the guards resolved their subject to {home}, outside the repo — only the "
        "pinned in-repo bundle or an explicit $ADCP_HOME is acceptable"
    )


@pytest.mark.skipif(not env.BUNDLE_RESOLVED, reason="no pinned bundle provisioned")
def test_the_gated_modules_are_not_all_skipped_when_the_bundle_is_present():
    """The bundle resolving must actually mean the gated guards RUN.

    Without this, the layer can regress to the measured state (green, gated
    modules inert) and only the skip count -- which nobody reads -- would move.
    """
    collected = {p.name for p in (REPO_ROOT / "tests" / "unit").glob("test_architecture_storyboard_*.py")}
    missing = BUNDLE_GATED_MODULES - collected
    assert not missing, f"pinned bundle-gated modules no longer exist: {sorted(missing)}"

    # skipif takes its condition positionally: mark.skipif(<cond>, reason=...)
    assert env.requires_pinned_bundle.args[0] is False, (
        "the pinned bundle resolved, but requires_pinned_bundle would still skip — "
        "the gated guards are inert while reporting green"
    )
