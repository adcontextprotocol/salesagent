"""
BDD test configuration and fixtures.

Every scenario runs against real production code through harness environments:
  - UC-005 (Creative Formats): CreativeFormatsEnv
  - UC-004 (Delivery Metrics): DeliveryPollEnv / WebhookEnv / CircuitBreakerEnv

There is no stub mode — steps call the harness directly and assert on
real response objects.

Unimplemented scenarios (missing step definitions) are auto-xfailed at runtime
via ``pytest_runtest_makereport``. No metadata or @pending tags needed — the
code is the source of truth.

Scenarios for unimplemented *production* features use explicit ``xfail`` markers
with a reason (e.g., "MCP wrapper does not accept disclosure_positions").
"""

from __future__ import annotations

import dataclasses
import functools
import os
import re
import ssl
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest

from scripts.audit import storyboard_spec
from tests.helpers.ledger import load_ledger_nodeids
from tests.helpers.marker_names import derive_marker_names

# Known mock-incompatible e2e_rest BDD scenarios — these dispatch over real HTTP
# to the separate server, so in-process mock injection (set_registry_formats /
# set_adapter_response / account billing-state fixtures) is invisible to it and
# the scenario cannot pass. xfail(strict=False)'d by exact nodeid in the
# collection hook. Regenerate from a clean in-network e2e_rest run. See the beads
# ledger task. File lives next to this conftest.
_E2E_REST_KNOWN_FAILURES: frozenset[str] = load_ledger_nodeids(Path(__file__).parent / "e2e_rest_known_failures.txt")

if TYPE_CHECKING:
    # Real types for the EnvRoute callbacks. Under TYPE_CHECKING so
    # the annotations stay honest without importing the harness at conftest
    # import time.
    from tests.harness._base import BaseTestEnv
    from tests.harness.transport import E2EConfig

# Register step definition modules as pytest plugins so that the fixtures
# created by @given/@when/@then decorators are visible to pytest-bdd's
# fixture lookup. Simple ``import`` is not enough — pytest only discovers
# fixtures from conftest files and registered plugins.
pytest_plugins = [
    "tests.bdd.scenario_liveness",
    "tests.bdd.steps.generic.given_auth",
    "tests.bdd.steps.generic.given_config",
    "tests.bdd.steps.generic.given_entities",
    "tests.bdd.steps.generic.given_media_buy",
    "tests.bdd.steps.generic.when_request",
    "tests.bdd.steps.generic.then_success",
    "tests.bdd.steps.generic.then_error",
    "tests.bdd.steps.generic.then_payload",
    "tests.bdd.steps.generic.then_schema",
    "tests.bdd.steps.domain.uc004_delivery",
    "tests.bdd.steps.domain.uc002_create_media_buy",
    "tests.bdd.steps.domain.uc002_nfr",
    "tests.bdd.steps.domain.uc003_update_media_buy",
    "tests.bdd.steps.domain.uc003_ext_error_scenarios",
    "tests.bdd.steps.domain.uc003_storyboard_generic_client",
    "tests.bdd.steps.domain.uc006_sync_creatives",
    "tests.bdd.steps.domain.uc006_storyboard_creative_sync",
    "tests.bdd.steps.domain.uc005_format_id_shape",
    "tests.bdd.steps.domain.uc005_format_id_roundtrip",
    "tests.bdd.steps.domain.uc005_format_id_third_party",
    "tests.bdd.steps.domain.uc010_capabilities",
    "tests.bdd.steps.domain.uc011_accounts",
    "tests.bdd.steps.domain.admin_accounts",
    "tests.bdd.steps.domain.uc_get_products_inventory",
    "tests.bdd.steps.domain.egress_ssrf",
    "tests.bdd.steps.domain.uc_brand_shorthand",
    "tests.bdd.steps.domain.compat_normalization",
    "tests.bdd.steps.domain.local_constraint_relaxations",
    "tests.bdd.steps.domain.codes_open_vocabulary",
    "tests.bdd.steps.domain.security_wire_safety",
]

# ---------------------------------------------------------------------------
# Auto-xfail: missing step definitions
# ---------------------------------------------------------------------------
# Instead of predicting which scenarios are "pending" via metadata tags,
# we let pytest-bdd tell us at runtime. If a scenario fails because a step
# definition is missing, we convert the failure to xfail. The code is the
# source of truth — no stale metadata needed.

# nodeid -> human-readable classification of the step that actually failed,
# populated by the pytest_bdd_step_* hooks below. Consumed (and popped) by
# pytest_runtest_makereport's dormancy-vs-production-gap tripwire (#1721 M4):
# a strict-xfail whose reason claims a graded "production gap" but whose real
# failure is a missing step binding or a Given-side setup error is a
# MISCLASSIFIED entry -- dormancy masquerading as a graded gap, exactly the
# pattern six independent reviewers converged on. This is a bounded
# conftest function extending the existing tripwire, not a new guard file.
_STEP_ERROR_CLASSIFICATION: dict[str, str] = {}


#: nodeid -> the dormancy BASELINE KEY for a missing binding, "<keyword> <normalized step>".
#: Separate from the human-readable text above because the key must survive scenario
#: edits that the message deliberately includes (line numbers).
_MISSING_STEP_KEY: dict[str, str] = {}


def _normalize_step_text(name: str) -> str:
    """Collapse Examples-row variation so one gap is one baseline entry.

    A Scenario Outline substitutes its placeholders before the lookup fails, so the
    SAME missing binding arrives here once per row with different literals baked in.
    Without this, adding a row to an already-dormant scenario would read as NEW
    dormancy and fail a build for no loss of coverage. Quoted literals, bare numbers
    and inline objects become placeholders; the step's identity is what remains.
    """
    text = re.sub(r'"[^"]*"', '"<>"', name)
    text = re.sub(r"\b\d+\b", "<n>", text)
    text = re.sub(r"\{[^}]*\}", "{<>}", text)
    return re.sub(r"\s+", " ", text).strip()


def pytest_bdd_step_func_lookup_error(request, feature, scenario, step, exception) -> None:  # noqa: ANN001
    """Record that this scenario's failure is a missing step BINDING (dormancy)."""
    _STEP_ERROR_CLASSIFICATION[request.node.nodeid] = (
        f"a missing step definition for {step.type} {step.name!r} (line {step.line_number})"
    )
    _MISSING_STEP_KEY[request.node.nodeid] = f"{step.type} {_normalize_step_text(step.name)}"


def pytest_bdd_step_error(request, feature, scenario, step, step_func, step_func_args, exception) -> None:  # noqa: ANN001
    """Record a Given-side setup failure -- test-wiring, not the graded behavior.

    Only the FIRST failing step's classification is kept (a scenario has one
    failure); only Given steps are flagged here -- a When/Then failure is (by
    construction) the scenario grading the behavior it exists to grade, never
    dormancy.
    """
    if step.type == "given" and request.node.nodeid not in _STEP_ERROR_CLASSIFICATION:
        _STEP_ERROR_CLASSIFICATION[request.node.nodeid] = (
            f"a Given-side setup error on {step.name!r} (line {step.line_number}): {exception!r}"
        )


DORMANT_SCENARIOS_PATH = Path(__file__).parent / "dormant_scenarios.txt"


@functools.lru_cache(maxsize=1)
def _dormant_baseline() -> frozenset[tuple[str, str]]:
    """The committed set of (scenario tag, missing step) pairs that already grade nothing.

    Read once. See ``dormant_scenarios.txt`` for why the key is the TAG and the STEP
    rather than anything positional, and why enforcement is per-test rather than a
    count.
    """
    entries = set()
    for line in DORMANT_SCENARIOS_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or " :: " not in line:
            continue
        tag, step = line.split(" :: ", 1)
        entries.add((tag.strip(), step.strip()))
    return frozenset(entries)


def _scenario_tag(item: pytest.Item) -> str | None:
    """The scenario's ``T-...`` tag, which is its stable identity across rewrites."""
    return next((k for k in item.keywords if re.match(r"^T-[A-Z0-9-]", k)), None)


def _record_dormancy(item: pytest.Item, report: pytest.TestReport) -> bool:
    """Report a missing-binding scenario AS DORMANCY, and refuse a NEW one.

    Returns True when the scenario is an already-recorded dormant entry (caller
    converts it to xfail), False when it is new (caller leaves it FAILING).

    WHY THIS EXISTS. A scenario whose step has no binding executes nothing, and the
    auto-convert below reported it as a plain xfail -- indistinguishable in any
    summary from a graded spec-production gap. A suite could shrink to nothing while
    every run stayed green, which is the state salesagent-prkv.39 found.

    The judgement was already in this file and was simply not reached:
    ``pytest_bdd_step_func_lookup_error`` classifies a missing binding as dormancy,
    and ``_classify_strict_xfail_dormancy`` fails a strict-xfail that CLAIMS a
    production gap when the cause is that classification. But the auto-convert's own
    reason claims nothing, so it sailed past the check written for it. This routes it
    through the same vocabulary instead of adding a third rule beside the two
    (salesagent-kp56h).

    The key is published as a ``user_property`` because pytest-json-report does NOT
    serialize ``wasxfail``: the reason string is invisible in the JSON reports, so the
    only trace of dormancy there is the exception class inside a traceback. Measuring
    this required knowing that trick, and the first attempt at it returned zero
    against a real count of 1356 (salesagent-vtreb). A user_property IS serialized, so
    the next audit does not depend on folklore.
    """
    tag = _scenario_tag(item)
    step_key = _MISSING_STEP_KEY.pop(item.nodeid, None)
    if step_key is None or tag is None:
        return True  # not a pytest-bdd scenario we can key; leave prior behaviour

    # CONSUME the classification. ``_classify_strict_xfail_dormancy`` exists to catch an
    # xfail that CLAIMS a production gap while the real cause is dormancy; once this
    # function has named the dormancy honestly there is nothing left for it to catch, and
    # its early return on a missing classification is exactly the right seam to use.
    #
    # This is also what keeps the two rules from being coupled by SUBSTRING. That
    # tripwire greps candidate reasons for "production gap"/"spec-production", so the
    # first draft of the honest reason below -- which ended "this is NOT a graded
    # spec-production gap" -- MATCHED IT and turned every recorded dormant scenario into
    # a MISCLASSIFIED failure. 138 of them, from a disclaimer. Popping removes the
    # coupling; the reason text avoids those words as well, so re-introducing the
    # coupling would take two mistakes rather than one.
    #
    # The tripwire's other job is untouched: a scenario rescued by an explicit strict
    # xfail MARKER never reaches here (it is not ``report.failed``), so a marker lying
    # about a production gap is still caught there.
    _STEP_ERROR_CLASSIFICATION.pop(item.nodeid, None)

    item.user_properties.append(("dormant_scenario", f"{tag} :: {step_key}"))
    if (tag, step_key) in _dormant_baseline():
        # KEEP THE "Step definition not found:" PREFIX. It is not decoration: three
        # other instruments classify this event by matching it, and
        # ``scenario_liveness._classify_reason`` buckets anything that does not start
        # with it as "ledgered", which then sets ``harness_wired=True`` on a scenario
        # that binds no steps at all -- an instrument overstating its own coverage,
        # which is the exact fault
        # ``test_provenance_tag_is_a_recorded_field_not_a_collection_filter`` exists to
        # catch. Rewording this line without the prefix silently flipped two dormant
        # UC-006 scenarios to "wired"; the detail is appended AFTER the prefix so the
        # reason can stay honest without being the machine-readable channel.
        #
        # It is no longer the ONLY channel either -- the user_property above and
        # scenario_liveness's typed classification both carry it now, so losing this
        # prefix costs a worse message rather than a wrong measurement.
        report.wasxfail = (
            f"Step definition not found: DORMANT (test-wiring) — no step definition for "
            f"{step_key!r} in {tag}, so this scenario grades nothing. Recorded in "
            f"tests/bdd/dormant_scenarios.txt; closing the hole is salesagent-8j5nf."
        )
        return True
    report.outcome = "failed"
    report.wasxfail = ""
    report.longrepr = (
        f"NEW DORMANT SCENARIO: {item.nodeid}\n"
        f"  {tag} has no step definition for {step_key!r}, so this scenario grades NOTHING.\n"
        f"  It is not in tests/bdd/dormant_scenarios.txt, so it is new coverage loss.\n"
        f"  Wire the step. Do NOT add a line to that file -- the list may only shrink.\n"
        f"  (If you just deleted a step definition, this is what that deletion cost.)"
    )
    return False


def _classify_strict_xfail_dormancy(item: pytest.Item, report: pytest.TestReport) -> None:
    """Fail loud when a strict-xfail claiming a production/spec gap is actually dormancy.

    Checks BOTH an explicit ``xfail`` marker's reason AND a ``wasxfail`` string
    this same hook may have just set (the missing-step-definition auto-convert
    above) -- either can carry the misleading "production gap" wording
    exhibited. Leaves alone any xfail that already reports honestly (e.g. "UC-010
    harness wiring not extended... dormant, never graded" names itself
    correctly) or that grades a real Then/When failure.
    """
    classification = _STEP_ERROR_CLASSIFICATION.pop(item.nodeid, None)
    if classification is None:
        return
    reasons = [str(report.wasxfail)] if getattr(report, "wasxfail", None) else []
    reasons += [str(m.kwargs.get("reason", "")) for m in item.iter_markers("xfail")]
    if not any("production gap" in r.lower() or "spec-production" in r.lower() for r in reasons):
        return
    if report.outcome not in ("skipped", "failed"):
        return
    report.outcome = "failed"
    report.wasxfail = ""
    report.longrepr = (
        f"MISCLASSIFIED strict-xfail: {item.nodeid} is cited as a production/spec gap "
        f"but the underlying failure is {classification} -- this is DORMANCY (test-wiring), "
        "not a graded production gap. Fix the wiring, or correct the xfail reason "
        "to say so honestly, before recording an xfail."
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, None, None]:
    """Auto-xfail scenarios that fail due to genuinely missing step definitions.

    Only StepDefinitionNotFoundError and NotImplementedError are converted to
    xfail. KeyError is NOT caught — use pytest.skip() in _harness_env for
    scenarios without a harness instead of relying on runtime KeyError interception.
    """
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed and call.excinfo is not None:
        from pytest_bdd.exceptions import StepDefinitionNotFoundError

        from tests.harness._realize import E2EUnsupportedSetup

        if call.excinfo.errisinstance(StepDefinitionNotFoundError):
            # Dormancy, not an expected failure. _record_dormancy names it honestly and
            # refuses a scenario that is not already on the committed baseline.
            if _record_dormancy(item, report):
                report.outcome = "skipped"
        elif call.excinfo.errisinstance(NotImplementedError):
            report.outcome = "skipped"
            report.wasxfail = f"Not implemented: {call.excinfo.value}"
        elif call.excinfo.errisinstance(E2EUnsupportedSetup):
            # A mock-setup intent the live e2e stack has no surface for. The
            # reason is declared at the env method (not a nodeid ledger), so it
            # is visible in the report. Non-strict xfail — in-process transports
            # of the same scenario still run normally.
            report.outcome = "skipped"
            report.wasxfail = f"impl-only setup declared in env: {call.excinfo.value}"

    if report.when == "call":
        _classify_strict_xfail_dormancy(item, report)


