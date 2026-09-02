#!/usr/bin/env python3
"""Roll the per-scenario re-grounding proposals into one reconciliation table.

Each ``@storyboard-v3.1`` scenario was re-grounded against AdCP 3.1.1 by a
dedicated reviewer, which wrote a proposal file containing a VERDICT and a
TICKET MATERIAL section. This collapses those into the table that answers the
only question that matters per scenario:

    is it graded for us, and what is the concrete next action?

Actions are derived from the verdict, never invented:

  RETAG      NOT GRADED — the @storyboard-v3.1 tag claims a grading that does
             not apply to us; becomes @schema-v3.1 (identifier tag preserved).
  REPIN      GRADED, binding correct in substance but the @source is stale,
             wrong, or absent.
  FIX-ASSERT GRADED, but the scenario asserts the wrong thing.
  TICKET     GRADED, but production is non-conformant — the scenario cannot be
             made green, so it stays dormant and the gap is filed.

Read-only over the proposal directory. ``--markdown`` emits the artifact.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_spec  # noqa: E402

# The single source of truth for how many @storyboard-v3.1 scenarios this
# sweep covers -- callers reuse this rather than repeating the number, since a
# magic 40 drifting silently out of sync with this one is exactly the disease
# this constant exists to prevent.
EXPECTED_SCENARIOS = 40

VERDICT_RE = re.compile(r"^##\s*\d*\.?\s*VERDICT\s*$", re.M)
NOT_GRADED_RE = re.compile(r"^\s*NOT GRADED", re.I)
GRADED_RE = re.compile(r"^\s*GRADED", re.I)


def first_prose_line(text: str, start: int) -> str:
    for line in text[start:].splitlines()[1:]:
        stripped = line.strip().replace("**", "").replace("`", "").strip()
        if stripped:
            return stripped
    return ""


# Verdicts that qualify themselves ("but only half", "one of its three phases",
# "for the behaviour the scenario currently asserts") are compound: part of the
# scenario is salvageable green, part is not. A single action label would
# misroute them, so they are surfaced as PARTIAL for a human to split rather
# than guessed at.
COMPOUND_RE = re.compile(
    r"but only|only half|\bhalf\b|one of its \w+ phases|only one of|"
    r"currently asserts|for the behaviour|partly|in part",
    re.I,
)


def derive_action(verdict: str) -> str:
    """Map a verdict sentence onto the concrete next action.

    Deliberately conservative: anything self-qualifying becomes PARTIAL rather
    than being forced into a single bucket.
    """
    lowered = verdict.lower()
    if COMPOUND_RE.search(verdict):
        return "PARTIAL"
    if NOT_GRADED_RE.match(verdict):
        return "RETAG"
    if "non-conformant" in lowered or "never emitted" in lowered or "unimplemented" in lowered:
        return "TICKET"
    if "asserts the wrong" in lowered or "not graded, and it" in lowered or "is prose, not a grad" in lowered:
        return "FIX-ASSERT"
    return "REPIN"


# The first four scenarios were re-grounded before the shared reviewer brief
# existed, so their proposals use a different heading and carry no parseable
# VERDICT line. Their conclusions are recorded here verbatim from those files
# rather than left unresolved — each is quoted in the proposal named alongside.
PRE_BRIEF_VERDICTS: dict[str, tuple[str, str, str]] = {
    "uc005-roundtrip": (
        "GRADED",
        "REPIN",
        "GRADED — list_formats_integrity lives in protocols/media-buy/index.yaml, not the "
        "cited protocols/creative/index.yaml; schema mandates canonicalized agent_url "
        "comparison where the storyboard grades byte equality.",
    ),
    "uc005-thirdparty": (
        "GRADED",
        "FIX-ASSERT",
        "GRADED — but the scenario asserts the compliance runner's on_out_of_scope grading "
        "policy, which no seller behaviour can falsify; the gradeable obligation is "
        "do-not-fabricate. Cited path also wrong.",
    ),
    "uc005-baseline": (
        "GRADED",
        "REPIN",
        "GRADED — storyboard grades formats[0] presence only; core/format-id.json is "
        "strictly stronger (every entry, type object, required pair, value patterns). "
        "Schema wins.",
    ),
    "uc018-conceptid": (
        "NOT GRADED",
        "RETAG",
        "NOT GRADED — concept_id appears only in specialisms/creative-ad-server ungraded "
        "expected: prose, and we do not declare that specialism.",
    ),
}


def parse(proposal: Path) -> dict[str, Any]:
    text = proposal.read_text(encoding="utf-8")
    name = proposal.stem.removeprefix("sb-").removeprefix("repin-")
    if name in PRE_BRIEF_VERDICTS:
        status, action, verdict = PRE_BRIEF_VERDICTS[name]
        return {
            "scenario": name,
            "status": status,
            "action": action,
            "verdict": verdict,
            "ticket_items": len(__import__("re").findall(r"^\*\*(?:T|TM|\d+\.)[-\w. ]*—", text, __import__("re").M)),
            "proposal": proposal.name,
        }
    match = VERDICT_RE.search(text)
    verdict = first_prose_line(text, match.start()) if match else ""
    if NOT_GRADED_RE.match(verdict):
        status = "NOT GRADED"
    elif GRADED_RE.match(verdict):
        status = "GRADED"
    else:
        status = "UNPARSED"
    tickets = len(re.findall(r"^\*\*(?:T|TM|\d+\.)[-\w. ]*—", text, re.M))
    return {
        "scenario": proposal.stem.removeprefix("sb-").removeprefix("repin-"),
        "status": status,
        "action": derive_action(verdict) if status != "UNPARSED" else "REVIEW",
        "verdict": verdict[:200],
        "ticket_items": tickets,
        "proposal": proposal.name,
    }


def build(proposals_dir: Path, expected: int) -> dict[str, Any]:
    files = sorted(list(proposals_dir.glob("sb-*.md")) + list(proposals_dir.glob("repin-*.md")))
    rows = [parse(f) for f in files]
    by_status: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        by_action[row["action"]] = by_action.get(row["action"], 0) + 1
    return {
        "assessed": len(rows),
        "expected": expected,
        "outstanding": max(0, expected - len(rows)),
        "by_status": by_status,
        "by_action": by_action,
        "ticket_items_total": sum(r["ticket_items"] for r in rows),
        "rows": sorted(rows, key=lambda r: (r["status"], r["scenario"])),
        # Carried so render() never types the version. The sibling generators
        # already publish it this way; this one hardcoded it in its header.
        "pinned_version": storyboard_spec.pinned_version(REPO_ROOT),
    }


def render(result: dict[str, Any]) -> str:
    out = [
        f"# Storyboard scenario reconciliation — AdCP {result['pinned_version']}",
        "",
        f"**{result['assessed']} of {result['expected']} scenarios assessed**"
        + (f" — {result['outstanding']} outstanding." if result["outstanding"] else " — complete."),
        "",
        "Status: " + " · ".join(f"**{k}** {v}" for k, v in sorted(result["by_status"].items())),
        "",
        "Action: " + " · ".join(f"**{k}** {v}" for k, v in sorted(result["by_action"].items())),
        "",
        "Actions — `RETAG` tag claims a grading that does not apply to us "
        "(becomes `@schema-v3.1`, identifier preserved) · `REPIN` graded, `@source` stale/wrong/absent · "
        "`FIX-ASSERT` graded, scenario asserts the wrong thing · "
        "`TICKET` graded, production non-conformant, scenario stays dormant · "
        "`PARTIAL` verdict is compound (part salvageable green, part not) — needs a human split.",
        "",
        "| Scenario | Status | Action | Verdict |",
        "|---|---|---|---|",
    ]
    for row in result["rows"]:
        out.append(f"| `{row['scenario']}` | {row['status']} | **{row['action']}** | {row['verdict']} |")
    return "\n".join(out) + "\n"


def _configure_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--expected", type=int, default=EXPECTED_SCENARIOS)


def main() -> int:
    return storyboard_spec.run_cli(
        __doc__ or "",
        build,
        render,
        configure_args=_configure_args,
        build_args=lambda args: (args.proposals, args.expected),
    )


if __name__ == "__main__":
    sys.exit(main())
