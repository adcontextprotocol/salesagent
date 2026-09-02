#!/usr/bin/env python3
"""Audit every @storyboard-v3.1 BDD scenario against the pinned AdCP storyboards.

Answers, per scenario, the questions that decide whether its tag is honest:

  1. Does the ``@source`` footer cite a path that EXISTS at the pinned version?
  2. Does the cited phase/step exist in that file?
  3. If not, where does it actually live?
  4. Is the behaviour GRADED (under ``validations:``) or narrative (``expected:``)?
  5. Which storyboard tier owns it -- universal / protocol / domain / specialism?
  6. Do we DECLARE the specialism or protocol that gates it?

Read-only. Emits JSON on stdout; ``--markdown`` renders the checked-in baseline.

The pinned version comes from docs/adcp-spec-version.md, never hardcoded here --
a sweep that hardcodes the version rots the same way the pins it audits did.

Parsing primitives (pinned version, declared capabilities, phase/check grading,
@source footer parsing, path normalization, tier classification) come from
scripts/audit/storyboard_spec.py -- the shared L0 module also used by
storyboard_coverage_map.py and the tests/fixtures/adcp_storyboards_pinned index,
so this sweep's findings agree with the coverage map and the make quality guard
by construction.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit import storyboard_spec  # noqa: E402


@dataclass
class Binding:
    """One @storyboard-v3.1 scenario and everything the sweep can prove about it."""

    feature: str
    line: int
    identifier: str
    tags: list[str]
    title: str
    sources: list[dict[str, str]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    bucket: str = "A"  # A ok · B wrong path · C wrong tag · D under-asserts · E prod-blocked

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON report.

        Every field, mechanically — a hand-written mirror drifts the moment a field is added.
        """
        return dataclasses.asdict(self)