# ---------------------------------------------------------------------------
# Auto-register BDD tag markers
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register BDD tag markers dynamically."""
    # Guard: BDD_E2E_ENABLED is incompatible with xdist. Under -n>0 the e2e_rest
    # transport is silently dropped at collection (the worker's
    # pytest_generate_tests never appends it), so the suite goes green WITHOUT
    # ever running the 5th transport. The ctx fixture's hard-error can't catch
    # this — collection never happens. Turn the silent drop into a hard error.
    # In-network bdd already pins BDD_XDIST_N=0 (docker-compose.e2e.yml). (#1420)
    # Exception: with E2E_PER_WORKER=1 each xdist worker targets its OWN server +
    # DB (Phase B), so e2e_rest CAN run in parallel. The worker inherits
    # BDD_E2E_ENABLED, and the bdd_e2e env runs `-k e2e_rest`, which pytest exits
    # 5 (no tests selected) on if the transport were dropped — so a silent drop
    # can't pass unnoticed. Keep the guard for the shared-server case (where the
    # silent-drop hazard genuinely remains).
    if os.environ.get("BDD_E2E_ENABLED") == "true" and os.environ.get("E2E_PER_WORKER") != "1":
        numprocesses = getattr(config.option, "numprocesses", None)
        if numprocesses not in (None, 0, "0"):
            raise pytest.UsageError(
                f"BDD_E2E_ENABLED=true is incompatible with xdist (-n {numprocesses!r}): "
                "the e2e_rest transport is silently dropped at collection and the suite "
                "passes without ever running it. Run serially (BDD_XDIST_N=0) or use "
                "per-worker servers (E2E_PER_WORKER=1)."
            )

    import pathlib

    features_dir = pathlib.Path(__file__).parent / "features"
    if not features_dir.exists():
        return

    seen: set[str] = set()
    for feature_file in features_dir.glob("**/*.feature"):
        text = feature_file.read_text()
        for match in re.finditer(r"@([\w.\-]+)", text):
            tag = match.group(1)
            if tag not in seen:
                seen.add(tag)
                config.addinivalue_line("markers", f"{tag}: BDD scenario tag")


# ---------------------------------------------------------------------------
# xfail: scenarios for unimplemented production features
# ---------------------------------------------------------------------------
# These tags correspond to features not yet implemented in production code.
# Each xfail has a FIXME pointing to the work needed.

_XFAIL_TAGS: dict[str, str] = {
    # ── Wired by this sweep; they FAIL, and that failure is the finding. ──
    # These three scenarios were dormant on main (routed to the uc003/uc006
    # not-wired catch-alls). This sweep wired them deliberately, because a
    # storyboard step graded them and the matching BDD scenario existed. They
    # now execute and fail, which CORROBORATES an already-filed gap from the
    # opposite direction: the GitHub issue predicted the storyboard step was
    # unreachable; the BDD scenario independently shows the behavior is absent.
    #
    # Ledgered, not hidden: each carries the issue that owns the fix, and each
    # graduates the moment that issue lands. See the PR description's
    # "corroborated gaps" table for the full evidence chain.
    #
    # Re-derived at this head; the previous reason here was wrong in both of its
    # claims. Re-cancel does NOT return silent success and production DOES have a
    # terminal-state guard: src/core/tools/media_buy_update.py:411 raises
    # AdCPGoneError, which the boundary translates to INVALID_STATE
    # ("Cannot update media buy in terminal state: canceled"). The scenario fails
    # on the CODE, not on the absence of enforcement.
    #
    # The gap is code specialization. The pinned enum carries both codes, both
    # `recovery: correctable` (tests/fixtures/adcp_schemas_pinned/enums/error-code.json),
    # and BR-UC-003-update-media-buy.feature:2094-2097 states the split correctly:
    # INVALID_STATE covers non-cancel updates to a terminal buy, while
    # NOT_CANCELLABLE is reserved for re-cancel attempts specifically.
    #
    # Graduation trigger: NOT #1261 (silent-ignore of `canceled`) -- landing that
    # leaves INVALID_STATE in place and this scenario still red. #1961 is the
    # sibling on the A2A `on_cancel_task` surface, not this one. No issue
    # currently owns specializing the code on update_media_buy; this entry
    # graduates when one lands.
    "T-UC-003-storyboard-not-cancellable-on-recancel": (
        "re-cancel is refused with the generic INVALID_STATE; the pinned enum reserves "
        "NOT_CANCELLABLE for a refused cancel specifically — a code-specialization gap, "
        "not a missing terminal-state guard (that guard is media_buy_update.py:411)"
    ),
    # Graduated (GH #1075, sync_creatives half): T-UC-006-idempotency-replay and
    # T-UC-006-idempotency-conflict. Both reasons are now false of production —
    # 981776bdb gave sync_creatives the shared replay path (src/core/idempotency_replay.py:
    # probe → conflict → cache), so a repeated key replays the stored envelope and a
    # reused key with a different canonical payload raises IDEMPOTENCY_CONFLICT.
    #
    # Per the graduation workflow, both were inspected before the rows came out rather
    # than removed on the strength of a green mark: the scenarios carry the full
    # obligation (the replay Then counts approval workflow steps against a pre-retry
    # baseline and asserts the per-creative `changes` list stayed empty; the conflict
    # Then asserts code AND recovery through the wire envelope via
    # ``result.assert_wire_error``), the Given performs the first sync through the
    # scenario's OWN transport so the retry is indistinguishable from a network retry,
    # and the demanded code/recovery match the pinned enum.
    #
    # a2a XPASSed alone only because the strict marker deselected the mcp/rest siblings;
    # the marker's removal re-selects them, and MCP passes because sync_creatives now
    # reaches _impl through sync_creatives_raw (it was the one wrapper dropping
    # request_hash, so replay was dead on that transport alone).
    # No sibling entry in e2e_rest_known_failures.txt.
    # FIXME: UC-003 main/alt-timing — production doesn't populate these fields
    # Steps have hard assertions now; xfail at scenario level until production catches up.
    "T-UC-003-main": "implementation_date, budget, sandbox not populated in update response — spec-production gap",
    "T-UC-003-alt-timing": "implementation_date not populated in update response — spec-production gap",
    # FIXME: UC-003 pause — sandbox flag not populated in update response
    "T-UC-003-alt-pause": "sandbox not populated in pause response — spec-production gap",
    # FIXME: UC-003 optimization_goals — affected_packages empty in response
    "T-UC-003-alt-optimization-goals": "affected_packages not populated for optimization_goals changes — spec-production gap",
    # FIXME: UC-003 ext-t — invoice_recipient authorization (BR-RULE-214) not implemented;
    # production accepts the override without an authorization check, so no VALIDATION_ERROR is raised.
    "T-UC-003-ext-t": "invoice_recipient authorization not implemented (BR-RULE-214) — production gap",
    # FIXME: UC-003 ext-u — new_packages midflight-additions capability check
    # (BR-RULE-217 -> UNSUPPORTED_FEATURE) not implemented; production accepts new_packages unhandled.
    "T-UC-003-ext-u": "new_packages midflight capability check not implemented (BR-RULE-217) — production gap",
    # FIXME: UC-002 ASAP — response doesn't expose resolved start_time
    "T-UC-002-alt-asap": "response lacks resolved start_time field — spec-production gap",
    # FIXME: UC-002 error code mismatch — Pydantic VALIDATION_ERROR vs spec INVALID_REQUEST
    "T-UC-002-inv-087-5": "duplicate optimization_goals priority: VALIDATION_ERROR instead of INVALID_REQUEST — spec-production gap",
    "T-UC-002-inv-087-6": "empty optimization_goals array: VALIDATION_ERROR instead of INVALID_REQUEST — spec-production gap",
    "T-UC-002-inv-087-7": "per_ad_spend without value_field: VALIDATION_ERROR instead of INVALID_REQUEST — spec-production gap",
    # FIXME(#1660): disclosure_positions filter not implemented in production
    # Note: violated/nofield pass vacuously (field rejected at schema level)
    "T-UC-005-inv-049-8-holds": "disclosure_positions filter not implemented",
    # adcp 3.12: FormatCategory/type filter removed from ListCreativeFormatsRequest.
    # Scenarios that rely on type filter or type-based sorting can no longer pass.
    "T-UC-005-main-filtered": "adcp 3.12: type filter removed from ListCreativeFormatsRequest",
    "T-UC-005-inv-031-1-holds": "adcp 3.12: type filter removed — combined type+asset_types AND filter not possible",
    "T-UC-005-inv-031-1-violated": "adcp 3.12: type filter removed — combined type+asset_types AND filter not possible",
    "T-UC-005-inv-031-2-holds": "adcp 3.12: type field removed — sort by type then name not possible",
    "T-UC-005-inv-049-1-holds": "adcp 3.12: type filter removed from ListCreativeFormatsRequest",
    "T-UC-005-inv-049-1-violated": "adcp 3.12: type filter removed from ListCreativeFormatsRequest",
    # Un-graduated: T-UC-005-sandbox-happy — sandbox=True not set on response (all transports)
    "T-UC-005-sandbox-happy": "sandbox mode not implemented in list_creative_formats response — spec-production gap",
    # Un-graduated: T-UC-005-sandbox-validation — sandbox validation not triggered (all transports)
    "T-UC-005-sandbox-validation": "sandbox validation not triggered for invalid filters — spec-production gap",
    # T-UC-005-main-referrals: in-process ONLY (the registry is mocked and returns no agents).
    # GRADUATED for e2e_rest in the apply loop below (#1417) — with a seeded tenant
    # the live server populates creative_agents (>=DEFAULT_AGENT). NOT a spec-production gap.
    "T-UC-005-main-referrals": "creative agent referrals empty — in-process registry mock returns no agents; "
    "production populates >=DEFAULT_AGENT over real transports (mock limitation, not a spec-production gap)",
    # FIXME: T-UC-005-main — format 'audio-spot' has no assets or renders (all transports)
    "T-UC-005-main": "some formats (e.g. audio-spot) lack asset_requirements and render_capabilities — spec-production gap",
    # Partially graduated: dispatch fix landed; error code mismatch remains
    # FIXME: production raises AUTH_REQUIRED, spec expects TENANT_REQUIRED
    "T-UC-005-ext-a": "error code AUTH_REQUIRED instead of TENANT_REQUIRED — spec-production gap",
    # Graduated: creative agent partition/boundary tests
    # Steps now dispatch through harness — all 34 tests pass across 4 transports.
    # FIXME(#1660): suggestion field not in production error model
    # NOTE(ah98 red-step inspection, 2026-07-06): NOT graduatable as-is — the
    # When step no-ops (type filter removed in adcp 3.12), so the scenario
    # fails on "operation should fail", not on the missing suggestion.
    # Suggestion parity for list_creative_formats is pinned instead by
    # tests/integration/test_request_validation_suggestion_parity.py.
    "T-UC-005-ext-b": "suggestion field not implemented in error responses",
    # Graduated (salesagent-prkv.65, cassini run 4e57e3338ca3407ab0d78d70f3a20a09):
    # T-UC-005-ext-b-disclosure-invalid, -disclosure-empty, -output-empty,
    # -output-invalid, -output-noid, -input-empty, -input-invalid, -input-noid.
    #
    # The gap was never in production — it was in the harness, the same finding as
    # T-UC-002-ext-f above. These scenarios reach production through
    # when_request.py's filter steps, which built ListCreativeFormatsRequest IN THE
    # TEST PROCESS; an out-of-enum disclosure position, an empty array or a FormatId
    # missing a member therefore raised pydantic HERE and never crossed a transport.
    # The recorded reasons ("validation not implemented", "specific validation error
    # codes not implemented") described the harness's own exception, not the seller.
    #
    # With the payload dispatched raw, production answers correctly and visibly:
    #   "A2A boundary translating AdCPInvalidRequestError to envelope: INVALID_REQUEST"
    # which is what the scenarios asked for all along. All eight xpassed strictly.
    # These scenarios are parametrized on a2a ONLY (verified: one test collected per
    # scenario), and none appears in tests/bdd/e2e_rest_known_failures.txt, so there is
    # no sibling-transport or e2e ledger entry to graduate alongside them.
    #
    # NOT graduated — T-UC-005-ext-b-disclosure-dupes still xfails, and it is a
    # SPEC question rather than a production gap: the pinned
    # list-creative-formats-request declares minItems=1 on disclosure_positions but NO
    # uniqueItems, so ["prominent","prominent"] violates no schema constraint and
    # production is right to accept it. The scenario is over-specified; reconciling it
    # upstream is the fix, not patching production to match.
    "T-UC-005-ext-b-disclosure-dupes": "scenario demands rejection of duplicate disclosure_positions, "
    "but the pinned schema declares no uniqueItems — over-specified scenario, pending upstream reconciliation",
    # Graduated: T-UC-002-ext-f. The gap was never in production -- it was in the harness.
    # The step built CreateMediaBuyRequest IN THE TEST PROCESS, so an unknown targeting
    # field raised pydantic's ValidationError there and never crossed a transport; the
    # scenario graded the harness's own exception. Dispatching the raw parameter bag lets
    # the payload reach the server, which answers INVALID_REQUEST with a suggestion, which
    # is what the scenario asked for all along (prkv.33).
    # FIXME: the error CODE is fixed (currency-not-supported now
    # raises AdCPCapabilityNotSupportedError -> UNSUPPORTED_FEATURE, verified by
    # tests/integration/test_currency_not_supported_error_code.py). But this scenario
    # selects a non-default-currency pricing_option_id, and create_media_buy derives
    # request_currency from the product's FIRST pricing option — it never validates the
    # SELECTED option's currency — so the create SUCCEEDS instead of failing. Graduates
    # once selected-option currency validation lands (#1417).
    "T-UC-002-ext-d": "selected pricing-option currency not validated against CurrencyLimit; create succeeds instead of UNSUPPORTED_FEATURE — spec-production gap",
    # Graduated (#1417/gh8p.10): duplicate product_id now raises AdCPValidationError
    # with a buyer-facing suggestion ("Each package must reference a distinct
    # product_id ..."), surfaced on the wire. T-UC-002-ext-e passes.
    # FIXME: stale .feature expectation, NOT a production gap.
    # Production correctly emits BUDGET_EXCEEDED for "daily budget exceeds cap"
    # (AdCPBudgetExceededError; verified at wire on mcp/rest/a2a). v3.1 renamed the
    # code BUDGET_TOO_LOW -> BUDGET_EXCEEDED for BR-RULE-012 "exceeds cap"
    # (adcp-req .impl-coverage/BR-UC-002.yaml:1198); the generated .feature still
    # asserts the pre-v3.1 BUDGET_TOO_LOW. Graduates once adcp-req is reconciled and
    # BR-UC-002 is regenerated (#1417). Strict xfail; assertion unchanged.
    "T-UC-002-ext-k": "generated .feature asserts pre-v3.1 BUDGET_TOO_LOW; production correctly emits BUDGET_EXCEEDED — stale spec, pending upstream regen",
    # FIXME(#1417): proposal-based create_media_buy is an unbuilt spec feature.
    # BR-UC-002-alt-proposal (status: active) + BR-UC-002-ext-l/ext-m define a full
    # proposal flow: resolve proposal_id, expiry check (PROPOSAL_EXPIRED), and
    # total_budget vs total_budget_guidance.min (BUDGET_TOO_LOW). The pinned
    # adcp library CreateMediaBuyRequest carries proposal_id, but production
    # src/core/tools/media_buy_create.py never reads it — no resolve_proposal,
    # no validate_proposal_budget, no proposal store. Scenario-level strict xfail
    # until the proposal feature is built (no proposal masking; Then steps still
    # hard-assert the BR error codes).
    "T-UC-002-ext-l": "BR-UC-002-ext-l: proposal_id resolution / PROPOSAL_EXPIRED unbuilt — proposal feature not implemented in production (spec-production gap)",
    "T-UC-002-ext-m": "BR-UC-002-ext-m: proposal total_budget_guidance.min validation / BUDGET_TOO_LOW unbuilt — proposal feature not implemented in production (spec-production gap)",
    # Graduated (#1417): the .feature now asserts the standard VALIDATION_ERROR
    # (PRICING_ERROR is not in the AdCP vocabulary @04f59d2d5) and production emits it with
    # a recovery suggestion. T-UC-002-ext-n / -ext-n-bid / -ext-n-floor pass; xfails removed.
    # FIXME: production errors lack suggestion field
    # AdCPNotFoundError/AdCPValidationError/AdCPAdapterError raised with details={"error_code": ...}
    # but no details["suggestion"]. Spec requires suggestion for buyer remediation.
    # FIXME: creative/format_id validation errors lack suggestion field
    # ext-g: _validate_creatives_before_adapter_call raises INVALID_CREATIVES without suggestion
    # ext-h: plain string format_id caught by Pydantic, not structured AdCPSalesAgentError
    # ext-h-agent: _validate_and_convert_format_ids is dead code — unregistered agent not detected
    # Graduated 2026-09-01: the reason named the defect exactly -- "produces Pydantic error,
    # not AdCPSalesAgentError with suggestion". d2d6609da maps a pydantic ValidationError to
    # AdCPInvalidRequestError, so the boundary now emits the typed error WITH a suggestion and
    # the scenario's three wire assertions (fails, code INVALID_REQUEST, suggestion present)
    # all hold. Inspected per .claude/rules/workflows/xpass-graduation.md: the assertions are
    # wire-level, not truthiness, so the pass is not vacuous.
    "T-UC-002-ext-h-agent": "unregistered agent_url validation not wired — _validate_and_convert_format_ids is dead code",
    # Graduated: T-UC-002-ext-i, for the same reason as ext-f above -- the auth error was
    # never reached. With the raw dispatch the request crosses the transport, the auth
    # boundary answers, and its envelope does carry a suggestion (prkv.33).
    # FIXME: adapter failure raises exception instead of returning failed result
    # Production wraps adapter exceptions as AdCPAdapterError and re-raises instead of
    # returning CreateMediaBuyResult(status="failed"). Also no suggestion field on error.
    "T-UC-002-ext-j": "adapter failure raises exception, no failed result envelope or suggestion — spec-production gap",
    "T-UC-002-inv-026-2": "INVALID_CREATIVES error lacks suggestion field",
    "T-UC-002-inv-026-4": "INVALID_CREATIVES error lacks suggestion field",
    # Graduated (#1417/gh8p.10): the request-construction boundary now derives a
    # field-aware suggestion (suggest_validation_fix) and attaches it to the
    # AdCPValidationError, so a missing idempotency_key rejects with a non-empty
    # wire suggestion. T-UC-002-v31-idempotency-missing passes.
    # FIXME: optimization_goals not in adcp v3.6.0 or production schemas
    # PackageRequest(extra='forbid') rejects the field with generic validation error,
    # not spec-expected UNSUPPORTED_FEATURE / INVALID_REQUEST with structured codes.
    "T-UC-002-ext-u": "optimization_goals not in production schemas — spec-production gap",
    # Graduated 2026-09-01 with T-UC-002-ext-h above, same cause: the scenario asserts the
    # operation fails with INVALID_REQUEST, recovery correctable, and a suggestion -- which is
    # what the boundary now emits for a schema rejection. T-UC-002-ext-u (the non-event row)
    # stays ledgered: it is a different assertion and has not been shown to pass.
    # RESOLVED: optimization_goals now accepted by production schemas (UC-003).
    # Removed stale xfails: T-UC-002-partition-optimization-goals, T-UC-002-boundary-optimization-goals
    # Valid rows now pass; invalid rows xfail via _assert_error_outcome _SPEC_PRODUCTION_CODE_MAP.
    # Removed: T-UC-003-partition-optimization-goals, T-UC-003-boundary-optimization-goals, T-UC-003-alt-optimization-goals
    # NOTE: principal-ownership error code gap — spec expects ACCOUNT_NOT_FOUND,
    # production raises AdCPAuthorizationError (PERMISSION_DENIED, )
    # — see T-UC-003-ext-c below
    # RESOLVED: UpdateMediaBuySuccess status="submitted" now handled
    # by then_response_status (empty affected_packages = approval pending).
    # Removed T-UC-003-alt-manual xfail — tests pass with the fix.
    # FIXME: catalog validation not implemented in production
    # PackageRequest accepts catalogs (inherited from adcp library) but production
    # code never validates duplicate types or catalog_id existence.
    "T-UC-002-ext-v": "catalog validation not implemented in production — spec-production gap",
    "T-UC-002-ext-v-notfound": "catalog validation not implemented in production — spec-production gap",
    # FIXME: proposal-based creation not implemented in production
    # proposal_id exists on adcp library CreateMediaBuyRequest but production code
    # never reads it — no proposal store, no allocation derivation, no budget distribution.
    "T-UC-002-alt-proposal": "proposal-based creation not implemented in production — spec-production gap",
    # FIXME: pricing XOR invariant not enforced during create_media_buy
    # Schema-level validate_pricing_option() enforces XOR but _validate_pricing_model_selection()
    # works at ORM level (is_fixed + rate + price_guidance) and doesn't check for both/neither.
    "T-UC-002-inv-006-3": "pricing XOR invariant (both set) not validated in create flow — spec-production gap",
    "T-UC-002-inv-006-4": "pricing XOR invariant (neither set) error lacks suggestion field — spec-production gap",
    # RESOLVED: budget positivity validation now works — removed stale xfail T-UC-002-inv-008-2
    # FIXME: ASAP case sensitivity error code mismatch
    # Production: Pydantic rejects "ASAP" → ValidationError, spec expects INVALID_REQUEST.
    "T-UC-002-inv-013-5": "INVALID_REQUEST error code not implemented for wrong-case ASAP — spec-production gap",
    # FIXME: sandbox mode not implemented in create_media_buy
    # CreateMediaBuyResult has no sandbox field; no sandbox suppression logic exists.
    # sandbox-production passes vacuously (sandbox absent from response by default).
    "T-UC-002-sandbox-happy": "sandbox mode not implemented in create_media_buy — spec-production gap",
    "T-UC-002-sandbox-validation": "sandbox mode not implemented in create_media_buy — spec-production gap",
    # FIXME(production-gap bead): natural-key sandbox resolution
    # without prior provisioning is unimplemented. _resolve_by_natural_key
    # (account_helpers.py:110) requires the sandbox account to already exist —
    # raises ACCOUNT_NOT_FOUND rather than auto-provisioning — and
    # CreateMediaBuyResult exposes no sandbox field to echo. Step dispatches the
    # real natural-key create on the wire; flips to a pass when sandbox
    # auto-provisioning + the sandbox echo land. BR-RULE-209 INV-8.
    "T-UC-002-sandbox-natural-key": "natural-key sandbox auto-provisioning + sandbox echo not implemented "
    "in create_media_buy (ACCOUNT_NOT_FOUND without prior provisioning) — spec-production gap",
    # FIXME: inline creative upload not persisted in create_media_buy
    # process_and_upload_package_creatives → _sync_creatives_impl should persist
    # creatives to DB, but the Then step "upload creatives to creative library" fails
    # because no Creative rows exist after creation. Gap was previously masked by
    # inline pytest.xfail() in the step body — moved to scenario-level here.
    "T-UC-002-alt-creatives": "inline creative upload not persisted in create_media_buy — spec-production gap",
    # RESOLVED: T-UC-004-webhook-hmac — DB setup fix exposed that Then steps are pending (no-op).
    # Test passes trivially; real HMAC assertion gap tracked separately.
    # RESOLVED: T-UC-004-webhook-creds-short — DB setup fix exposed that Then steps are pending (no-op).
    # Test passes trivially; real credential assertion gap tracked separately.
    # Graduated: T-UC-002-inv-080-1 ("account field absent"). The entry said production
    # accepts a create_media_buy without account while BR-RULE-080 INV-1 and
    # create-media-buy-request.json /required both demand it. CreateMediaBuyRequest.account
    # is REQUIRED now (salesagent-prkv.68; it was the last surviving instance of
    # salesagent-prkv.28, which had already fixed update_media_buy and sync_creatives), so
    # an absent account is refused at the request boundary as the scenario always said.
    # FIXME: rate limiting + payload size validation not implemented
    # Rate limiting middleware does not exist (AdCPRateLimitError never raised).
    # No ASGI middleware checks content-length for oversized bodies.
    "T-UC-002-nfr-001": "rate limiting + payload size validation not implemented — spec-production gap",
    # ── UC-010 batch-1 wiring — remaining per-family gaps re-cited to their GH homes ──
    # Verified against a real run 2026-07-14: every entry below fails on all
    # three wire transports (strict holds); per-row / per-transport gaps use
    # _SELECTIVE_XFAIL / _MCP_SELECTIVE_XFAIL instead.
    # T-UC-010-main's live gap, MEASURED not assumed (#1721). The previous reason
    # here claimed reporting_delivery_methods; that was stale -- the scenario never
    # reaches it. It stops EARLIER, at media_buy.portfolio.primary_channels, which
    # comes back ["display"] (the "couldn't determine from adapter" default)
    # because the harness's set_adapter_channels has no realize_e2e write-through:
    # unlike its sibling set_targeting_capabilities, it configures only the
    # in-process adapter mock, so the real MCP/A2A/REST auth chain resolves an
    # adapter that never saw the channels. Verified by running the split scenario
    # against PRISTINE source in a separate worktree: identical failure, so it is
    # pre-existing and not caused by #1721's changes.
    # The fix is the AdapterConfig.test_behavior write-through — owned by this
    # plan's Lane E step 2, tracked as #1871 — NOT a production defect.
    # SPLIT (#1721): the scenario's one SPEC-blocked assert no longer sits here. Its single undeliverable
    # assert -- media_buy.reporting_delivery_methods -- moved to its own scenario,
    # @T-UC-010-main-reporting-delivery, which carries the xfail below. The rest of
    # T-UC-010-main (account.*, supported_pricing_models, media_buy.features,
    # execution.targeting.geo_*, portfolio, last_updated) now EXECUTES on every
    # transport for the first time; those asserts were being masked by this entry.
    "T-UC-010-main-reporting-delivery": "media_buy.reporting_delivery_methods not emitted -- declaring it "
    "is SPEC-FORBIDDEN while webhook_signing (RFC 9421) is unsupported: get-adcp-capabilities-response.json "
    "must_equal_when requires webhook_signing.supported=true whenever the method list contains 'webhook'. "
    "Production pushes HMAC-signed reporting webhooks but may not advertise them until RFC 9421 lands — #1291",
    # Graduated: _build_adcp_block() now always emits
    # adcp.supported_versions (derived from SUPPORTED_ADCP_VERSIONS) on both
    # the no-tenant and tenant-resolved paths. T-UC-010-ext-a removed.
    # Graduated: T-UC-010-auth-data-identity — capability
    # discovery now resolves the adapter CLASS tenant-only (INV-4), identical
    # for anonymous and authenticated callers.
    # Graduated: T-UC-010-ext-c-a2a — A2A public-skill list
    # now always validates a presented token (adcp_a2a_server.py), rejecting
    # an invalid one with AUTH_INVALID regardless of skill-level auth
    # requirement, matching v3.1.1 error-code.json.
    # Graduated: T-UC-010-ext-c-mcp — MCP ToolResult now
    # pre-serializes via model_dump(mode="json"), so audience_targeting is
    # correctly omitted instead of serialized as null.
    # T-UC-010-ext-d-filter FULLY GRADUATED: the new POST
    # /api/v1/capabilities route carries protocols/context/adcp_version on all
    # 3 transports, so a2a/mcp/rest all now pass (removed from both this dict
    # and the _SELECTIVE_XFAIL rest-only entry below).
    # T-UC-010-ext-d-invalid-value / -empty / T-UC-010-ext-e-echo / -nested / -empty
    # FULLY GRADUATED: GetAdcpCapabilitiesRequest now
    # constructs a real typed GetAdcpCapabilitiesRequest (Pydantic enforces the
    # protocols enum + minItems:1), and _get_adcp_capabilities_impl echoes
    # req.context verbatim onto the response on every transport.
    "T-UC-010-ext-d-all-protocols": "signals/governance/sponsored_intelligence/creative sections never emitted — #1724",
    # Graduated: T-UC-010-v31-supported-versions removed —
    # see T-UC-010-ext-a graduation note above (same _build_adcp_block fix).
    # Graduated: version negotiation now implemented
    # (src/core/version_negotiation.py) — a bad adcp_version/adcp_major_version
    # pin raises AdCPVersionUnsupportedError -> VERSION_UNSUPPORTED on all
    # transports. T-UC-010-v31-version-unsupported /
    # -major-fallback / -build-version-advisory removed from this dict.
    # Wired non-dormant + strengthened: steps execute and grade the
    # spec-pinned shape, then fail on the unemitted/hard-coded block (strict xfail on all transports).
    "T-UC-010-v31-compliance-testing": "compliance_testing block not emitted by the capabilities builder; no comply_test_controller surface — #1724",
    # Re-cited #1592 -> #1724 (a recorded gap batch B3). The OLD reason ("hard-coded,
    # not derived from tenant config") is now FALSE: specialisms ARE declaration-driven
    # and registry-validated. The scenario stays xfailed for a different, permanent
    # reason — it claims postures this deployment does not back.
    "T-UC-010-v31-specialisms": "scenario claims unbacked postures the STRICT policy forbids declaring: `creative-generative` (no generative creative implemented) and the `creative` protocol (bundle required_tools unimplemented) — #1724",
    # Ledger SHRINK (a recorded gap batch B5): T-UC-010-v31-advisory-errors removed —
    # the capabilities builder now emits top-level advisory errors[] for genuinely
    # faulted discovery lookups (except-path only), so the gap the row recorded is closed.
    # T-UC-010-account-supported-billing / T-UC-010-account-block-presence GRADUATED
    #: account.supported_billing now derives from resolve_supported_billing(tenant)
    # and the account block is now emitted on the tenant-resolved path.
    # Graduated (a recorded gap R1): media_buy.supported_pricing_models now derives from
    # adapter.get_supported_pricing_models() (mirrors products.py:721). T-UC-010-pricing removed.
    "T-UC-010-audience-caps": "media_buy.audience_targeting not emitted by the capabilities builder — #1855",
    # Wired non-dormant + strengthened: steps execute and grade the
    # spec-pinned shape, then fail on the missing block (strict xfail on all transports).
    "T-UC-010-conversion-caps": "media_buy.conversion_tracking not emitted by the capabilities builder — #1855",
    "T-UC-010-creative-caps": "creative section not emitted — production advertises only the media_buy protocol — #1724",
    # Graduated (a recorded gap R2): CHANNEL_MAPPING now includes sponsored_intelligence,
    # the 20th canonical channel. T-UC-010-channel-all-canonical removed.
    # Wired non-dormant + strengthened: each scenario executes and grades the
    # spec-pinned shapes, then fails on a block the capabilities builder never emits (strict
    # xfail on all transports).
    "T-UC-010-features": "media_buy.content_standards / conversion_tracking / audience_targeting presence-objects not emitted (#1855) and the account block (account.sandbox) not emitted (#1856) by the capabilities builder",
    # _build_geo_postal_areas builds the native country-keyed map correctly --
    # geo_postal_areas is not part of the gap. The remaining gap is the non-geo
    # targeting dimensions never being built.
    "T-UC-010-targeting": "targeting emits only geo_countries/geo_regions/geo_metros/geo_postal_areas — "
    "age_restriction, language, keyword_targets, negative_keywords, geo_proximity not built "
    "— #1857 non-geo targeting capability dimensions",
    # Wired non-dormant + strengthened: each scenario executes and grades the
    # spec-pinned v3.1.1 shape, then fails on a block the capabilities builder never emits
    # (brand is not in supported_protocols; measurement block never built). Strict xfail, all
    # transports.
    # Re-cited #1592 -> #1724 (a recorded gap, owner decision 2026-07-27). The brand family
    # was re-homed ENTIRELY rather than partially delivered: `brand` in supported_protocols
    # commits the seller to `get_brand_identity` (protocols/brand/index.yaml#required_tools),
    # which has zero implementations here, and the schema forbids emitting the block without
    # that protocol claim ("Only present if brand is in supported_protocols"). Emitting roster
    # facts either way would be the over-advertising STRICT exists to prevent.
    "T-UC-010-v31-brand-block": "scenario requires the brand protocol claim, which commits to get_brand_identity (unimplemented), and brand.rights=true, an unbacked tool commitment — #1724",
    # Ledger SHRINK (a recorded gap batch B1): T-UC-010-v31-measurement-catalog removed.
    # The tenant's measurement catalog is a declarable business fact, so the scenario is
    # graded by the capability-declaration store (measurement block + supported_protocols
    # union + the measurement.core experimental-feature implication) rather than ledgered
    # as a permanent production gap.
    # Wired non-dormant + strengthened: each row executes and grades the
    # spec-pinned bound/relation, then fails on all transports because the capabilities builder
    # never derives idempotency from tenant config and runs no version negotiation (#1592).
    # Strict tag-level xfail — every parametrized row fails.
    # T-UC-010-v31-request-signing-monotonicity / T-UC-010-v31-webhook-signing-bounds moved to
    # _SELECTIVE_XFAIL: request_signing/webhook_signing={supported:false} now
    # emitted, so the "valid" rows (which only assert schema-valid subset/disjoint relations or
    # must_equal_when bounds against an unsupported posture) pass; the "invalid" rows (which
    # require the builder to REJECT a relation-violating/out-of-bounds posture with
    # CONFIGURATION_ERROR) still fail. NOTE: a per-tenant config surface DOES now
    # exist (tenants.capability_declarations, #1592 T1a) — what it deliberately lacks is any
    # signing field, under the STRICT capability policy. Re-cited #1592 -> #1291.
    # Graduated: get_idempotency_posture() now returns a
    # typed IdempotencyPosture whose check_bounds() enforces the
    # replay_ttl_seconds/in_flight_max_seconds schema bounds, raising
    # CONFIGURATION_ERROR (terminal) on the invalid rows; the harness
    # CapabilitiesEnv.set_idempotency_posture override lets the boundary rows
    # drive it. T-UC-010-v31-idempotency-ttl-bounds removed from this dict.
    # Graduated: version negotiation now emits a non-empty,
    # release-precision supported_versions in VERSION_UNSUPPORTED details on
    # every row. T-UC-010-v31-version-unsupported-details-bounds removed.
    # ── UC-011 list wiring — graduated; provenance below ───────────────────
    # Graduated: _apply_list_account_filters honors req.account
    # (AccountReference oneOf, both account_id and natural-key arms), forwarded by
    # all 3 transports. T-UC-011-list-account-filter removed.
    # T-UC-011-list-authorization: the Account schema carries no authorization
    # object (account-with-authorization item shape is new in 3.1.1), so the
    # wire items never expose allowed_tasks. Out of scope (GH #1615).
    "T-UC-011-list-authorization": "per-account authorization block (account-with-authorization / allowed_tasks) not "
    "emitted — production Account schema has no authorization field, list items are bare — tracked as GH #1615, "
    "out of #1592 A3 core scope",
    # Graduated: ListAccountsRequest.idempotency_key added --
    # the read wrapper now tolerates the 3.1 idempotency envelope instead of
    # rejecting it under extra=forbid. T-UC-011-list-read-idempotency-tolerance removed.
    # Graduated: settings-update (AccountReference) mode implemented
    # via _process_settings_update_entry (both AccountReference1/account_id and
    # AccountReference2/natural-key arms), mode-exclusivity enforced in _impl before
    # dispatch (VALIDATION_ERROR naming accounts[i]), unmatched references rejected
    # with UNSUPPORTED_PROVISIONING. T-UC-011-sync-settings-update,
    # T-UC-011-sync-settings-update-no-provision, T-UC-011-sync-mode-exclusive removed.
    # Graduated: _check_billing_policy now emits recovery="correctable"
    # + details={scope, supported_billing} (conditionally, honest-absence on an empty
    # policy) on the per-account BILLING_NOT_SUPPORTED error. T-UC-011-ext-c-rejected removed.
    # ── UC-011 per-buyer-agent commercial gate wiring (FIXME(#1772)) ──
    # Steps now execute non-dormant on a2a/mcp/rest and grade the spec-pinned
    # v3.1.1 shape (error-details/billing-not-permitted-for-agent.json); each
    # fails because production (src/core/tools/accounts.py) has NO per-buyer-agent
    # commercial gate. The passthrough-only Given declares agent as
    # capability-supported (supported_billing), so _check_billing_policy accepts
    # the value and production PROVISIONS the account (action "created") instead
    # of rejecting it with BILLING_NOT_PERMITTED_FOR_AGENT — the code is never
    # emitted anywhere in production.
    "T-UC-011-billing-agent-gate-reject": "no per-buyer-agent commercial gate exists in production — agent billing is "
    "capability-supported so _check_billing_policy accepts it and the account is provisioned (action 'created') "
    "instead of rejected with BILLING_NOT_PERMITTED_FOR_AGENT + clamped rejected_billing/suggested_billing details — "
    "#1772",
    "T-UC-011-billing-agent-gate-recover": "no per-buyer-agent commercial gate exists in production — the first leg "
    "never emits BILLING_NOT_PERMITTED_FOR_AGENT (capability-supported agent billing is provisioned), so the "
    "autonomous suggested_billing recovery flow is unreachable — #1772",
    # ── UC-011 account-level notification_configs + sandbox capability gate — ALL GRADUATED ──
    # Graduated (T2 increment F4a): T-UC-011-notif-register-paused,
    # -notif-replace-clear and -notif-omit-preserves removed. accounts.notification_configs now
    # persists as a whole-array JSONType column with declarative-replace semantics (omit preserves,
    # [] clears, re-sent subscriber_id replaces in place) and is echoed on both sync_accounts and
    # list_accounts with authentication.credentials scrubbed. The three scenarios grade that surface
    # on a2a/mcp/rest.
    # Graduated: _check_sandbox_capability gate added -- rejects
    # sandbox provisioning with UNSUPPORTED_FEATURE (accounts[i].sandbox) when the
    # tenant's account_sandbox capability is not declared. T-UC-011-sandbox-capability-not-declared removed.
    # ── UC-011 notification_configs per-account rejections — ALL GRADUATED ──
    # Graduated (T2 increment F4b): T-UC-011-notif-event-scope-reject and
    # -notif-duplicate-subscriber removed. _check_notification_configs runs pre-persist in BOTH
    # entry handlers and emits a per-account failure inside a transport-level success, with the
    # exact error.field pointers the storyboards grade.
    # Graduated (T2 increment F4c): T-UC-011-notif-activation-proof-fail
    # removed. NotificationProofService performs a bounded proof-of-control challenge BEFORE the
    # write transaction opens; a failed proof
    # rejects the entry with VALIDATION_ERROR at notification_configs[j].url and writes nothing,
    # so the prior array is untouched.
    #
    # ── Delivery webhooks POST the result document with no protocol envelope ──
    # These seven were LIVE and passing. They now carry "the webhook payload is
    # compliant with the AdCP delivery webhook spec" and fail on it, so xfailing
    # them costs the assertions they already made. That price is recorded here
    # deliberately rather than avoided by grading only the layer production
    # happens to satisfy: the payload they were grading is not a conformant
    # webhook body, so those assertions were checking the contents of an
    # envelope that never existed.
    #
    # Owned by GH #2058, violation 2, which already carries the full evidence:
    # the authority is dist/docs/3.1.1/building/by-layer/L3/webhooks.mdx:198-200
    # ("Delivery-report content lives under `result`; it is not valid as the
    # top-level POST body by itself"), and :237-248 prints the flat delivery
    # report AS THE COUNTER-EXAMPLE. The schema chain agrees:
    # core/mcp-webhook-payload.json is the POST body, its `result` is
    # $ref async-response-data.json, which resolves per enums/task-type.json to
    # media-buy/media-buy-delivery-webhook-result.json for media_buy_delivery.
    #
    # THERE ARE TWO BUILDERS AND THEY DISAGREE, which is what makes this worth
    # reading before acting on a failure here:
    #   delivery_webhook_scheduler.py:332  -> create_mcp_webhook_payload(...), the
    #                                         CORRECT envelope; the live path
    #   webhook_delivery_service.py:302    -> the flat body, the counter-example
    # The in-process BDD legs route through the SECOND one
    # (CircuitBreakerEnv.call_deliver -> send_delivery_webhook,
    # tests/harness/_mixins.py:1087), so these seven fail on the builder the
    # harness reaches, NOT on the one a live buyer receives. #2058 says which of
    # the two to reconcile is still open — a production fix and a harness fix are
    # both live options — so do not "fix" this by pointing the step at the
    # scheduler; that would hide the disagreement rather than settle it.
    #
    # Each graduates when #2058 lands, whichever way it is resolved.
    "T-UC-004-webhook-window-update": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-webhook-partial-data": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-webhook-adjusted-resend": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-window-first-report": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-delayed-count-nonnegative": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-delayed-no-false-complete": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
    "T-UC-004-delayed-all-available": "#2058 violation 2: WebhookDeliveryService posts the flat result document, not the envelope",
}

# Selective xfail for parametrized scenarios where only
# some examples exercise unimplemented features. Each entry: (tag, node_id
# substrings that should xfail, reason).
_SELECTIVE_XFAIL: list[tuple[str, set[str], str]] = [
    # #1721 M4: @T-UC-010-v31-account-sandbox newly wired. The true/false rows
    # pass for real; the "absent" row expects the wire to OMIT account.sandbox
    # (buyer applies the schema default) but _build_account_block
    # (capabilities.py) always assigns an explicit tenant.get("account_sandbox",
    # True) value and never conditionally omits it — same root as the other
    # #1856 account-config-surface entries (require_operator_auth,
    # required_for_products, authorization_endpoint).
    (
        "T-UC-010-v31-account-sandbox",
        {"sandbox absent in response"},
        "account.sandbox is always assigned an explicit boolean by _build_account_block, "
        "never conditionally omitted — #1856 account-config surface",
    ),
    # #1417 wiring surfaced pre-existing UC-003 targeting-overlay gaps
    # (tracked separately). The geo include/exclude overlap partitions DO reach the
    # converged update.py:444 raise and PASS (proving da07); these other partitions
    # hit unrelated gaps: pydantic extra='forbid' on unknown/managed/device_platform
    # fields raising a raw ValidationError before dispatch, GeoProximity requiring
    # lat/lng (geometry/radius/travel_time-only modes + method-conflict unmodeled),
    # frequency_cap field-combo validation, keyword-duplicate detection, and
    # device_type include/exclude overlap validation.
    (
        "T-UC-003-partition-targeting-overlay",
        {
            # GRADUATED on every transport: unknown_field, managed_only_dimension and
            # proximity_method_conflict. The recorded gap was "pydantic extra='forbid'
            # raising a raw ValidationError before dispatch", i.e. a rejection that never
            # reached the buyer as an envelope. It does now.
            #
            # Reached by measuring three times, not by deleting the entry: a2a xpassed
            # first, so the rows were split per transport; that run showed mcp xpassing
            # too; removing mcp showed rest xpassing as well. Splitting first is what made
            # each transport's evidence separable -- graduating the bare label on a2a's
            # xpass alone would have been right by luck.
            "multiple_dimensions",
            "device_type_overlap",
            "proximity_geometry",
            "proximity_radius",
            "proximity_travel_time",
            "frequency_cap_missing_fields",
            "keyword_duplicate",
        },
        "Pre-existing UC-003 targeting-overlay validation gaps (not da07): pydantic "
        "extra='forbid' / GeoProximity coordinate modes / frequency_cap / keyword-dup / device_type overlap",
    ),
    (
        "T-UC-003-boundary-targeting-overlay",
        {
            # GRADUATED on every transport, same three-step measurement as the partition
            # entry above.
            "device_type include/exclude overlap",
            "with travel_time only",
            "with radius only",
            "with geometry only",
            "frequency_cap max_impressions without per",
            "keyword_targets with duplicate",
        },
        "Pre-existing UC-003 targeting-overlay validation gaps (not da07): pydantic "
        "extra='forbid' / GeoProximity coordinate modes / frequency_cap / keyword-dup / device_type overlap",
    ),
    # ── #1721 lane D: three UC-018 outlines newly wired ──
    # The lane converts _handle_list_creatives_skill to the shared build_*_request
    # seam and moves the MCP structured->flat sort/pagination coercion into
    # ListCreativesRequest. Only the rows whose behavior that conversion can
    # silently delete are authored; the siblings below grade production the lane does
    # NOT touch, so they are parked PER ROW rather than the whole outline being left
    # dormant at the harness gate (which is how the merge and coercion rows came to be
    # ungraded in the first place). Every entry cites #1721.
    (
        "T-UC-018-partition-filters",
        {
            "no_filters",
            "flat_only",
            "structured_only",
            "flat_and_structured_no_conflict",
            "flat_and_structured_conflict",
            "tags_and_semantics",
            "tags_or_semantics",
            "combined_date_range",
            "invalid_date_format",
            "empty_tags_array",
            "creative_ids_over_limit",
        },
        "UC-018 filter-semantics rows outside the media_buy_id/media_buy_ids merge this lane "
        "grades: flat/structured precedence, tags AND/OR semantics, date-range and creative_ids "
        "validation are unimplemented or ungraded production surfaces — #1721",
    ),
    (
        "T-UC-018-partition-field-selector",
        {
            "omitted",
            "single_field",
            "minimal_set",
            "all_fields",
            "enrichment_fields",
            "invalid_db_status_tolerance",
            "empty_array",
            "unknown_field",
            "non_string_item",
        },
        "UC-018 fields[] projection is not implemented in production (nothing reads req.fields; "
        "no field selector exists in src/), so only the include_assignments row of this outline "
        "grades a real behavior — #1721",
    ),
    (
        "T-UC-018-boundary-pagination",
        {
            "assignment_count",
        },
        # GRADUATED (2026-08-31, ): the max_results rows are OUT of this
        # entry because the gap it described is closed -- list_creatives_raw and
        # ListCreativesBody now declare the spec's pagination object, so max_results has a
        # path on A2A and REST and those rows XPASSed strict. The limit=1000/1001 rows are
        # gone entirely: `limit` is not an AdCP 3.1.1 field, and the code cap they graded is
        # not a spec behaviour.
        # Still dormant: assignment_count sorting is genuinely unimplemented --
        # CreativeRepository.get_by_principal maps only name/status/created_at -- so the
        # enum's last member cannot be honoured yet. That is a real production gap, not a
        # wiring one — #1721
        "UC-018: assignment_count sorting is unimplemented (CreativeRepository."
        "get_by_principal maps only name/status/created_at), so the last member of "
        "creative-sort-field.json cannot be honoured — #1721",
    ),
    (
        "T-UC-005-partition-disclosure",
        {"duplicate_positions"},
        "disclosure_positions filter/validation not implemented",
    ),
    # Graduated: all_positions, no_matching_formats on impl (disclosure filter now partially works)
    # Non-impl transports still fail — handled in transport-aware section below.
    # MCP-specific disclosure xfails are in _MCP_SELECTIVE_XFAIL
    (
        "T-UC-005-boundary-disclosure",
        {"duplicate positions"},
        "disclosure_positions filter/validation not implemented",
    ),
    # Graduated: "all 8 positions", "format has no" on impl (disclosure filter now partially works)
    # Non-impl transports still fail — handled in transport-aware section below.
    # MCP-specific boundary disclosure xfails are in _MCP_SELECTIVE_XFAIL
    # adcp 3.12: type filter removed — only "invalid" examples fail (valid rows dispatch unfiltered and pass)
    (
        "T-UC-005-partition-type-filter",
        {"invalid_type"},
        "adcp 3.12: type filter removed from ListCreativeFormatsRequest — invalid type no longer rejected",
    ),
    (
        "T-UC-005-boundary-type-filter",
        {"invalid type (rejected)"},
        "adcp 3.12: type filter removed from ListCreativeFormatsRequest — invalid type no longer rejected",
    ),
    # Graduated: T-UC-005-boundary-asset-types (all 4 transports pass — brief/catalog now in enum)
    # Graduated: T-UC-005-partition-agent-type, T-UC-005-boundary-agent-type,
    # T-UC-005-boundary-agent-asset — all pass now that When steps dispatch through harness.
    # FIXME: BR-RULE-029 defines 4 notification types but production
    # WebhookDeliveryService only emits {scheduled, final, adjusted}. No is_delayed flag.
    (
        "T-UC-004-webhook-notification-type",
        {"delayed"},
        "BR-RULE-029: production webhook service has no is_delayed flag — only scheduled/final/adjusted emitted",
    ),
    # ── UC-010 batch-1 per-row gaps — re-cited to their GH homes ───────────
    # The 'omitted' / absence rows of these outlines pass vacuously (the field
    # is absent because the whole block is missing), so only the value rows xfail.
    # Graduated: invalid_token_a2a row — A2A now always
    # validates a presented token, rejecting invalid ones with AUTH_INVALID.
    # operator_auth_not_required GRADUATED: require_operator_auth is now
    # emitted as the true constant False. operator_auth_required (expects True) can never
    # pass with this plan — no per-tenant operator-auth config surface exists.
    (
        "T-UC-010-account-require-operator-auth",
        {"operator_auth_required"},
        "account.require_operator_auth is a hardcoded False constant — no config surface to "
        "make it True exists — #1856",
    ),
    (
        "T-UC-010-account-required-for-products",
        {"products_gated", "products_open"},
        "account.required_for_products not emitted — #1856",
    ),
    (
        "T-UC-010-account-authorization-endpoint",
        {"oauth_supported"},
        "account.authorization_endpoint not emitted — #1856",
    ),
    # Graduated (#1721 M4): given_capability_config now writes account_sandbox
    # through configure_tenant_field when the row spells sandbox={true,false} --
    # sandbox_disabled passes for real on all 3 transports.
    (
        "T-UC-010-degradation-account",
        {"account_degraded"},
        # _build_account_block (src/core/tools/capabilities.py) always emits
        # require_operator_auth (a constant) and sandbox (tenant.account_sandbox,
        # default True) as real, non-null values -- only authorization_endpoint/
        # required_for_products/account_financials are honestly omitted. The
        # scenario expects a supported_billing-only shape, which this design
        # cannot produce.
        "account_degraded expects a supported_billing-only account block, but "
        "_build_account_block always emits require_operator_auth and sandbox as real "
        "constant/config values, not honestly omitted — #1856 account-config surface",
    ),
    # Wired non-dormant + strengthened: the 'absent' rows (adapter
    # fails / capability disabled) pass — the block is genuinely off the wire; only the
    # 'present' rows (full_response: adapter succeeds AND capability enabled) fail,
    # because production never emits the media_buy.audience_targeting /
    # conversion_tracking blocks yet. Strict on the present rows only.
    (
        "T-UC-010-degradation-sections",
        {"full_response"},
        "media_buy.audience_targeting / conversion_tracking sections not emitted by the capabilities builder — #1855",
    ),
    # Wired non-dormant + strengthened: targeting-partitions rows that
    # production satisfies (adapter_unavailable_defaults, nested_absent) pass; the rest execute
    # the real assertion and fail because the capabilities builder never emitted the richer
    # non-geo dimensions (age_restriction/language/keyword_targets/negative_keywords/geo_proximity
    # -- R8 follow-up, out of core scope). Graduated (a recorded gap R4): nested_populated /
    # postal_areas_native / postal_areas_legacy_alias now pass -- the native country-keyed
    # geo_postal_areas map is built (_build_geo_postal_areas, capabilities.py), no longer the
    # deprecated boolean-alias shape.
    (
        "T-UC-010-targeting-partitions",
        {
            "full_adapter",
            "partial_dimensions",
            "age_restriction_supported",
            "keyword_targeting",
            "geo_proximity_supported",
        },
        "targeting builder never emits the non-geo dimensions (age_restriction/language/"
        "keyword_targets/negative_keywords/geo_proximity) — #1857",
    ),
    # Wired non-dormant + strengthened: degradation-partitions rows that
    # production satisfies (adapter_fail, db_fail, adapter_and_db_fail, *_absent) pass; the
    # gap rows fail — no_tenant needs adcp.supported_versions (not emitted), and no_principal
    # expects [display] but INV-4 keeps the adapter principal-free so channels are NOT degraded
    # by a missing principal. full_response GRADUATED: the account block is
    # now emitted with non-empty supported_billing and adcp.idempotency is already present.
    # account_degraded stays xfailed — a separate, still-ungraded gap (needs investigation).
    (
        "T-UC-010-degradation-partitions",
        {"no_tenant", "no_principal", "account_degraded"},
        # _build_adcp_block(None) always emits supported_versions, so that is not
        # the no_tenant gap. The real no_tenant gap is extra top-level keys:
        # _deg_no_tenant asserts wire keys are a SUBSET of {adcp,
        # supported_protocols}, but the no-tenant response also includes
        # specialisms/webhook_signing/request_signing, which are non-null and
        # therefore present on the wire.
        "no_tenant top-level response carries extra keys (specialisms, webhook_signing, "
        "request_signing) beyond the minimal {adcp, supported_protocols} contract; "
        "INV-4 keeps adapter channels principal-free so no_principal does not degrade to "
        "[display]; account_degraded expects a supported_billing-only account block but "
        "_build_account_block always emits require_operator_auth/sandbox as real values "
        "— #1856 account-config surface",
    ),
    # Wired (a recorded gap R7): approval_unspecified (creative_approval_mode omitted
    # by default -- TenantFactory.human_review_required=False and no
    # gam/kevel/mock_manual_approval_required column set) passes today with zero
    # production change -- honest-absence regression armor. Graduated: approval_human
    # now passes -- resolve_manual_approval_signal() derives require_human from
    # tenant.human_review_required (adapter_helpers.py), wired into the MediaBuy build.
    # approval_auto stays xfailed -- no config surface exists to affirmatively claim
    # auto_approve (Q2, deferred; declaring it without certainty would be a false
    # conformance claim).
    (
        "T-UC-010-v31-creative-approval-mode",
        {"approval_auto"},
        "media_buy.creative_approval_mode=auto_approve has no backing config surface (Q2 deferred) — #1724",
    ),
    # Moved from _XFAIL_TAGS: request_signing/webhook_signing={supported:false}
    # now emitted, so "valid" rows (asserting schema-valid relations/bounds against an
    # unsupported posture) pass; "invalid" rows (requiring the builder to REJECT a
    # relation-violating/out-of-bounds posture with CONFIGURATION_ERROR) still fail — no
    # per-tenant signing-posture config surface exists to reject against.
    (
        "T-UC-010-v31-request-signing-monotonicity",
        {
            "required_for adds one operation not in supported_for",
            "warn_for and required_for share exactly one operation",
            "protocol_methods_required_for adds one method not in protocol_methods_supported_for",
        },
        "the declaration store deliberately carries NO request_signing field under the STRICT "
        "capability policy, so there is no relation-violating posture to reject: declaring one is "
        "refused up front with CONFIGURATION_ERROR naming the block. Rejecting a relation VIOLATION "
        "requires the posture to be declarable first, which lands with RFC 9421 signing — #1291",
    ),
    (
        "T-UC-010-v31-webhook-signing-bounds",
        {
            "reporting_delivery_methods=['webhook'], supported=false",
            "supports_webhook_delivery=true, supported absent",
            "algorithms=['rsa-pss-sha512']",
        },
        "the declaration store deliberately carries NO webhook_signing field under the STRICT "
        "capability policy, so a supported!=true-under-trigger or out-of-enum-algorithm posture "
        "cannot be declared and therefore cannot be rejected on its own terms; declaring the block "
        "at all is refused with CONFIGURATION_ERROR. Grading these bounds needs the posture to be "
        "declarable, which lands with RFC 9421 signing — #1291",
    ),
    # Wired non-dormant + strengthened: the baseline-absence row passes
    # (polling_only → reporting_delivery_methods/offline_delivery_protocols absent, webhook_signing
    # honest-tautology); the push-delivery rows fail because the capabilities builder never emits
    # media_buy.reporting_delivery_methods / offline_delivery_protocols / webhook_signing.
    (
        "T-UC-010-v31-reporting-delivery-methods",
        {"webhook_only", "offline_only", "mixed_delivery"},
        "media_buy.reporting_delivery_methods / offline_delivery_protocols are not declarable: "
        "declaring [webhook] fires the schema must_equal_when forcing webhook_signing.supported=true, "
        "and no offline report delivery is implemented, so under the STRICT capability policy the "
        "store carries no field for either. Both unlock with RFC 9421 signing / real report "
        "delivery — #1291",
    ),
    # Wired non-dormant + strengthened: the no-emission row passes (no
    # must_equal_when trigger fires → webhook_signing absent is schema-valid); the emission rows
    # grade the conditional invariant (supported MUST equal true) and fail because the
    # capabilities builder emits no webhook_signing block.
    (
        "T-UC-010-v31-webhook-signing-required-when",
        {"reporting_webhook_emission", "content_standards_webhook", "wholesale_feed_webhook"},
        "no webhook-emitting field is declarable under the STRICT capability policy, so the "
        "must_equal_when(webhook emission → webhook_signing.supported=true) invariant has no trigger "
        "to fire on; it becomes gradable when signing makes the postures declarable — #1291",
    ),
    # Wired non-dormant + strengthened: the no-posture row passes (a valid
    # capabilities response is emitted); the signing-posture-without-brand_json_url rows grade the
    # required_when rejection (CONFIGURATION_ERROR, recovery terminal) and fail because the builder
    # never builds identity/the signing posture and so never rejects the invalid config.
    (
        "T-UC-010-v31-identity-required-when-signing",
        {"posture_declared_identity_absent", "posture_declared_identity_empty"},
        "the store deliberately carries NO identity or request_signing field under the STRICT "
        "capability policy (identity.brand_json_url/key_origins exist only to anchor signing keys we "
        "do not publish), so a signing posture missing brand_json_url cannot be declared and the "
        "required_when rejection has nothing to fire on — #1291",
    ),
    # Wired non-dormant + strengthened: the no-posture / brand_json_url-present
    # valid rows pass (a degraded-but-schema-valid baseline response is emitted and no malformed
    # brand_json_url is on the wire); the signing-posture-without-brand_json_url invalid rows grade
    # the required_when rejection (CONFIGURATION_ERROR, recovery terminal, naming brand_json_url)
    # and fail because the builder never builds identity/the signing posture and so never rejects.
    (
        "T-UC-010-v31-identity-brand-json-url-bounds",
        {"posture_url_absent", "posture_identity_empty"},
        "same as -identity-required-when-signing: no identity/request_signing field exists in the "
        "declaration store under the STRICT capability policy, so the required_when boundary rows "
        "have no declarable posture to violate — #1291",
    ),
]


# MCP selective xfails: previously the MCP wrapper did not accept the
# disclosure_positions keyword. #1417 added disclosure_positions +
# disclosure_persistence to the MCP list_creative_formats wrapper, so the param
# is now accepted on MCP exactly like A2A/REST. The disclosure *filter* gap
# (_impl does not filter by disclosure) is all-transport and handled by
# _UC005_PARTIAL_TAGS / _XFAIL_TAGS, so no UC-005 MCP-specific entries remain.
# (tag, example_substrings, reason, strict)
# strict=True  → must fail (genuine xfail)
# strict=False → may pass vacuously (MCP errors → empty list → exclusion assertions pass)
_MCP_SELECTIVE_XFAIL: list[tuple[str, set[str], str, bool]] = [
    # Graduated: MCP ToolResult now pre-serializes via
    # model_dump(mode="json") (src/core/tools/_mcp.py), so unset
    # fields are correctly omitted instead of serialized as JSON null.
    # Former entries: T-UC-010-ext-e-absent (context: null), T-UC-010-
    # degradation-account/no_tenant (account: null).
]

# NOTE: the former _REST_XFAIL_TAGS set was retired once the stale
# CreativeFormatsEnv.build_rest_body override (which returned {}) was removed.
# In-process REST now serializes the request body and filters for real, so these
# UC-005 filter scenarios pass on [rest] like every other transport. The only
# UC-005 filter tags that still cannot hold are not REST-specific: inv-031-1-holds
# / inv-031-1-violated stay xfailed via _XFAIL_TAGS because adcp 3.12 removed the
# `type` filter for ALL transports (not a REST body issue).


#: Causes a typed xfail reason may declare. A reason whose ``cause=`` is not here is a
#: typo or an invention, and either way the row it exempts would be silently mis-routed.
#:
#: ENUMERATED FROM THE TREE, not chosen. The first version of this set was written from
#: imagination -- "spec-gap", "harness-gap", "upstream-defect" -- none of which exists
#: here, while the real "harness-limitation" was missing, so every typed reason in the
#: suite failed to parse. An AST scan of the strings that actually BEGIN with "cause="
#: gives the population; extend these sets from that scan, never from a guess.
_XFAIL_CAUSES = frozenset({"transport-drops-parameter", "production-gap", "harness-limitation"})

#: Scopes a typed xfail reason may declare.
_XFAIL_SCOPES = frozenset({"per-transport", "transport-independent"})

#: The DECLARATION: a run of ``key=value`` tokens at the HEAD of the reason, ending at
#: the first word that is not one. Anchored with ``\A`` so prose later in the string is
#: not part of the declaration -- which is the entire point of parsing instead of
#: substring-matching.
_XFAIL_DECLARATION_RE = re.compile(r"\A(?:\s*(?:cause|scope|ref)=\S+)+")
_XFAIL_TOKEN_RE = re.compile(r"(?P<key>cause|scope|ref)=(?P<value>\S+)")


class XfailReasonError(AssertionError):
    """A typed xfail reason declares a token this suite does not recognise."""


class XfailReason(NamedTuple):
    """The parsed form of a ``cause=... scope=... ref=...`` xfail reason."""

    cause: str
    scope: str
    ref: str


def parse_xfail_reason(reason: str) -> XfailReason | None:
    """Parse a typed xfail reason, or return None if it is free text.

    Why a parse and not a tighter substring match. The predicate this replaces asked
    ``"scope=per-transport" in reason``, and that is satisfied by any text CONTAINING the
    phrase -- including a sentence *describing* the token. Measured: retyping the
    declaration at :687 while leaving the prose at :706 ("scope=per-transport because each
    transport enforces ... independently") changed the collected set by ZERO rows. The
    declaration was decorative and the English sentence was load-bearing, by accident.
    A substring predicate cannot tell a declaration from a description of one; only
    position can, so ONLY the leading run of ``key=value`` tokens is read — the
    declaration ends at the first word that is not one, and everything after it is prose
    the parser never consults.

    Free text returns None rather than raising: 62 reasons in this tree are prose, three
    of them carrying unrelated ``k=`` pairs, and sweeping them is not this change's job.
    Only a reason that ANNOUNCES itself typed -- by OPENING with a run of ``key=value``
    tokens, in any order -- is held to the vocabulary. A reason that merely mentions one
    later is prose.

    The residue, stated rather than papered over: a typo in ``cause=`` ITSELF -- or in the
    leading token's key, which is the same thing -- degrades the reason into free text and
    returns None. So this DETECTS an unknown value; it does not make one unrepresentable.
    Leading whitespace is tolerated (``lstrip``) so that a reason indented in a source
    literal is still recognised as typed rather than silently becoming prose.
    """
    # Recognition is the leading TOKEN RUN, not the literal "cause=". Gating on that
    # keyword made a complete, in-vocabulary declaration whose tokens were written in a
    # different ORDER — `scope=... cause=... ref=...` — classify as free text and route
    # nothing, silently: exactly the drop this function exists to prevent, reachable by
    # word order rather than by a typo. All three live reasons happen to lead with
    # `cause=`, so it was latent, in the same way the first-occurrence bug was.
    # Only the leading declaration is parsed. Scanning the whole string was the first
    # version of this function and it carried the defect it was written to remove:
    #   'cause=production-gap — unlike scope=per-transport rows this one is global.
    #    scope=transport-independent ref=#1607'
    # parsed to scope='per-transport', because finditer took the first match ANYWHERE and
    # the first one was inside an English sentence. A reason DECLARING
    # transport-independent would have been routed per-transport by its own prose. The
    # live reason at conftest.py:781 contains 'This is NOT scope=per-transport' and
    # parsed correctly only because its declaration happened to come first — one word
    # order away from wrong.
    declaration = _XFAIL_DECLARATION_RE.match(reason.lstrip())
    if declaration is None:
        return None
    found: dict[str, str] = {}
    for match in _XFAIL_TOKEN_RE.finditer(declaration.group(0)):
        found.setdefault(match.group("key"), match.group("value").rstrip(",;."))
    missing = {"cause", "scope", "ref"} - found.keys()
    if missing:
        raise XfailReasonError(f"typed xfail reason is missing {sorted(missing)}: {reason!r}")
    if found["cause"] not in _XFAIL_CAUSES:
        raise XfailReasonError(f"unknown xfail cause={found['cause']!r} in {reason!r}; known: {sorted(_XFAIL_CAUSES)}")
    if found["scope"] not in _XFAIL_SCOPES:
        raise XfailReasonError(f"unknown xfail scope={found['scope']!r} in {reason!r}; known: {sorted(_XFAIL_SCOPES)}")
    if not found["ref"].startswith("#"):
        raise XfailReasonError(f"xfail ref={found['ref']!r} must be an issue reference like '#1607': {reason!r}")
    return XfailReason(cause=found["cause"], scope=found["scope"], ref=found["ref"])


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply xfail markers to scenarios with unimplemented production features."""
    for item in items:
        marker_names = {m.name for m in item.iter_markers()}
        nodeid = item.nodeid

        # Detect transport from parametrized nodeid: [mcp], [mcp-...], [a2a], [rest], etc.
        is_mcp = "[mcp]" in nodeid or "[mcp-" in nodeid
        is_a2a = "[a2a]" in nodeid or "[a2a-" in nodeid
        is_rest = "[rest]" in nodeid or "[rest-" in nodeid
        is_impl = "[impl]" in nodeid or "[impl-" in nodeid
        is_e2e_rest = "[e2e_rest]" in nodeid or "[e2e_rest-" in nodeid

        # T-UC-002-ext-i on MCP ONLY: an unauthenticated caller gets its PAYLOAD critiqued
        # instead of being told it is unauthenticated. The scenario sends a deliberately
        # minimal body (it is an auth test, not a payload test); a2a and rest answer
        # AUTH_MISSING, MCP validates the announced shape first and answers INVALID_REQUEST
        # naming brand/start_time/end_time. Auth-before-validation is the correct order --
        # it is also what stops an unauthenticated caller learning the request shape.
        #
        # Only visible since the step began dispatching the raw parameter bag (prkv.33);
        # while it built the request in-process the payload never reached any transport.
        # The other leg of this tag GRADUATED on a2a/rest in that same change. Filed as
        # the ordering bug it is rather than left red.
        if "T-UC-002-ext-i" in marker_names and is_mcp:
            item.add_marker(
                pytest.mark.xfail(
                    reason="MCP validates the payload before checking auth, so an "
                    "unauthenticated caller gets INVALID_REQUEST instead of AUTH_MISSING",
                    strict=True,
                )
            )

        # uc005 type-filter / disclosure-validation scenarios cannot hold as strict
        # xfails over e2e_rest — but NOT because the body is dropped (build_rest_body
        # now serializes the request and the live server observes the filters). The
        # remaining gaps are transport-independent production gaps that the in-process
        # transports xfail strict=True: the `type` filter was removed from the SDK 5.7
        # request model (adcp 3.12 — the pin 3.1.0-beta.3 still lists it, but the
        # generated request cannot carry it), and disclosure_positions lacks the pin's
        # uniqueItems validation. Against the live Docker server these scenarios pass
        # vacuously (valid rows dispatch unfiltered) rather than failing deterministically,
        # so strict=True would XPASS — weaken to strict=False to tolerate either outcome.
        uc005_filter_e2e_untestable = {
            # type filter — removed from the SDK 5.7 request model (pin still lists it)
            "T-UC-005-inv-031-1-violated",
            "T-UC-005-partition-type-filter",
            "T-UC-005-boundary-type-filter",
            # disclosure_positions duplicate — prod lacks the pin's uniqueItems validation
            "T-UC-005-partition-disclosure",
            "T-UC-005-boundary-disclosure",
        }
        uc005_filter_e2e_reason = (
            "e2e_rest: type filter removed from SDK 5.7 request model / disclosure_positions "
            "uniqueItems not validated in production — transport-independent gaps that pass "
            "vacuously over the live server, so the strict in-process xfail cannot hold here"
        )

        # Graduated: UC-005 creative agent type/asset_type filter tests now pass —
        # When steps dispatch through harness (blanket xfail removed).

        # NOTE (#1417/S5 reconciliation): the UC-002 @account error
        # scenarios (ext-r / ext-r-nk / ext-s / ext-t) are NOT impl-exclusive and
        # are NOT a wire-only gap — they failed on ALL four transports (impl + wire)
        # in the pre-drop baseline. They are the pre-existing budget-branch When-step
        # routing bug (create_media_buy account-resolution scenarios build a request
        # with `account_ref`, which CreateMediaBuyRequest rejects). That is a step
        # bug fixable in the When step, not a production wire gap, so it is left as a
        # genuine (pre-existing) failure rather than masked with an xfail. The
        # drop-impl change introduces 0 new failures; this debt is out of scope.

        # Transport-specific xfails: MCP wrappers don't accept certain filter params
        if is_mcp:
            for tag, substrings, reason, strict in _MCP_SELECTIVE_XFAIL:
                if tag in marker_names:
                    if not substrings or any(s in nodeid for s in substrings):
                        item.add_marker(pytest.mark.xfail(reason=reason, strict=strict))
                    break

        # UC-011 REST: per-request auth implemented
        # UC-011 MCP: billing policy and approval mode now populated from DB via
        # account_approval_mode column + proper harness writes (#1184 complete).

        # Graduated: T-UC-011-ext-d-push — push notification test now passes
        # (approval workflow implemented or assertion adjusted)

        # Graduated: UC-006 REST account resolution (success AND error paths).
        # SyncCreativesBody now forwards `account`, so the sync_creatives REST route
        # resolves accounts and raises ACCOUNT_* errors instead of returning 200.
        # The former xfail block for T-UC-006-partition-account/boundary-account error
        # rows on rest is removed — those scenarios pass.

        # RESOLVED: MCP transport suggestion field now correctly unpacked by
        # _unwrap_mcp_tool_error (was double-nesting the extra JSON blob).

        # RESOLVED: in-process REST no longer drops UC-005 filter params. The
        # CreativeFormatsEnv.build_rest_body override that returned {} was removed,
        # so [rest] serializes the request body and filters for real — the former
        # _REST_XFAIL_TAGS block is gone (see note above the function).

        # E2E_REST: Docker always has the creative agent — can't test empty catalog
        if is_e2e_rest and "T-UC-005-empty-catalog" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="E2E Docker always has creative agents — cannot test empty catalog",
                    strict=True,
                )
            )

        # E2E_REST: the 3 UC-003 manual-approval scenarios (T-UC-003-alt-manual,
        # T-UC-003-approval-tenant, T-UC-003-approval-adapter) GRADUATED — the old
        # strict xfail ("RestE2EDispatcher lacks update-endpoint support") became
        # stale when MediaBuyDualEnv gained dynamic REST_ENDPOINT/REST_METHOD update
        # dispatch (_active_update, PR #1567 lineage) and the trio XPASSed the
        # in-network run. They now grade on all four transports.
        # Per-scenario graduation inspection (scenario → BR → siblings → production):
        # - T-UC-003-alt-manual → GRADUATE — POST-S7/S8: MediaBuyDualEnv.build_rest_body
        #   sets _active_update + _update_target_id, so RestE2EDispatcher PUTs the real
        #   /api/v1/media-buys/{id} route (src/routes/api_v1.py:345) and stashes the raw
        #   HTTP JSON as wire_response; task_id/NOT-contain steps grade that wire via
        #   _submitted_wire_dict (loud failure if wire_response missing on non-IMPL).
        # - T-UC-003-approval-tenant → GRADUATE — BR-RULE-017 INV-2: same real-wire path;
        #   status "submitted" asserted on the typed payload parsed from the live wire.
        # - T-UC-003-approval-adapter → GRADUATE — BR-RULE-017 INV-3: same real-wire path;
        #   the last_a2a_task guard is Transport.A2A-gated and inert on e2e_rest.
        # No UC-003 entries remain in e2e_rest_known_failures.txt — no sibling conflict.

        # FIXME: E2E_REST —
        # set_registry_formats has no sidecar mock path. Docker's real creative
        # agent serves its own catalog, so scenarios that inject specific format
        # fixtures via Given steps and assert on those names can't run against
        # E2E. Remove when E2E gains catalog-injection.
        _UC005_E2E_FIXTURE_INJECTION_TAGS: set[str] = {
            "T-UC-005-inv-031-1-holds",
            # Graduated e2e_rest: inv-031-1-violated, inv-049-3-violated,
            # inv-049-4-violated, inv-049-4-nodim (pass with strong assertions)
            "T-UC-005-inv-031-2-holds",
            "T-UC-005-inv-049-1-holds",
            "T-UC-005-inv-049-1-violated",
            "T-UC-005-inv-049-2-holds",
            "T-UC-005-inv-049-2-violated",
            "T-UC-005-inv-049-3-holds",
            "T-UC-005-inv-049-3-group",
            "T-UC-005-inv-049-4-holds",
            "T-UC-005-inv-049-5-holds",
            "T-UC-005-inv-049-6-holds",
            "T-UC-005-inv-049-7-holds",
            "T-UC-005-inv-049-7-violated",
            # Graduated: inv-049-9 and inv-049-10 (u04y: no e2e_rest variants exist)
            "T-UC-005-dim-boundary",
        }
        if is_e2e_rest and (marker_names & _UC005_E2E_FIXTURE_INJECTION_TAGS):
            item.add_marker(
                pytest.mark.xfail(
                    reason="E2E: set_registry_formats has no sidecar mock — real creative agent catalog used",
                    strict=False,
                )
            )

        # FIXME(#2098): E2E_REST — webhook/circuit assertions observe
        # the in-process local origin or CircuitBreaker state, neither of which
        # is reachable from the Docker HTTP path (the origin listens on the
        # runner's loopback, not the container's). Remove when an E2E webhook
        # receiver or circuit-breaker introspection is available.
        _UC004_E2E_WEBHOOK_INTERNAL_TAGS: set[str] = {
            "T-UC-004-webhook-bearer",
            "T-UC-004-webhook-hmac",
            "T-UC-004-webhook-notification-type",
            "T-UC-004-webhook-no-aggregated",
            # DEFERRED to prebid/salesagent#2060, which owns both halves of the
            # breaker's missing coverage. These two were briefly un-routed by
            # #2098's rewrite attempt; they are RESTORED here because #2060's
            # Conditions are explicit that the routing stays until the scenario
            # actually grades the live server. Un-routed, the leg reports a plain
            # PASS, which reads as real coverage — strictly worse than an XPASS,
            # which at least records that nothing is being graded.
            #
            # Measured, not assumed: deleting circuit_breaker.record_failure() from
            # the server and re-running in-network leaves this leg passing
            # (test-results/innet_260826_1216 vs _1221, byte-identical counts).
            # Re-run it yourself with `make mutation-check-breaker`.
            "T-UC-004-webhook-circuit-open",
            "T-UC-004-webhook-circuit-recovery",
            "T-UC-004-webhook-retry-success",
            # #1873: retry/sequence observability — assert on the requests the
            # in-process origin received, not visible over the Docker HTTP path.
            # #1873 is the webhook-capture service that makes them observable.
            "T-UC-004-webhook-retry-5xx",
            "T-UC-004-webhook-retry-network",
            "T-UC-004-webhook-no-retry-4xx",
            "T-UC-004-webhook-sequence",
        }
        if is_e2e_rest and (marker_names & _UC004_E2E_WEBHOOK_INTERNAL_TAGS):
            item.add_marker(
                pytest.mark.xfail(
                    reason="E2E: in-process webhook origin + CircuitBreaker state not observable through Docker HTTP",
                    strict=False,
                )
            )

        # GRADUATED (#1417/nzjx): UC-003 empty update now rejected. Production raises
        # AdCPInvalidRequestError (INVALID_REQUEST + buyer suggestion) per BR-RULE-022
        # INV-3. Grounded against AdCP 3.1 GA: update fields are all optional in
        # update-media-buy-request.json, so an empty update passes schema validation and
        # is a SEMANTIC rejection → INVALID_REQUEST, not the schema-level VALIDATION_ERROR
        # (GA L3 error-handling). The two Scenario-Outline rows that asserted
        # VALIDATION_ERROR were corrected to INVALID_REQUEST in the same change.

        # FIXME: UC-003 keyword_targets_add — production applies the
        # keyword additions but returns empty affected_packages. All transports pass the When
        # step (no error) but the Then step "affected_packages including pkg_001" fails.
        if "T-UC-003-alt-keyword-ops" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="keyword_targets_add: affected_packages empty after keyword add (spec-production gap)",
                    strict=True,
                )
            )

        # FIXME: UC-003 inline creatives — _sync_creatives_impl
        # FK violation: creative_assignments references creative before commit.
        # _sync_creatives_impl uses its own UoW scope; assignment FK check fails
        # because the creative hasn't been committed in the outer transaction yet.
        if "T-UC-003-alt-creatives-inline" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="inline creatives: FK violation in _sync_creatives_impl assignment path (spec-production gap)",
                    strict=True,
                )
            )

        # T-UC-003-boundary-revision is wired (see _UC003_REVISION_TAGS and the
        # uc003-manual-approval row in the routing registry below), so its steps
        # RUN and each row fails or passes on its own assertion. Routing is per ROW,
        # selected on the Examples `outcome` column rather than a node-id substring, so
        # a row that changes its expected outcome stops matching instead of silently
        # keeping someone else's exemption.
        #
        # Two rows expect CONFLICT and are the coverage half of #1607. Verified failure:
        # `_assert_error_outcome` raises `AssertionError: Expected an error for outcome:
        # error "CONFLICT" with suggestion` — an assertion about a response that came
        # back 200 OK, NOT a StepDefinitionNotFoundError. Production accepts the stale
        # and ahead tokens on a2a, mcp and rest and returns success; enforcement is what
        # #1607 owns. strict=True so implementing it XPASSes and the graduation workflow
        # catches the row rather than letting it sit green-by-omission.
        #
        # One row expects INVALID_REQUEST for revision 0 and fails for a DIFFERENT
        # reason, which is why it is not filed under #1607: production DOES reject it,
        # but `UpdateMediaBuyRequest.revision` carries `ge=1`, so pydantic raises during
        # request construction inside the step — before any transport dispatch. The row
        # cannot grade the seller's response because the request never reaches the
        # seller. That is a harness limitation, not a production gap, and calling it one
        # is the exact mislabelling this task exists to stop.
        if marker_names & {"T-UC-003-boundary-revision", "T-UC-003-partition-revision"}:
            # pytest-bdd nests a Scenario Outline's Examples row under the single
            # `_pytest_bdd_example` param rather than exposing each column, so reading
            # `params["outcome"]` returns None and every row falls through unrouted.
            _row = (getattr(item, "callspec", None) and item.callspec.params.get("_pytest_bdd_example")) or {}
            _row_outcome = str(_row.get("outcome") or "")
            if "CONFLICT" in _row_outcome and is_a2a:
                # a2a fails EARLIER than the others and for a different reason, so it
                # does not carry #1607's label. Measured: a probe in _update_media_buy_impl
                # reads `req.revision=None` on a2a and `6` on mcp/rest, because
                # _handle_update_media_buy_skill rebuilds the request from five hand-listed
                # fields and forwards another hand-listed subset — `revision` is in neither.
                # Implementing CONFLICT would NOT xpass this row; the token never arrives.
                item.add_marker(
                    pytest.mark.xfail(
                        reason=(
                            "cause=transport-drops-parameter scope=per-transport ref=#1885 — the "
                            "a2a skill handler discards `revision` before it reaches the tool, so "
                            "this row cannot grade CONFLICT enforcement on a2a at all. NOT #1607: "
                            "enforcing the check would leave this row red. #1885 is the remedy — "
                            "route the handler through media_buy_update.UpdateMediaBuyRequest, which "
                            "already forwards every field — so closing it makes this row gradeable. "
                            "#1259 owns the separate question of why no guard sees the drop."
                        ),
                        strict=True,
                    )
                )
            elif "CONFLICT" in _row_outcome:
                item.add_marker(
                    pytest.mark.xfail(
                        reason=(
                            "cause=production-gap scope=per-transport ref=#1607 — update_media_buy "
                            "accepts a stale or ahead revision and returns success; the spec MUST "
                            "reject it with CONFLICT. Steps execute, the token arrives (probed: "
                            "req.revision=6 on mcp and rest), and the failure is the missing "
                            "rejection. scope=per-transport because each transport enforces (or "
                            "fails to enforce) independently, so each must xpass on its own when "
                            "#1607 lands."
                        ),
                        strict=True,
                    )
                )
            elif '"7"' in item.nodeid:
                # The wrong_type row only. The blanket entry below had been MASKING this,
                # and it is a different defect: not a harness limitation, a production gap.
                item.add_marker(
                    pytest.mark.xfail(
                        reason=(
                            "cause=production-gap scope=transport-independent ref=#1721 — pydantic "
                            'runs in lax mode, so the string "7" is coerced to 7 and a revision '
                            "whose JSON type is wrong is ACCEPTED on a2a, mcp and rest alike. "
                            "update-media-buy-request.json declares revision as an integer, so a "
                            "type violation is INVALID_REQUEST; the scenario says why it matters -- "
                            '7 and "7" must not behave alike. REMEDY: strict typing on the field. '
                            "Not done inline because revision is INHERITED from the SDK model, so "
                            "enforcing it means redeclaring the field (or making the whole request "
                            "strict), which is a cross-cutting decision about every numeric field "
                            "rather than a property of this row."
                        ),
                        strict=True,
                    )
                )
            # GRADUATED (the remaining INVALID_REQUEST rows). The entry described a harness
            # limitation -- "revision 0 is rejected by UpdateMediaBuyRequest's ge=1 during
            # request construction in the step, so the request never reaches the seller" --
            # and prescribed its own remedy: dispatch the raw payload instead of the typed
            # model. That remedy is in place. The a2a handler log for these rows now reads
            #   Found explicit skill invocation: update_media_buy with params:
            #   ['revision', 'idempotency_key', 'media_buy_id', 'paused', 'account']
            # so `revision` DOES reach the seller and the rows grade the seller's rejection
            # as written. Strict XPASS on all three transports.
            #
            # The wrong_type row ("7" as a string) came out of this graduation red, because
            # the blanket entry had been masking a REAL gap: pydantic lax mode coerced the
            # string to an int and the request succeeded. That is fixed at the field
            # instead of re-parked here -- see UpdateMediaBuyRequest.revision.

        # FIXME: UC-003 extension/error scenarios — production uses
        # different error codes than spec, or doesn't validate at all. These are
        # spec-production gaps where the step definitions are correct but production
        # code doesn't implement the expected validation.
        _UC003_EXT_XFAILS: dict[str, str] = {
            # Error code mismatches (production uses different codes than spec)
            # Graduated (#1417/gh8p.10): both auth error paths now carry a buyer-facing
            # suggestion. The REST auth boundary (_require_auth_dep) raises
            # AdCPAuthRequiredError with AUTH_REQUIRED_SUGGESTION (REST no-identity envelope
            # no longer drops it), and the unknown-principal ownership check
            # (AdCPAuthorizationError) carries a "verify your x-adcp-auth token" suggestion.
            # T-UC-003-ext-a / -ext-a-unknown pass on a2a/mcp/rest.
            "T-UC-003-ext-c": "production returns PERMISSION_DENIED (AdCPAuthorizationError), spec expects ACCOUNT_NOT_FOUND",
            # Graduated: T-UC-003-ext-d, T-UC-003-ext-d-negative (production now returns BUDGET_TOO_LOW)
            # Production doesn't validate these cases at all
            "T-UC-003-ext-e": "production doesn't validate end_time < start_time on update",
            "T-UC-003-ext-e-equal": "production doesn't validate end_time == start_time on update",
            # FIXME: stale .feature expectation, NOT a production gap.
            # Production validates currency on update and correctly emits
            # UNSUPPORTED_FEATURE (AdCPCapabilityNotSupportedError, media_buy_update.py:441;
            # verified at wire on mcp/rest/a2a). The generated .feature asserts INVALID_REQUEST.
            # UNSUPPORTED_FEATURE is the authoritative code (adcp-req BR-UC-002 impl-coverage;
            # matches UC-002 ext-d). Graduates after upstream regen.
            "T-UC-003-ext-f": "generated .feature asserts INVALID_REQUEST; production correctly emits UNSUPPORTED_FEATURE for unsupported currency on update — stale spec, pending upstream regen",
            # FIXME: stale .feature expectation, NOT a production gap.
            # Production validates the daily spend cap on update and correctly emits
            # BUDGET_EXCEEDED (AdCPBudgetExceededError, media_buy_update.py:484;
            # verified at wire on mcp/rest/a2a). The generated .feature asserts the
            # pre-v3.1 BUDGET_TOO_LOW (see UC-002 ext-k). Graduates after upstream regen.
            "T-UC-003-ext-g": "generated .feature asserts pre-v3.1 BUDGET_TOO_LOW; production validates and correctly emits BUDGET_EXCEEDED — stale spec, pending upstream regen",
            # Graduated (#1417/gh8p.10): a failed creative sync no longer crashes with an
            # FK violation. _process_assignments skips assignment for un-synced creatives,
            # and update_media_buy raises a clean retryable AdCPAdapterError carrying a
            # buyer-facing retry suggestion. T-UC-003-ext-k passes on a2a/mcp/rest.
            # Graduated (#1417): the .feature now asserts standard codes
            # (VALIDATION_ERROR for an invalid placement id, UNSUPPORTED_FEATURE when the
            # product defines no placements; invalid_placement_ids is not in the AdCP
            # vocabulary @04f59d2d5) and production emits them with a recovery suggestion.
            # The placement fixture gap (placement_configs -> placements) is fixed.
            # T-UC-003-ext-m / -ext-m-unsupported pass; xfails removed.
            # T-UC-003-ext-n moved to a dedicated STRICT xfail below (production gap).
            # Graduated: T-UC-003-ext-o (rczc: adapter failure returns correct shape on all 4 transports)
            "T-UC-003-ext-q-rejected": "production doesn't reject updates to terminal-status media buys",
            "T-UC-003-ext-q-canceled": "production doesn't reject updates to terminal-status media buys",
            "T-UC-003-ext-q-completed": "production doesn't reject updates to terminal-status media buys",
            "T-UC-003-ext-r-keyword": "production doesn't validate keyword operation conflicts",
            "T-UC-003-ext-r-negative": "production doesn't validate negative keyword conflicts",
        }
        for tag, reason in _UC003_EXT_XFAILS.items():
            if tag in marker_names:
                item.add_marker(
                    pytest.mark.xfail(
                        reason=f"spec-production gap: {reason}",
                        strict=False,
                    )
                )
                break  # One xfail per scenario is sufficient

        # FIXME(production-gap bead): UC-003 ext-n insufficient
        # privileges. Storyboard BR-UC-003-ext-n grounds an ADMIN-only adapter gate
        # (e.g. GAM guaranteed-item activation) that emits the canonical
        # PERMISSION_DENIED (pinned enum @04f59d2d5; reconciled from the prose's
        # non-canonical "insufficient_privileges" in adcp-req BR-UC-003 impl-coverage).
        # Production has NO privilege gate on update, and the AdCP buyer protocol has
        # no principal-role concept (roles live on the admin-UI User model, not
        # Principal). The fields-less ext-n request also short-circuits through the
        # empty-update INVALID_REQUEST path before any adapter call. The step now
        # arms the real update adapter with a canonical PERMISSION_DENIED rejection,
        # so this strict xfail flips to a wire-asserted pass the moment production
        # gates admin-only update actions. Strict: fails loudly when that lands.
        if "T-UC-003-ext-n" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="production gap: no admin-only privilege gate on update_media_buy; "
                    "AdCP buyers have no principal-role concept and the fields-less request "
                    "short-circuits via empty-update INVALID_REQUEST before any adapter call "
                    "(canonical target: PERMISSION_DENIED)",
                    strict=True,
                )
            )

        # FIXME(production-gap bead): UC-003 ext-v cancellation
        # refused. canceled IS a valid UpdateMediaBuyRequest field but production
        # never reads it, has no state-based NOT_CANCELLABLE check, and
        # has_updatable_fields() omits canceled — so a media_buy_id+canceled
        # request trips the empty-update INVALID_REQUEST path instead of
        # NOT_CANCELLABLE. The step arms the update adapter with the canonical
        # NOT_CANCELLABLE refusal and dispatches the real cancel on the wire, so
        # this strict xfail flips to a pass when production wires the cancel path.
        if "T-UC-003-ext-v" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="production gap: update_media_buy never reads canceled and has no state-based "
                    "cancellation gate; has_updatable_fields() omits canceled so the request short-circuits "
                    "via empty-update INVALID_REQUEST (canonical target: NOT_CANCELLABLE)",
                    strict=True,
                )
            )

        # Retired (both sides, 20e5b60d8 / PR #1567 round-2 item 2): the former
        # T-UC-002-alt-manual workflow_step_id xfail targeted the pre-3.1.1
        # scenario assertion. The scenario was reconciled to the 3.1.1
        # CreateMediaBuySubmitted contract (task_id, no media_buy_id/
        # workflow_step_id) and passes on all 4 transports — a strict xfail here
        # would XPASS-fail.

        # --- UC-005: disclosure/asset scenarios with partial impl ---
        # FIXME(#1660): disclosure_positions and brief/catalog asset types
        # partially implemented — some transport variants pass, others fail.
        # Must run BEFORE selective xfails (which use strict=True) to avoid
        # XPASS failures on transport variants that now pass.
        _UC005_PARTIAL_TAGS = {
            # disclosure_positions filter is not implemented in _impl (all transports).
            # #1417 added the param to the MCP wrapper, so MCP now sends it
            # and fails the exclusion assertion exactly like impl/a2a/rest — hence the
            # former `not is_mcp` exclusion is removed (MCP no longer passes vacuously).
            "T-UC-005-inv-049-8-violated",
            "T-UC-005-inv-049-8-nofield",
        }
        if marker_names & _UC005_PARTIAL_TAGS and not is_e2e_rest:
            item.add_marker(pytest.mark.xfail(reason="disclosure/asset partial impl", strict=False))
            # Skip selective xfails for these — the strict=False above covers them
        else:
            # Graduated (#1417): the partition/boundary-disclosure "valid"
            # examples (all_positions / no_matching_formats / all 8 positions /
            # "format has no") return unfiltered results that satisfy the assertion,
            # so they now PASS on every wire transport (a2a/mcp/rest) — no marker.
            # NOTE: main's MCP-specific strict xfails ("MCP wrapper does not accept
            # the disclosure_positions keyword") are intentionally dropped here —
            # #1417 added disclosure_positions to the MCP list_creative_formats
            # wrapper (src/core/tools/creative_formats.py:519), so MCP now accepts the
            # keyword exactly like a2a/rest and the valid examples pass on MCP too.

            # Selective xfail for parametrized scenarios
            for tag, substrings, reason in _SELECTIVE_XFAIL:
                if tag in marker_names:
                    if is_e2e_rest and tag in uc005_filter_e2e_untestable:
                        # tolerate either outcome — see uc005_filter_e2e_reason
                        item.add_marker(pytest.mark.xfail(reason=uc005_filter_e2e_reason, strict=False))
                        break
                    if any(s in item.nodeid for s in substrings):
                        item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
                    break  # tag matched — skip remaining selective entries

        # Original rejection scenario missing webhook Given step.
        # Replaced by BR-UC-002-manual-overrides.feature with webhook config.
        if "T-UC-002-alt-manual-reject" in marker_names and "T-UC-002-alt-manual-reject-override" not in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="missing webhook Given step — see test_uc002_manual_overrides.py",
                    strict=False,
                )
            )

        # NFR-006: original dispatch-in-Then scenario replaced by
        # BR-UC-002-nfr-enforcement.feature with proper Given/When/Then structure.
        if "T-UC-002-nfr-006" in marker_names:
            item.add_marker(
                pytest.mark.skip(
                    reason="replaced by test_uc002_nfr_enforcement.py::test_budget_below_minimum_order_size_is_rejected",
                )
            )

        # UC-002: e2e_rest auth middleware — unauthenticated_request graduated (pzqp),
        # but identity_missing still fails (error shape differs from spec).
        if is_e2e_rest and "T-UC-002-nfr-001-enforcement" in marker_names:
            if "unauthenticated_request" not in nodeid:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: Docker auth middleware rejects with AUTH_REQUIRED "
                        "before business logic — error shape differs from spec",
                        strict=True,
                    )
                )

        # Tag-based xfail for all other scenarios
        for tag, reason in _XFAIL_TAGS.items():
            if tag in marker_names:
                # DELETED (#1721 F14b): the e2e_rest arm of T-UC-005-main used to add a
                # SECOND, strict=False escape hatch here. It was redundant with the first
                # one, by its own account: over e2e_rest the Given never reaches the graded
                # gap because CreativeFormatsEnv._validate_registry_formats raises
                # E2EUnsupportedSetup ("the live stack can't be told to serve arbitrary
                # synthetic format ids"), and that declaration is already pinned in
                # EXPECTED_UNSUPPORTED_DECLARATIONS and already surfaced as xfail by the
                # report hook above -- with its reason readable at the env method rather
                # than buried in a conftest branch. Two mechanisms for one gap is how an
                # escape-hatch registry grows; the weaker one goes. strict=False was the
                # weaker one in the literal sense too: it would have swallowed an xpass, so
                # if the live catalog ever DOES serve these ids, nothing would have said so.
                if is_e2e_rest and tag == "T-UC-005-main-referrals":
                    # GRADUATED for e2e_rest (#1417): with a seeded tenant the
                    # live server populates creative_agents (>=DEFAULT_AGENT), so referrals
                    # are present on the wire and the (wire-asserting) Then passes. The marker
                    # stays strict for in-process transports where the registry mock is empty.
                    break
                if is_e2e_rest and tag in uc005_filter_e2e_untestable:
                    # tolerate either outcome — see uc005_filter_e2e_reason
                    item.add_marker(pytest.mark.xfail(reason=uc005_filter_e2e_reason, strict=False))
                    break
                item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
                break

        # --- UC-002: validation xfails (production not implemented) ---
        # NOTE: the former account-ref entries (missing_account / invalid_oneOf_both /
        # "account field absent" / "both account_id and brand") were REMOVED by
        # #1417: those scenarios now dispatch a full create_media_buy on
        # the wire. account is OPTIONAL, so an absent account SUCCEEDS (not
        # INVALID_REQUEST); the oneOf-both shape is rejected by Pydantic at the
        # boundary as VALIDATION_ERROR. The feature outcomes were reconciled to
        # match production and the scenarios now pass on a2a/mcp/rest.
        _UC002_VALIDATION_XFAIL: list[tuple[str, set[str], str]] = [
            # FIXME: daily spend cap error code mismatch
            # Production raises plain ValueError → code="validation_error", no suggestion.
            # Spec expects BUDGET_TOO_LOW with suggestion field.
            (
                "T-UC-002-partition-daily-spend-cap",
                {"exceeds_cap"},
                "daily spend cap returns validation_error, not BUDGET_TOO_LOW — spec-production gap",
            ),
            (
                "T-UC-002-boundary-daily-spend-cap",
                {"daily budget > cap"},
                "daily spend cap returns validation_error, not BUDGET_TOO_LOW — spec-production gap",
            ),
            # FIXME: creative error code mismatch
            # Production uses CREATIVES_NOT_FOUND / VALIDATION_ERROR / INVALID_CREATIVES,
            # spec expects CREATIVE_REJECTED. No max_creatives limit in production either.
            (
                "T-UC-002-partition-creative-asset",
                {"creative_not_found", "format_mismatch", "missing_required_assets"},
                "creative error code mismatch: production uses NOT_FOUND/VALIDATION_ERROR/INVALID_CREATIVES, spec expects CREATIVE_REJECTED — spec-production gap",
            ),
            (
                "T-UC-002-partition-creative-asset",
                {"exceeds_max_creatives"},
                "max_creatives limit not enforced in production — spec-production gap",
            ),
            (
                "T-UC-002-boundary-creative-asset",
                {"cr-bad", "wrong format"},
                "creative error code mismatch: production uses NOT_FOUND/VALIDATION_ERROR, spec expects CREATIVE_REJECTED — spec-production gap",
            ),
            (
                "T-UC-002-boundary-creative-asset",
                {"101 uploads"},
                "max_creatives limit not enforced in production — spec-production gap",
            ),
        ]
        if any(t.startswith("T-UC-002") for t in marker_names):
            for tag, substrings, reason in _UC002_VALIDATION_XFAIL:
                if tag in marker_names and any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
                    break

        # GRADUATED (#1534 merge): the former UC-002 oneOf-both account and
        # UC-004 webhook short-credential MCP routes are retired. The documented
        # "MCP TypeAdapter forward-compat gap" (FastMCP's TypeAdapter rejected
        # the request as a bare ToolError before the AdCP boundary translator
        # ran) is closed by RequestCompatMiddleware (#1534,
        # src/core/mcp_compat_middleware.py): TypeAdapter ValidationErrors are
        # now normalized to the AdCP two-layer VALIDATION_ERROR envelope on the
        # MCP wire (spec 3.1.1 enums/error-code.json names VALIDATION_ERROR for
        # schema-level rejections), matching what a2a/rest already emitted. The
        # strict=True markers fired as designed — deterministic XPASS on the
        # merged in-network run for both the oneOf-both rows (partition +
        # boundary) and webhook-creds-short — so the routes are removed and the
        # scenarios grade live on all transports.

        # Graduated: UC-002 ext-g inline-creative missing URL (#1417) no longer
        # xfails on MCP. The gap was: the inline creative carries a FormatId on the
        # wire, and `_upgrade_legacy_format_ids` (src/core/schemas/_base.py) wrote
        # LIVE FormatId objects into the caller's own request dicts — pydantic hands
        # a mode="before" validator its input by reference — so the dict that
        # reached rfc8785 idempotency canonicalization held an unserializable
        # object and raised a bare CanonicalizationError BEFORE the AdCP boundary
        # translator ran, yielding no two-layer envelope on MCP.
        #
        # `copy_before_mutating()` (same module) now gives that validator a
        # defensive copy, so the canonicalized dict stays plain JSON,
        # canonicalization succeeds, the boundary translator runs, and MCP emits the
        # same CREATIVE_REJECTED envelope a2a/rest already did. The strict=True
        # marker fired as designed — deterministic XPASS on run sa-d9585e1a — so the
        # route is removed and the scenario grades live on all transports.
        #
        # NOTE: this scenario's Then steps are weaker than the obligation (they
        # assert failure + "URL" in the RECONSTRUCTED message and never name an
        # error code, so CREATIVE_REJECTED itself is ungraded). That weakness is
        # pre-existing, not introduced by graduating this route; strengthening it to
        # a wire-envelope + error-code assertion is tracked separately.

        # --- UC-006: auth error code mismatch (production returns VALIDATION_ERROR, spec expects AUTH_REQUIRED) ---
        _UC006_AUTH_XFAIL = {"T-UC-006-ext-a"}
        if marker_names & _UC006_AUTH_XFAIL:
            item.add_marker(
                pytest.mark.xfail(
                    reason="AUTH_REQUIRED error code not implemented (returns VALIDATION_ERROR)", strict=True
                )
            )

        # --- UC-006: INVALID_REQUEST validation xfails (production not implemented) ---
        _UC006_VALIDATION_XFAIL: list[tuple[str, set[str], str]] = [
            (
                "T-UC-006-partition-account",
                {"missing_account", "invalid_oneOf_both"},
                "INVALID_REQUEST validation not implemented (schema-level)",
            ),
            (
                "T-UC-006-boundary-account",
                {"account field absent", "both account_id and brand"},
                "INVALID_REQUEST validation not implemented (schema-level)",
            ),
            # boundary-format-id: error-path examples need "suggestion" field
            (
                "T-UC-006-boundary-format-id",
                {"suggestion"},
                "SPEC-PRODUCTION GAP: _SyntheticError lacks suggestion field",
            ),
        ]
        if any(t.startswith("T-UC-006") for t in marker_names):
            for tag, substrings, reason in _UC006_VALIDATION_XFAIL:
                if tag in marker_names and any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
                    break

        # --- UC-006: spec-production gaps surfaced by Wave 1B step implementations ---
        # Production uses generic error codes / plain-string errors where the spec
        # demands specific codes and structured AdCPSalesAgentError with suggestion fields.
        _UC006_SPECGAP_XFAIL_TAGS: dict[str, str] = {
            # Split out of @T-UC-006-storyboard-multi-format-sync.
            # While the status obligation shared a scenario with the action
            # obligations, its xfail ABORTED the scenario and the sibling
            # action-value assertion never ran on any transport. It now owns a
            # scenario, so the action half runs LIVE and this half is ledgered.
            # Production defect: SyncCreativeResult deliberately never populates
            # the inherited spec `status` (src/core/schemas/creative.py) — it
            # stays None on the wire rather than carrying a creative-status enum.
            # e2e_rest decision (owed explicitly by the lane's design): NO
            # e2e_rest_known_failures.txt entry is required. These tag markers are
            # applied here in pytest_collection_modifyitems with no transport
            # gate, so they cover the e2e_rest param identically to a2a/mcp/rest.
            # Routing the gap through the tag ledger therefore registers it once
            # and grows NO ratchet — which is the whole point of preferring it to
            # a per-nodeid entry.
            "T-UC-006-storyboard-multi-format-sync-status": (
                "SPEC-PRODUCTION GAP: SyncCreativeResult.status is never populated by production; "
                "every per-creative status is None on the wire, not a creative-status enum value"
            ),
            # ── Storyboard provenance scenarios (#1858) ──────────────
            # These carried per-assertion pytest.xfail() calls inside the step
            # bodies, which turned ANY failure (a 401, a 500, a timeout) into a
            # green "known gap". The gaps are real, so they are registered here
            # the one sanctioned way — by scenario tag, strict=True — and the
            # steps now assert unconditionally.
            #
            # Production defect: check_provenance_required
            # (src/core/tools/creatives/_validation.py) only ever emits a soft
            # WARNING on missing/incomplete provenance. It never produces a
            # per-creative action="failed" nor the spec's PROVENANCE_REQUIRED /
            # PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING / PROVENANCE_DISCLOSURE_MISSING
            # error codes.
            "T-UC-006-storyboard-provenance-required-rejection": (
                "SPEC-PRODUCTION GAP: structural provenance rejection is not implemented — "
                "check_provenance_required emits a soft warning, never action='failed' with "
                "PROVENANCE_REQUIRED"
            ),
            "T-UC-006-storyboard-provenance-digital-source-type-missing": (
                "SPEC-PRODUCTION GAP: structural provenance rejection is not implemented — "
                "no action='failed' with PROVENANCE_DIGITAL_SOURCE_TYPE_MISSING"
            ),
            "T-UC-006-storyboard-provenance-disclosure-missing": (
                "SPEC-PRODUCTION GAP: structural provenance rejection is not implemented — "
                "no action='failed' with PROVENANCE_DISCLOSURE_MISSING"
            ),
            # Distinct defect, same family: the internal Creative.provenance model
            # (src/core/schemas/creative.py) is structurally incompatible with the
            # wire-level adcp.types Provenance it is converted from (disclosure: str
            # vs a Disclosure object, human_oversight: bool vs an enum, verification:
            # dict vs a list), so even a well-formed corrected resubmission is rejected.
            "T-UC-006-storyboard-provenance-corrected-acceptance": (
                "SPEC-PRODUCTION GAP: internal Creative.provenance is structurally incompatible "
                "with the wire-level adcp.types Provenance shape, so a spec-compliant corrected "
                "resubmission is not accepted"
            ),
            # Error-path scenarios: production returns CREATIVE_VALIDATION_FAILED or
            # plain-string errors[] instead of spec-specific error codes / AdCPSalesAgentError.
            # See _processing.py error handling paths.
            "T-UC-006-ext-d-whitespace": (
                "SPEC-PRODUCTION GAP: production returns plain-string errors[] via "
                "_SyntheticError, spec expects structured AdCPSalesAgentError with suggestion"
            ),
            "T-UC-006-ext-f": (
                "SPEC-PRODUCTION GAP: error_code is CREATIVE_VALIDATION_FAILED, spec expects CREATIVE_FORMAT_UNKNOWN"
            ),
            "T-UC-006-ext-g": (
                "SPEC-PRODUCTION GAP: error_code is CREATIVE_VALIDATION_FAILED, spec expects CREATIVE_AGENT_UNREACHABLE"
            ),
            "T-UC-006-ext-h": (
                "SPEC-PRODUCTION GAP: production returns plain-string errors[] via "
                "_SyntheticError, spec expects structured AdCPSalesAgentError with suggestion "
                "(preview-failure path, _processing.py:712-737)"
            ),
            "T-UC-006-ext-i": (
                "SPEC-PRODUCTION GAP: production returns plain-string errors[] via "
                "_SyntheticError, spec expects structured AdCPSalesAgentError with suggestion "
                "(GEMINI_API_KEY not configured path)"
            ),
            # Creative unchanged: production returns action "updated" not "unchanged"
            "T-UC-006-main-unchanged": (
                "SPEC-PRODUCTION GAP: production returns action 'updated', "
                "spec expects 'unchanged' when creative data is identical"
            ),
            # ext-c: schema violation — wrong error code
            "T-UC-006-ext-c": (
                "SPEC-PRODUCTION GAP: error_code is CREATIVE_FORMAT_REQUIRED, "
                "spec expects CREATIVE_VALIDATION_FAILED for schema violations"
            ),
            # ext-d: empty name — _SyntheticError lacks suggestion field
            "T-UC-006-ext-d": (
                "SPEC-PRODUCTION GAP: production returns plain-string errors[] via "
                "_SyntheticError, spec expects structured AdCPSalesAgentError with suggestion"
            ),
            # ext-e: missing format_id — wrong error code
            "T-UC-006-ext-e": (
                "SPEC-PRODUCTION GAP: error_code is CREATIVE_VALIDATION_FAILED, "
                "spec expects CREATIVE_FORMAT_REQUIRED for missing format_id"
            ),
            # Invariant scenarios: production behaviour diverges from spec
            "T-UC-006-rule-039-inv2": (
                "OVER-SPECIFIED OBLIGATION (#1417): scenario asserts the non-canonical "
                "FORMAT_MISMATCH. Production now emits CREATIVE_REJECTED WITH a suggestion + "
                "details (#1417), so the suggestion gap is closed; the code "
                "assertion awaits upstream reconciliation (FORMAT_MISMATCH -> CREATIVE_REJECTED)."
            ),
            # FIXME(#1417): ext-k asserts FORMAT_MISMATCH, which is NOT in the pinned
            # error-code enum (non-canonical). Production now emits CREATIVE_REJECTED
            # (_assignments.py), converged with the update path for the identical
            # condition. Reconcile upstream (adcp-req: FORMAT_MISMATCH -> CREATIVE_REJECTED),
            # then remove this xfail.
            "T-UC-006-ext-k": (
                "OVER-SPECIFIED OBLIGATION (#1417): scenario asserts the non-canonical "
                "FORMAT_MISMATCH (absent from the pinned error-code enum). Production emits "
                "the canonical CREATIVE_REJECTED, converged with the update path. Awaiting "
                "upstream reconciliation of the generated feature."
            ),
            # FIXME(#TBD): inv5-lenient: lenient mode format mismatch doesn't populate assigned_to
            # In lenient mode, the compatible package assignment should be created
            # and incompatible reported in assignment_errors. Production skips both
            # because the creative-not-found guard or format check logic prevents
            # the compatible assignment from completing.
            "T-UC-006-rule-039-inv5-lenient": (
                "SPEC-PRODUCTION GAP: lenient format mismatch does not create "
                "compatible assignment — assigned_to is empty (BR-RULE-039 INV-5)"
            ),
            # T-UC-006-rule-037-inv5: e2e_rest only — handled below with transport check
            # Sandbox: sync_creatives does not set sandbox=true on response
            "T-UC-006-sandbox-happy": (
                "SPEC-PRODUCTION GAP: sync_creatives does not set sandbox=true on "
                "response for sandbox accounts (BR-RULE-209 INV-4)"
            ),
            # Sandbox: invalid format_id does not trigger validation error at _impl level
            "T-UC-006-sandbox-validation": (
                "SPEC-PRODUCTION GAP: production does not validate format_id pattern "
                "at _impl level — invalid format_id processed without error (BR-RULE-209 INV-7)"
            ),
        }
        for tag, reason in _UC006_SPECGAP_XFAIL_TAGS.items():
            if tag in marker_names:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=True))

        # UC-006: assignment_package_validation — PACKAGE_NOT_FOUND outcome not
        # wired in the Then step dispatch (raises ValueError). The production
        # error is AdCPNotFoundError('NOT_FOUND'), spec demands 'PACKAGE_NOT_FOUND'.
        if "T-UC-006-partition-assignment-pkg" in marker_names and "package_not_found" in nodeid:
            item.add_marker(
                pytest.mark.xfail(
                    reason=(
                        "SPEC-PRODUCTION GAP: outcome 'PACKAGE_NOT_FOUND' not in Then dispatch — "
                        "production returns AdCPNotFoundError(code='NOT_FOUND'), spec expects "
                        "'PACKAGE_NOT_FOUND'. See _assignments.py:62-69"
                    ),
                    strict=True,
                )
            )

        # UC-006: format_validation_boundary agent-unreachable — production returns
        # success with per-creative action="failed" instead of raising an error.
        if "T-UC-006-boundary-format-id" in marker_names and "agent unreachable" in nodeid:
            item.add_marker(
                pytest.mark.xfail(
                    reason=(
                        "SPEC-PRODUCTION GAP: agent-unreachable returns success with "
                        "per-creative action='failed', not a top-level error — "
                        "Then step expects ctx['error'] but gets ctx['response']"
                    ),
                    strict=True,
                )
            )

        # Graduated: T-UC-004-webhook-bearer, T-UC-004-webhook-hmac,
        # T-UC-004-webhook-no-aggregated, T-UC-004-webhook-notification-type
        # (integration CircuitBreakerEnv now has make_webhook_config/set_db_webhooks
        # so webhook POST fires on all transports)

        # Graduated: UC-004 boundary-account a2a valid rows
        # ("account exists" / "single match" / "sandbox account exists") now resolve
        # once their accounts are seeded — the former "dict lacks .root serialization
        # gap" xfail was masking the missing seed, not a real transport gap.

        # --- UC-004: xfails for unimplemented production features ---
        # FIXME: These production features are not yet implemented.
        # strict=True: test MUST fail. strict=False: test MAY pass (some examples work).
        _UC004_XFAIL_TAGS: dict[str, tuple[str, bool]] = {
            # Graduated: T-UC-004-identify-empty. The reason -- "empty media_buy_ids=[] not
            # rejected by schema" -- no longer holds. The a2a boundary log shows the real
            # thing on this path: "A2A boundary translating AdCPInvalidRequestError to
            # envelope: INVALID_REQUEST (operation=get_media_buy_delivery)", i.e. a typed
            # error reaching the wire, which is what the scenario asserts. Strict XPASS, so
            # the pass is graded on the envelope rather than a reconstruction.
            "T-UC-004-identify-buyer-refs-empty": (
                "buyer_refs removed in adcp 3.12 — empty buyer_refs=[] is now an unknown field, silently ignored",
                True,
            ),
            # Invalid status filter: NOT a production gap — the generic
            # 'with {request_params}' When step shadows the specific
            # status_filter step and parses 'status_filter "X"' (no '=') to {},
            # so the request dispatches with NO params and succeeds (ah98
            # red-step inspection, 2026-07-06). GetMediaBuyDeliveryRequest DOES
            # reject invalid values; the REST wire already returns 400.
            # Suggestion parity for this path is pinned by
            # tests/integration/test_request_validation_suggestion_parity.py.
            # Graduated: T-UC-004-filter-invalid. This entry recorded a TEST defect, not a
            # production gap -- the generic 'with {request_params}' When step shadowed the
            # specific status_filter step and parsed 'status_filter "X"' (no '=') to {}, so
            # the request dispatched with no params and succeeded. The generic step now
            # requires the \w+=... key=value form, which is mutually exclusive with the
            # space form, so the specific step matches and the invalid value reaches
            # GetMediaBuyDeliveryRequest -- which, as the comment above always said, DOES
            # reject it. Strict XPASS on a2a.
            # Date range validation: production doesn't validate start>end
            "T-UC-004-daterange-invalid": ("date range validation (start>end) not implemented", True),
            "T-UC-004-daterange-equal": ("date range validation (start==end) not implemented", True),
            # Webhook delivery: not yet in production
            "T-UC-004-webhook-scheduled": ("webhook delivery not implemented", True),
            # Graduated: T-UC-004-webhook-sequence (production fixed: sequence numbers now strictly ascending)
            # Graduated: T-UC-004-webhook-circuit-halfopen (merge from main fixed circuit breaker probe timing)
            # Graduated: T-UC-004-webhook-retry-5xx (production fixed: retry count now correct)
            # Graduated: T-UC-004-webhook-retry-network (ebb527c6 fixed the off-by-one)
            # Sandbox: not yet in delivery _impl
            "T-UC-004-sandbox-happy": ("sandbox mode not implemented in delivery", True),
            "T-UC-004-sandbox-validation": ("sandbox mode not implemented in delivery", True),
        }
        for tag, (reason, strict) in _UC004_XFAIL_TAGS.items():
            if tag in marker_names:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=strict))
                break

        # UC-004: additional xfails for features needing production enhancements
        # FIXME: These require production changes, not BDD wiring.
        _UC004_XFAIL_ADDITIONAL: dict[str, tuple[str, bool]] = {
            # Graduated (#1721 M4 dormancy tripwire): T-UC-004-status-pending-legacy-alias
            # was masked by a missing second Then step (never actually reached the
            # assertion this xfail claimed was failing) -- production DOES correctly
            # surface the persisted pending_start status (XPASS(strict) once the
            # missing step was bound). Removed.
            # Graduated: T-UC-004-aggregated-roas-and-cpa (production now computes
            # conversions/conversion_value/roas/cost_per_acquisition in
            # aggregated_totals — DeliveryTotals.conversion_value + aggregation
            # quotients with omit-on-zero semantics).
            # T-UC-004-attr-supported: resolved — steps now assert attribution_window model and echo
            # T-UC-004-attr-unsupported: resolved — xfail now in step function for specific production gap
            # T-UC-004-attr-echo: resolved — vvx9 + ral2 fixed enum→str handling
            # T-UC-004-attr-omitted: resolved — vvx9 + ral2 fixed enum→str handling
            # T-UC-004-attr-campaign-valid: resolved — _impl now resolves campaign unit to days
            # T-UC-004-attr-campaign-invalid: GRADUATED (#1417). The standalone
            # "Campaign unit with interval != 1 - rejected" scenario now asserts on the wire
            # envelope (its When uses the non-shadowed 'for "mb-001" with attribution_window'
            # regex step, so the window reaches production and INV-5 fires VALIDATION_ERROR
            # with a suggestion on a2a and e2e_rest). The old transport-blind strict marker
            # was stale — removed rather than re-scoped (BDD has no in-process/_impl variant).
            # FIXME: _impl uses str(enum) instead of enum.value for sort_by metric
            # T-UC-004-dim-sortby-valid: resolved — sort_by now works in _impl
            # Graduated: T-UC-004-dim-sortby-fallback (impl, mcp, rest pass — only a2a still fails)
            # T-UC-004-dim-supported: resolved — by_device_type now populated by _impl (#1376)
            # T-UC-004-dim-truncated: resolved — truncation flags (by_*_truncated) now implemented (#1376)
            # T-UC-004-dim-complete: resolved — by_device_type_truncated flag now implemented (#1376)
            # T-UC-004-dim-geo-system: resolved — by_geo now populated by _impl
            # T-UC-004-dim-geo-postal: resolved — by_geo now populated by _impl
            # T-UC-004-dim-multi: resolved — by_device_type now on PackageDelivery (#1376)
            # Partial-success Error model lacks suggestion field and rich messages
            "T-UC-004-ext-a": ("partial-success Error needs suggestion field + authentication in message", True),
            "T-UC-004-ext-b": ("partial-success Error model needs suggestion field — production enhancement", True),
            "T-UC-004-ext-c": ("partial-success Error model needs suggestion field — production enhancement", True),
            "T-UC-004-ext-d": ("partial-success Error model needs suggestion field — production enhancement", True),
            # Graduated: T-UC-004-identify-partial, T-UC-004-identify-batch-ownership
            # (merge from main fixed _impl to silently omit missing/non-owned IDs per BR-RULE-030 INV-5)
            # Adapter error: message text + suggestion not wired in partial-success response
            # Graduated (subdl): T-UC-004-ext-f — the reason was "needs suggestion field
            # and message refinement". The suggestion field was never missing: every one
            # of the 100 CODE_TABLE entries carries one, and AdCPAdapterError resolves to
            # SERVICE_UNAVAILABLE / transient / "retry with exponential backoff", matching
            # the pin verbatim ("Seller service is temporarily unavailable. Retry with
            # exponential backoff."). What blocked it was "message refinement" — the
            # scenario demanding authored sentences that CODE_TABLE derivation makes
            # unconstructible. Removing those tautologies un-xfailed it; the scenario now
            # grades the code and the suggestion-presence (which does grade envelope
            # serialization) and nothing derived.
            # Adapter partial failure: _impl silently swallows data construction exceptions
            "T-UC-004-adapter-partial": (
                "adapter partial failure handling needs enriched test data or production fix",
                True,
            ),
            # Graduated (subdl): T-UC-004-response-error — the reason claimed the
            # suggestion field was missing and needed a "production enhancement". It
            # was never missing: ALL 100 CODE_TABLE entries carry a suggestion, so
            # the presence check cannot fail for any emittable error. The scenario
            # was actually blocked by demanding the SUGGESTION read "provide valid
            # authentication", while the no-auth path raises AdCPAuthRequiredError
            # -> AUTH_MISSING, whose table suggestion is "provide credentials via
            # the auth header and retry". Replacing that sentence-match with the
            # AUTH_MISSING code assertion — what the pin actually mandates for a
            # request carrying no Authorization header — un-xfailed it.
        }
        for tag, (reason, strict) in _UC004_XFAIL_ADDITIONAL.items():
            if tag in marker_names:
                item.add_marker(pytest.mark.xfail(reason=reason, strict=strict))
                break

        # Graduated: T-UC-004-dim-sortby-fallback — all transports pass.
        # A2A previously dropped by_placement; that serialization gap is fixed.
        # Verified: the scenario passes with by_placement present and sorted by
        # spend (then_placement_sorted_fallback asserts values == sorted(values,
        # reverse=True); inline pytest.xfail guards the vacuous case), so the
        # pass is real, not a weakened assertion.

        # UC-004 status filter: "active" works, other values may not
        # NOTE: the T-UC-004-filter / -empty / -array shadow entries were removed
        # once the generic `{request_params}` step was restricted to key=value
        # form (#1545): the specific status_filter step is no longer shadowed, so
        # values (single, empty-result, array) are all honored and pass.
        _UC004_FILTER_SELECTIVE: list[tuple[str, set[str], str]] = [
            (
                "T-UC-004-filter-default",
                set(),  # all examples
                "default status_filter=active not applied when no explicit IDs",
            ),
        ]
        if any(t.startswith("T-UC-004-filter") for t in marker_names):
            for tag, substrings, reason in _UC004_FILTER_SELECTIVE:
                if tag in marker_names:
                    if not substrings or any(s in nodeid for s in substrings):
                        item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                    break

        # Graduated: T-UC-004-daterange. When both start_date and end_date are
        # supplied, src/core/tools/media_buy_delivery.py uses them verbatim on
        # all transports (only the single-sided start-only/end-only defaulting
        # paths have a real gap, tracked separately as T-UC-004-daterange-end-only
        # / debt C7 below).

        # Per-row strict=True xfails for partition/boundary scenarios where
        # blanket markers were removed and production gaps are real and named
        # (see docs/test-debt-bdd-strict-markers.md). strict=True forces marker
        # removal the moment the underlying gap closes.
        _UC004_GENUINE_XFAIL_ROWS: list[tuple[str, set[str], str]] = [
            # Graduated (run innet_010926_0144): geo_missing_geo_level, limit_zero and
            # limit_negative. The C4 reason -- "Pydantic raises ValidationError, not
            # AdCPSalesAgentError(INVALID_REQUEST, suggestion)" -- no longer holds:
            # adcp_error_for now maps a pydantic ValidationError to
            # AdCPInvalidRequestError, so those three reach the wire as an
            # INVALID_REQUEST envelope with a suggestion, which is what the rows assert.
            # They xpassed strictly on a2a, i.e. the pass is graded on the real envelope,
            # not on a reconstructed exception.
            # geo_metro_missing_system stays: it did NOT xpass, so its gap is a different
            # one than the code mapping and has not been shown to be closed.
            (
                "T-UC-004-partition-reporting-dims",
                {"geo_metro_missing_system"},
                "Pydantic raises ValidationError, not AdCPSalesAgentError(INVALID_REQUEST, suggestion). See docs/test-debt-bdd-strict-markers.md item C4.",
            ),
            # GRADUATED (removed): T-UC-004-partition-attribution interval_zero /
            # interval_negative / invalid_unit / invalid_model — the attribution_window
            # reference now asserts the wire envelope (error "INVALID_REQUEST" with
            # suggestion), which a2a/mcp/rest emit, closing the old reconstructed-path
            # C4 gap. campaign_interval_not_one is xfailed separately below — its window
            # never reaches production due to generic-step shadowing (#1417),
            # not the #1462 in-process drop.
            (
                "T-UC-004-boundary-reporting-dims",
                {"geo with geo_level=metro but no system"},
                "AdCP spec defines metro/postal_area system requirement only in field description; no validator. See docs/test-debt-bdd-strict-markers.md item C10.",
            ),
            # GRADUATED (removed): T-UC-004-boundary-attribution "unit=campaign with
            # interval=2" — BR-RULE-092 INV-5 is now enforced by the _validate_attribution_window
            # check in _get_media_buy_delivery_impl (returns INVALID_REQUEST on all
            # transports), so the description-only C10 gap is closed.
            # GRADUATED (#1534 merge): the boundary-reporting-dims and
            # boundary-attribution mcp/rest invalid-row entries (the C4
            # transport-boundary error-normalization gap: Pydantic rejected but
            # the wire got a bare ToolError / 422 detail instead of the AdCP
            # envelope) are retired. RequestCompatMiddleware (#1534) normalizes
            # MCP TypeAdapter ValidationErrors to the two-layer VALIDATION_ERROR
            # envelope, and the merged REST boundary emits the same envelope for
            # these schema rejections — the strict=True rows fired as designed
            # (deterministic XPASS on the merged in-network run for
            # mcp-geo-without-geo_level / mcp-limit=0 / mcp-limit-negative and
            # mcp-unit=weeks / rest-interval=0 / rest-model=last_click; the
            # remaining siblings are the same rejection class on the same
            # boundary). a2a graduated earlier (#1417). Rows removed so the
            # scenarios grade live on all transports.
            # C11 retired : the "production ignores buyer
            # start_date" failure was an artefact of the greedy with-params
            # step shadowing when_request_date_range and mis-parsing the
            # request. With correct step routing, production echoes the
            # buyer-supplied start_date/end_date in response.reporting_period,
            # so T-UC-004-daterange now genuinely passes (no strict xfail).
            #
            # date-range partition (#1545): the a2a rows GRADUATED —
            # the Examples now name the wire code (error "VALIDATION_ERROR" with
            # suggestion) and production emits exactly that on the a2a wire ("Start date
            # must be before end date", media_buy_delivery.py:209-218 via
            # AdCPValidationError). Under the transport-aware harness (e2e-harness-wiring)
            # mcp/rest ARE parametrized for this partition and still gap, so they retain a
            # marker below.
            # date-range partition: fully GRADUATED. a2a first (a recorded gap,
            # #1545: "Start date must be before end date",
            # media_buy_delivery.py via AdCPValidationError), then mcp/rest
            # (2026-07-25, below). The mcp/rest partition entry the merge
            # temporarily re-added from main's e2e-harness-wiring lineage was
            # STALE — the pre-merge feature run already had all four mcp/rest
            # invalid rows passing, and on the merged in-network run the
            # re-added rows fired as deterministic strict XPASS — so it is
            # removed again (no partition marker remains).
            # Transport-scoped: impl genuinely PASSES start>=end on the _impl
            # path now.
            # GRADUATED (2026-07-25): mcp/rest now also validate
            # start_date>=end_date (confirmed XPASS on both once the single-transport
            # dedup fix stopped hiding them) — entry removed. The stricter standalone
            # T-UC-004-daterange-invalid/-equal scenarios (exact error_code/message/
            # suggestion pin) are unaffected and still genuinely xfail — this boundary
            # outline only asserts the looser "date handling should be invalid".
            # end-only date_range default (debt C7, Gap G40):
            # when only end_date is provided, the spec says start_date defaults
            # to MediaBuy.created_at but production sets start = today-30d
            # (src/core/tools/media_buy_delivery.py:162-165). The scenario's
            # Then-step asserts the exact creation-date (2025-12-01), so the
            # row genuinely fails today — upgraded from the former vacuous
            # strict=False in _UC004_DATE_SELECTIVE to strict=True here.
            (
                "T-UC-004-daterange-end-only",
                set(),
                "production defaults start_date to today-30d when only end_date is given; "
                "spec says default to MediaBuy.created_at. See docs/test-debt-bdd-strict-markers.md item C7.",
            ),
            # ---- 18h.10 Phase-2: 7 more UC-004 fields reconciled ----
            # Each field's when_partition/boundary_<field> now translates the
            # Gherkin descriptor into the real request kwargs/setup it
            # represents (mirroring the typed when_request_* steps) instead of
            # routing the axis name through _dispatch_partition. With real
            # wiring the "valid" descriptors genuinely PASS (no marker); only
            # the descriptors below genuinely fail for a real, named
            # production gap, so they carry strict=True (forces marker removal
            # the moment the gap closes). See docs/test-debt-bdd-strict-markers.md.
            #
            # daily-breakdown: include_package_daily_breakdown
            # is a real bool field; production lax-coerces non-boolean strings
            # ("yes"/"true" → True) instead of raising INVALID_REQUEST.
            (
                "T-UC-004-partition-daily-breakdown",
                {"non_boolean"},
                "production lax-coerces non-boolean strings to bool (no strict-bool "
                "validation, no AdCPSalesAgentError(INVALID_REQUEST)). See docs/test-debt-bdd-strict-markers.md item C4.",
            ),
            (
                "T-UC-004-boundary-daily-breakdown",
                {"string 'true' (non-boolean type)"},
                "production lax-coerces non-boolean strings to bool (no strict-bool "
                "validation). See docs/test-debt-bdd-strict-markers.md item C4.",
            ),
            # account: only the omitted/(field absent) rows
            # pass on every transport. The other rows fail transport-asym-
            # metrically — a2a/mcp/rest never parse/resolve AccountReference
            # at the boundary (resolve_account does account_ref.root on a raw
            # dict → RuntimeError); the invalid-account rows raise Pydantic
            # ValidationError instead of AdCPSalesAgentError(INVALID_REQUEST/
            # ACCOUNT_NOT_FOUND). Substrings are transport-prefixed so only
            # the genuinely-failing rows are marked (impl valid rows pass).
            # GRADUATED (whole entry removed, not emptied): the invalid-oneOf / empty
            # account reference now resolves into a typed AdCPSalesAgentError and reaches
            # the wire as INVALID_REQUEST. NOTE FOR NEXT TIME -- the rows cannot simply be
            # deleted one by one: this matcher reads
            #     if not substrings or any(s in nodeid for s in substrings)
            # so an entry whose set becomes EMPTY xfails EVERY row carrying its tag, and
            # rows that were passing turn into strict xpasses. Thinning this set to zero
            # produced 12 failures, including a row graduated earlier. Remove the entry.
            (
                "T-UC-004-boundary-account",
                {
                    "impl-account_id present + not found",
                    # Valid rows (account exists / single match = "brand + operator
                    # present", incl. the sandbox:true variant) now resolve on a2a/mcp/rest
                    # once their accounts are seeded — removed. a2a invalid rows (both / not found / empty) already
                    # raise AdCPSalesAgentError (wire-drop XPASS, #1417) — removed.
                    # GRADUATED (#1534 merge): mcp-both / mcp-empty-object —
                    # RequestCompatMiddleware normalizes the MCP TypeAdapter oneOf
                    # rejection to the VALIDATION_ERROR envelope; both rows fired
                    # as deterministic strict XPASS on the merged in-network run
                    # — removed.
                    # mcp-account_id present + not found genuinely passes
                    # (ValidationError satisfies 'invalid') — NOT marked.
                },
                "impl does not resolve the account_id-not-found reference into an "
                "AdCPSalesAgentError at the _impl boundary for this row. "
                "See docs/test-debt-bdd-strict-markers.md items C1/C2/C4.",
            ),
            # sampling: sampling_method is NOT a
            # GetMediaBuyDeliveryRequest field — the artifact-sampling feature
            # is entirely unimplemented. Only (omitted)/not_provided genuinely
            # pass; rest silently drops the unknown param so its named-method
            # rows accidentally "pass" (must NOT be marked). impl/a2a/mcp
            # named-method + every unknown_value/systematic row fails.
            (
                "T-UC-004-partition-sampling",
                {
                    "impl-random-random",
                    "impl-stratified",
                    "impl-recent",
                    "impl-failures_only",
                    "impl-unknown_value-systematic",
                    "a2a-random-random",
                    "a2a-stratified",
                    "a2a-recent",
                    "a2a-failures_only",
                    # Graduated: a2a-unknown_value-systematic. An unknown sampling_method
                    # value now rejects on a2a with a typed error on the wire. The set keeps
                    # its other rows, so it stays non-empty -- emptying it would xfail every
                    # row carrying this tag (see the account entry above).
                    "mcp-random-random",
                    "mcp-stratified",
                    "mcp-recent",
                    "mcp-failures_only",
                    "[rest-unknown_value-systematic",
                },
                "sampling_method is unimplemented in get_media_buy_delivery (no schema "
                "field); ValidationError not AdCPSalesAgentError (rest silently drops it). "
                "See docs/test-debt-bdd-strict-markers.md item C4.",
            ),
            (
                "T-UC-004-boundary-sampling",
                {
                    "impl-random (first enum value)",
                    "impl-failures_only (last enum value)",
                    "a2a-random (first enum value)",
                    "a2a-failures_only (last enum value)",
                    # a2a now rejects the unknown sampling_method value via extra=forbid
                    # -> AdCPSalesAgentError (wire-drop confirmed XPASS, #1417) — removed.
                    "mcp-random (first enum value)",
                    "mcp-failures_only (last enum value)",
                    # GRADUATED (#1534 merge): mcp-Unknown-string — the unknown
                    # sampling_method now rejects on the MCP wire with the AdCP
                    # envelope (extra=forbid rejection normalized by
                    # RequestCompatMiddleware, same class as the a2a graduation
                    # above); deterministic strict XPASS on the box slice —
                    # removed. rest still silently drops the unknown param
                    # (row kept).
                    "[rest-Unknown string not in enum",
                },
                "sampling_method is unimplemented in get_media_buy_delivery (no schema "
                "field); ValidationError not AdCPSalesAgentError (rest silently drops it). "
                "See docs/test-debt-bdd-strict-markers.md item C4.",
            ),
            # resolution (#1545): GRADUATED on all transports. The
            # Examples now name error "VALIDATION_ERROR" with suggestion, and the empty
            # media_buy_ids=[] hits the SDK min_length=1 constraint, surfacing as
            # AdCPValidationError(VALIDATION_ERROR)+suggestion on the a2a/mcp/rest wire
            # (empirically verified: a2a/mcp/rest all PASS the named code). The earlier
            # INVALID_REQUEST framing (and the "A2A wraps in RuntimeError" note) were both
            # stale — production emits VALIDATION_ERROR here, not INVALID_REQUEST — so no
            # partition marker remains. (e2e-harness-wiring corroborates: strict XPASS
            # observed on the merged tree 2026-07-09, the merged A2A boundary raises
            # AdCPSalesAgentError on the empty-array reject — adcp_validation_boundary from the
            # #1417 embed — matching the boundary-resolution graduation below. Entry removed.)
            # T-UC-004-boundary-resolution: a2a now raises AdCPSalesAgentError on the empty-array
            # reject (wire-drop confirmed XPASS, #1417); the only remaining
            # transport-aware failure (a2a empty array) is handled below — entry removed
            # here so it does not blanket-xfail every boundary-resolution row.
            # ownership: owner-matches rows pass on all
            # transports. owner-mismatch is the C3 security gap — cross-
            # principal access returns 200+empty instead of MEDIA_BUY_NOT_FOUND.
            (
                "T-UC-004-partition-ownership",
                {"owner_mismatch"},
                "cross-principal access returns 200+empty instead of "
                "AdCPSalesAgentError(MEDIA_BUY_NOT_FOUND). See docs/test-debt-bdd-strict-markers.md item C3.",
            ),
            # boundary-ownership: fully GRADUATED. a2a first (wire-drop XPASS,
            # #1417), then mcp/rest at the #1534 merge — production reports the
            # cross-principal buy as MEDIA_BUY_NOT_FOUND (spec 3.1.1
            # enums/error-code.json; the tenant-scoped repository excludes
            # foreign buys, media_buy_delivery.py not_found_errors) on every
            # wire transport, not the old 200+empty. The mcp row fired as a
            # deterministic strict XPASS on the merged in-network run; entry
            # removed so the boundary grades live. (The stricter
            # PERMISSION_DENIED partition/boundary Examples remain genuinely
            # xfailed via _UC004_PARTITION_SELECTIVE — that expectation gap is
            # separate and still open.)
            # status-filter : all valid single statuses +
            # arrays + (field absent) pass. pending_activation rows fail
            # (Gherkin uses a non-spec MediaBuyStatus — item B1); empty-array /
            # unknown-value "failed" rows raise ValidationError not
            # AdCPSalesAgentError(INVALID_REQUEST) — item C4.
            # partition: impl now genuinely PASSES single_pending (production
            # normalizes the legacy 'pending_activation' label). a2a/mcp/rest
            # still fail on the unknown-value/empty-array C4 normalization.
            # GRADUATED (whole entry removed, not emptied). Both halves of its bundled
            # reason are closed: single_pending's legacy-label normalization was retired
            # earlier, and the empty_array / unknown_value rows now reach the wire as a
            # typed AdCPSalesAgentError on a2a, mcp AND rest. The entry is DELETED rather
            # than left with an empty set, because this matcher reads
            #     if not substrings or any(s in nodeid for s in substrings)
            # so an empty set xfails EVERY row carrying the tag.
            # boundary: pending_activation fails everywhere; the 'failed' /
            # '[] (empty array...)' rows pass on impl/rest (ValidationError
            # satisfies 'invalid') but fail on a2a/mcp — transport-prefixed
            # substrings so only the genuinely-failing rows are marked.
            (
                "T-UC-004-boundary-status-filter",
                {
                    "impl-pending_activation (first enum value)",
                    "a2a-pending_activation (first enum value)",
                    # a2a now raises AdCPSalesAgentError on failed/[] (wire-drop confirmed XPASS,
                    # #1417) — removed.
                    # GRADUATED (#1534 merge): mcp-failed — RequestCompatMiddleware
                    # normalizes the MCP TypeAdapter enum rejection to the
                    # VALIDATION_ERROR envelope; the row fired as a deterministic
                    # strict XPASS on the merged in-network run — removed.
                    "mcp-pending_activation (first enum value)",
                    "[rest-pending_activation (first enum value)",
                },
                "pending_activation: Gherkin value not a valid AdCP MediaBuyStatus "
                "(item B1). See docs/test-debt-bdd-strict-markers.md.",
            ),
            # credentials: FULLY reconciled — the When step
            # now validates the real AdCP reporting_webhook Authentication
            # model (scheme enum + credentials min_length=32). All 40 rows
            # genuinely PASS on all transports; NO strict=True entry needed
            # (same shape as the reconciled date-range valid rows).
        ]
        # e2e_rest items must NOT be marked by this loop. Its row substrings use
        # bare transport prefixes ("[rest-…", not the "[rest-" bracket guard at :402),
        # so a "[rest-…" row substring-matches an "[e2e_rest-…]" nodeid and would stamp
        # a strict=True in-process "impl passes" reason onto e2e_rest items —
        # contradicting the ledger's non-strict policy and, once e2e_rest reaches the
        # real boundary and passes (e.g. INVALID_REQUEST now emitted), turning the pass
        # into a spurious strict-XPASS failure. e2e_rest xfails are owned by the
        # dedicated tripwire blocks (~:1490/:1517) and the ledger collapse. (PR #1420)
        if not is_e2e_rest:
            for tag, substrings, reason in _UC004_GENUINE_XFAIL_ROWS:
                if tag in marker_names and (not substrings or any(s in nodeid for s in substrings)):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
                    break

        # UC-004 boundary scenarios: strict=False because some examples pass.
        # Invalid boundary values SHOULD fail validation but production doesn't validate.
        # Valid boundary values pass through fine.
        # Graduated to transport-aware selective xfail:
        # T-UC-004-boundary-attribution, T-UC-004-boundary-daily-breakdown,
        # T-UC-004-boundary-account, T-UC-004-boundary-status-filter,
        # T-UC-004-boundary-resolution, T-UC-004-boundary-ownership,
        # T-UC-004-boundary-reporting-dims, T-UC-004-boundary-sampling,
        # T-UC-004-boundary-date-range
        _UC004_BOUNDARY_TAGS: set[str] = set()
        # Graduated: T-UC-004-boundary-credentials (transport-aware selective below)
        # Graduated: T-UC-004-boundary-reporting-dims (transport-aware selective below)
        # Graduated: T-UC-004-boundary-sampling (transport-aware selective below)
        # Graduated: T-UC-004-boundary-date-range (transport-aware selective below)
        # Graduated: T-UC-004-boundary-ownership (transport-aware below)
        if marker_names & _UC004_BOUNDARY_TAGS:
            item.add_marker(pytest.mark.xfail(reason="boundary validation partially implemented", strict=False))

        # Graduated: T-UC-004-boundary-credentials — the When now validates the real
        # AdCP reporting_webhook Authentication at the create_media_buy boundary
        # (scheme enum + credentials min_length=32), so all rows pass on all transports.

        # T-UC-004-boundary-ownership. The mcp XPASS this replaces was VACUOUS, so it
        # was NOT graduated -- the step was fixed instead (debt item B3, previously
        # RECONCILED for the partition twin only). when_boundary_ownership sent the
        # Gherkin label as a literal `ownership=` kwarg; that is not a request field, so
        # FastMCP's TypeAdapter rejected it as unrecognized before
        # _get_media_buy_delivery_impl ran, matching `invalid` regardless of what
        # production does about cross-principal access. The old per-transport table
        # below was therefore a table of "which transport rejects an unknown argument",
        # not of ownership enforcement. The When now routes through
        # _dispatch_ownership_partition, the same real identity swap the partition
        # outline uses, so the split is the obligation's: querying as the owner returns
        # the buy on every transport, and querying a non-owned id hits the C3 gap --
        # production answers 200 + empty instead of MEDIA_BUY_NOT_FOUND -- on every
        # transport, exactly like T-UC-004-partition-ownership/owner_mismatch above.
        if "T-UC-004-boundary-ownership" in marker_names and "matches owner" not in nodeid:
            item.add_marker(
                pytest.mark.xfail(
                    reason="cross-principal access returns 200+empty instead of "
                    "AdCPSalesAgentError(MEDIA_BUY_NOT_FOUND). See docs/test-debt-bdd-strict-markers.md item C3.",
                    strict=False,
                )
            )

        # Graduated: T-UC-004-boundary-reporting-dims — "metro but no system" is the
        # only row still genuinely gapped (prose-only spec constraint, no formal
        # validator; separately tracked as C10 in _UC004_GENUINE_XFAIL_ROWS above).
        # "geo without geo_level", "limit=0", "limit negative" also now genuinely
        # reject on mcp/rest (a2a already passed, #1417) — required geo_level /
        # limit>=1 per the pinned v3.1.1 get-media-buy-delivery-request.json, and
        # RequestCompatMiddleware normalizes the ToolError to a two-layer envelope
        # on mcp/rest.
        if "T-UC-004-boundary-reporting-dims" in marker_names:
            _rdim_all_transport_fail = "geo_level=metro but no system" in nodeid
            if _rdim_all_transport_fail:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="reporting_dimensions boundary: validation gaps on some transports", strict=False
                    )
                )
            # Graduated: e2e_rest invalid reporting_dimensions schema violations now
            # return 400 INVALID_REQUEST (the RequestValidationError handler in
            # src/app.py; not a raw 500/empty body), so the wire-envelope assertion
            # handles them.

        # Graduated: T-UC-004-boundary-sampling — "Not provided" passes everywhere;
        # "random"/"failures_only" pass on rest only; "Unknown string" passes on impl only.
        if "T-UC-004-boundary-sampling" in marker_names:
            _samp_not_rest_fail = (
                not is_rest
                and not is_e2e_rest
                and any(s in nodeid for s in ("random (first enum", "failures_only (last enum"))
            )
            # a2a now rejects the unknown value via extra=forbid -> AdCPSalesAgentError (wire-drop
            # confirmed XPASS, #1417); mcp still fails the type check.
            _samp_not_impl_fail = (
                not is_impl and not is_a2a and not is_e2e_rest and "Unknown string not in enum" in nodeid
            )
            if _samp_not_rest_fail or _samp_not_impl_fail:
                # mcp's xpass here is VACUOUS. `sampling_method` is not a real
                # get_media_buy_delivery request field (does not exist in the
                # pinned v3.1.1 schema at all -- it belongs to content-standards
                # native-creative sampling, a different domain).
                # when_boundary_sampling sends it as a raw kwarg, which FastMCP's
                # TypeAdapter rejects as unrecognized before
                # _get_media_buy_delivery_impl runs -- coincidentally matching
                # `invalid` for ANY value, valid or not, so this scenario cannot
                # distinguish "enum rejected" from "field doesn't exist". See
                # docs/test-debt-bdd-strict-markers.md item B4 -- the documented fix
                # is to relocate/delete this scenario family, not graduate rows.
                item.add_marker(
                    pytest.mark.xfail(
                        reason="sampling_method boundary: not implemented on this transport", strict=False
                    )
                )
            # FIXME(#1270): e2e_rest: Docker doesn't validate sampling_method —
            # invalid enum value succeeds instead of failing.
            if is_e2e_rest and "Unknown string not in enum" in nodeid:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: Docker does not validate sampling_method — invalid value succeeds",
                        strict=True,
                    )
                )

        # Graduated: T-UC-004-boundary-date-range. a2a/mcp/rest all accept a valid
        # start_date<end_date pair and omitted dates without error — the shared
        # _get_media_buy_delivery_impl (src/core/tools/media_buy_delivery.py) has
        # no transport-specific date-range branch. Production also validates date
        # range over e2e_rest, rejecting the invalid cases (equals, after).

        # T-UC-004-daterange-end-only over e2e_rest: same Gap G40 (debt C7) as
        # in-process — when only end_date is given, production defaults start to
        # today-30d, not the media buy creation date the Then-step asserts. The
        # _UC004_GENUINE_XFAIL_ROWS loop is gated to in-process only (see :1422),
        # so e2e_rest needs its own strict tripwire. Deterministic: the live
        # server reliably returns today-30d. Retire when Gap G40 is closed.
        if is_e2e_rest and "T-UC-004-daterange-end-only" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="e2e_rest: Gap G40 — start defaults to today-30d, not media buy creation date",
                    strict=True,
                )
            )

        # attribution_window REFERENCE (clean scenario->step->harness path): the Examples
        # name the exact error code (error "VALIDATION_ERROR" — the schema-canonical code
        # for value/enum/range/business-rule violations; reconciled from the earlier
        # INVALID_REQUEST mis-pin per the AdCP graded error-compliance storyboard), the
        # step asserts it on the harness wire envelope. interval=0 / unit=weeks /
        # model=last_click PASS on a2a/mcp/rest (VALIDATION_ERROR).
        # GRADUATED (#1545): the partition "campaign with interval=2"
        # (campaign_interval_not_one) now passes on a2a — the only transport parametrized
        # for that row — because the attribution_window.post_click reaches production and
        # INV-5 fires (VALIDATION_ERROR "interval must be 1 when unit is 'campaign'"), which
        # the Examples now name and the step asserts on the wire. So the former strict=True
        # _aw_partition_campaign leg is dropped; the row passes unmasked. (The old #1462
        # "request path drops post_click" framing was wrong for the wire transports; #1462 is
        # the in-process _impl path, which BDD does not parametrize.)
        # Graduated: T-UC-004-partition-attribution error "INVALID_REQUEST" rows on
        # e2e_rest. The step-binding bug this routed around is FIXED, and the fix is
        # visible at the source: the generic step is now
        # ``parsers.re(r"the Buyer Agent requests delivery metrics with (?P<request_params>\w+=.+)")``
        # (uc004_delivery.py:733), and requiring ``\w+=`` means the JSON-form window
        # ``with attribution_window {"post_click": ...}`` no longer matches it. It binds to
        # the specific step instead, so the window reaches the live server, validation
        # fires, and the rejection assertion the row makes can actually be met -- the pass
        # is explained by real behavior, not by the assertion going vacuous.
        # Verified: bdd_inprocess OK on all in-process transports; these four rows XPASS
        # (strict) on e2e_rest in the in-network full run, which is the only job that
        # grades them. They are NOT listed in tests/bdd/e2e_rest_known_failures.txt, so
        # there is no sibling ledger entry to retire alongside this.
        # (#1545/x18x had already dropped the campaign leg here for the same reason: INV-5
        # fires VALIDATION_ERROR with suggestion on a2a.)

        # Graduated: T-UC-004-boundary-account — transport-aware.
        # "account_id present"/"brand + operator" (valid): fail on mcp/rest only.
        # "both account_id"/"empty object" (invalid): fail on a2a only.
        # "account_id not found" (invalid): fail on impl/a2a only.
        # "omitted": already PASS everywhere.
        if "T-UC-004-boundary-account" in marker_names:
            # a2a now raises AdCPSalesAgentError on invalid-account rows (both / empty / not found)
            # (wire-drop confirmed XPASS, #1417). Valid rows (account exists / single
            # match / sandbox account exists) now pass on mcp/rest once their accounts
            # are seeded — the former "production gaps" mask hid the
            # missing seed. impl still gaps on not-found (impl is not in the default
            # BDD parametrization).
            # mcp's "both account_id"/"empty object" invalid rows also now reject
            # correctly — FastMCP's TypeAdapter validates the account param against
            # the adcp library's AccountReference oneOf (RootModel,
            # additionalProperties:false per branch) BEFORE the tool body runs,
            # normalized to VALIDATION_ERROR via the shared adcp_error_for().
            _acc_notfound_fail = is_impl and "not found" in nodeid
            if _acc_notfound_fail:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="delivery account boundary: production gaps on this transport", strict=False
                    )
                )
            # e2e_rest fully graduated: invalid rows ("not found", "both
            # account_id", "empty object") passed first; the valid rows
            # ("account exists", "single match") followed at the #1417 merge —
            # the jr5b seeded-account Given is realized against the server DB,
            # so the account fixture IS visible now (XPASS innet_140726_1516).

        # --- UC-004 boundary: selective xfail for graduated strong groups ---
        # Only the failing subset gets xfailed; clean-pass examples graduate to PASS.
        _UC004_BOUNDARY_SELECTIVE: list[tuple[str, set[str], str]] = [
            # include_package_daily_breakdown: only non_boolean fails (all transports)
            (
                "T-UC-004-boundary-daily-breakdown",
                {"non-boolean", "non_boolean", "string 'true'"},
                "include_package_daily_breakdown boundary: non-boolean validation not implemented",
            ),
            # Graduated: "buyer_refs only" and "zero resolution" (all 4 transports pass)
            # Graduated: "empty array" passes on impl/mcp/rest (only a2a fails)
            # Graduated: "partial resolution" -- the transport-agnostic _impl
            # (src/core/tools/media_buy_delivery.py) diffs requested media_buy_ids
            # vs. resolved buys and appends an advisory MEDIA_BUY_NOT_FOUND to
            # response.errors[] instead of hard-failing, which is exactly the shape
            # get-media-buy-delivery-response.json#/properties/errors documents
            # (v3.1.1), on all 3 transports.
            # Clean-pass: media_buy_ids only, both provided, neither provided
            # Graduated: status_filter "not in AdCP enum" passes on impl+rest,
            # "empty array, violates" passes on impl+mcp+rest (transport-aware below)
        ]
        for tag, substrings, reason in _UC004_BOUNDARY_SELECTIVE:
            if tag in marker_names:
                if any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                break

        # T-UC-004-boundary-resolution "empty array": a2a now raises AdCPSalesAgentError
        # (wire-drop confirmed XPASS, #1417) — no transport still fails here.
        # T-UC-004-boundary-status-filter: graduated per-transport
        # "not in AdCP enum" (failed): all transports now pass.
        # "empty array, violates" ([]): a2a now passes — no transport still fails
        if "T-UC-004-boundary-status-filter" in marker_names:
            # mcp's "not in AdCP enum" (status_filter="failed") row also now
            # rejects correctly — FastMCP's TypeAdapter validates status_filter
            # against the adcp library's MediaBuyStatus enum before the tool body
            # runs, same mechanism/adcp_error_for() path as the account
            # boundary graduation above.
            # Graduated: e2e_rest invalid status_filter (unknown enum value) now
            # returns 400 INVALID_REQUEST (the RequestValidationError handler in
            # src/app.py; not a raw 500/empty body), so the wire-envelope assertion
            # handles it.
            # adcp 3.12: pending_activation renamed to pending_start — feature file
            # still uses old name, schema rejects it as unknown enum value.
            if "pending_activation" in nodeid or "all 6 statuses" in nodeid:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="adcp 3.12: pending_activation renamed to pending_start — feature file needs update",
                        strict=True,
                    )
                )

        # Graduated: "both provided (priority rule)". #1417 already retired
        # buyer_refs and rewrote _dispatch_resolution
        # (tests/bdd/steps/domain/uc004_delivery.py) to send media_buy_ids +
        # status_filter instead, so the row tests a real, spec-permitted
        # combination, not obsolete content.

        # Graduated: e2e_rest media_buy_resolution "empty array" now returns a
        # structured AdCP error envelope (not a raw 500/empty body), so the
        # wire-envelope assertion handles it.

        # e2e_rest: principal_ownership "differs from owner" — ownership check not enforced
        # through REST layer; test succeeds when it should fail (strict=True xfail).
        if "T-UC-004-boundary-ownership" in marker_names and is_e2e_rest and "differs from owner" in nodeid:
            item.add_marker(
                pytest.mark.xfail(
                    reason="e2e_rest: ownership boundary not enforced through REST — test succeeds unexpectedly",
                    strict=True,
                )
            )

        # e2e_rest: sort_by_metric_not_available — the spend-fallback needs injected
        # by_placement data, but the injector (_inject_placement_data) is in-process
        # mock state invisible to the live server, so the fallback is untestable over
        # e2e_rest (the buyer-facing assertions pass without exercising it). strict=False
        # tolerates the hollow pass; wiring the injector so a2a/mcp/rest genuinely test
        # it is the follow-up.
        if "T-UC-004-dim-sortby-fallback" in marker_names and is_e2e_rest:
            item.add_marker(
                pytest.mark.xfail(
                    reason="e2e_rest: by_placement injection is in-process-only (invisible to live server) — "
                    "sort_by spend-fallback untestable over e2e_rest",
                    strict=False,
                )
            )

        # UC-004 partition scenarios: adcp 3.10 changed schema validation behavior.
        # Partition tests exercise valid/invalid value ranges per field.
        # strict=False: some partition values pass, others fail depending on schema version.
        _UC004_PARTITION_TAGS: set[str] = set()
        # Graduated (all 4 transports pass with strong assertions):
        # T-UC-004-partition-reporting-dims, T-UC-004-partition-attribution,
        # T-UC-004-partition-daily-breakdown, T-UC-004-partition-account,
        # T-UC-004-partition-sampling, T-UC-004-partition-status-filter,
        # T-UC-004-partition-date-range, T-UC-004-partition-resolution,
        # T-UC-004-partition-ownership
        # Graduated: T-UC-004-partition-credentials (transport-aware selective below)
        if marker_names & _UC004_PARTITION_TAGS:
            item.add_marker(
                pytest.mark.xfail(reason="partition validation behavior varies with adcp schema version", strict=False)
            )

        # --- UC-004 partition: selective xfail for error-expecting examples ---
        # FIXME: Graduated partition tags still have invalid-value
        # examples that expect INVALID_REQUEST/ACCOUNT_NOT_FOUND but production
        # doesn't validate. Only xfail the failing subset; valid-value examples pass.
        _UC004_PARTITION_SELECTIVE: list[tuple[str, set[str], str]] = [
            # Graduated: geo_missing_geo_level, limit_zero, limit_negative. The reason here
            # -- "production accepts invalid configs" -- is no longer true of them: they
            # XPASS on a2a, mcp AND rest, so all three now reject the config and answer
            # INVALID_REQUEST with a suggestion, which is what the rows assert. This entry
            # is the non-strict twin of the one in _UC004_GENUINE_XFAIL_ROWS; both listed
            # the same four rows, so leaving this one in place turned the strict
            # graduation into a silent XPASS instead of a pass.
            # geo_metro_missing_system stays: it does not XPASS, so production still
            # accepts it and the reason still holds for that row alone.
            (
                "T-UC-004-partition-reporting-dims",
                {"geo_metro_missing_system"},
                "reporting_dimensions validation not implemented — production accepts invalid configs",
            ),
            # Graduated: T-UC-004-partition-attribution
            # interval_zero/interval_negative/invalid_unit/invalid_model. The
            # generic "with {request_params}" step no longer shadows the specific
            # "with attribution_window {value}" step (the generic step now
            # requires \w+=... key=value form, mutually exclusive with the
            # space-form "attribution_window {json}" step). attribution_window is
            # a real-wire-asserted field (_WIRE_ASSERTED_FIELDS), and all 4 rows
            # pass with the correct VALIDATION_ERROR+suggestion on all 3
            # transports.
            # daily breakdown: production doesn't validate non-boolean values
            (
                "T-UC-004-partition-daily-breakdown",
                {"non_boolean"},
                "include_package_daily_breakdown validation not implemented — production accepts non-boolean",
            ),
            # Graduated: T-UC-004-partition-account. ENTRY DELETED, not thinned — its set
            # named invalid_oneOf_both and empty_object, and with impl sunsetted (#1417)
            # a2a/mcp/rest are the only in-process transports, so all SIX matching rows
            # graduate at once and nothing is left for the entry to mark. (Thinning to an
            # empty set would xfail every row carrying the tag; see the account note in
            # _UC004_GENUINE_XFAIL_ROWS.) The reason -- "raises ValidationError, not
            # AdCPSalesAgentError(INVALID_REQUEST)" -- is disproved by production: the
            # pydantic oneOf/extra_forbidden rejection is translated into a typed
            # AdCPInvalidRequestError, which the boundary frames as INVALID_REQUEST.
            # (This used to cite adcp_validation_boundary inside the builder; that wrapper
            # is gone and the TRANSPORT boundary makes the identical conversion, off the
            # same exception, through the same adcp_error_for. The outcome is unchanged --
            # which is the point -- but the citation would send a reader to a frame that no
            # longer exists.) -- the first code in the pinned
            # v3.1.1 enums/error-code.json, correctable, with a suggestion. The scenario
            # names that exact outcome (error "INVALID_REQUEST" with suggestion) and grades
            # it through TransportResult.assert_wire_error -> assert_envelope_shape on the
            # captured envelope, both mirrored layers, so the pass is not vacuous. The Given
            # and the When run the shared cross-transport path (_dispatch_partition ->
            # dispatch_request) with no per-transport branch. Six deterministic XPASS rows
            # on the serial box slice, 2026-09-02 (534 passed / 484 xfailed / 16 xpassed).
            # account_not_found was never in this set: with the valid siblings seeded,
            # resolution runs and the unseeded id correctly raises ACCOUNT_NOT_FOUND.
            # Graduated: T-UC-004-partition-sampling (transport-aware block below)
            # "not_provided" passes all transports; valid named methods pass on REST only.
            # Graduated: T-UC-004-partition-status-filter. ENTRY DELETED, not thinned — the
            # set named unknown_value and empty_array, and a2a/mcp/rest are the only
            # in-process transports since impl was sunsetted (#1417), so all six matching
            # rows graduate together and nothing is left to mark.
            #
            # unknown_value ("failed") graduated on the evidence as it stood: the reason
            # "production accepts invalid values" is false — the value is not a pinned
            # MediaBuyStatus, the transport boundary (adcp_error_for) converts the
            # pydantic rejection to a typed AdCPInvalidRequestError -- it used to be
            # converted a frame earlier, by adcp_validation_boundary inside the builder;
            # same call, same result -- and the wire carries INVALID_REQUEST +
            # suggestion, exactly what the Example names and what assert_wire_error grades
            # on the captured envelope.
            #
            # empty_array did NOT graduate on its xpass — that xpass was VACUOUS and the
            # step was fixed first. when_request_with_status_filter wrapped the Example
            # cell, sending status_filter=["[]"], so the row rejected as an unknown enum
            # value: a duplicate of its unknown_value sibling, never the minItems
            # obligation its name claims. With the cell now parsed as the array it spells,
            # the row sends status_filter=[] and rejects on the pinned v3.1.1 StatusFilter
            # min-items constraint ("List should have at least 1 item after validation,
            # not 0") — same INVALID_REQUEST on the wire, but now for the reason the row
            # is named for.
            # date range partition GRADUATED (#1545): only [a2a-…] is
            # parametrized for start_equals_end/start_after_end, and a2a now emits
            # VALIDATION_ERROR+suggestion ("Start date must be before end date",
            # media_buy_delivery.py:209-218) for the named Examples — passes unmasked. Entry
            # removed. (mcp/rest are only parametrized on the BOUNDARY counterpart, which
            # stays masked in _UC004_GENUINE_XFAIL_ROWS above.)
            # resolution partition GRADUATED (#1545): empty media_buy_ids=[]
            # hits the SDK min_length=1 constraint -> VALIDATION_ERROR+suggestion on the
            # a2a/mcp/rest wire (all three empirically PASS the named Example). Entry removed.
            # ownership: production doesn't validate principal mismatch
            (
                "T-UC-004-partition-ownership",
                {"owner_mismatch"},
                "ownership validation not implemented — production accepts non-owned media buys",
            ),
        ]
        for tag, substrings, reason in _UC004_PARTITION_SELECTIVE:
            if tag in marker_names:
                if not substrings or any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                break

        # (#1545 review) The generic `{request_params}` step was restricted to
        # key=value form, which un-shadowed the date-range / ownership / resolution
        # partition steps so their params are now genuinely applied. The latent
        # step-plumbing bugs that exposed (labels leaking as bogus request kwargs;
        # a partial-resolution assertion demanding the deliberately-absent id) are
        # fixed in uc004_delivery.py's _dispatch_date_range_partition /
        # _dispatch_ownership_partition / _dispatch_resolution, so these rows are
        # graded rather than deferred. The genuinely-unimplemented rows
        # (start>=end, owner_mismatch, empty_array) remain in _UC004_PARTITION_SELECTIVE.

        # Graduated: T-UC-004-partition-credentials — the When now validates the real
        # AdCP reporting_webhook Authentication at the create_media_buy boundary
        # (scheme enum + credentials min_length=32), so all rows pass on all transports.

        # Graduated: T-UC-004-partition-sampling — "not_provided" passes all transports;
        # valid named methods (random, stratified, recent, failures_only) pass on REST only.
        # Non-REST + named method → still fails; unknown_value → fails on all transports.
        if "T-UC-004-partition-sampling" in marker_names and "not_provided" not in nodeid:
            _samp_named = {"random", "stratified", "recent", "failures_only"}
            _samp_is_named = any(s in nodeid for s in _samp_named)
            if _samp_is_named and (is_rest or is_e2e_rest):
                pass  # REST/e2e_rest + named method → passes, no xfail
            else:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="sampling_method not implemented in delivery _impl or transport wrappers",
                        strict=False,
                    )
                )

        # FIXME: catalog distinct type partition/boundary
        # Production accepts catalogs but never validates duplicate types or catalog_id
        # existence. Valid partitions pass; invalid partitions succeed when they should fail.
        # Graduated (all 4 transports pass with strong assertions):
        # T-UC-002-partition-catalog-distinct-type, T-UC-002-boundary-catalog-distinct-type
        _UC002_CATALOG_TAGS: set[str] = set()
        if marker_names & _UC002_CATALOG_TAGS:
            item.add_marker(
                pytest.mark.xfail(
                    reason="catalog validation not implemented in production — spec-production gap", strict=False
                )
            )

        # --- UC-019: xfails for spec-production gaps ---
        # Graduated (k31s): status_computation active variants, default_status_filter
        # simple variants, status_filter boundary simple variants, inv-150-2/4,
        # inv-151-1, inv-152-1/2/3/5, inv-154-tenant, sandbox-production,
        # snapshot available variants, principal_scoping valid variants.
        _UC019_XFAIL_TAGS: set[str] = {
            # Status filter invalid — all parametrizations still fail.
            # NOTE(ah98 red-step inspection, 2026-07-06): NOT graduatable —
            # with this entry removed the scenario still xfails at the fixture
            # ("No harness wired for None": not env-wired), and its examples
            # assert non-canonical codes (STATUS_FILTER_INVALID_VALUE /
            # STATUS_FILTER_EMPTY — absent from the pinned error-code enum),
            # which the shared-boundary fix will not emit. Reconcile upstream.
            # Suggestion parity for get_media_buys is pinned by
            # tests/integration/test_request_validation_suggestion_parity.py.
            "T-UC-019-partition-status-filter-invalid",
            # Creative approval mapping — not implemented
            "T-UC-019-partition-approval",
            "T-UC-019-partition-approval-invalid",
            "T-UC-019-boundary-approval",
            # Graduated (#1545 review), now wired + passing on the A2A/MCP wire:
            #   inv-150-1 (pre-flight active -> pending_start)
            #   inv-150-3 (post-flight active -> completed)
            # Graduated: T-UC-019-inv-150-5 (status filter no longer blocks by-ID queries)
            "T-UC-019-inv-151-4",
            # inv-153-3/4/5 moved to _UC019_SNAPSHOT_HARNESS_GAP_TAGS (#1721 M4):
            # they were mislabeled here as production gaps but actually fail on the
            # Given (no adapter mock in this harness), never reaching graded behavior.
            # Sandbox mode (response echo) — not implemented
            "T-UC-019-sandbox-happy",
            # Graduated (6szx): T-UC-019-sandbox-validation — BR-RULE-209 INV-7:
            # invalid status_filter on a sandbox account yields a REAL rejection
            # (_resolve_status_filter → AdCPValidationError → VALIDATION_ERROR wire
            # envelope). Given now seeds a real sandbox Account + AgentAccountAccess
            # (was an inert ctx flag); Then steps assert wire-first.
            # Graduated: T-UC-019-partition-principal-invalid identity_missing (impl/a2a/mcp pass)
            # — moved to _UC019_PARAM_XFAIL for selective identity_missing exclusion.
            # Graduated: T-UC-019-ext-a (no-auth get_media_buys)
            # now correctly emits AUTH_MISSING per the v3.1.1 AUTH_MISSING/
            # AUTH_INVALID split — was previously stale on AUTH_TOKEN_INVALID/
            # AUTH_REQUIRED.
            # Extension errors — error code mismatches / not implemented.
            "T-UC-019-ext-b",
            "T-UC-019-ext-c",
            # Graduated (6szx): T-UC-019-ext-d — invalid parameter types are rejected at
            # request construction (GetMediaBuysRequest) and translated at the
            # transport boundary, with field-level details (field="media_buy_ids"),
            # recovery=correctable and a top-level suggestion, on the A2A wire and via
            # the typed exception on the legacy MCP wrapper. Then steps assert wire-first.
            # Graduated (subdl): T-UC-019-ext-e — the xfail reason "feature not yet
            # implemented" was WRONG. The feature IS implemented: media_buy_list.py:107
            # raises AdCPCapabilityNotSupportedError -> UNSUPPORTED_FEATURE / correctable
            # / 422, which is exactly what the pin defines ("A requested feature or field
            # is not supported by this seller"). What actually failed was the scenario
            # demanding the MESSAGE contain "account_id filtering is not yet supported" —
            # an authored sentence that cannot exist, since AdCPSalesAgentError.message is a
            # read-only property returning CODE_TABLE[code].message ("Feature not
            # supported"). Removing that tautology is what un-xfailed it. Then steps are
            # wire-graded via then_fail_with_code (both envelope layers must agree, and
            # a no-wire run raises). Verified xpassing on a2a and mcp — the only
            # transports this module collects; its total absence of [rest] is a
            # module-wide parametrize-time gap filed separately.
            # Transport-agnostic main scenario
            "T-UC-019-main",
        }
        # Snapshot scenarios (main-snapshot, inv-153-3/4/5): given_adapter_supports_reporting /
        # given_adapter_no_reporting assert "adapter" in env.mock, but MediaBuyListEnv
        # (the UC-019 harness) deliberately runs get_media_buys against a real DB with
        # NO adapter mock at all ("list is a pure read" — see the UC-019 harness comment).
        # This is a TEST-HARNESS gap (the snapshot Given can never succeed), not a
        # production behavior gap -- was mislabeled "spec-production gap" (#1721 M4
        # dormancy tripwire caught it: the scenarios fail on the Given, before ever
        # reaching the production code the reason claimed was ungraded).
        _UC019_SNAPSHOT_HARNESS_GAP_TAGS: set[str] = {
            "T-UC-019-main-snapshot",
            "T-UC-019-inv-153-3",
            "T-UC-019-inv-153-4",
            "T-UC-019-inv-153-5",
        }
        if marker_names & _UC019_SNAPSHOT_HARNESS_GAP_TAGS:
            item.add_marker(
                pytest.mark.xfail(
                    reason="UC-019 test-harness gap: MediaBuyListEnv wires no adapter mock "
                    "(get_media_buys list is a pure DB read), so the snapshot Given steps "
                    "(given_adapter_supports_reporting / given_adapter_no_reporting) cannot "
                    "configure anything and fail before reaching the graded behavior — FIXME",
                    strict=False,
                )
            )
        elif marker_names & _UC019_XFAIL_TAGS:
            item.add_marker(
                pytest.mark.xfail(
                    reason="UC-019 spec-production gap — feature not yet implemented",
                    strict=False,
                )
            )

        # --- UC-019: selective boundary xfails for un-implemented sub-features ---
        # These scenario outlines are mostly graduated; only the rows exercising a
        # not-yet-implemented sub-feature are xfailed. All are pre-existing gaps
        # unrelated to this PR's status-taxonomy work.
        _UC019_BOUNDARY_SELECTIVE: list[tuple[str, set[str], str]] = [
            # Invalid status_filter VALUES need a dedicated STATUS_FILTER_INVALID_VALUE
            # code; production raises the generic VALIDATION_ERROR instead.
            (
                "T-UC-019-boundary-status-filter",
                {"pending_activation", "expired"},
                "status_filter value validation emits VALIDATION_ERROR, not STATUS_FILTER_INVALID_VALUE (unimplemented)",
            ),
            # Sandbox echo (sandbox=true/false in the response) is not implemented;
            # only the production-absent row is graded.
            (
                "T-UC-019-boundary-sandbox",
                {"sandbox account", "explicit production"},
                "sandbox response echo not implemented (BR-RULE-209)",
            ),
        ]
        for tag, substrings, reason in _UC019_BOUNDARY_SELECTIVE:
            if tag in marker_names and any(s in nodeid for s in substrings):
                item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                break

        # --- UC-019: principal_id=null/empty/ghost boundary — unreachable via HTTP ---
        # BR-RULE-154 INV-3 tests defensive behavior when _impl receives a broken
        # identity (principal_id null/empty/not-found). This can't happen through
        # HTTP: a valid token always resolves to a real principal; an invalid token
        # gets rejected by auth middleware before _impl runs. These scenarios are
        # only testable at the _impl level (impl/a2a/mcp pass the identity directly).
        if (is_rest or is_e2e_rest) and "T-UC-019-boundary-principal" in marker_names:
            if any(
                s in nodeid
                for s in (
                    "principal_id is null",
                    "principal_id is empty string",
                    "principal_id not in registry",
                )
            ):
                item.add_marker(
                    pytest.mark.xfail(
                        reason="HTTP transport: principal_id=null/empty/ghost is unreachable — "
                        "valid token always resolves to a real principal; invalid token "
                        "rejected by auth middleware before _impl. Test only valid at _impl level.",
                        strict=True,
                    )
                )

        # --- UC-019: HTTP transport xfails for auth suggestion mismatch ---
        # Graduated on `rest`: the reason below -- a REST-only
        # suggestion string -- cannot be true any more. Suggestions derive from
        # CODE_TABLE[code], one source for every transport, so no transport can
        # carry a different one. Verified xpassing on rest
        # once UC-019 regained REST parametrization.
        #
        # e2e_rest STAYS routed: it dispatches real HTTP to the live stack, which
        # this local run cannot exercise, so graduating it here would be a claim
        # I have not tested. Narrowed rather than removed.
        if is_e2e_rest and "T-UC-019-ext-a" in marker_names:
            item.add_marker(
                pytest.mark.xfail(
                    reason="HTTP transport: auth error suggestion says 'authenticate' not 'authentication' — spec-production gap",
                    strict=False,
                )
            )
        if (is_rest or is_e2e_rest) and "T-UC-019-partition-principal-invalid" in marker_names:
            if "identity_missing" in nodeid:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="HTTP transport: auth error suggestion says 'authenticate' not 'authentication' — spec-production gap",
                        strict=False,
                    )
                )

        # --- UC-019: parametrization-specific xfails for partially-passing scenarios ---
        # These scenario outlines have some parametrizations that pass (graduated)
        # and some that still fail. Only the failing variants are xfailed.
        _UC019_PARAM_XFAIL: list[tuple[str, set[str], str]] = [
            # Graduated: T-UC-019-partition-status pre_flight/post_flight
            # (status filter no longer blocks by-ID queries)
            # Graduated: T-UC-019-boundary-status day before/day after
            # (status filter no longer blocks by-ID queries)
            # Graduated (#1545 review): T-UC-019-partition-status-filter
            # multiple_statuses / all_statuses — multi-status filtering works on the
            # wire once status_filter is coerced to the MediaBuyStatus enum and the
            # scenario pins its clock. The remaining status-filter gaps are the
            # value/empty VALIDATION rows below, not the mapping.
            # Status filter boundary: STATUS_FILTER_EMPTY (empty array) is not a
            # dedicated code yet (the value-validation rows are handled by
            # _UC019_BOUNDARY_SELECTIVE above). "all seven" now grades and passes.
            (
                "T-UC-019-boundary-status-filter",
                {"empty array"},
                "STATUS_FILTER_EMPTY not implemented — empty array returns empty success, not an error",
            ),
            # Snapshot: not-requested variant fails (include_snapshot=false path)
            (
                "T-UC-019-partition-snapshot",
                {"snapshot_not_requested"},
                "UC-019: snapshot_not_requested path not implemented",
            ),
            # Snapshot boundary: omitted/false/mixed variants fail
            (
                "T-UC-019-boundary-snapshot",
                {"include_snapshot omitted", "include_snapshot explicitly false", "mixed"},
                "UC-019: snapshot boundary omitted/false/mixed paths not implemented",
            ),
            # Graduated: identity_missing (impl/a2a/mcp) — only missing_principal_id
            # and principal_not_found still fail.
            (
                "T-UC-019-partition-principal-invalid",
                {"missing_principal_id", "principal_not_found"},
                "UC-019: principal_id missing/not-found not implemented",
            ),
        ]
        if any(t.startswith("T-UC-019") for t in marker_names):
            for tag, substrings, reason in _UC019_PARAM_XFAIL:
                if tag in marker_names and any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
                    break

        # --- UC-019: e2e_rest xfails for Givens that seed the SUITE db ---
        # UC-019 regained REST parametrization when get_media_buys got a REST
        # route. That correctly enabled `rest`, and it also
        # enabled `e2e_rest`, which is a different proposition: e2e_rest sends
        # real HTTP to the LIVE server, and the server reads its OWN database.
        #
        # Every UC-019 Given seeds through MediaBuyFactory into the harness
        # session -- the step file contains no realize_e2e call at all -- so on
        # e2e_rest the rows land in the suite DB while the request is answered
        # from the server's, and the buys are simply not there. It presents as
        # "Filter 'active' returned no media buys" and "got IDs: []", which reads
        # like a filtering bug and is not one.
        #
        # Routed rather than dropped from parametrization: an xfail is visible to
        # the escape-hatch detectors in
        # test_architecture_e2e_rest_escape_hatches.py, and a parametrize-time
        # exclusion is not -- that invisibility is exactly what hid UC-019's
        # missing REST coverage in the first place. Graduating these needs the
        # Givens seeding through realize_e2e (a recorded gap separately), not
        # a change to production.
        # (folded into the existing UC-019 e2e_rest block below rather than
        # opening a second one on the same condition -- one guard, several
        # reasons, and no new entry in EXPECTED_XFAIL_ROUTES.)
        _UC019_E2E_SUITE_DB_SEED_TAGS: set[str] = {
            "T-UC-019-partition-status-filter",
            "T-UC-019-boundary-status-filter",
            "T-UC-019-inv-150-1",
            "T-UC-019-inv-150-11",
        }

        # --- UC-019: e2e_rest xfails for datetime-mock-dependent tests ---
        # These scenarios use `And today is "<date>"` which patches datetime
        # in-process. The patch has no effect on Docker — real datetime.now()
        # is used, so status assertions fail.
        if is_e2e_rest and any(t.startswith("T-UC-019") for t in marker_names):
            _UC019_E2E_DATETIME_TAGS: set[str] = {
                "T-UC-019-partition-status",
                "T-UC-019-boundary-status",
                "T-UC-019-inv-150-2",
                "T-UC-019-inv-150-4",
                "T-UC-019-inv-150-5",
                # Default filter test creates flight dates relative to mock_today
                # (default 2026-03-15), making both buys "completed" on real date.
                "T-UC-019-inv-151-1",
            }
            _UC019_E2E_MOCK_TAGS: set[str] = {
                # Adapter mock (get_adapter patch) has no effect in Docker.
                "T-UC-019-partition-snapshot",
                "T-UC-019-boundary-snapshot",
            }
            # Graduated e2e_rest examples that pass despite datetime/mock concern:
            # These variants have expected status=completed, which matches the
            # real date (all flight dates are in the past).
            _UC019_E2E_DT_GRADUATED = {
                ("T-UC-019-partition-status", "post_flight"),
                ("T-UC-019-boundary-status", "day after end_date"),
                ("T-UC-019-boundary-status", "start_date equals end_date and today is day after"),
            }
            _dt_graduated = any(tag in marker_names and substr in nodeid for tag, substr in _UC019_E2E_DT_GRADUATED)
            _inv150_5_graduated = "T-UC-019-inv-150-5" in marker_names  # all examples pass
            if marker_names & _UC019_E2E_DATETIME_TAGS and not _dt_graduated and not _inv150_5_graduated:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: datetime.now() mock has no effect in Docker — status computed from real date",
                        strict=False,
                    )
                )
            if marker_names & _UC019_E2E_SUITE_DB_SEED_TAGS:
                item.add_marker(
                    pytest.mark.xfail(
                        reason=(
                            "e2e_rest: UC-019 Givens seed via MediaBuyFactory into the suite DB; "
                            "the live server reads its own DB, so the seeded buys are invisible. "
                            "Needs realize_e2e seeding, not a production change."
                        ),
                        strict=False,
                    )
                )
            _UC019_E2E_MOCK_GRADUATED = {
                ("T-UC-019-partition-snapshot", "supported_but_unavailable"),
                # Only "snapshot null" passes on e2e_rest: Docker's mock adapter
                # has no test media buy data, so get_packages_snapshot returns None,
                # and production maps that to SNAPSHOT_TEMPORARILY_UNAVAILABLE —
                # matching the expected outcome. Other variants FAIL because:
                # - "snapshot returned"/"all packages" expect real snapshot data
                # - "does not support" expects UNSUPPORTED but mock says supported=True
                ("T-UC-019-boundary-snapshot", "snapshot null"),
            }
            _mock_graduated = any(tag in marker_names and substr in nodeid for tag, substr in _UC019_E2E_MOCK_GRADUATED)
            if marker_names & _UC019_E2E_MOCK_TAGS and not _mock_graduated:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: adapter mock has no effect in Docker — snapshot data not controllable",
                        strict=False,
                    )
                )
            # Un-graduated: T-UC-019-inv-154-tenant returns empty response on e2e_rest
            # because in-process fixture data doesn't populate Docker DB.
            if "T-UC-019-inv-154-tenant" in marker_names:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: cross-principal isolation test returns empty set — "
                        "in-process fixtures don't populate Docker DB",
                        strict=False,
                    )
                )
            # Graduated: T-UC-019-inv-152-1/2/5 (: creative approval data seeded)
            # — only in-process transports graduated; e2e_rest still fails (below).

            # principal_scoping_boundary error cases are excluded on e2e_rest
            # (handled by the REST+e2e_rest block below, outside this if-block).

            # Graduated: T-UC-019-inv-152-1, T-UC-019-inv-152-2, T-UC-019-inv-152-5
            # (: creative approval data now visible to e2e_rest Docker)

        # --- UC-026: xfails for spec-production gaps ---
        # Transport wiring done (a3xo: MediaBuyDualEnv routes updates correctly).
        # Remaining failures are production-level: AffectedPackage lacks full state,
        # keyword targeting ops not implemented, error codes/suggestions missing.
        # FIXME: UC-026 production gaps in update response and validation.
        _UC026_XFAIL_TAGS: set[str] = {
            # Graduated: T-UC-026-main-explicit-formats (qq6f: format_ids now echoed)
            # Full-config: optimization_goals missing `kind`, targeting_overlay.audiences extra_forbidden
            "T-UC-026-main-full-config",
            # Update alt-flows: AffectedPackage lacks budget/targeting_overlay/format_ids;
            # keyword_targets_add/remove and negative_keywords_add/remove not implemented
            "T-UC-026-alt-update",
            "T-UC-026-alt-pause",
            "T-UC-026-alt-resume",
            "T-UC-026-alt-keyword-add",
            "T-UC-026-alt-keyword-upsert",
            "T-UC-026-alt-keyword-remove",
            "T-UC-026-alt-keyword-remove-noop",
            "T-UC-026-alt-negative-keyword-add",
            "T-UC-026-alt-negative-keyword-remove-noop",
            "T-UC-026-alt-dedup",
            # Graduated: T-UC-026-alt-dedup-crossbuy (all 4 transports pass)
            # Extension error scenarios — error codes/suggestions not implemented
            # Graduated: T-UC-026-ext-a (all 4 transports pass)
            "T-UC-026-ext-b",
            "T-UC-026-ext-c",
            "T-UC-026-ext-d",
            "T-UC-026-ext-e",
            "T-UC-026-ext-f",
            "T-UC-026-ext-g-product",
            "T-UC-026-ext-g-format",
            "T-UC-026-ext-g-pricing",
            "T-UC-026-ext-h-keyword",
            "T-UC-026-ext-h-negative",
            "T-UC-026-ext-h-cross-ok",
            "T-UC-026-ext-h-cross-reverse",
            "T-UC-026-ext-i",
            # Invariant scenarios — production validation gaps
            # Graduated: T-UC-026-inv-194-1 (all 4 transports pass)
            "T-UC-026-inv-194-2",
            "T-UC-026-inv-195-1",
            "T-UC-026-inv-195-2",
            # Graduated: T-UC-026-inv-195-3 (rczc: bid_price ceiling semantics pass all 4 transports)
            # Graduated: T-UC-026-inv-195-4 (rczc: bid_price exact semantics pass all 4 transports)
            # Graduated: T-UC-026-inv-196-3 (all 4 transports pass)
            "T-UC-026-inv-197-3",
            "T-UC-026-inv-197-4",
            "T-UC-026-inv-198-4",
            "T-UC-026-inv-199-3",
            "T-UC-026-inv-199-4",
            # Graduated: T-UC-026-inv-200-1 (all 4 transports pass)
            "T-UC-026-inv-200-2",
            "T-UC-026-inv-201-1",
            "T-UC-026-inv-201-2",
            "T-UC-026-inv-201-3",
            "T-UC-026-inv-201-4",
            "T-UC-026-inv-201-5",
            # Graduated: T-UC-026-inv-089-2 (t8iq: catalogs now echoed, default pkg fields added)
            # Graduated: T-UC-026-inv-089-3 (all 4 transports pass)
            # Graduated to _UC026_PARTITION_SELECTIVE (x2l0): keyword boundary/partition
            # tags now mostly pass — only REST update dispatch + specific cross-transport
            # validation gaps remain. Selective xfail handles the narrower failure set.
        }
        if marker_names & _UC026_XFAIL_TAGS:
            item.add_marker(
                pytest.mark.xfail(
                    reason="UC-026 spec-production gap — AffectedPackage lacks full state / "
                    "keyword ops not implemented / error codes missing",
                    strict=False,
                )
            )

        # --- UC-026 partition/boundary: selective xfail for graduated tags ---
        # FIXME: Remaining failures are production-level gaps.
        # x2l0: narrowed from set() (all-fail) after a3xo MediaBuyDualEnv wiring
        # graduated most partition/boundary examples. Two failure patterns remain:
        #   1. REST update dispatch: REST success-path update tests fail (error-path
        #      tests and create-path tests pass because validation catches them first)
        #   2. Cross-transport production gaps: conflict_with_overlay validation,
        #      creative_assignments/optimization_goals replacement, empty keyword
        #      validation not implemented
        _UC026_PARTITION_SELECTIVE: list[tuple[str, set[str], str]] = [
            # budget=0 rejected with BUDGET_TOO_LOW — spec says 0 is valid
            (
                "T-UC-026-partition-required-fields",
                {"budget_zero"},
                "production rejects budget=0 with BUDGET_TOO_LOW — spec allows zero budget",
            ),
            (
                "T-UC-026-boundary-required-fields",
                {"budget = 0"},
                "production rejects budget=0 with BUDGET_TOO_LOW — spec allows zero budget",
            ),
            # Graduated: T-UC-026-partition-format-ids (all 4 transports pass after a3xo)
            # max_bid validation: production requires bid_price for auction-based pricing
            (
                "T-UC-026-partition-pricing-option",
                {"valid_with_max_bid"},
                "max_bid pricing validation rejects valid ceiling semantics — spec-production gap",
            ),
            # FIXME: pricing option not-found / wrong-product returns
            # 'validation_error' instead of AdCP-spec 'INVALID_REQUEST'.
            (
                "T-UC-026-partition-pricing-option",
                {"pricing_option_not_found", "pricing_option_wrong_product"},
                "Production returns 'validation_error' instead of AdCP-spec 'INVALID_REQUEST' — "
                "AdCPValidationError caught and re-raised as plain ValueError, stripping error code",
            ),
            # Immutable: only REST success-path update tests fail (error tests pass)
            (
                "T-UC-026-partition-immutable",
                {"[rest-update_mutable_only", "[rest-no_immutable_fields_present"},
                "REST update dispatch not wired for partition immutable success tests",
            ),
            (
                "T-UC-026-boundary-immutable",
                {"[rest-update with only mutable"},
                "REST update dispatch not wired for boundary immutable success tests",
            ),
            # Keyword add partition: only REST success-path tests fail
            (
                "T-UC-026-partition-keyword-add",
                {
                    "[rest-new_keyword",
                    "[rest-existing_keyword_update_bid",
                    "[rest-mixed_new_and_update",
                    "[rest-same_keyword_different_match",
                },
                "REST update dispatch not wired for partition keyword-add success tests",
            ),
            # Keyword remove partition: only REST success-path tests fail
            (
                "T-UC-026-partition-keyword-remove",
                {
                    "[rest-remove_existing_pair",
                    "[rest-remove_nonexistent_pair",
                    "[rest-remove_all_keywords",
                    "[rest-mixed_existing_and_nonexistent",
                },
                "REST update dispatch not wired for partition keyword-remove success tests",
            ),
            # Keyword boundary add: empty keyword string on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-boundary-keyword-add",
                {
                    "impl-empty keyword string",
                    "a2a-empty keyword string",
                    "mcp-empty keyword string",
                    "[rest-single new keyword target",
                    "[rest-existing (keyword, match_type) pair",
                    "[rest-same keyword with broad and exact",
                    "[rest-bid_price = 0",
                },
                "empty keyword validation not implemented / REST update not wired",
            ),
            # Keyword boundary remove: empty keyword string on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-boundary-keyword-remove",
                {
                    "impl-empty keyword string",
                    "a2a-empty keyword string",
                    "mcp-empty keyword string",
                    "[rest-remove single existing",
                    "[rest-remove non-existent pair",
                    "[rest-remove all keyword targets",
                    "[rest-mix of existing and non-existent",
                },
                "empty keyword validation not implemented / REST update not wired",
            ),
            # Keyword shared partition: conflict_with_overlay on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-partition-kw-add-shared",
                {
                    "impl-conflict_with_overlay",
                    "a2a-conflict_with_overlay",
                    "mcp-conflict_with_overlay",
                    "[rest-typical_add",
                    "[rest-add_with_bid_price",
                    "[rest-add_without_bid_price",
                    "[rest-all_match_types",
                    "[rest-boundary_min_array",
                    "[rest-boundary_min_keyword",
                    "[rest-cross_dimension_valid",
                    "[rest-upsert_existing",
                    "[rest-zero_bid_price",
                },
                "conflict_with_overlay not implemented / REST update not wired",
            ),
            (
                "T-UC-026-partition-kw-remove-shared",
                {
                    "impl-conflict_with_overlay",
                    "a2a-conflict_with_overlay",
                    "mcp-conflict_with_overlay",
                    "[rest-typical_remove",
                    "[rest-all_match_types",
                    "[rest-boundary_min_array",
                    "[rest-boundary_min_keyword",
                    "[rest-cross_dimension_valid",
                    "[rest-remove_nonexistent",
                },
                "conflict_with_overlay not implemented / REST update not wired",
            ),
            # Keyword shared boundary: overlay conflict on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-boundary-kw-add-shared",
                {
                    "impl-keyword_targets_add WITH targeting_overlay.keyword_targets-error",
                    "a2a-keyword_targets_add WITH targeting_overlay.keyword_targets-error",
                    "mcp-keyword_targets_add WITH targeting_overlay.keyword_targets-error",
                    "[rest-array length 1",
                    "[rest-keyword length 1",
                    "[rest-keyword_targets_add WITH targeting_overlay.negative_keywords",
                    "[rest-keyword_targets_add WITHOUT",
                    "[rest-match_type = 'broad'",
                    "[rest-match_type = 'exact'",
                    "[rest-match_type = 'phrase'",
                },
                "overlay conflict validation not implemented / REST update not wired",
            ),
            (
                "T-UC-026-boundary-kw-remove-shared",
                {
                    "impl-keyword_targets_remove WITH targeting_overlay.keyword_targets-error",
                    "a2a-keyword_targets_remove WITH targeting_overlay.keyword_targets-error",
                    "mcp-keyword_targets_remove WITH targeting_overlay.keyword_targets-error",
                    "[rest-array length 1",
                    "[rest-keyword length 1",
                    "[rest-keyword_targets_remove WITHOUT",
                    "[rest-match_type = 'broad'",
                    "[rest-match_type = 'exact'",
                    "[rest-match_type = 'phrase'",
                    "[rest-remove pair that does NOT exist",
                    "[rest-remove pair that exists",
                },
                "overlay conflict validation not implemented / REST update not wired",
            ),
            # Negative keyword partition: conflict_with_overlay on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-partition-neg-kw-add",
                {
                    "impl-conflict_with_overlay",
                    "a2a-conflict_with_overlay",
                    "mcp-conflict_with_overlay",
                    "[rest-typical_add",
                    "[rest-add_duplicate",
                    "[rest-all_match_types",
                    "[rest-boundary_min_array",
                    "[rest-boundary_min_keyword",
                    "[rest-cross_dimension_valid",
                },
                "conflict_with_overlay not implemented / REST update not wired",
            ),
            (
                "T-UC-026-partition-neg-kw-remove",
                {
                    "impl-conflict_with_overlay",
                    "a2a-conflict_with_overlay",
                    "mcp-conflict_with_overlay",
                    "[rest-typical_remove",
                    "[rest-all_match_types",
                    "[rest-boundary_min_array",
                    "[rest-boundary_min_keyword",
                    "[rest-cross_dimension_valid",
                    "[rest-remove_nonexistent",
                },
                "conflict_with_overlay not implemented / REST update not wired",
            ),
            # Negative keyword boundary: overlay conflict on impl/a2a/mcp +
            # REST success-path tests fail
            (
                "T-UC-026-boundary-neg-kw-add",
                {
                    "impl-negative_keywords_add WITH targeting_overlay.negative_keywords-error",
                    "a2a-negative_keywords_add WITH targeting_overlay.negative_keywords-error",
                    "mcp-negative_keywords_add WITH targeting_overlay.negative_keywords-error",
                    "[rest-negative_keywords_add WITHOUT",
                    "[rest-negative_keywords_add WITH targeting_overlay.keyword_targets",
                    "[rest-add pair that already exists",
                    "[rest-array length 1",
                    "[rest-keyword length 1",
                    "[rest-match_type = 'broad'",
                    "[rest-match_type = 'exact'",
                    "[rest-match_type = 'phrase'",
                },
                "overlay conflict validation not implemented / REST update not wired",
            ),
            (
                "T-UC-026-boundary-neg-kw-remove",
                {
                    "impl-negative_keywords_remove WITH targeting_overlay.negative_keywords-error",
                    "a2a-negative_keywords_remove WITH targeting_overlay.negative_keywords-error",
                    "mcp-negative_keywords_remove WITH targeting_overlay.negative_keywords-error",
                    "[rest-negative_keywords_remove WITHOUT",
                    "[rest-array length 1",
                    "[rest-keyword length 1",
                    "[rest-match_type = 'broad'",
                    "[rest-match_type = 'exact'",
                    "[rest-match_type = 'phrase'",
                    "[rest-remove pair that does NOT exist",
                    "[rest-remove pair that exists",
                },
                "overlay conflict validation not implemented / REST update not wired",
            ),
            # Paused: only REST update-path tests fail (create-path passes)
            (
                "T-UC-026-partition-paused",
                {"[rest-pause_on_update", "[rest-resume_on_update"},
                "REST update dispatch not wired for partition paused update tests",
            ),
            # d09y: boundary scenarios exposing real production gaps after step-parser fix.
            (
                "T-UC-026-boundary-pricing-option",
                {"empty string", "different product", "max_bid=true", "not in product", "matches last entry"},
                "pricing_option validation returns 'validation_error' instead of AdCP 'INVALID_REQUEST' / "
                "max_bid pricing requires bid_price / last-entry pricing_option rejects valid id — spec-production gap",
            ),
            # Paused boundary: only REST update-path tests fail (create-path passes)
            (
                "T-UC-026-boundary-paused",
                {
                    "[rest-paused=false on update",
                    "[rest-paused=true on update",
                    "[rest-paused=true on already-paused",
                },
                "REST update dispatch not wired for boundary paused update tests",
            ),
            # Replacement: REST all tests fail (update dispatch) +
            # creative_assignments/optimization_goals on impl/a2a/mcp
            (
                "T-UC-026-partition-replacement",
                {
                    "creative_assignments",
                    "optimization_goals",
                    "[rest-omit_array_fields",
                    "[rest-replace_catalogs",
                    "[rest-replace_targeting_overlay",
                },
                "creative_assignments/optimization_goals replacement not implemented / REST update not wired",
            ),
            (
                "T-UC-026-boundary-replacement",
                {
                    "creative_assignments",
                    "optimization_goals",
                    "[rest-all array fields omitted",
                    "[rest-catalogs provided",
                    "[rest-only scalar fields updated",
                    "[rest-targeting_overlay replacement",
                },
                "creative_assignments/optimization_goals replacement not implemented / REST update not wired",
            ),
        ]
        for tag, substrings, reason in _UC026_PARTITION_SELECTIVE:
            if tag in marker_names:
                if not substrings or any(s in nodeid for s in substrings):
                    item.add_marker(pytest.mark.xfail(reason=reason, strict=False))

        # --- UC-011: xfails for spec-production gaps ---
        # FIXME: Production doesn't implement these UC-011 features.
        # Graduated: T-UC-011-list-status-filter payment_required (all 4 transports pass — status now mapped)
        # Graduated: T-UC-011-ext-g-echo list_accounts (all 4 transports pass — context echo implemented)

        # Graduated: no-token/no-principal scenarios now pass after Gherkin
        # correction to AUTH_REQUIRED (commit 13b4ca8d). Production returns
        # AUTH_REQUIRED on rest/e2e_rest, matching the corrected Gherkin.
        # Graduated: expired-token also passes — AUTH_REQUIRED matches.

        # T-UC-011-ext-g-echo-error: impl passes (AdCPSalesAgentError carries context=req.context);
        # a2a/mcp/rest xfail+note via the context-echo Then step (pytest.xfail) because the
        # wire error envelope does not echo context — #1417 / D2. No marker here.
        # Graduated: T-UC-011-sync-missing-brand (all 4 transports pass — ValidationError now structured)
        # Graduated: T-UC-011-sync-missing-operator (all 4 transports pass — ValidationError now structured)
        # Graduated: T-UC-011-ext-f-scoped (all 4 transports now pass — deactivation scoping works on a2a)

        # --- Entity marker auto-application based on BDD tags ---
        # BDD tests don't have entity keywords in filenames; instead they
        # use tags like T-UC-004-* (delivery) and T-UC-005-* (creative).
        if any(t.startswith("T-UC-002") for t in marker_names):
            item.add_marker(pytest.mark.media_buy)
        if any(t.startswith("T-UC-006") for t in marker_names):
            item.add_marker(pytest.mark.creative)
        if any(t.startswith("T-UC-004") for t in marker_names):
            item.add_marker(pytest.mark.delivery)
        if any(t.startswith("T-UC-005") for t in marker_names):
            item.add_marker(pytest.mark.creative)
        if any(t.startswith("T-UC-026") for t in marker_names):
            item.add_marker(pytest.mark.media_buy)
        if any(t.startswith(_ADMIN_TAG_PREFIX) for t in marker_names):
            item.add_marker(pytest.mark.admin)

        # ── E2E_REST ledger + non-strict policy ──────────────────────
        # The e2e_rest transport dispatches over real HTTP to a separate server,
        # so scenarios relying on in-process mock injection can't pass. xfail the
        # known ones (ledger) as non-strict — e2e is environment-dependent, so a
        # ledger xpass must not fail CI. Authored strict=True markers (the #1270
        # validation tripwires at ~1475/~1502) are PRESERVED by the collapse
        # below, so a real production fix still surfaces as a strict xpass.
        if is_e2e_rest:
            if nodeid in _E2E_REST_KNOWN_FAILURES:
                item.add_marker(
                    pytest.mark.xfail(
                        reason="e2e_rest: mock-incompatible scenario (tests/bdd/e2e_rest_known_failures.txt)",
                        strict=False,
                    )
                )
            # Collapse the e2e_rest xfail markers into ONE, but PRESERVE authored
            # strictness: if any source marker is strict=True (the #1270 validation
            # tripwires at ~1475/~1502), the collapsed marker stays strict so a
            # production fix surfaces as a strict xpass instead of being silently
            # swallowed. Ledger-only items carry only non-strict markers, so they
            # stay non-strict — an environment-dependent xpass must not fail CI.
            xfails = [m for m in item.own_markers if m.name == "xfail"]
            if xfails:
                strict = next((m for m in xfails if m.kwargs.get("strict", False)), None)
                chosen = strict or xfails[0]
                item.own_markers = [m for m in item.own_markers if m.name != "xfail"]
                item.add_marker(
                    pytest.mark.xfail(
                        reason=chosen.kwargs.get("reason", "e2e_rest xfail"),
                        strict=strict is not None,
                    )
                )

    # ── Single-transport optimization for strict xfails ──────────────
    # Scenarios that xfail(strict=True) waste runtime running the same failure
    # path on every transport. Keep one canonical transport running (so the
    # xfail still proves out and an xpass is still caught when production catches
    # up) and deselect the redundant ones.
    #
    # That rationale holds only when the failure IS transport-independent. It is
    # not always: an obligation each transport enforces separately fails three
    # times for three reasons, and each has to xpass on its own when production
    # catches up — deselecting two of them would grade a cross-transport MUST on
    # one transport and call it covered.
    #
    # So the exemption is keyed on the xfail reason declaring `scope=per-transport`,
    # not on a list of node ids. A node list is an allowlist under another name and
    # rots the moment someone adds a row; a declared property is inherited by every
    # future row that carries it. See the cause taxonomy the UC-003 revision rows
    # use above (`cause=... scope=... ref=...`).
    # IMPL was dropped from the BDD default parametrization (#1417), so
    # a2a is now the canonical transport that always runs; mcp/rest are the
    # redundant transports deselected when the scenario carries a strict xfail.
    # (Previously impl was canonical; keeping a2a preserves the "still xfail on
    # wire, not deselected-to-nothing" guarantee for the impl-exclusive ledger.)
    #
    # Opt out: set BDD_ALL_TRANSPORTS=1 to run everything (for full runs).
    if not os.environ.get("BDD_ALL_TRANSPORTS"):
        # With IMPL sunsetted there is NO [impl] variant — deselecting every
        # strict-xfail wire variant removes the scenario entirely and loses the
        # xpass tripwire. Keep ONE wire representative per scenario.
        #
        # UC-010 opt-in retained for scenarios that want an mcp/rest
        # representative even when a2a ALSO carries the strict marker (pure
        # runtime-reduction opt-out, not a correctness requirement — see the
        # a2a-strict-marker check below for the correctness half).
        _REPRESENTATIVE_UC_PREFIXES = ("T-UC-010-",)
        _transport_param = re.compile(r"^(?P<head>.*?\[)(?:impl|a2a|mcp|rest)(?P<tail>[-\]].*)$")

        def _scenario_base(nodeid: str) -> str | None:
            match = _transport_param.match(nodeid)
            return f"{match.group('head')}{match.group('tail')}" if match else None

        impl_bases = {
            base for base in (_scenario_base(i.nodeid) for i in items if "[impl" in i.nodeid) if base is not None
        }
        # The kept a2a variant is NOT always the one carrying
        # the strict-xfail marker — several UC-004 markers are deliberately
        # transport-selective (applied to mcp/rest only because a2a already
        # validates). Deselecting every mcp/rest sibling in that case removes
        # the ONLY items that could ever XPASS(strict), killing the tripwire
        # for that scenario. Only treat mcp/rest as redundant when the a2a
        # sibling ALSO carries an equivalent strict marker — otherwise keep
        # one mcp/rest representative, same as the UC-010 opt-in.
        a2a_strict_bases = {
            base
            for i in items
            if ("[a2a]" in i.nodeid or "[a2a-" in i.nodeid)
            and any(m.name == "xfail" and m.kwargs.get("strict", False) for m in i.iter_markers())
            for base in [_scenario_base(i.nodeid)]
            if base is not None
        }
        kept_representatives: set[str] = set()

        deselected: list[pytest.Item] = []
        remaining: list[pytest.Item] = []
        # Collected rather than raised in-loop: an exception escaping
        # pytest_collection_modifyitems surfaces as INTERNALERROR, which reports the
        # hook rather than the malformed reason and truncates the run. Gathering them
        # and failing once at the end names every offender.
        reason_errors: list[str] = []
        for item in items:
            nodeid = item.nodeid
            is_redundant_transport = "[mcp]" in nodeid or "[mcp-" in nodeid or "[rest]" in nodeid or "[rest-" in nodeid
            if not is_redundant_transport:
                remaining.append(item)
                continue
            # Check if this item has a strict xfail marker
            strict_xfails = [m for m in item.iter_markers() if m.name == "xfail" and m.kwargs.get("strict", False)]
            if not strict_xfails:
                remaining.append(item)
                continue
            # Consult the PARSE, not the string. A substring match here was satisfied by
            # prose quoting the token, so the declaration it appeared to read was
            # decorative.
            per_transport = False
            for marker in strict_xfails:
                try:
                    parsed = parse_xfail_reason(str(marker.kwargs.get("reason", "")))
                except XfailReasonError as exc:
                    reason_errors.append(f"{item.nodeid}: {exc}")
                    parsed = None
                if parsed is not None and parsed.scope == "per-transport":
                    per_transport = True
            if per_transport:
                # An obligation each transport enforces separately has to xpass on its
                # own when production catches up; deselecting the siblings would grade a
                # cross-transport MUST on one transport and call it covered.
                remaining.append(item)
                continue
            base = _scenario_base(nodeid)
            item_markers = {m.name for m in item.iter_markers()}
            opted_in = any(t.startswith(_REPRESENTATIVE_UC_PREFIXES) for t in item_markers) or (
                base is not None and base not in a2a_strict_bases
            )
            if opted_in and base is not None and base not in impl_bases and base not in kept_representatives:
                # No impl sibling to catch the xpass — keep this variant as
                # the scenario's single strict-xfail representative.
                kept_representatives.add(base)
                remaining.append(item)
            else:
                deselected.append(item)

        if reason_errors:
            raise pytest.UsageError(
                "malformed typed xfail reason(s) — a row whose reason does not parse would be "
                "routed by accident:\n  " + "\n  ".join(reason_errors)
            )

        if deselected:
            items[:] = remaining
            config = items[0].config if items else None
            if config:
                config.hook.pytest_deselected(items=deselected)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Multi-transport dispatch
