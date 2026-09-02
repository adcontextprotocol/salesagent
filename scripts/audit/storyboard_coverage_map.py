#!/usr/bin/env python3
"""Reverse map: which pinned AdCP storyboards are on OUR conformance path, and are they covered?

The binding sweep asks "does this scenario's @source resolve?". This asks the
question that actually decides compliance: **for every storyboard the pinned spec
would grade us on, do we have a BDD scenario?**

A storyboard is on our path unless a gate the spec defines excludes it:

  * ``universal/``            — applies to every agent type, but is NOT
                                exempt from ``required_tools`` (see below).
                                Confirmed against a real-runner baseline
                               : the SDK's capability-driven
                                selection put every one of the 35 real,
                                gradable ``universal/`` storyboards through the
                                same any-of tool gate as protocol/specialism
                                storyboards — 25 ran, 10 graded fully skipped
                                as ``not_applicable`` because our agent
                                advertises none of their ``required_tools``
                                (e.g. ``comply_test_controller``,
                                ``validate_input``, ``get_signals``). Treating
                                ``universal/`` as ungated was the bug this
                                comment used to describe.
  * ``protocols/``            — a protocol we must declare
  * ``specialisms/``          — a specialism we must declare
  * ``requires_capability:``  — a capability we must advertise
  * ``required_tools:``       — lenient any-of; only advertising NONE of the
                                listed tools triggers a coverage-gap skip.
                                Applies to every tier, ``universal/`` included.

``requires_scenarios`` plays exactly one role, and it is easy to get backwards.
It is NOT a whitelist of what applies — the schema defines it as composition,
"scenario IDs that must pass alongside this storyboard" — so a scenario absent
from every list is still graded on its own applicability. But it IS the
reachability edge: when a scenario appears ONLY in lists belonging to gates we
fail, nothing can pull it in, and its own directory is irrelevant.
`governance_conditions` lives under `protocols/media-buy/scenarios/` yet is
required only by two specialisms we do not declare.

UNRESOLVED: whether a scenario in no ``requires_scenarios`` list at all is
reachable standalone on its own ``required_tools``, or is simply orphaned. This
classifier assumes the former. ``provenance_enforcement`` is the case that
decides it, and settling it needs the compliance runner's source. The measured baseline's real
run does NOT settle this: its capability probe (``get_adcp_capabilities``)
was itself rejected by our agent (``VALIDATION_ERROR: Unexpected keyword
argument``), so ``resolveStoryboardsForCapabilities`` never got far enough to
attempt selecting anything under ``protocols/`` or ``specialisms/`` —
``provenance_enforcement`` never appears anywhere in the run's output, neither
executed nor missing-tools nor observations. The 35 storyboards the run did
select are exactly (byte-for-byte) the ``universal/`` tier's real, gradable
files gated by ``required_tools`` — see the ``universal/`` note above. This
remains open; do not treat that baseline as evidence either way for
``requires_scenarios`` reachability.

Uncovered on-path storyboards are conformance gaps with no test. Covered
off-path scenarios are tests claiming a grading that does not apply to us.

Parsing primitives (universe filter, gate-field extraction, tagged-scenario
block extraction, storyboard identity) come from scripts/audit/storyboard_spec.py
— the shared L0 module also used by storyboard_binding_sweep.py and the
tests/fixtures/adcp_storyboards_pinned index, so this map's classification and
the binding sweep's audit agree by construction.

Read-only. Emits JSON, or ``--markdown`` for the checked-in artifact.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit import storyboard_spec  # noqa: E402

# ADVERTISED_TOOLS is intentionally still hand-maintained here — deriving it
# from src/core/tools/ is tracked separately as part of the repo's broader
# "5 hand-maintained discovery surfaces" initiative (#1210/qz2g), not folded
# into this ticket's parsing-primitive extraction.
ADVERTISED_TOOLS = {
    "activate_signal",
    "create_media_buy",
    "get_adcp_capabilities",
    "get_media_buy_delivery",
    "get_media_buys",
    "get_products",
    "get_signals",
    "list_accounts",
    "list_authorized_properties",
    "list_creative_formats",
    "list_creatives",
    "sync_accounts",
    "sync_creatives",
    "update_media_buy",
}


def classify(
    rel: str,
    text: str,
    decl: dict[str, set[str]],
    tools: set[str],
    required_by: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    """Return (status, reason) for one storyboard file, reading gates from raw YAML text.

    Thin adapter over :func:`classify_gates` — it extracts the three gate values from
    the storyboard's text and delegates. Callers that already hold structured gates
    (the vendored index, for instance) should call ``classify_gates`` directly rather
    than re-serialising to YAML: the extraction regexes match the upstream files'
    exact layout, and a round-trip through ``yaml.safe_dump`` silently parses as
    "no gates at all", which reads every gated storyboard as ON-PATH.
    """
    return classify_gates(
        rel,
        required_tools=storyboard_spec.required_tools(text),
        requires_capability=storyboard_spec.requires_capability(text),
        decl=decl,
        tools=tools,
        required_by=required_by,
    )


def classify_gates(
    rel: str,
    required_tools: set[str],
    requires_capability: tuple[str, str, str] | None,
    decl: dict[str, set[str]],
    tools: set[str],
    required_by: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    """Return (status, reason) for one storyboard from its already-extracted gates.

    This is the single implementation of applicability. The gate logic has been wrong
    four separate times during this sweep — loose phase matching, `Path.stem` collapse,
    `requires_scenarios` read as a whitelist, and gating by directory — so it exists
    exactly once and every caller routes through it.

    Applicability follows the gates the storyboard schema actually defines:

    * ``requires_capability`` — a capability we must advertise
    * ``specialisms/`` / ``protocols/`` — the declared-gate tiers
    * ``required_tools`` — LENIENT any-of; per storyboard-schema.yaml, only
      "missing **all** listed tools triggers a coverage-gap skip". Applies to
      EVERY tier, including ``universal/`` — confirmed against a real
      runner baseline, which graded 10 ``universal/`` storyboards fully
      skipped (``not_applicable``) purely on this gate.

    ``requires_scenarios`` is deliberately NOT used as a whitelist. The schema
    defines it as composition ("scenario IDs that must pass alongside this
    storyboard"), not an exhaustive list of what applies — treating it as one
    wrongly excludes scenarios that are graded on their own applicability.
    """
    # Reachability first: if every index that pulls this scenario in is behind a
    # gate we fail, the scenario is unreachable regardless of its own directory.
    owners = (required_by or {}).get(storyboard_spec.storyboard_key(rel), [])
    if owners and not any(storyboard_spec.index_reachable(o, decl) for o in owners):
        return "OFF-PATH", f"only required by {sorted(owners)} — all behind gates we do not declare"

    def tool_gate() -> tuple[str, str] | None:
        if required_tools and not (required_tools & tools):
            return "OFF-PATH", f"advertises none of required_tools {sorted(required_tools)}"
        return None

    # The tier dispatch decides OFF-PATH ONLY. It cannot return ON-PATH or
    # GATED, so no tier can reach a positive verdict without passing the shared
    # epilogue below — which is what makes "this tier never consulted the
    # capability gate" unrepresentable rather than merely guarded against.
    #
    # Before this, `universal/` and `specialisms/` returned ON-PATH directly and
    # never read requires_capability at all: 64 records from 6 universal
    # storyboards were published as fully graded with an empty gate_reason.
    if rel.startswith("universal/"):
        tier_reason = "universal — applies to every agent"
    elif rel.startswith("specialisms/"):
        name = rel.split("/")[1]
        if name not in decl["specialisms"]:
            return "OFF-PATH", f"specialism {name!r} not declared"
        tier_reason = f"specialism {name!r} declared"
    elif rel.startswith(("protocols/", "domains/")):
        protocol = rel.split("/")[1]
        if protocol not in decl["protocols"]:
            return "OFF-PATH", f"protocol {protocol!r} not declared"
        tier_reason = f"protocol {protocol!r}, required_tools advertised"
    else:
        return "UNKNOWN", "unclassified tier"

    # Shared epilogue. The capability gate is consulted BEFORE tool_gate(),
    # matching the precedence `protocols/` already had — it was the only tier
    # that consulted the gate at all, so its order is the one with precedent.
    #
    # This precedence is UNOBSERVABLE at the current pin but not inert forever.
    # A `universal/` or `specialisms/` storyboard that declares a capability gate
    # AND advertises none of its required_tools used to be OFF-PATH (tool gate
    # first, and the capability gate never read); it is now GATED, which means it
    # ENTERS the index. Measured at 3.1.1 that class is empty: 0 of 54 declaring
    # storyboards fail their tool gate, and 0 declare in `specialisms/`. A future
    # pin can populate it — if the gated count jumps on a repin, look here first.
    if requires_capability:
        return "GATED", f"requires_capability {storyboard_spec.capability_predicate(requires_capability)}"
    return tool_gate() or ("ON-PATH", tier_reason)


def _index_capability(entry: dict[str, Any] | None) -> tuple[str, str, str] | None:
    """A vendored-index capability entry as (path, matcher, value), or None.

    The index used to store only ``{path, equals}`` because it was transcribed by
    the equals-only regex, and this consumer subscripted ``["equals"]`` directly.
    Refreshing the index with the `contains` and `present` shapes the schema
    defines would have raised KeyError here — a crash rather than a misgrade.
    """
    if not entry:
        return None
    for matcher in ("equals", "contains", "present"):
        if matcher in entry:
            return (entry["path"], matcher, str(entry[matcher]))
    raise storyboard_spec.StoryboardAuditError(
        f"vendored index capability entry declares no known matcher: {entry!r} "
        "(expected one of equals / contains / present)"
    )


def statuses_from_vendored_index(repo: Path, index: dict[str, Any]) -> dict[str, str]:
    """Storyboard path -> gate status (ON-PATH / GATED / OFF-PATH), offline.

    Classified purely from a vendored index snapshot.

    No live ``~/projects/adcp`` clone: every gate value (``required_tools``,
    ``requires_capability``, ``required_by``) is already structured in
    ``tests/fixtures/adcp_storyboards_pinned/index.json``, so this calls
    :func:`classify_gates` directly rather than re-deriving gates from raw YAML
    text the way :func:`classify` does (see its docstring). The single
    implementation behind both the issue-map guard
    (``test_architecture_storyboard_issue_map.py``) and the check index — a fixture-driven
    on-path judgement drifted into two disagreeing implementations before this
    module existed; it does not get a third here.
    """
    declared = storyboard_spec.declared_capabilities(repo)
    storyboards: dict[str, dict[str, Any]] = index["storyboards"]
    required_by = {
        storyboard_spec.storyboard_key(rel): entry["required_by"]
        for rel, entry in storyboards.items()
        if entry.get("required_by")
    }

    statuses: dict[str, str] = {}
    for rel, entry in storyboards.items():
        capability = entry.get("requires_capability")
        status, _ = classify_gates(
            rel,
            required_tools=set(entry.get("required_tools", [])),
            requires_capability=_index_capability(capability),
            decl=declared,
            tools=ADVERTISED_TOOLS,
            required_by=required_by,
        )
        statuses[rel] = status
    return statuses


def on_path_from_vendored_index(repo: Path, index: dict[str, Any]) -> set[str]:
    """The ON-PATH subset of :func:`statuses_from_vendored_index`.

    Kept as its own name because two guards ask exactly this question and
    reading ``{k for k, v in ... if v == "ON-PATH"}`` at each call site is how a
    second implementation starts.
    """
    return {rel for rel, status in statuses_from_vendored_index(repo, index).items() if status == "ON-PATH"}


def covered_storyboards(repo: Path) -> dict[str, list[str]]:
    """Storyboard stems our @storyboard-v3.1 scenarios claim, by scenario identifier."""
    claims: dict[str, list[str]] = {}
    for scenario in storyboard_spec.tagged_scenarios(repo / "tests" / "bdd" / "features"):
        # Prefer the scenario's self-declared storyboard name over its (often wrong) @source.
        for name in scenario.self_declared_names:
            claims.setdefault(name, []).append(scenario.identifier)
        try:
            footer = storyboard_spec.parse_source_footer(scenario.block)
        except storyboard_spec.SourceFooterError:
            continue  # malformed footer -- reported by the make quality guard, not this map
        if footer and "schemas" not in footer.path:
            rel = storyboard_spec.normalize_cited_path(footer.path)
            claims.setdefault(storyboard_spec.storyboard_key(rel), []).append(scenario.identifier)
    return claims


def build(repo: Path, adcp: Path) -> dict[str, Any]:
    version = storyboard_spec.pinned_version(repo)
    dist = storyboard_spec.dist_root(adcp, version)
    if not dist.is_dir():
        raise storyboard_spec.StoryboardAuditError(f"missing pinned compliance tree: {dist}")

    decl = storyboard_spec.declared_capabilities(repo)
    claims = covered_storyboards(repo)
    required_by = storyboard_spec.requiring_indexes(dist)

    rows: list[dict[str, Any]] = []
    for sb in storyboard_spec.storyboards(dist):
        status, reason = classify(sb.rel, sb.text, decl, ADVERTISED_TOOLS, required_by)
        rows.append(
            {
                "storyboard": sb.rel,
                "stem": sb.stem,
                "status": status,
                "reason": reason,
                "covered_by": sorted(set(claims.get(sb.stem, []))),
            }
        )

    on_path = [r for r in rows if r["status"] == "ON-PATH"]
    return {
        "pinned_version": version,
        "declared": {k: sorted(v) for k, v in decl.items()},
        "advertised_tools": sorted(ADVERTISED_TOOLS),
        "totals": {
            "storyboards": len(rows),
            "on_path": len(on_path),
            "on_path_uncovered": len([r for r in on_path if not r["covered_by"]]),
            "off_path_but_claimed": len([r for r in rows if r["status"] in {"OFF-PATH", "GATED"} and r["covered_by"]]),
        },
        "storyboards": rows,
    }


def render(result: dict[str, Any]) -> str:
    out = [
        f"# Storyboard coverage map — AdCP {result['pinned_version']}",
        "",
        f"Declared protocols: `{', '.join(result['declared']['protocols'])}` · "
        f"specialisms: `{', '.join(result['declared']['specialisms'])}`",
        "",
        f"- storyboards examined: **{result['totals']['storyboards']}**",
        f"- on our conformance path: **{result['totals']['on_path']}**",
        f"- **on-path with NO scenario: {result['totals']['on_path_uncovered']}**",
        f"- off-path/gated but claimed by a scenario: **{result['totals']['off_path_but_claimed']}**",
        "",
        "## On our conformance path",
        "",
        "| Storyboard | Why on path | Covered by |",
        "|---|---|---|",
    ]
    for r in result["storyboards"]:
        if r["status"] != "ON-PATH":
            continue
        covered = ", ".join(f"`{c}`" for c in r["covered_by"]) or "**— NOT COVERED —**"
        out.append(f"| `{r['storyboard']}` | {r['reason']} | {covered} |")
    out += [
        "",
        "## Off path or gated, but a scenario claims them",
        "",
        "| Storyboard | Why off path | Claimed by |",
        "|---|---|---|",
    ]
    for r in result["storyboards"]:
        if r["status"] == "ON-PATH" or not r["covered_by"]:
            continue
        out.append(f"| `{r['storyboard']}` | {r['reason']} | {', '.join(f'`{c}`' for c in r['covered_by'])} |")
    return "\n".join(out) + "\n"


def main() -> int:
    return storyboard_spec.run_cli(__doc__ or "", build, render)


if __name__ == "__main__":
    sys.exit(main())