def audit(repo: Path, adcp: Path) -> dict[str, Any]:
    version = storyboard_spec.pinned_version(repo)
    dist = storyboard_spec.dist_root(adcp, version)
    if not dist.is_dir():
        raise storyboard_spec.StoryboardAuditError(f"pinned compliance tree missing: {dist}")

    declared = storyboard_spec.declared_capabilities(repo)
    scenarios = storyboard_spec.tagged_scenarios(repo / "tests" / "bdd" / "features")
    phases = storyboard_spec.phase_index(dist)

    bindings: list[Binding] = []
    for scenario in scenarios:
        binding = Binding(
            feature=scenario.feature,
            line=scenario.line,
            identifier=scenario.identifier,
            tags=scenario.tags,
            title=scenario.title,
        )
        for match in re.finditer(r"@source\s+\S.*", scenario.block):
            try:
                footer = storyboard_spec.parse_source_footer(match.group(0))
            except storyboard_spec.SourceFooterError as exc:
                binding.findings.append(f"malformed @source footer: {exc}")
                binding.bucket = "C"
                continue
            if footer is not None:
                binding.sources.append(
                    {
                        "repo": footer.repo,
                        "ref": footer.ref,
                        "commit": footer.commit or "",
                        "phase": footer.phase or "",
                        "step": footer.step or "",
                        "path": footer.path,
                    }
                )

        # Phases the scenario names in prose, whether or not it set `phase=`.
        #
        # Match only an explicit phase REFERENCE ("<id> phase:", "phase=<id>",
        # "step <id>"), never a bare token: most phase ids are also tool names
        # (`create_media_buy`, `get_products`, `list_creatives`) that appear in
        # ordinary prose, and treating those as bindings manufactures findings.
        named = sorted(
            p
            for p in phases
            if re.search(
                rf"(?:\b{re.escape(p)}\s+(?:phase|step)\b|\bphase[=:]\s*{re.escape(p)}\b"
                rf"|\bstep\s+{re.escape(p)}\b)",
                scenario.block,
            )
        )
        cited_files = {
            storyboard_spec.normalize_cited_path(s["path"]) for s in binding.sources if "schemas" not in s["path"]
        }
        # Scenarios name their own storyboard in a summary line ("# <name>: <claim>")
        # immediately above the @source footer. When that self-declared name does not
        # match the cited file, the footer points somewhere the scenario never claimed.
        declared_names = scenario.self_declared_names
        cited_stems = {storyboard_spec.storyboard_key(p) for p in cited_files}
        if declared_names and cited_stems and not (declared_names & cited_stems):
            # Only a finding when the declared name is a real storyboard/phase id.
            real = {
                n
                for n in declared_names
                if n in phases or any(storyboard_spec.storyboard_key(f) == n for f in phases.get(n, []))
            }
            real |= {
                n
                for n in declared_names
                if any((dist / f).exists() for f in [f"protocols/media-buy/scenarios/{n}.yaml"])
            }
            if real:
                binding.findings.append(
                    f"self-declared storyboard {sorted(real)} does not match cited file {sorted(cited_stems)} "
                    "— footer points at a storyboard this scenario never claims"
                )
                binding.bucket = "B"

        for phase in named:
            owners = phases[phase]
            if cited_files and not (cited_files & set(owners)):
                binding.findings.append(
                    f"names phase {phase!r} but cites {sorted(cited_files)} — that phase lives in {owners}"
                )
                binding.bucket = "B"

        if not binding.sources:
            binding.findings.append("NO @source footer — binding is unverifiable")
            binding.bucket = "C"
            bindings.append(binding)
            continue

        for source in binding.sources:
            raw_path, ref, phase, step = source["path"], source["ref"], source["phase"], source["step"]

            if version not in ref:
                binding.findings.append(f"stale ref {ref!r} — pinned version is {version}")
                binding.bucket = max(binding.bucket, "B")

            rel = storyboard_spec.normalize_cited_path(raw_path)
            is_schema = "schemas" in raw_path
            if is_schema:
                source["verdict"] = "schema-path (not a storyboard)"
                continue

            target = dist / rel
            source["resolved"] = str(target.relative_to(adcp)) if target.exists() else ""
            if not target.exists():
                binding.findings.append(f"cited path does not exist at {version}: {rel}")
                binding.bucket = "B"
                continue

            text = target.read_text(encoding="utf-8")
            tier = storyboard_spec.storyboard_tier(rel)
            source["tier"] = tier
            grading = storyboard_spec.phase_is_graded(text, phase)
            if grading:
                source["grading"] = grading
                if grading == "absent":
                    binding.findings.append(f"phase {phase!r} not in cited file at {version}")
                    binding.bucket = "B"
                elif grading == "prose":
                    binding.findings.append(f"phase {phase!r} is narrative (expected:) not graded (validations:)")
                    binding.bucket = "C"

            if step:
                # `step` is the addressable unit the conformance ledger keys on
                # (protocol, track, storyboard_id, step_id) -- resolved against
                # the cited file exactly like `phase` is, so a `step=` that
                # names nothing real fails loudly instead of being carried
                # unchecked.
                step_grading = storyboard_spec.phase_is_graded(text, step)
                if step_grading == "absent":
                    binding.findings.append(f"step {step!r} not in cited file at {version}")
                    binding.bucket = "B"

            if tier == "specialisms":
                name = rel.split("/")[1]
                if name not in declared["specialisms"]:
                    binding.findings.append(f"gated by specialism {name!r} which we do NOT declare — tag is wrong")
                    binding.bucket = "C"

        bindings.append(binding)

    buckets: dict[str, int] = {}
    for binding in bindings:
        buckets[binding.bucket] = buckets.get(binding.bucket, 0) + 1

    return {
        "pinned_version": version,
        "declared": {k: sorted(v) for k, v in declared.items()},
        "scenario_count": len(bindings),
        "buckets": buckets,
        "bindings": [b.to_dict() for b in bindings],
    }


def render_markdown(result: dict[str, Any]) -> str:
    version = result["pinned_version"]
    out = [
        f"# Storyboard binding baseline — AdCP {version}",
        "",
        f"`{result['scenario_count']}` scenarios tagged `{storyboard_spec.TAG}`. "
        f"Declared specialisms: `{', '.join(result['declared']['specialisms']) or 'none'}`; "
        f"protocols: `{', '.join(result['declared']['protocols']) or 'none'}`.",
        "",
        "Buckets — **A** binding verified · **B** wrong/stale `@source` · "
        "**C** tag unjustified (ungraded or undeclared gate) · "
        "**D** graded but under-asserted · **E** graded, blocked on production.",
        "",
        "| Scenario | Feature:line | Bucket | Findings |",
        "|---|---|---|---|",
    ]
    for b in result["bindings"]:
        findings = "<br>".join(b["findings"]) or "—"
        out.append(f"| `{b['identifier']}` | {b['feature']}:{b['line']} | **{b['bucket']}** | {findings} |")
    return "\n".join(out) + "\n"


def main() -> int:
    return storyboard_spec.run_cli(__doc__ or "", audit, render_markdown)


if __name__ == "__main__":
    sys.exit(main())