# ---------------------------------------------------------------------------
# Tags that indicate a scenario already dispatches through a specific transport.
# These scenarios must NOT be multiplied — they have explicit When steps.
_TRANSPORT_SPECIFIC_TAGS = {"rest", "mcp", "a2a"}

# Scenarios whose graded production is reachable on ONE wire transport only.
#
# @a2a_untyped_ingest: the two surviving scenarios are A2A PROTOCOL-ENVELOPE
# surfaces — the ``message/send`` push config — which has no counterpart on MCP
# or REST at all. That, and only that, is what makes them single-transport.
#
# It used to carry three tool-surface scenarios as well, on the stated grounds
# that MCP and REST refuse the invalid document above the ingest gate "with a
# field path relative to the sub-model they validated", so grading them would
# grade the request model rather than the gate. MEASURED, that was false: every
# transport reports the ABSOLUTE path
# ``push_notification_config.authentication.credentials``, which is the literal
# the scenarios assert. The three now run on all four transports, so the
# agreement is a standing executable proof rather than a claim in a comment.
#
# The tag NAME is now a misnomer — neither survivor is an untyped ingest. It is
# left for the rename that owns the registry.
#
# PARAMETRIZED on that one transport rather than dropped from parametrization:
# an excluded transport is exactly as ungraded as an xfail but invisible to both
# escape-hatch detectors (GH #1892), whereas this keeps a real ``[a2a]`` test id
# that ``--collect-only`` shows.
_SINGLE_TRANSPORT_TAGS = {"a2a_untyped_ingest": "A2A"}

