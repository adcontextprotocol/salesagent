"""Skip a scenario that calls a spec tool this seller has not built.

A scenario naming an unregistered tool cannot pass. Nothing dispatches it, so no
response exists to grade and no assertion in it is reachable. Running it yields a
guaranteed failure saying only "the tool does not exist" — noise a reader has to
re-diagnose every time it appears.

SKIP, NOT XFAIL, and the distinction carries the meaning. An xfail RUNS the
scenario and tolerates the failure, which is right when production is expected to
be wrong about something being graded. Here there is nothing to grade: the tool is
absent, so the scenario never reaches a contract. Reporting it as an expected
FAILURE would claim a measurement that was never taken.

TWO LIVE SOURCES, NOTHING DECLARED. The vocabulary of real AdCP tools comes from
the pinned schemas (every ``*-request.json``); what this seller actually built
comes from ``src/core/tools/registry.py``. A hand-written list of "tools we have
not built" would be a third copy of a fact both already carry, and it would go
stale in the direction that hurts: a tool gets built, nobody updates the list, and
its scenarios stay skipped while everyone believes they run.

Measured at the pin: 71 tools defined, 14 registered here, and every tool we
register is one the pin defines — so the seller's surface is a strict subset, and
"in the vocabulary but not in TOOLS" is exactly the unbuilt remainder.

WHY THE VOCABULARY IS REQUIRED AND A NAME PATTERN IS NOT ENOUGH. The first
version of this matched any ``(get|list|sync|create|...)_*`` token in a step. It
was wrong in both directions at once: it read the FIELD ``list_id`` as a tool
(skipping scenarios that call nothing of the sort), while missing scenarios whose
steps name their tool only in prose. Checking membership in a real vocabulary
removes the false positives outright. The false negatives remain and are
harmless: a scenario that never names its tool is simply not skipped by this rule
and runs like any other.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
from functools import cache
from typing import Any

from src.core.tools.registry import TOOLS
from tests.helpers.adcp_pinned_schema import schema_roots

#: A tool-shaped token. Only a CANDIDATE — membership in the pinned vocabulary
#: below is what makes it a tool. Anchored on the protocol's verbs so the scan
#: does not have to consider every snake_case word in a feature file.
_CANDIDATE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


@cache
def spec_tools() -> frozenset[str]:
    """Every tool the pinned AdCP schemas define, from their request documents.

    ``media-buy/create-media-buy-request.json`` means the protocol defines
    ``create_media_buy``. Reading the directory is what keeps this current across
    a version bump: a tool the next pin adds appears here with no edit.
    """
    names: set[str] = set()
    for root in schema_roots():
        for path in glob.glob(os.path.join(str(root), "**", "*-request.json"), recursive=True):
            names.add(pathlib.Path(path).stem.removesuffix("-request").replace("-", "_"))
    return frozenset(names)


#: A token used AS a tool: named right before "request"/"response"/"call", or as
#: the object of a dispatch verb. This is how the scenarios themselves phrase it
#: ("the Buyer Agent sends the create_media_buy request"), and requiring that
#: context is what lets an unknown name be judged a TOOL rather than a field.
#: Measured across every feature file: it yields exactly four unknown names —
#: update_performance_index, get_task, list_authorized_properties, list_scenarios
#: — and no field names at all.
_DISPATCHED = re.compile(
    r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b(?=\s+(?:request|response|call|tool|operation|skill))"
    r"|(?:call|calls|invoke[sd]?|send[s]?|dispatch(?:es)?)\s+(?:the\s+)?([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"
)


def _dispatched_in(steps: Any) -> set[str]:
    """Tool names dispatched by *steps*, reading GIVEN and WHEN only.

    A Then DESCRIBES an outcome, and describing a tool is not calling one:
    "compliance_testing.scenarios should be a subset of the ids returned by the
    seller's list_scenarios call" names a tool this seller lacks, inside a
    scenario that dispatches ``get_adcp_capabilities`` and passes today. Reading
    Thens skipped it — the exact harm this rule exists to prevent.
    """
    found: set[str] = set()
    for step in steps:
        if (getattr(step, "type", "") or "").lower() not in {"given", "when"}:
            continue
        text = getattr(step, "name", "") or ""
        found.update(name for match in _DISPATCHED.finditer(text) for name in match.groups() if name)
    return found


def _feature_dispatches_nothing_we_have(feature: Any) -> frozenset[str]:
    """The undispatchable tools of a feature that dispatches NOTHING we registered.

    Empty when the feature dispatches at least one registered tool — such a file
    is MIXED and must be judged scenario by scenario.

    This exists because per-scenario detection under-skips badly on a file whose
    whole subject is missing. Measured: BR-UC-009 is entirely about
    ``update_performance_index``, which exists in neither the pin nor the
    registry, yet 95% of its scenarios named it in prose the dispatch pattern
    does not match — so they would have run and failed for no reason anyone can
    act on. BR-UC-007 was 94% the same. Sixteen of the twenty unbound files
    dispatch no registered tool at all; for those, the FEATURE is the honest unit.

    The four mixed files (UC-010, UC-027, UC-030, UC-032) each dispatch a real
    tool alongside an absent one, and fall through to the per-scenario rule --
    skipping them wholesale would silence scenarios that genuinely exercise
    ``create_media_buy`` or ``get_adcp_capabilities``.
    """
    registered: set[str] = set()
    absent: set[str] = set()
    for scenario in getattr(feature, "scenarios", {}).values():
        steps = list(getattr(scenario, "all_background_steps", []) or []) + list(getattr(scenario, "steps", []) or [])
        for name in _dispatched_in(steps):
            (registered if name in TOOLS else absent).add(name)
    return frozenset() if registered else frozenset(absent)


def undispatchable_tools_in(scenario: Any) -> dict[str, str]:
    """Tools a scenario calls that this seller cannot dispatch, each with its reason.

    Reads the scenario's own step text, including background steps — a Given that
    dispatches an absent tool sinks the scenario as surely as a When does.

    Two reasons, kept apart because they send the reader to different places:

    ``unbuilt``
        The pinned spec defines the tool; this seller has not built it. Inventory
        for protocol surface that does not exist yet. It starts running the day
        the tool is registered.
    ``stale``
        The tool is in neither the pinned spec nor the registry, so the scenario
        describes an operation that exists NOWHERE. Not something waiting to be
        built — something to reconcile or delete. Measured: exactly four such
        names across every feature file, and ``update_performance_index`` is
        already known to have left the spec.

    Collapsing the two under one message would tell a reader "not built yet"
    about a tool nobody is going to build.
    """
    steps = list(getattr(scenario, "all_background_steps", []) or []) + list(getattr(scenario, "steps", []) or [])
    dispatched = set(_dispatched_in(steps))

    # A feature that dispatches NOTHING this seller registered is unbuilt surface
    # whole, so every scenario in it inherits the verdict — including the ones
    # that name their tool only in prose. Without this, 95% of BR-UC-009 ran
    # against a tool that exists nowhere.
    feature = getattr(scenario, "feature", None)
    if feature is not None:
        dispatched |= _feature_dispatches_nothing_we_have(feature)

    known = spec_tools()
    verdict = {name: "unbuilt" for name in dispatched & known if name not in TOOLS}
    verdict.update({name: "stale" for name in dispatched if name not in known and name not in TOOLS})
    return verdict
