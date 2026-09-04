"""Shared authentication helper for BDD step definitions.

Plain helper module (no ``@given``/``@when``/``@then`` decorators) — importing it
never registers a step, mirroring ``_account_resolution.py``. Home for the
principal-switch shared by every "authenticated as principal" Given/When across
use cases (UC-018 isolation; UC-003 error + update).

**Live coverage.** Only UC-018 (``test_uc018_list_creatives``) exercises this
helper at runtime today. The UC-003 callers (``uc003_update_media_buy`` and
``uc003_ext_error_scenarios``) are currently **dormant**: neither step module is
registered in ``tests/bdd/conftest.py`` ``pytest_plugins`` and UC-003 is not wired
into the BDD harness, so every UC-003 update scenario auto-xfails (verified: 0
passed / 1404 xfailed). Those sites are converted to this shared helper anyway so
they are correct-by-construction when UC-003 is later activated — but the DRY edit
there is uncovered until then. Wiring UC-003 into the harness (registering the step
modules + mapping ``MediaBuyUpdateEnv`` in ``_detect_uc`` / ``_harness_env``) remains
a follow-up.
"""

from __future__ import annotations

from typing import Any


def authenticate_env_as(ctx: dict, principal_id: str) -> Any:
    """Switch the harness env to *principal_id*, record it canonically; return the env.

    Owns the full principal-switch contract so callers don't re-implement it:

    - re-points the env via the public ``env.switch_principal`` (clears the identity
      cache so the next ``env.identity``/``identity_for`` access re-resolves —
      picking up a principal row committed after the env was created);
    - records the canonical ``ctx["principal_id"]`` (the key read downstream by
      uc004/uc006 — there is no second key for this concept).

    Deliberately does NOT eagerly access ``env.identity`` here (salesagent-z9e0):
    identity resolution is lazy by design (tests/harness/test_harness_base.py's
    "identity is built on first access" contract) and, in integration mode, now
    depends on real DB state (identity_for() nulls principal_id when no Principal
    row exists yet, mirroring production's resolve_identity()). Forcing resolution
    at switch time — before a Given step later in the same scenario creates the
    row — would cache a stale/None identity that a real dispatch would never see.
    Callers add only genuinely use-case-specific ctx state (e.g. uc003's ``has_auth``).
    """
    env = ctx["env"]
    env.switch_principal(principal_id)
    ctx["principal_id"] = principal_id
    return env


def setup_tenant_and_principal(ctx: dict) -> tuple[Any, Any]:
    """The default tenant + principal, created once per scenario and cached in ctx.

    Lives HERE, in the generic auth layer, because establishing "a buyer with a
    valid identity" is the single most reused setup in the suite -- 383 feature
    lines across three sentences reach it. It used to live inside
    ``steps/domain/uc011_accounts.py``, which is why every other domain module
    re-implemented it: a helper in a domain module is not importable vocabulary,
    it is that module's private business.
    """
    if "tenant" not in ctx:
        ctx["tenant"], ctx["principal"] = ctx["env"].setup_default_data()
    return ctx["tenant"], ctx["principal"]