# UC + tag combinations that should run IMPL-only (no 4-way parametrization).
# (UC-002 @account used to live here when it ran resolve_account() via IMPL on
# MediaBuyAccountEnv; #1417 routed those scenarios through a full
# create_media_buy on the wire, so they now parametrize across a2a/mcp/rest.)
_IMPL_ONLY: set[tuple[str, str]] = set()

# UC-002 idempotency scenarios wired to MediaBuyCreateEnv (run a real
# create_media_buy across all 4 transports). Only these two @idempotency-key
# tags are live; the rest stay blanket-xfailed in _harness_env until their
# production gaps + steps are wired.
_UC002_IDEMPOTENCY_WIRED: set[str] = {
    "T-UC-002-v31-idempotency-replay",
    "T-UC-002-v31-idempotency-missing",
}

# UC-002 manual-approval scenario wired to MediaBuyCreateEnv (PR #1567 round-2 item 2):
# grades the spec-3.1.1 CreateMediaBuySubmitted envelope (status="submitted" +
# task_id, no media_buy_id/confirmed_at/revision) across all 4 transports —
# the create mirror of the BR-UC-003 wiring (1b2f03bc9). Other @alt-manual
# scenarios (reject/approve flows) stay dormant until their steps are wired.
_UC002_MANUAL_APPROVAL_WIRED: set[str] = {
    "T-UC-002-alt-manual",
}

