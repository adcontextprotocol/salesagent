"""Single owner of the pinned-bundle subject for the storyboard guard modules.

Two round-6 findings on #1858 meet here.

**Finding 12** — the ``ADCP_HOME`` / ``DIST`` / ``skipif`` triple was copied into
seven guard modules. The skip-reason string was identical in six and had already
drifted in the seventh, and the marker name was split ``requires_clone`` (5) vs a
bare ``pytestmark`` (2). Every fact inside ``scripts/audit/`` has exactly one
owner; the guards that consume them did not. This module is that owner.

**Finding 8** — the resolution FAILED OPEN. Measured on the branch:
``ADCP_HOME=/nonexistent uv run pytest tests/unit/test_architecture_*.py`` gave
``670 passed, 25 skipped, exit 0``. Twenty-five guards across seven modules
switched themselves off and the suite stayed green. A guard that skips when it
cannot see its subject is not a guard.

Three states, three behaviours — this distinction is the whole module:

===============  ==================================================  ==========
state            condition                                           behaviour
===============  ==================================================  ==========
RESOLVED         the pinned tree is present                          run
MISCONFIGURED    ``$ADCP_HOME`` is set but does not resolve          **FAIL**
UNPROVISIONED    no bundle, no override                              skip
===============  ==================================================  ==========

MISCONFIGURED is never a legitimate state: someone pointed the guards at a tree
that is not there, and every gated guard silently stopping is the worst possible
answer. It raises at import, so it surfaces as a collection error, not a skip.

UNPROVISIONED *is* legitimate — a contributor who has not downloaded the bundle
can still run the rest of the suite — so it skips, but the reason carries the
command that fixes it. CI always provisions (``.github/actions/_adcp-bundle``),
so CI never takes this branch; the meta-test in
``test_architecture_storyboard_guard_env.py`` is what proves that claim rather
than assuming it.

Deliberately NOT accepted here: ``adcp_home()``'s third resolution candidate,
``~/projects/adcp``. Its own docstring calls it "one maintainer's checkout at
whatever revision that happens to sit on, which is not a thing CI or a
contributor can reproduce" — and during the origin/main merge it silently
retargeted a fresh worktree to an unrelated tree and produced 39 phantom ledger
failures. A guard subject must be the pinned artifact or nothing. The audit
scripts keep the fallback; the guards do not.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.audit import storyboard_spec

REPO_ROOT = Path(__file__).resolve().parents[2]

ADCP_HOME_ENV_VAR = storyboard_spec.ADCP_HOME_ENV_VAR

PROVISIONING_HINT = (
    "download the pinned bundle: "
    "gh release download v<pinned> --repo adcontextprotocol/adcp -p '<pinned>.tgz' "
    "&& tar -xzf it into tests/storyboard/runner/, or set $ADCP_HOME"
)


def _resolve() -> tuple[Path | None, Path | None]:
    """(adcp_home, dist) for the pinned tree, or (None, None) if unprovisioned.

    Raises when ``$ADCP_HOME`` is set and does not resolve — see MISCONFIGURED.
    """
    version = storyboard_spec.pinned_version(REPO_ROOT)

    override = os.environ.get(ADCP_HOME_ENV_VAR)
    if override:
        home = Path(override)
        dist = storyboard_spec.dist_root(home, version)
        if not dist.is_dir():
            raise RuntimeError(
                f"${ADCP_HOME_ENV_VAR} is set to {override!r} but no pinned AdCP "
                f"compliance tree resolves under it (looked for {dist}). "
                "Refusing to silently disable the storyboard guards: unset the "
                f"variable to fall back to the in-repo bundle, or {PROVISIONING_HINT}."
            )
        return home, dist

    bundle = REPO_ROOT / storyboard_spec.BUNDLE_PARENT / f"adcp-{version}"
    if bundle.is_dir():
        dist = storyboard_spec.dist_root(bundle, version)
        if dist.is_dir():
            return bundle, dist

    return None, None


ADCP_HOME, DIST = _resolve()

#: True when the pinned tree is present and the gated guards will really run.
BUNDLE_RESOLVED = DIST is not None

requires_pinned_bundle = pytest.mark.skipif(
    not BUNDLE_RESOLVED,
    reason=(
        f"pinned AdCP compliance tree not provisioned under "
        f"{REPO_ROOT / storyboard_spec.BUNDLE_PARENT} ({PROVISIONING_HINT})"
    ),
)