#: BR-CODES-001 — a declared error code reaches the buyer unrewritten. Needs the same
#: FULL create-through-the-wire dispatch as the manual-approval scenarios, but is not a
#: manual-approval scenario, so it gets its own set rather than overloading that name.
_UC002_FULL_CREATE_WIRED: set[str] = {
    "T-CODES-001-platform-code-reaches-buyer",
    # BR-CODES-002's bare-raise scenario deliberately reuses that same rejection path:
    # it is the cheapest BARE, non-auth raise site already wired to all four transports.
    "T-CODES-002-suggestion-appears-on-a-bare-raise",
}

# The v3.1 sync-success envelope scenario. It was dormant because it had no step
# definitions, not because the harness could not reach it — it needs exactly the full
# create the manual-approval arm already runs. It grades revision / confirmed_at /
# valid_actions on the response the buyer meets first, which is the surface where
# those three were being fabricated from schema defaults.
_UC002_V31_SUCCESS_WIRED: set[str] = {
    "T-UC-002-v31-success-revision-and-actions",
}


# Admin scenarios have their own transport (Flask test_client / requests.Session).
# They must NOT be parametrized across MCP/A2A/REST/IMPL API transports.
_ADMIN_TAG_PREFIX = "T-ADMIN-"

# Scenario outlines whose <channel> column IS the transport: each Examples row
# dispatches through its own channel inside the When step, so pytest-level
# transport multiplication adds zero coverage (×3 identical in-process runs,
# and an e2e_rest variant that never touches the live server — the channel
# map has no e2e leg). Run once, like the @mcp/@a2a-tagged scenarios. The
# UC-010 feature header declares the auth-policy rows deliberately
# transport-specific (#1592).
_CHANNEL_COLUMN_TAGS = {"T-UC-010-auth"}

# UCs whose tool has no REST route — parametrize across A2A + MCP only (a REST
# variant would 404).
#
# EMPTY, and it must stay that way. It held "T-UC-019-" because get_media_buys
# genuinely had no REST route, which silently dropped 61 scenarios from REST
# while the suite read as covering three transports. The tool now has one
# (POST /api/v1/media-buys/query), so the entry is gone rather than the
# exclusion being kept as documentation of a fixed gap.
#
# The repo invariant is that every _impl is wrapped by MCP, A2A and REST
# (tests/CLAUDE.md). A missing wrapper is therefore a production gap to close,
# not a parametrization to trim: dropping a transport here is INVISIBLE to both
# escape-hatch detectors in test_architecture_e2e_rest_escape_hatches.py, which
# walk xfail conditions and E2EUnsupportedSetup sites — neither sees a scenario
# that was never parametrized. Add the route; do not re-add a prefix.
_NO_REST_UC_TAG_PREFIXES: tuple[str, ...] = ()


def _parametrize_ctx(
    metafunc: pytest.Metafunc,
    base_transports: list[Any],
    base_ids: list[str],
    e2e_member: Any | None,
    e2e_id: str | None,
) -> None:
    """Parametrize ``ctx`` over the in-process transports, plus the e2e one when enabled.

    Extracted so the AdCP arm and the admin arm share ONE copy of the
    append-e2e-when-enabled tail. Duplicating it would be the
    same logical operation with substituted enum members — the R0801 shape the
    DRY invariant treats as a defect, against a duplication baseline that may
    only shrink.
    """
    transports = list(base_transports)
    ids = list(base_ids)
    if e2e_member is not None and os.environ.get("BDD_E2E_ENABLED") == "true":
        transports.append(e2e_member)
        ids.append(e2e_id)
    metafunc.parametrize("ctx", transports, ids=ids, indirect=True)


#: Per-tag tracking issue for the dormant UC-010 scenarios.
#:
#: There was ONE shared reason string here, citing #1855 for all 33 dormant T-UC-010-*
#: tags. It was right for the media_buy presence-object cluster and wrong for everything
#: else, and because it was a single hardcoded fallback rather than a per-tag reason,
#: neither stale-citation guard could see it (they read .feature comments and _XFAIL_TAGS,
#: not this branch). Swapping it to #1291 would only have inverted the defect onto the tags
#: #1855 genuinely homes (#1721 review F2).
#:
#: Every entry was checked with `gh issue view` against the scenario it labels. A tag with
#: no ESTABLISHED home is deliberately ABSENT rather than guessed: a citation-free reason is
#: honest, an invented one is the defect this map exists to remove.
_UC010_DORMANT_TRACKING: dict[str, str] = {
    # RFC 9421 signing + agent key lifecycle. #1291's title scopes it to "inbound, outbound
    # and key lifecycle"; the in-file _SELECTIVE_XFAIL entries already cite #1291 for
    # webhook_signing, so this keeps the file internally consistent.
    "T-UC-010-v31-request-signing-posture": "#1291",
    "T-UC-010-v31-request-signing-namespace-split": "#1291",
    "T-UC-010-v31-request-signing-subset": "#1291",
    "T-UC-010-v31-webhook-signing": "#1291",
    "T-UC-010-v31-identity-brand-json-url": "#1291",
    "T-UC-010-v31-identity-key-origins": "#1291",
    "T-UC-010-v31-identity-compromise-notification": "#1291",
    "T-UC-010-v31-agent-signing-key-bounds": "#1291",
    "T-UC-010-v31-agent-encryption-key-bounds": "#1291",
    # media_buy presence-object sections. #1855's body enumerates these by name, including
    # media_buy.content_standards -- which the old blanket citation got right by accident
    # and a naive #1855 -> #1291 swap would have got wrong.
    "T-UC-010-v31-creative-multiplicity": "#1855",
    "T-UC-010-v31-creative-agentic-flags": "#1855",
    "T-UC-010-v31-governance-aware": "#1855",
    "T-UC-010-v31-vendor-metric-optimization": "#1855",
    "T-UC-010-v31-content-standards-block": "#1855",
    # Capability surfaces excluded from declaration under the strict policy. #1724 names
    # adapter creative_specs and generative creative; conftest already cites it in-file for
    # the specialism tags.
    "T-UC-010-v31-creative-specs": "#1724",
    "T-UC-010-v31-creative-extended": "#1724",
}


def _uc010_wired_tags() -> frozenset[str]:
    """The UC-010 tags whose step batch has landed, so CapabilitiesEnv serves them.

    get_adcp_capabilities wiring lands in BATCHES: only tag families whose steps
    exist pay ``integration_db`` + env setup; every other ``T-UC-010-*`` tag is
    routed to its own dormancy row (built from ``_UC010_DORMANT_TRACKING`` below)
    and xfails fast, citing that tag's OWN tracking issue. The set SHRINKS as
    batches land — a tag added here must be deleted from the tracking map, which
    ``tests/unit/test_architecture_uc010_dormancy_citations.py`` enforces (it
    reads this literal, so keep the name and the set literal here).
    """
    _UC010_WIRED_TAGS = frozenset(
        {
            # Batch 1 — envelope + account families
            "T-UC-010-main",
            # Split out of T-UC-010-main (#1721); wired by the same steps, so it
            # must join the wired set or it would xfail as "not yet wired" rather
            # than for its real, cited reason (#1291).
            "T-UC-010-main-reporting-delivery",
            "T-UC-010-degradation-no-cascade",
            "T-UC-010-main-timestamp",
            "T-UC-010-main-readonly",
            "T-UC-010-pricing",
            "T-UC-010-audience-caps",
            "T-UC-010-conversion-caps",
            "T-UC-010-creative-caps",
            "T-UC-010-ext-b-schema-valid",
            "T-UC-010-ext-a",
            "T-UC-010-account-require-operator-auth",
            "T-UC-010-account-authorization-endpoint",
            "T-UC-010-account-required-for-products",
            "T-UC-010-account-supported-billing",
            "T-UC-010-account-financials-declaration",
            "T-UC-010-account-block-presence",
            "T-UC-010-degradation-account",
            "T-UC-010-features-partitions",
            "T-UC-010-auth",
            "T-UC-010-auth-data-identity",
            "T-UC-010-ext-c-a2a",
            "T-UC-010-ext-c-mcp",
            "T-UC-010-ext-e-echo",
            "T-UC-010-ext-e-absent",
            "T-UC-010-ext-e-nested",
            "T-UC-010-ext-e-empty",
            "T-UC-010-ext-d-filter",
            "T-UC-010-ext-d-all-protocols",
            "T-UC-010-ext-d-invalid-value",
            "T-UC-010-ext-d-empty",
            "T-UC-010-v31-supported-versions",
            "T-UC-010-v31-version-unsupported",
            "T-UC-010-v31-version-unsupported-major-fallback",
            "T-UC-010-v31-version-unsupported-build-version-advisory",
            # Batch 3 — degradation-sections + channel-all-canonical
            "T-UC-010-degradation-sections",
            "T-UC-010-channel-all-canonical",
            # Batch 4 — features / targeting / idempotency-required
            "T-UC-010-features",
            "T-UC-010-targeting",
            "T-UC-010-targeting-partitions",
            "T-UC-010-degradation-partitions",
            "T-UC-010-v31-idempotency-required",
            # Batch 5 — v3.1 signing / brand / reporting / measurement
            "T-UC-010-v31-reporting-delivery-methods",
            "T-UC-010-v31-brand-block",
            "T-UC-010-v31-webhook-signing-required-when",
            "T-UC-010-v31-identity-required-when-signing",
            "T-UC-010-v31-measurement-catalog",
            # Batch 6 — compliance_testing / specialisms / advisory errors
            "T-UC-010-v31-compliance-testing",
            "T-UC-010-v31-specialisms",
            "T-UC-010-v31-advisory-errors",
            # Batch 7 — bounds / monotonicity outlines
            "T-UC-010-v31-request-signing-monotonicity",
            "T-UC-010-v31-idempotency-ttl-bounds",
            "T-UC-010-v31-version-unsupported-details-bounds",
            "T-UC-010-v31-identity-brand-json-url-bounds",
            # Batch 8 — webhook-signing bounds outline
            "T-UC-010-v31-webhook-signing-bounds",
            # Batch 9 — version negotiation + idempotency posture
            "T-UC-010-v31-idempotency-supported",
            "T-UC-010-v31-idempotency-in-flight-bound",
            # Batch 10 — creative_approval_mode (a recorded gap R7)
            "T-UC-010-v31-creative-approval-mode",
            # Batch 11 — trusted_match surfaces
            "T-UC-010-v31-trusted-match-surfaces",
            # Batch 12 — measurement accreditations
            "T-UC-010-v31-measurement-accreditations",
            # Batch 13 — locally-added declaration-backing graders.
            # These grade validate_backing()'s rejection rules, which the generated
            # specialisms scenario cannot: it declares creative-generative + the
            # creative protocol, both unbacked, so it stays xfailed against #1724.
            "T-UC-010-local-backed-specialism",
            "T-UC-010-local-unbacked-specialism",
            "T-UC-010-local-orphaned-specialism",
            "T-UC-010-local-unbacked-protocol",
            # Batch 14 — account.sandbox boundary outline (#1721 M4). Was dormant
            # (no bound Given for "the tenant account is configured for
            # {boundary_point}"), citing #1855 (generic wiring) instead of the
            # accurate #1856 (account-config surface) -- both fixed.
            "T-UC-010-v31-account-sandbox",
            # Batch 15 — request-ext acceptance (#1721 lane D / ).
            # Authored as the grader for adding `ext` to the get_adcp_capabilities
            # MCP wrapper, get_adcp_capabilities_raw and the REST body: the request
            # schema declares core/ext.json, so a vendor-namespaced ext must be
            # served the normal response on every transport.
            "T-UC-010-ext-request-vendor-namespaced",
        }
    )
    return _UC010_WIRED_TAGS


def _build_capabilities_env(e2e_config: object | None) -> AbstractContextManager:
    """get_adcp_capabilities — CapabilitiesEnv mocks only the adapter factory and
    the audit logger; the DB, TenantConfigUoW (publisher partners) and every
    transport wrapper are real. Capabilities is a pure read.
    """
    from tests.harness.capabilities import CapabilitiesEnv

    return CapabilitiesEnv(principal_id="buyer-001", e2e_config=e2e_config)


def _uc010_dormancy_rows() -> list[EnvRoute]:
    """One row per dormant UC-010 tag, each citing that tag's OWN tracking issue.

    There was ONE shared reason string for all 33 dormant tags, citing #1855 for
    every one of them — right for the media_buy presence-object cluster, wrong
    for the signing, identity and unbacked-capability clusters, and invisible to
    both stale-citation guards because it was a hardcoded fallback rather than a
    per-tag reason (#1721 review F2). A citation that is plausible but wrong is
    worse than none: it reads as tracked work, so nobody re-checks it.

    Rows, not an inline branch: a marker-set predicate inside the routing
    fixture is exactly what the ENV_ROUTES registry replaced, and a row is
    visible to ``scripts/audit``'s join, which resolves the same table.
    """
    rows = [
        EnvRoute(
            tag=f"uc010-dormant-{tag}",
            when=(lambda dormant: lambda m: dormant in m)(tag),
            env_builder=_build_capabilities_env,
            xfail_reason=(
                f"UC-010 harness wiring not extended to this tag (dormant, never graded) — tracked by {issue}"
            ),
        )
        for tag, issue in sorted(_UC010_DORMANT_TRACKING.items())
    ]
    # A dormant tag with no ESTABLISHED tracking home is deliberately absent from
    # the map — a citation-free reason is honest, an invented one is the defect
    # the map exists to remove — so it lands here, on the same catch-all shape
    # every other branch UC carries.
    rows.append(
        EnvRoute(
            tag="uc010-not-wired",
            when=_uc("UC-010", lambda m: True),
            env_builder=_build_capabilities_env,
            xfail_reason="UC-010 harness wiring not extended to this tag (dormant, never graded)",
        )
    )
    return rows


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize BDD scenarios across the wire transports (a2a/mcp/rest).

    The IMPL transport was dropped from the BDD default parametrization
    (#1417): BDD asserts AdCP *wire* conformance only. IMPL/call_impl
    remain available for unit/integration tests via the harness; they are simply
    no longer auto-parametrized here.

    Scenarios tagged with @rest, @mcp, or @a2a are transport-specific
    and skip parametrization — they already dispatch through their
    explicit transport in the When step.

    Uses ``ctx`` as the parametrize target (indirect) so every scenario
    gets a fresh dict with ``ctx["transport"]`` set to the Transport enum.
    """
    if "ctx" not in metafunc.fixturenames:
        return

    from tests.harness.transport import Transport

    marker_names = {m.name for m in metafunc.definition.iter_markers()}
    if marker_names & _TRANSPORT_SPECIFIC_TAGS:
        # Transport-specific scenario — don't multiply
        return

    if marker_names & _CHANNEL_COLUMN_TAGS:
        # Channel-column outline — each row dispatches via its own channel
        return

    # Single-transport scenarios still get a real (one-element) parametrization,
    # so the transport that grades them is visible at collection. See
    # _SINGLE_TRANSPORT_TAGS.
    single = marker_names & _SINGLE_TRANSPORT_TAGS.keys()
    if single:
        transport = Transport[_SINGLE_TRANSPORT_TAGS[next(iter(single))]]
        metafunc.parametrize("ctx", [transport], ids=[transport.value], indirect=True)
        return

    # Admin scenarios are not AdCP tool surfaces (no a2a/mcp/rest/e2e_rest), but
    # they DO have two transports of their own, both declared in
    # BR-ADMIN-ACCOUNTS.feature's header and both implemented by AdminAccountEnv.
    # Parametrize over them here so the transport is chosen at collection time
    # rather than pinned inside the harness.
    if any(t.startswith(_ADMIN_TAG_PREFIX) for t in marker_names):
        from tests.harness.admin_accounts import AdminTransport

        _parametrize_ctx(
            metafunc,
            [AdminTransport.INTEGRATION],
            [AdminTransport.INTEGRATION.value],
            AdminTransport.E2E,
            AdminTransport.E2E.value,
        )
        return

    # IMPL-only scenarios: harness has no transport wrappers for this path
    for uc_prefix, required_tag in _IMPL_ONLY:
        tag_prefix = f"T-{uc_prefix}-"
        if any(t.startswith(tag_prefix) for t in marker_names) and required_tag in marker_names:
            return

    # IMPL sunsetted: it adds no coverage the wire transports don't, and it has no
    # wire envelope (so it can't participate in error-envelope assertions). The four
    # truthful transports are a2a/mcp/rest + e2e_rest (added below when enabled).
    transports = [Transport.A2A, Transport.MCP, Transport.REST]
    ids = ["a2a", "mcp", "rest"]

    # UCs without a REST endpoint are graded on the A2A + MCP wire transports only
    # — including a REST variant would 404, on e2e_rest identically since it
    # dispatches real HTTP to the live server. The set is EMPTY now: UC-019 was
    # its only member and get_media_buys has a REST route again, so this branch
    # is dormant by design (see the declaration's note before re-populating it).
    no_rest_uc = any(t.startswith(_uc_prefix) for _uc_prefix in _NO_REST_UC_TAG_PREFIXES for t in marker_names)
    if no_rest_uc:
        transports = [Transport.A2A, Transport.MCP]
        ids = ["a2a", "mcp"]

    # The ONLY reason to withhold e2e_rest is a UC whose tool has no REST route
    # at all (it would 404 there identically). The former in-process-only webhook
    # exemption (_NO_E2E_REST_TAGS) is gone: a transport dropped at collection is
    # exactly as ungraded as an xfail but invisible to both escape-hatch
    # detectors, which is what
    # tests/unit/test_e2e_rest_ssrf_blocked_scenario_collected.py now pins.
    _parametrize_ctx(
        metafunc,
        transports,
        ids,
        None if no_rest_uc else Transport.E2E_REST,
        None if no_rest_uc else "e2e_rest",
    )


def _ssl_failure(exc: BaseException | None, depth: int = 0) -> ssl.SSLError | None:
    """The ``ssl.SSLError`` reachable from *exc*, walking the exception chain.

    httpx does not surface a certificate failure as an ``ssl`` exception: it
    raises ``httpx.ConnectError`` **wrapping** one, which is indistinguishable
    from "connection refused" by type alone. The chain is where the difference
    lives, so that is where the probe looks. Depth-bounded — a malformed chain
    must not hang the probe.
    """
    if exc is None or depth > 20:
        return None
    if isinstance(exc, ssl.SSLError):
        return exc
    return _ssl_failure(exc.__cause__ or exc.__context__, depth + 1)


def _probe_verify(base_url: str, ca_bundle: str | None) -> dict[str, object]:
    """``verify=`` kwargs for the health probe: the generated CA, when there is one.

    Only for an https base URL, and only when the bundle is really on disk — a
    missing file must reach the handshake and be reported as the TLS failure it
    is, not raise a ``FileNotFoundError`` from context construction that would
    read as a probe bug.
    """
    if not base_url.startswith("https://") or not ca_bundle or not Path(ca_bundle).is_file():
        return {}
    return {"verify": ssl.create_default_context(cafile=ca_bundle)}


@pytest.fixture(scope="session")
def e2e_stack():
    """Detect the live E2E stack; return an E2EConfig or None (never skips here).

    Reads E2E_BASE_URL / E2E_POSTGRES_URL (set by the in-network runner /
    run_all_tests via tox pass_env). Health-checks base_url so non-e2e transports
    still run when the stack is absent (returns None). For an e2e_* transport a
    None here is a hard ERROR (the ctx fixture raises) — never a skip, because
    e2e_* is only parametrized when BDD_E2E_ENABLED=true, so a missing stack means
    an explicitly-requested transport could not run. The RestE2EDispatcher reads
    config off the env, never the environment.
    """
    import httpx

    from tests.harness.transport import E2EConfig

    base_url = os.environ.get("E2E_BASE_URL")
    postgres_url = os.environ.get("E2E_POSTGRES_URL")

    # Phase B: per-worker e2e stacks. With E2E_PER_WORKER=1 under xdist, each
    # worker (PYTEST_XDIST_WORKER="gwN") targets its OWN server container
    # (network alias "server-gwN", port 8080) and its OWN database (adcp_gwN),
    # provisioned by run_all_tests.sh — so e2e_rest runs in parallel with no
    # shared-server/shared-DB contention. Falls back to the shared stack when off.
    ca_bundle = os.environ.get("E2E_CA_BUNDLE")
    tls_base_url = os.environ.get("E2E_TLS_BASE_URL")
    worker = os.environ.get("PYTEST_XDIST_WORKER")  # e.g. "gw3"
    if os.environ.get("E2E_PER_WORKER") == "1" and worker and worker.startswith("gw"):
        import re

        # Server containers are named "<project>-server-gwN" (globally-unique so
        # parallel worktrees don't collide) and reachable by that name on the
        # compose network. Hit the server directly on :8080 (SKIP_NGINX).
        proj = os.environ.get("COMPOSE_PROJECT_NAME", "")
        prefix = f"{proj}-" if proj else ""
        base_url = f"http://{prefix}server-{worker}:8080"
        # Each worker's TLS sidecar carries its own DOTTED CONTAINER NAME for the
        # same reason — `docker compose run` cannot give it a network alias.
        if tls_base_url:
            tls_base_url = f"https://{prefix}tls-{worker}.adcp.test:8443"
        if postgres_url:
            # swap the database name in the URL path -> adcp_<worker>
            postgres_url = re.sub(r"/[^/?]+(\?|$)", rf"/adcp_{worker}\1", postgres_url, count=1)

    if not base_url:
        return None

    probe_url = f"{base_url}/health"
    try:
        resp = httpx.get(probe_url, timeout=5, **_probe_verify(base_url, ca_bundle))
        resp.raise_for_status()
    except Exception as exc:
        # THREE outcomes, and collapsing any two of them is a defect:
        #   * a TLS/certificate failure is a BROKEN RIG -> raise. Reporting it as
        #     "absent" would hand back the plaintext config below and let an https
        #     scenario grade the http branch while reporting green — the exact
        #     vacuity #1291's TLS front exists to remove.
        #   * a transport/HTTP failure means nothing is listening -> None, so the
        #     in-process transports still run on a machine with no Docker stack.
        #   * anything else is a bug in this probe or in httpx -> propagate. A
        #     bare `except Exception: return None` classified those as "no stack".
        if _ssl_failure(exc) is not None:
            raise RuntimeError(
                f"TLS verification FAILED probing the e2e stack at {probe_url} "
                f"(E2E_CA_BUNDLE={ca_bundle!r}). A certificate failure is a broken test rig, not an "
                f"absent stack: reporting it as absent would silently fall back to the plaintext "
                f"config and grade an https scenario on the http branch."
            ) from exc
        if isinstance(exc, httpx.TransportError | httpx.HTTPStatusError):
            return None
        raise

    if not postgres_url:
        postgres_url = (
            f"postgresql://adcp_user:secure_password_change_me@localhost:{os.environ.get('POSTGRES_PORT', '5435')}/adcp"
        )
    return E2EConfig(
        base_url=base_url,
        postgres_url=postgres_url,
        tls_base_url=tls_base_url,
        ca_bundle=ca_bundle,
    )


# Every sequence OWNED BY a column of a public table, i.e. exactly the set
# ``TRUNCATE ... RESTART IDENTITY`` would have restarted. ``setval(seq, 1, false)``
# leaves is_called false, so the next ``nextval`` returns 1 -- identical end state.
_E2E_RESTART_IDENTITY_SQL = (
    "SELECT setval(s.oid::regclass, 1, false) "
    "FROM pg_class s "
    "JOIN pg_namespace n ON n.oid = s.relnamespace "
    "JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = s.oid "
    "  AND d.refclassid = 'pg_class'::regclass AND d.deptype = 'a' "
    "WHERE s.relkind = 'S' AND n.nspname = 'public'"
)


def _reset_e2e_db(e2e_config) -> None:
    """Flush the live server DB to a clean baseline before an e2e scenario.

    Live-server e2e shares ONE database and the server process commits
    independently, so the transaction-rollback isolation the in-process
    transports get (via the per-test integration_db) is impossible here. Instead
    empty every data table so each scenario's harness setup recreates exactly the
    rows it needs into a clean DB. The server reads the DB live, so it observes
    the reset immediately. alembic_version is preserved (schema stays).

    DELETE rather than TRUNCATE, and the lock mode is the whole point.
    TRUNCATE takes an AccessExclusiveLock on every table it names, one relation
    at a time, in whatever order ``pg_tables`` returned them. The server running
    against this same database sweeps it from background schedulers --
    ``delivery_webhook_scheduler`` every DELIVERY_WEBHOOK_INTERVAL (5s under
    run_all_tests.sh) and ``media_buy_status_scheduler`` every 60s -- and each
    sweep reads ``media_buys`` FIRST and a second table (webhook_delivery_log,
    creative_assignments, creatives) LATER in the SAME transaction, taking an
    AccessShareLock on each. AccessShareLock and AccessExclusiveLock conflict, the
    two orders are opposite, and neither side knows about the other: a textbook
    ABBA cycle. Postgres broke it by killing whichever party it picked, which
    surfaced as one rotating ``DeadlockDetected`` per full in-network run, always
    in scenario SETUP and never on an assertion (salesagent-prkv.48).

    DELETE takes a RowExclusiveLock, which does not conflict with AccessShareLock
    at all, so the reset can neither block nor be blocked by a concurrent reader
    and the cycle has nowhere to form. Do NOT "fix" a recurrence by retrying or by
    serialising the suite -- both leave the cycle in place.

    Emptying every table makes the delete order irrelevant, so FK triggers are
    suppressed for the transaction (``session_replication_role = replica``, SET
    LOCAL so it reverts at COMMIT) instead of topologically sorting 40+ tables --
    that is the property ``CASCADE`` was supplying. It needs a superuser, which
    the e2e Postgres role already is (run_all_tests.sh calls pg_terminate_backend
    on other backends with it); if that ever stops being true this raises loudly
    rather than silently leaving rows behind.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(e2e_config.postgres_url)
    try:
        with engine.begin() as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                    )
                )
            ]
            if tables:
                statements = ["SET LOCAL session_replication_role = replica"]
                statements += [f'DELETE FROM "{t}"' for t in tables]
                conn.exec_driver_sql("; ".join(statements))
                conn.exec_driver_sql(_E2E_RESTART_IDENTITY_SQL)
    finally:
        engine.dispose()


@pytest.fixture()
def ctx(request: pytest.FixtureRequest, e2e_stack) -> Generator[dict, None, None]:
    """Per-scenario mutable context shared across Given/When/Then steps.

    When parametrized by pytest_generate_tests, ``request.param`` is a
    Transport enum injected as ctx["transport"]. Transport-specific
    scenarios (tagged @rest/@mcp/@a2a) are NOT parametrized and get
    an empty ctx (When steps handle dispatch explicitly).

    For an e2e_* transport, stash the live-stack E2EConfig in ctx so
    ``_harness_env`` passes it to the harness env (which then binds factories to
    the server's DB and dispatches over real HTTP). Skip if the stack is absent.
    """
    d: dict = {}
    if hasattr(request, "param"):
        d["transport"] = request.param
        t = request.param
        if hasattr(t, "value") and str(t.value).startswith("e2e_"):
            if e2e_stack is None:
                # e2e_* transports are only parametrized when BDD_E2E_ENABLED=true
                # (see pytest_generate_tests), so reaching here means e2e was
                # EXPLICITLY requested but the live stack could not be reached. That
                # is a hard ERROR, never a skip: a skipped e2e test masks the fact
                # that the transport never ran, turning a non-executed test into a
                # false green (No Quiet Failures / Test Integrity).
                base_url = os.environ.get("E2E_BASE_URL")
                cause = "E2E_BASE_URL is unset" if not base_url else f"{base_url}/health failed"
                raise RuntimeError(
                    f"BDD_E2E_ENABLED=true but the live E2E stack is unreachable ({cause}). "
                    "The e2e_rest transport cannot run. Start the in-network stack "
                    "(run_all_tests.sh) or unset BDD_E2E_ENABLED to run the in-process "
                    "transports only. Refusing to skip — a skipped e2e test is a false green."
                )
            d["e2e_config"] = e2e_stack
    try:
        yield d
    finally:
        # Stop any step-level patchers stashed on ctx (e.g. given_today_is patches
        # src.core.tools.media_buy_list.datetime; snapshot/adapter steps patch
        # get_adapter). These use patch().start() and are NOT tracked by the
        # harness's context-managed EXTERNAL_PATCHES, so without this teardown they
        # leak the module patch into later scenarios in the same worker — an
        # order-dependent contamination (masked today only by the wide factory
        # flight window). Stop in reverse (LIFO) and ignore already-stopped.
        for patcher in reversed(d.get("_patchers", [])):
            try:
                patcher.stop()
            except RuntimeError:
                pass  # already stopped


def _setup_existing_media_buy(ctx: dict, env: object, tenant: object, principal: object, product: object) -> None:
    """Create an existing media buy + package for UC-003 update scenarios.

    Seeds the database with a committed media buy and one package, then
    stores references in ctx so Given/When/Then steps can find them.
    Also registers the package label mapping for Gherkin "pkg_001".
    """
    from datetime import UTC, datetime, timedelta

    from tests.factories import MediaBuyFactory, MediaPackageFactory

    mb = MediaBuyFactory(
        tenant=tenant,
        principal=principal,
        status="pending_approval",
        currency="USD",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC) + timedelta(days=30),
    )
    pkg = MediaPackageFactory(
        media_buy=mb,
        package_config={
            "package_id": "pkg_001",
            "product_id": product.product_id,
            "budget": 5000.0,
        },
    )
    env._commit_factory_data()
    ctx["existing_media_buy"] = mb
    ctx["existing_package"] = pkg
    # Register Gherkin label → real package_id mapping (see uc003 _register_package)
    from tests.bdd.steps.domain.uc003_update_media_buy import _register_package

    _register_package(ctx, "pkg_001", pkg)


@dataclass(frozen=True)
class EnvRoute:
    """One row of the declarative BDD env-routing registry.

    ``env_builder`` constructs the harness env (a ``BaseTestEnv`` context
    manager, not yet entered); ``seed`` — given the entered ``env`` — stashes
    ``ctx["env"]`` plus whatever tenant/principal/client/existing-data a
    scenario's steps need. ``xfail_reason``, when set, means this row is a
    placeholder: the generic consumer xfails immediately instead of building
    anything, so a UC can be registered ahead of a harness existing for it.

    The registry exists so authoring a new routing case is adding a row —
    there is no field for hand-rolling seeding or skipping DB scoping.

    ``when``, when set, is the row's ROUTING PREDICATE over the scenario's
    marker-name set. Rows carrying one are tried before the coarse ``uc``
    buckets. These predicates used to live as a hardcoded ``elif`` chain inside
    ``_harness_env``, invisible to ``scripts/audit``'s join — which knew only
    about the buckets and therefore reported every predicate-routed scenario as
    dormant. Moving them into rows is what lets ONE resolver answer for both
    sides.

    ``uc`` is the coarse bucket this row serves, matched against
    ``storyboard_spec.detect_uc``. A row sets ``when`` or ``uc``, not both.
    """

    tag: str
    env_builder: Callable[[E2EConfig | None], AbstractContextManager[BaseTestEnv]]
    seed: Callable[[dict, BaseTestEnv], None] | None = None
    xfail_reason: str | None = None
    when: Callable[[frozenset[str]], bool] | None = None
    uc: str | None = None


def _seed_uc003_storyboard_generic_client(ctx: dict, env: object) -> None:
    """Seed ctx for the UC-003 storyboard scenarios that dispatch via AdCPTestClient.

    Demonstrator: dispatches through the transport-
    generic ``AdCPTestClient`` (``tests/harness/client.py``) instead of
    ``MediaBuyDualEnv``/``dispatch_request`` — see
    ``tests/bdd/steps/domain/uc003_storyboard_generic_client.py``. Background
    still seeds "mb_existing" (BR-UC-003-update-media-buy.feature:24-28 runs
    for this scenario too), so seeding reuses ``_setup_existing_media_buy``
    (the same named helper the ext-/targeting-overlay branch uses) instead of
    a hand-rolled ``MediaBuyFactory``/``_commit_factory_data`` block —
    ``given_buyer_owns_media_buy_by_id`` registers whatever real id the
    factory generates under the Gherkin "mb_existing" label, so the literal
    id is not required. ``BareIntegrationEnv`` has no product dependency
    chain, so a minimal ``Product`` row is created here purely to satisfy
    ``_setup_existing_media_buy``'s package_config.product_id.
    """
    from tests.factories import ProductFactory

    tenant, principal = env.setup_default_data()
    # And the ACCOUNT, with this principal's access to it. update-media-buy-request.json
    # lists ``account`` in /required, and the boundary now RESOLVES the reference rather
    # than accepting and dropping it, so an unseeded account comes back as
    # PERMISSION_DENIED before the scenario reaches what it grades.
    env.setup_default_account()
    product = ProductFactory(tenant=tenant)
    # ctx["client"] is built once by _run_env_route for every row (B8).
    ctx["tenant"] = tenant
    ctx["principal"] = principal
    _setup_existing_media_buy(ctx, env, tenant, principal, product)


def _build_uc003_storyboard_generic_client_env(e2e_config: object | None) -> AbstractContextManager:
    from tests.harness._base import BareIntegrationEnv

    return BareIntegrationEnv(e2e_config=e2e_config)


def _build_admin_env(e2e_config: object | None) -> AbstractContextManager:
    """Both transports BR-ADMIN-ACCOUNTS.feature declares, chosen at collection.

    ``pytest_generate_tests`` parametrizes ADMIN scenarios over
    ``AdminTransport.INTEGRATION`` plus ``AdminTransport.E2E`` (when
    ``BDD_E2E_ENABLED=true``), and the ``ctx`` fixture stashes ``e2e_config``
    for the ``e2e_``-prefixed one. The env is TOLD its transport and, over e2e,
    the per-worker address ``e2e_stack`` synthesised — it discovers neither.

    This is the ONE builder that passes ``base_url=`` instead of
    ``e2e_config=``, and the asymmetry is deliberate: the admin UI is an HTML
    form surface, not an AdCP tool surface, so the env needs the ADDRESS and
    nothing else from ``E2EConfig``. Handing it the whole object would pull an
    AdCP-shaped dependency into a surface that has no AdCP protocol — the same
    reason ``AdminTransport`` is not a member of the ``Transport`` enum (see its
    docstring). A census asking "does every builder here receive e2e_config?"
    will flag this line; that flag is expected. What actually must hold — no
    branch pins its own DB scope — is machine-checked by
    ``tests/unit/test_bdd_admin_transport_parametrization.py``.
    """
    from tests.harness.admin_accounts import AdminAccountEnv

    mode = "e2e" if e2e_config is not None else "integration"
    base_url = e2e_config.base_url if e2e_config is not None else None  # type: ignore[attr-defined]
    return AdminAccountEnv(mode=mode, base_url=base_url)


def _build_product_env(e2e_config: object | None) -> AbstractContextManager:
    """Shared by COMPAT and UC-GET-PRODUCTS — both are read-only product listing."""
    from tests.harness.product import ProductEnv

    return ProductEnv(e2e_config=e2e_config)


def _build_creative_formats_env(e2e_config: object | None) -> AbstractContextManager:
    from tests.harness.creative_formats import CreativeFormatsEnv

    return CreativeFormatsEnv(e2e_config=e2e_config)


def _seed_uc005(ctx: dict, env: object) -> None:
    """Seed a tenant ONLY in e2e mode.

    The live server authenticates the token against the DB tenant, and UC-005
    baseline scenarios carry no account/tenant Given step to seed it (unlike
    UC-006/UC-011). In-process the registry is mocked and the DB is per-test,
    so the in-process status quo must stay unseeded. Mirrors the UC-004 poll
    branch (#1417).
    """
    if env.e2e_config is not None:
        env.setup_default_data()


def _build_media_buy_list_env(e2e_config: object | None) -> AbstractContextManager:
    """get_media_buys — MediaBuyListEnv runs the real _get_media_buys_impl and
    its A2A/MCP wrappers against a real DB (no adapter mock; list is a pure
    read). Genuine spec-production gaps stay xfailed via _UC019_XFAIL_TAGS /
    the selective blocks in the UC-002 branch above.
    """
    from tests.harness.media_buy_list import MediaBuyListEnv

    return MediaBuyListEnv(principal_id="buyer-001", e2e_config=e2e_config)


def _build_media_buy_create_list_env(e2e_config: object | None) -> AbstractContextManager:
    """UC-019 @post-create-poll — create_media_buy AND get_media_buys in ONE
    scenario on ONE identity; a factory-seeded buy would make the poll vacuous.
    MediaBuyCreateListEnv extends MediaBuyCreateEnv with the shared get_media_buys
    dispatch and routes a GetMediaBuysRequest to it (same shape as UC-003's
    MediaBuyDualEnv fork). Seeded with _seed_media_buy_chain, which runs
    setup_media_buy_data — the full create dependency chain (property tag, product,
    pricing option, authorized property).
    """
    from tests.harness.media_buy_create_list import MediaBuyCreateListEnv

    return MediaBuyCreateListEnv(principal_id="buyer-001", e2e_config=e2e_config)


def _seed_tenant_and_principal(ctx: dict, env: object) -> None:
    """``setup_default_data()``, stashed under the keys the steps read.

    Shared by UC-019 and UC-010: both seed one tenant plus the "buyer-001"
    principal their feature files name, and nothing else. Two copies of this
    three-line body is the substituted-variable shape the DRY invariant treats
    as a defect, so it is one seed with two rows.
    """
    tenant, principal = env.setup_default_data()
    ctx["tenant"] = tenant
    ctx["principal"] = principal


# ── Seeds extracted from the former _harness_env elif chain ────
# Each was an inline body inside a marker-keyed branch. As rows they are visible
# to storyboard_spec.resolve_env_route, which is what lets scripts/audit resolve
# the SAME route instead of re-implementing a coarser lookup.


def _seed_media_buy_chain(ctx: dict, env: object) -> None:
    """Seed the full create dependency chain (tenant/principal/product/pricing)."""
    tenant, principal, product, pricing_option = env.setup_media_buy_data()
    ctx["tenant"] = tenant
    ctx["principal"] = principal
    ctx["default_product"] = product
    ctx["default_pricing_option"] = pricing_option


def _seed_media_buy_chain_create_dispatch(ctx: dict, env: object) -> None:
    """The chain, plus the flag telling the shared When step to dispatch a create."""
    _seed_media_buy_chain(ctx, env)
    ctx["dispatch_mode"] = "create"


def _seed_media_buy_chain_full_create(ctx: dict, env: object) -> None:
    """The chain, plus the manual-approval full-create flag (PR #1567)."""
    _seed_media_buy_chain(ctx, env)
    ctx["uc002_full_create"] = True


def _seed_update_with_existing_buy(ctx: dict, env: object) -> None:
    """The chain plus an existing media buy + package for UC-003 update scenarios."""
    _seed_media_buy_chain(ctx, env)
    _setup_existing_media_buy(ctx, env, ctx["tenant"], ctx["principal"], ctx["default_product"])
    env._seeded_media_buy_id = ctx["existing_media_buy"].media_buy_id


def _seed_update_with_mb_existing(ctx: dict, env: object) -> None:
    """The chain plus a standalone MediaBuy carrying the literal Background id."""
    from tests.factories import MediaBuyFactory

    _seed_media_buy_chain(ctx, env)
    existing_media_buy = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id="mb_existing",
        status="active",
    )
    env._commit_factory_data()
    env._seeded_media_buy_id = "mb_existing"
    ctx["existing_media_buy"] = existing_media_buy


def _seed_default_data(ctx: dict, env: object) -> None:
    """Envs whose setup is a bare ``setup_default_data()``."""
    env.setup_default_data()


def _seed_delivery_poll(ctx: dict, env: object) -> None:
    """UC-004 polling: stash the tenant/principal under the keys its steps read."""
    tenant, principal = env.setup_default_data()
    ctx["db_tenant"] = tenant
    ctx[f"db_principal_{env._principal_id}"] = principal


def _env(factory_path: str, **kwargs: object) -> Callable[[object | None], AbstractContextManager]:
    """Build an env_builder that imports its harness lazily, as the branches did."""

    def _builder(e2e_config: object | None) -> AbstractContextManager:
        import importlib

        module_name, _, class_name = factory_path.rpartition(".")
        env_cls = getattr(importlib.import_module(module_name), class_name)
        return env_cls(e2e_config=e2e_config, **kwargs)

    return _builder


def _uc(uc_name: str, predicate: Callable[[frozenset[str]], bool]) -> Callable[[frozenset[str]], bool]:
    """Scope a marker predicate to one UC bucket.

    The former chain tested ``uc == "UC-00N"`` FIRST and only then the markers,
    so a bare marker predicate would over-match across UCs (``account`` and
    ``BR-RULE-034`` are both carried by more than one use case).
    """
    return lambda markers: storyboard_spec.detect_uc(markers) == uc_name and predicate(markers)


@contextmanager
def _production_db_pointed_at(url: str) -> Generator[None, None, None]:
    """Point production's cached DB engine at ``url`` for the scenario duration.

    The e2e counterpart of ``integration_db``'s engine repoint: over e2e_rest
    the env's factories write to the live server DB (``e2e_config.postgres_url``),
    but the runner's ``DATABASE_URL`` targets the in-process test base (in-network:
    ``.../adcp_test``), so any in-process production call inside an e2e scenario
    (e.g. a TRANSPORT-BYPASS Given calling an ``_impl``) would read a different
    database than the one being seeded. Repoint DATABASE_URL + reset the cached
    engine on entry, restore both on exit (mirrors tests/conftest_db.py).
    """
    import src.core.context_manager as _context_manager_module
    from src.core.database.database_session import reset_engine

    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    reset_engine()
    _context_manager_module._context_manager_instance = None
    try:
        yield
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        reset_engine()
        _context_manager_module._context_manager_instance = None


def _db_scope_for(request: pytest.FixtureRequest, e2e_config: object | None) -> AbstractContextManager[None]:
    """Select the production-DB scope for an e2e-capable harness branch.

    In-process transports need the per-test database (``integration_db``).
    Over e2e_rest, ``integration_db`` would repoint production's cached engine
    at an empty per-test DB while the env's factories write to the live server
    DB — so any in-process production call inside an e2e scenario (raw
    ``get_db_session()`` read-backs in Then steps, TRANSPORT-BYPASS Givens
    calling an ``_impl``) would read the wrong database. Point production at
    the server DB instead for the scenario duration.
    """
    if e2e_config is None:
        request.getfixturevalue("integration_db")
        return nullcontext()
    return _production_db_pointed_at(e2e_config.postgres_url)  # type: ignore[attr-defined]


def _run_env_route(
    request: pytest.FixtureRequest, ctx: dict, route: EnvRoute, e2e_config: object | None
) -> Generator[None, None, None]:
    """The one generic ``ENV_ROUTES`` consumer.

    Enters ``_db_scope_for`` — the structural DB-scoping entry point — before
    the row's ``env_builder`` runs, so on the e2e_rest parametrization
    production's cached engine is pointed at the live server DB (not an empty
    per-test DB) before any factory writes happen. Stashes the entered env on
    ``ctx["env"]``, runs the row's ``seed`` callback if present, then yields
    control to the scenario. A row with ``xfail_reason`` set never builds an
    env at all.
    """
    from tests.harness.client import AdCPTestClient

    if route.xfail_reason is not None:
        pytest.xfail(route.xfail_reason)
    with _db_scope_for(request, e2e_config), route.env_builder(e2e_config) as env:
        ctx["env"] = env
        # Build the client ONCE, here, for every row — it used to be constructed
        # inside a single hand-wired seed callback, so only that one row could
        # dispatch via the client and any new row wanting it had to remember to
        # repeat the line. Construction is cheap and
        # side-effect-free; a row that never dispatches via the client simply
        # does not read the key.
        ctx["client"] = AdCPTestClient(env)
        if route.seed is not None:
            route.seed(ctx, env)
        yield


_UC_BUCKET_ROUTES: dict[str, EnvRoute] = {
    "T-UC-003-storyboard-media-buy-not-found": EnvRoute(
        tag="T-UC-003-storyboard-media-buy-not-found",
        env_builder=_build_uc003_storyboard_generic_client_env,
        seed=_seed_uc003_storyboard_generic_client,
    ),
    # Same env + same seed as the row above: the re-cancel scenario also needs
    # the Background's "mb_existing" buy plus a client that sends the buyer's
    # literal payload (`canceled` must reach the
    # seller rather than being dropped by a harness flattener).
    "T-UC-003-storyboard-not-cancellable-on-recancel": EnvRoute(
        tag="T-UC-003-storyboard-not-cancellable-on-recancel",
        env_builder=_build_uc003_storyboard_generic_client_env,
        seed=_seed_uc003_storyboard_generic_client,
    ),
    # The five rows below are keyed by the coarse `uc` bucket (from
    # _detect_uc), not a per-scenario tag: they are what a scenario in these
    # UCs falls back to when no predicate row above claims it. ADMIN, COMPAT,
    # UC-GET-PRODUCTS and UC-005 have no predicate rows at all — one env + one
    # seed serves every scenario. UC-019 does have one (@post-create-poll needs
    # create + list in a single scenario), so its bucket row is the remainder.
    "ADMIN": EnvRoute(tag="ADMIN", env_builder=_build_admin_env),
    "COMPAT": EnvRoute(tag="COMPAT", env_builder=_build_product_env),
    "UC-GET-PRODUCTS": EnvRoute(tag="UC-GET-PRODUCTS", env_builder=_build_product_env),
    "UC-005": EnvRoute(tag="UC-005", env_builder=_build_creative_formats_env, seed=_seed_uc005),
    "UC-019": EnvRoute(tag="UC-019", env_builder=_build_media_buy_list_env, seed=_seed_tenant_and_principal),
}

# Tag sets the routing predicates below key on. They were inline `if` conditions
# in the former _harness_env elif chain; as named sets they are readable from the
# rows AND from scripts/audit, which now resolves through the same table.
_UC002_MANUAL_APPROVAL_ROW_TAGS = _UC002_MANUAL_APPROVAL_WIRED
_UC003_TARGETING_OVERLAY_TAGS = frozenset(
    {"T-UC-003-partition-targeting-overlay", "T-UC-003-boundary-targeting-overlay"}
)
_UC003_MANUAL_APPROVAL_TAGS = frozenset(
    {"T-UC-003-alt-manual", "T-UC-003-approval-tenant", "T-UC-003-approval-adapter"}
)
# The BR-RULE-215 revision scenarios. They were dormant for a reason that was not
# "the harness cannot reach them": they had NO step definitions at all, so the
# not-wired row was standing in for missing work rather than for a production gap.
# The steps exist now, and these grade the obligation the whole revision surface
# rests on — a mutating update advances the buyer's optimistic-concurrency token
# and REPORTS the advanced value. They need the same seeded existing buy as the
# manual-approval arm, so they share its row.
_UC003_REVISION_TAGS = frozenset(
    {
        "T-UC-003-revision-success-increments",
        "T-UC-003-revision-and-idempotency-independent",
        "T-UC-003-boundary-revision",
        "T-UC-003-partition-revision",
    }
)
_UC003_STORYBOARD_CLIENT_TAGS = frozenset(
    {"T-UC-003-storyboard-media-buy-not-found", "T-UC-003-storyboard-not-cancellable-on-recancel"}
)

ENV_ROUTES: list[EnvRoute] = [
    # ── @egress (local SSRF / webhook-credential refusal feature) ───────────
    # These scenarios carry T-EGRESS-* identity tags, NOT T-UC-<n>, so
    # storyboard_spec.detect_uc returns None for them and no coarse bucket can
    # claim them. They are UNSCOPED `when` rows (no _uc(...) wrapper) declared
    # FIRST, which is exactly how the former elif chain expressed them: the
    # egress tests checked before the shared UC arms and each borrowed one arm's
    # env. Two of them need an env that does NOT patch the surface under test —
    # a refusal manufactured by a mock proves nothing about the real egress seam.
    EnvRoute(
        tag="egress-sync",
        # sync_creatives leg: the buyer-supplied agent_url must be refused by the
        # REAL registry plus the REAL egress seam, so it takes the unpatched
        # registry variant rather than CreativeSyncEnv.
        when=lambda m: "egress_sync" in m,
        env_builder=_env("tests.harness.creative_sync.RealRegistryCreativeSyncEnv"),
        # sync_creatives is an AUTHENTICATED tool (`require_principal_id` in
        # src/core/tools/creatives/_sync.py) and its request now carries a
        # spec-required `account`, which the wrappers resolve through
        # `enrich_identity_with_account` — the first thing that asks the identity
        # for a principal. `identity_for` no longer fabricates one: with no
        # Principal row it nulls `principal_id`, so an unseeded row dispatches
        # UNAUTHENTICATED and production correctly answers AUTH_MISSING before the
        # egress seam is ever reached. Same seed the @egress_create/@egress_update
        # rows below carry, for the same reason.
        seed=_seed_default_data,
    ),
    EnvRoute(
        tag="egress-sync-creds",
        # The CREDENTIAL half of the registration is refused before the
        # per-creative loop is reached, so it wants the ordinary
        # (registry-mocked) sync env, not the real-registry variant above.
        when=lambda m: "egress_sync_creds" in m,
        env_builder=_env("tests.harness.creative_sync.CreativeSyncEnv"),
        # Authenticated for the same reason as the row above. The typed transports
        # refuse the credential half above `_impl`, so they never needed a
        # principal; A2A forwards the buyer's raw dict and reaches the account
        # enrichment first, so without this seed only the a2a leg died on
        # AUTH_MISSING — grading nothing about credentials on the one transport the
        # scenario exists to cover.
        seed=_seed_default_data,
    ),
    EnvRoute(
        tag="egress-update",
        # Dispatches a real update_media_buy carrying a push_notification_config,
        # so it needs the UC-003 ext arm: the update wrappers plus a seeded
        # existing media buy for the update to target.
        when=lambda m: "egress_update" in m,
        env_builder=_env("tests.harness.media_buy_dual.MediaBuyDualEnv"),
        seed=_seed_update_with_existing_buy,
    ),
    EnvRoute(
        tag="egress-create",
        # Ingest-time refusal of a buyer webhook URL — dispatches a real
        # create_media_buy, so it needs the UC-004 "create" arm's env and the
        # full create dependency chain.
        when=lambda m: "egress_create" in m,
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain,
    ),
    EnvRoute(
        tag="egress-get-products",
        # The remaining @egress scenarios dispatch get_products (and the A2A
        # message/send envelope pair). They share the UC-GET-PRODUCTS arm and
        # differ only in the env: the refusal must come from the REAL
        # resolve_property_list, so ProductEnv's patch is not applied.
        when=lambda m: "egress" in m,
        env_builder=_env("tests.harness.product.RealResolverProductEnv"),
    ),
    # ── Cross-cutting wire obligations (no T-UC-<n> identity tag) ───────────
    # Like the @egress rows above, these carry their own identity tags, so
    # storyboard_spec.detect_uc returns None and no coarse bucket can claim them.
    # They are UNSCOPED `when` rows naming the harness each one needs.
    EnvRoute(
        tag="security-wire-error-safety",
        # BR-SECURITY-001 grades that an UNTYPED exception cannot leak internals to
        # the wire. It dispatches get_products, so it takes the UC-GET-PRODUCTS arm.
        when=lambda m: any(t.startswith("T-SECURITY-001") for t in m),
        env_builder=_build_product_env,
    ),
    EnvRoute(
        tag="codes-declared-code-reaches-buyer",
        # BR-CODES-001 (a declared error code reaches the buyer unrewritten) and
        # BR-CODES-002's bare-raise scenario both exercise their obligation through a
        # FULL create_media_buy — it is the cheapest bare, non-auth raise site already
        # wired to every transport — so they need the UC-002 full-create arm rather
        # than a harness of their own.
        when=lambda m: bool(m & _UC002_FULL_CREATE_WIRED),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain_full_create,
    ),
    # ── UC-002 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc002-account",
        when=_uc("UC-002", lambda m: "account" in m),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain,
    ),
    EnvRoute(
        tag="uc002-ext",
        when=_uc(
            "UC-002",
            lambda m: (
                any(t.startswith("T-UC-002-ext-") for t in m)
                or "nfr-highvalue" in m
                or "T-UC-002-nfr-001-enforcement" in m
            ),
        ),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain_create_dispatch,
    ),
    EnvRoute(
        tag="uc002-manual-approval",
        # Also claims the v3.1 sync-success envelope scenario: it needs exactly the
        # full create this arm already runs, so it shares the row rather than
        # duplicating the seed. The former chain expressed the same thing by OR-ing
        # _UC002_V31_SUCCESS_WIRED into the manual-approval full-create flag.
        when=_uc("UC-002", lambda m: bool(m & (_UC002_MANUAL_APPROVAL_ROW_TAGS | _UC002_V31_SUCCESS_WIRED))),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain_full_create,
    ),
    EnvRoute(
        tag="uc002-idempotency",
        when=_uc(
            "UC-002",
            lambda m: bool(m & _UC002_IDEMPOTENCY_WIRED) or storyboard_spec.is_brand_shorthand_media_buy(m),
        ),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain,
    ),
    EnvRoute(
        tag="uc002-inv-015-6",
        when=_uc("UC-002", lambda m: "T-UC-002-inv-015-6" in m),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        xfail_reason="T-UC-002-inv-015-6 create_media_buy harness wiring is tracked in #1652",
    ),
    EnvRoute(
        tag="uc002-not-wired",
        when=_uc("UC-002", lambda m: True),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        xfail_reason="UC-002 harness not yet wired for non-extension scenarios",
    ),
    # ── UC-003 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc003-ext",
        when=_uc(
            "UC-003",
            lambda m: any(t.startswith("T-UC-003-ext-") for t in m) or bool(m & _UC003_TARGETING_OVERLAY_TAGS),
        ),
        env_builder=_env("tests.harness.media_buy_dual.MediaBuyDualEnv"),
        seed=_seed_update_with_existing_buy,
    ),
    EnvRoute(
        tag="uc003-manual-approval",
        when=_uc("UC-003", lambda m: bool(m & (_UC003_MANUAL_APPROVAL_TAGS | _UC003_REVISION_TAGS))),
        env_builder=_env("tests.harness.media_buy_dual.MediaBuyDualEnv"),
        seed=_seed_update_with_mb_existing,
    ),
    EnvRoute(
        tag="uc003-storyboard-generic-client",
        when=_uc("UC-003", lambda m: bool(m & _UC003_STORYBOARD_CLIENT_TAGS)),
        env_builder=_build_uc003_storyboard_generic_client_env,
        seed=_seed_uc003_storyboard_generic_client,
    ),
    EnvRoute(
        tag="uc003-not-wired",
        when=_uc("UC-003", lambda m: True),
        env_builder=_env("tests.harness.media_buy_dual.MediaBuyDualEnv"),
        xfail_reason=(
            "UC-003 harness not yet wired for non-extension scenarios (full graduation pending, PR #1567 follow-up)"
        ),
    ),
    # ── UC-006 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc006-creative-sync",
        when=_uc(
            "UC-006",
            lambda m: bool(
                m
                & {
                    "account",
                    "creative-invariant",
                    "BR-RULE-034",
                    "webhook-ssrf",
                    "uc006-storyboard-routing",
                    "uc006-idempotency",
                    # @creative-approval drives the approval_mode arms of
                    # _processing.py, whose ai-powered branch reaches the background
                    # AI-review executor — an effect that leaves the sync
                    # transaction. CreativeSyncEnv mocks that executor, which is what
                    # makes the effect observable rather than a race with a real
                    # background thread. This set is the ONLY thing standing between a
                    # UC-006 scenario and dormancy, so a scenario CreativeSyncEnv
                    # genuinely serves belongs in it — the entry grows the executing
                    # surface, it does not exempt anything from grading.
                    "creative-approval",
                }
            ),
        ),
        env_builder=_env("tests.harness.creative_sync.CreativeSyncEnv"),
    ),
    EnvRoute(
        tag="uc006-not-wired",
        when=_uc("UC-006", lambda m: True),
        env_builder=_env("tests.harness.creative_sync.CreativeSyncEnv"),
        xfail_reason="UC-006 harness not yet wired for non-account scenarios",
    ),
    # ── UC-018 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc018-list",
        # The three T-UC-018-* outlines (#1721 lane D) carry the rows the
        # _handle_list_creatives_skill -> shared build_*_request conversion can
        # silently delete, so they must EXECUTE rather than xfail fast:
        #  - partition-filters: singular media_buy_id + plural media_buy_ids
        #    merge/dedup (a bare select_request_fields(ListCreativesRequest, bag)
        #    drops both keys — they live on CreativeFilters, not the request model);
        #  - partition-field-selector: include_assignments, one of the projection
        #    flags the A2A hand-list carries today;
        #  - boundary-pagination: the sort_by/sort_order coercions the builder
        #    performs on the FLAT path.
        # Rows in these outlines that grade behavior the lane does not implement are
        # parked per-row in _SELECTIVE_XFAIL, not per-scenario.
        when=_uc(
            "UC-018",
            lambda m: bool(
                m
                & {
                    "list-after-sync",
                    "concept-id",
                    "BR-RULE-034",
                    "T-UC-018-partition-filters",
                    "T-UC-018-partition-field-selector",
                    "T-UC-018-boundary-pagination",
                }
            ),
        ),
        env_builder=_env("tests.harness.creative_list.CreativeListEnv"),
    ),
    EnvRoute(
        tag="uc018-ext-c",
        when=_uc("UC-018", lambda m: "T-UC-018-ext-c" in m),
        env_builder=_env("tests.harness.creative_list.CreativeListEnv"),
        xfail_reason="T-UC-018-ext-c list_creatives validation harness wiring is tracked in #1652",
    ),
    # When the dormant all-fields boundary scenarios are wired, their Then must
    # assert value-when-present, not key-presence-of-13: list_creatives drops a
    # corrupt tags/assets blob to absent and collapses an empty stored tags list
    # to omission (both conformant at 3.1.1) -- see the #1508 reconciliation note
    # in test_uc018_list_creatives.py's module docstring.
    EnvRoute(
        tag="uc018-not-wired",
        when=_uc("UC-018", lambda m: True),
        env_builder=_env("tests.harness.creative_list.CreativeListEnv"),
        xfail_reason=(
            "UC-018 harness wired only for the @list-after-sync (#1405), @concept-id (#1407), "
            "and @BR-RULE-034 isolation (#1503) scenarios"
        ),
    ),
    # ── UC-011 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc011-list",
        when=_uc("UC-011", lambda m: storyboard_spec.uc011_harness(m) == "list"),
        env_builder=_env("tests.harness.account_list.AccountListEnv"),
    ),
    EnvRoute(
        tag="uc011-sync",
        when=_uc("UC-011", lambda m: storyboard_spec.uc011_harness(m) == "sync"),
        env_builder=_env("tests.harness.account_sync.AccountSyncEnv"),
    ),
    EnvRoute(
        tag="uc011-not-wired",
        when=_uc("UC-011", lambda m: True),
        env_builder=_env("tests.harness.account_sync.AccountSyncEnv"),
        xfail_reason="UC-011 harness not yet wired for these markers",
    ),
    # ── UC-004 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc004-create",
        when=_uc("UC-004", lambda m: storyboard_spec.uc004_harness(m) == "create"),
        env_builder=_env("tests.harness.media_buy_create.MediaBuyCreateEnv"),
        seed=_seed_media_buy_chain,
    ),
    EnvRoute(
        tag="uc004-circuit-breaker",
        when=_uc("UC-004", lambda m: storyboard_spec.uc004_harness(m) == "circuit-breaker"),
        env_builder=_env("tests.harness.delivery_circuit_breaker.CircuitBreakerEnv"),
        seed=_seed_default_data,
    ),
    EnvRoute(
        tag="uc004-poll",
        when=_uc("UC-004", lambda m: storyboard_spec.uc004_harness(m) == "poll"),
        env_builder=_env("tests.harness.delivery_poll.DeliveryPollEnv", principal_id="buyer-001"),
        seed=_seed_delivery_poll,
    ),
    # ── UC-010 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc010-capabilities",
        when=_uc("UC-010", lambda m: bool(m & _uc010_wired_tags())),
        env_builder=_build_capabilities_env,
        seed=_seed_tenant_and_principal,
    ),
    # ── UC-019 ──────────────────────────────────────────────────────────────
    EnvRoute(
        tag="uc019-post-create-poll",
        when=_uc("UC-019", lambda m: "post-create-poll" in m),
        env_builder=_build_media_buy_create_list_env,
        seed=_seed_media_buy_chain,
    ),
]

# The dormant UC-010 tags, one row each so every one keeps its own tracking
# citation. They come AFTER the wired row above: a tag that is both wired and
# still listed as dormant resolves to the wired row, and the stale entry is
# caught by tests/unit/test_architecture_uc010_dormancy_citations.py.
ENV_ROUTES += _uc010_dormancy_rows()


def _uc_bucket_rows() -> list[EnvRoute]:
    """The coarse uc-bucket rows, each re-keyed to the bucket it routes.

    A function, not a module-level comprehension, for the same reason
    ``_uc010_dormancy_rows`` is one: ``dataclasses.replace`` is spelled exactly
    like ``Path.replace`` (a rename), so the import-time filesystem-I/O guard —
    which matches by attribute NAME, and says so in its DETECTOR NOTE — reports
    it at module scope. Nothing here needs to be computed during collection, so
    the deferral is free; the call below still runs at import, and ``ENV_ROUTES``
    is unchanged for every consumer that imports it as a module attribute.
    """
    return [dataclasses.replace(route, uc=key) for key, route in _UC_BUCKET_ROUTES.items() if not key.startswith("T-")]


# The coarse uc-bucket rows come last: a predicate row above always wins, which
# preserves the former chain's order (it matched the bucket first only for UCs
# that had NO predicate branches). Tag-keyed rows are already represented above
# as predicate rows, so only the bucket keys are appended.
ENV_ROUTES += _uc_bucket_rows()


@pytest.fixture(autouse=True)
def _harness_env(request: pytest.FixtureRequest, ctx: dict) -> Generator[None, None, None]:
    """Provide the appropriate harness for each BDD scenario.

    - A ``uc`` bucket with no marker_names-based sub-branching (ADMIN, COMPAT,
      UC-GET-PRODUCTS, UC-005, UC-019) is a row in ``ENV_ROUTES`` and goes
      through the one generic ``_run_env_route`` consumer.
    - UC-004 @polling → DeliveryPollEnv
    - UC-004 @webhook → WebhookEnv (unit variant, no DB needed)
    - UC-004 @webhook-reliability → CircuitBreakerEnv (unit variant)
    - A UC recognized by ``storyboard_spec.detect_uc`` but not (yet) claimed by a row
      xfails with a UC-specific reason via the catch-all at the bottom.
    - A tag ``_detect_uc`` does not recognize at all falls through to the
      same catch-all as ``uc=None`` -- an opaque "No harness wired for None".
      That is a bug, not intended behavior: widen ``_detect_uc`` instead of
      relying on this fixture to paper over it.
    """
    # ONE derivation, ONE routing call. The marker set comes from the
    # shared accessor so the conftest and the liveness plugin cannot narrow it
    # differently, and the route comes from the shared resolver so scripts/audit
    # answers the same question the same way.
    marker_names = derive_marker_names(request.node)
    uc = storyboard_spec.detect_uc(marker_names)
    e2e_config = ctx.get("e2e_config")

    # E2E shares one live DB across all scenarios; flush it to a clean baseline so
    # this scenario's harness setup starts fresh (no cross-scenario tenant_id
    # collisions). No-op for the in-process transports (they use per-test DBs).
    if e2e_config is not None:
        _reset_e2e_db(e2e_config)

    route = storyboard_spec.resolve_env_route(marker_names, ENV_ROUTES)
    if route is None:
        # NOT WIRED is a real answer, not an absence. Each branch UC keeps its own
        # catch-all row (below) carrying the reason it used to xfail with inline;
        # reaching here means no row claimed the scenario at all.
        pytest.xfail(f"No harness wired for {uc} (markers: {sorted(marker_names)})")
    yield from _run_env_route(request, ctx, route, e2e_config)
