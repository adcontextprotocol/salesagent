"""Regression tests for scripts/audit/ledger.py.

Three facts this audit pipeline joins used to each have MULTIPLE parsing/loading
owners: the ledger check-id grammar (``test_storyboard_check[protocol::track::
storyboard::step]``) was re-derived independently in ``storyboard_roadmap.
_ledgered_failures`` and ``storyboard_check_index._ledger_steps`` (the latter
reaching into the former's underscore-private ``_LEDGER_ID_RE`` as a sibling
module), and ``storyboard_check_index._binding_buckets`` recovered
``{scenario_id: bucket}`` by regexing a RENDERED markdown table even though
``storyboard_binding_sweep.audit()`` already returns that exact join as
structured data. That markdown (``storyboard-binding-baseline.md``) is no longer
committed at all, so the regex path is now unreachable by construction rather
than by assertion -- which is why the structural test that used to guard it was
deleted alongside the file.

This module pins the new single-owner shape:

* ``scripts.audit.ledger.LedgerCheckId`` is a LOSSLESS identity record --
  ``parse(line).format()`` reconstructs the bracket content exactly, with no
  hyphen normalization baked into ``parse()`` (that was the old bug: both call
  sites did ``match.group(3).replace("-", "_")`` inline, silently coupling
  identity to a join concern). Normalization is a *derived* property,
  ``storyboard_key``.
* ``ledger.load()``/``load_issue_map()``/``load_wireability()`` are the one
  loader each input gets.
* ``scripts.audit.storyboard_check_index.binding_buckets(repo, adcp)`` is a
  PUBLIC function that calls ``storyboard_binding_sweep.audit()`` for its data
  -- never rendered markdown -- so the published numbers depend on structured
  audit data alone, provable in CI without a live ``~/projects/adcp`` clone.
* ``storyboard_check_index.build()`` raises ``storyboard_spec.
  StoryboardAuditError`` naming any scenario id an on-path row's
  ``covered_by`` names but the binding-bucket join cannot resolve -- the real
  zero-join invariant (the originally-proposed "raise if bindings is empty"
  was near-vacuous: bindings and covered_by share a key space by
  construction, so an empty result only happens when nothing was at risk in
  the first place). Typed, not ``SystemExit`` -- this is a library function
  importable from tests and sibling scripts, and ``SystemExit`` would kill
  the importing process rather than give the caller something catchable
 .

"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit import (
    ledger,
    storyboard_binding_sweep,
    storyboard_check_index,
    storyboard_coverage_map,
    storyboard_spec,
)
from tests.unit._storyboard_guard_env import (  # noqa: E402
    ADCP_HOME,
    requires_pinned_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# A real, currently-ledgered line (tests/storyboard/known_failures.txt:40), also
# pinned verbatim in tests/unit/test_storyboard_ledger_state.py's EXPECTED_LEDGER
# -- keeping the two literals identical is what proves ledger.LedgerCheckId will
# be a drop-in replacement for that file's hand-rolled partition-based parse.
REAL_LEDGER_LINE = (
    "tests/storyboard/test_storyboard_conformance.py::"
    "test_storyboard_check[mcp::core::read_tool_idempotency::assert_omitted_key_grace_handled]"
)
REAL_LEDGER_BRACKET_CONTENT = "mcp::core::read_tool_idempotency::assert_omitted_key_grace_handled"


def test_parse_round_trips_a_real_ledger_line():
    """format(parse(line)) reconstructs the bracket content exactly (losslessness).

    Guards the MEDIUM-2 architect finding: normalizing hyphens inside parse()
    would make this assertion fail for any hyphenated storyboard segment. It
    happens to be green "by luck" today only if parse() stores the RAW group(3)
    -- this line has no hyphen, so a lossy parse() could slip past a weaker
    round-trip test that only checked this one line; test_storyboard_key_
    normalizes_hyphens_while_storyboard_id_stays_raw below closes that gap.
    """
    parsed = ledger.LedgerCheckId.parse(REAL_LEDGER_LINE)
    assert parsed is not None
    assert parsed.format() == REAL_LEDGER_BRACKET_CONTENT
    # The reconstructed bracket content must also be a literal substring of the
    # original line -- not just field-by-field equal -- proving format() emits
    # exactly what parse() consumed, byte for byte.
    assert f"[{parsed.format()}]" in REAL_LEDGER_LINE


def test_parse_captures_the_four_grammar_segments():
    """parse() exposes protocol/track/storyboard_id/step_id as named fields."""
    parsed = ledger.LedgerCheckId.parse(REAL_LEDGER_LINE)
    assert parsed is not None
    assert parsed.protocol == "mcp"
    assert parsed.track == "core"
    assert parsed.storyboard_id == "read_tool_idempotency"
    assert parsed.step_id == "assert_omitted_key_grace_handled"


@pytest.mark.parametrize(
    "line",
    [
        "# Known-failing storyboard-conformance checks — GENUINE production gaps only.",
        "this is not a ledger line at all",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::onlythree::segments]",
    ],
)
def test_parse_returns_none_on_a_non_matching_line(line):
    """A comment line, prose, or a short-grammar line must not parse silently.

    The three-group variant (only TWO `::` separators inside the brackets --
    protocol::storyboard::step, no track) is the exact grammar-drift bug the
    design doc calls out: a three-group pattern would silently read the track
    as the storyboard and join nothing. It must not parse at all, rather than
    parse into the wrong fields.
    """
    assert ledger.LedgerCheckId.parse(line) is None


def test_load_skips_comments_and_blanks_but_raises_on_an_unparsable_line(tmp_path):
    """Comments and blanks are skipped; a line the grammar rejects RAISES.

    The silent-skip behaviour this used to assert is gone: a typo'd
    entry that is quietly dropped stops grading its check with nothing to
    notice, so an unparsable ledger line is now a loud ValueError naming the
    file and line number.
    """
    fixture = tmp_path / "known_failures.txt"
    fixture.write_text(
        "\n".join(
            [
                "# a comment line, must be skipped",
                "",  # blank line, must be skipped
                "   ",  # whitespace-only line, must be skipped
                REAL_LEDGER_LINE,
                "tests/storyboard/test_storyboard_conformance.py::"
                "test_storyboard_check[a2a::security::security_baseline::probe_unauth]",
                "# trailing comment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = ledger.load(fixture)

    assert isinstance(loaded, list)
    assert all(isinstance(entry, ledger.LedgerCheckId) for entry in loaded)
    assert len(loaded) == 2
    assert loaded[0].format() == REAL_LEDGER_BRACKET_CONTENT
    assert loaded[1].format() == "a2a::security::security_baseline::probe_unauth"

    # And the loud half: one unparsable line fails the whole load, naming it.
    fixture.write_text(f"{REAL_LEDGER_LINE}\nnot a ledger line\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a ledger line"):
        ledger.load(fixture)


def test_storyboard_key_normalizes_hyphens_while_storyboard_id_stays_raw():
    """storyboard_id is raw; storyboard_key is the hyphen->underscore join spelling.

    The ledger spells hyphenated `universal/` storyboard stems with underscores
    per the runner's own emission, but a synthetic hyphenated segment must still
    prove the split: storyboard_id keeps whatever parse() actually captured
    (identity, must round-trip), while storyboard_key is the derived, normalized
    join spelling every consumer (roadmap._ledgered_failures, check_index.
    _ledger_steps) actually groups on.
    """
    line = (
        "tests/storyboard/test_storyboard_conformance.py::"
        "test_storyboard_check[mcp::core::capability-discovery::get_capabilities_filtered]"
    )
    parsed = ledger.LedgerCheckId.parse(line)
    assert parsed is not None
    assert parsed.storyboard_id == "capability-discovery"
    assert parsed.storyboard_key == "capability_discovery"
    # And the identity record still round-trips even though the segment has a
    # hyphen in it -- proves the losslessness holds beyond the accidental "no
    # hyphens in today's 128-line ledger" case.
    assert parsed.format() == "mcp::core::capability-discovery::get_capabilities_filtered"


# --- load_issue_map / load_wireability: same read-or-{} behavior as the old privates ---

_ISSUE_MAP_YAML = """\
storyboards:
  universal/signed-requests.yaml:
    issues: [1291]
    coverage: partial
"""

_WIREABILITY_YAML = """\
steps:
  universal/signed-requests.yaml::get_capabilities:
    verdict: wireable
    axes: {given: yes, when: yes, then: yes}
"""


def test_load_issue_map_reads_the_curated_yaml(tmp_path):
    (tmp_path / "docs" / "test-obligations").mkdir(parents=True)
    (tmp_path / "docs" / "test-obligations" / "storyboard-issue-map.yaml").write_text(_ISSUE_MAP_YAML, encoding="utf-8")

    loaded = ledger.load_issue_map(tmp_path)

    assert loaded == {
        "universal/signed-requests.yaml": {"issues": [1291], "coverage": "partial"},
    }


def test_load_issue_map_returns_empty_dict_when_file_is_missing(tmp_path):
    assert ledger.load_issue_map(tmp_path) == {}


def test_load_wireability_reads_the_curated_yaml(tmp_path):
    (tmp_path / "docs" / "test-obligations").mkdir(parents=True)
    (tmp_path / "docs" / "test-obligations" / "storyboard-wireability.yaml").write_text(
        _WIREABILITY_YAML, encoding="utf-8"
    )

    loaded = ledger.load_wireability(tmp_path)

    # PyYAML's SafeLoader parses bare `yes`/`no` as booleans (YAML 1.1) -- the
    # real docs/test-obligations/storyboard-wireability.yaml spells its axes
    # this exact way (`axes: {given: yes, when: yes, then: yes}`), so this is
    # production behavior, not a fixture quirk to work around.
    assert loaded == {
        "universal/signed-requests.yaml::get_capabilities": {
            "verdict": "wireable",
            "axes": {"given": True, "when": True, "then": True},
        },
    }


def test_load_wireability_returns_empty_dict_when_file_is_missing(tmp_path):
    assert ledger.load_wireability(tmp_path) == {}


# --- THE ACCEPTANCE-CRITERION PROOF: the bucket join is driven by audit() data ---


def test_binding_buckets_is_driven_by_audit_data_not_rendered_markdown(monkeypatch, tmp_path):
    """binding_buckets(repo, adcp) returns exactly what storyboard_binding_sweep.audit()
    reports, independent of any markdown file or its formatting.

    This is the CI-runnable, no-live-clone-needed form of "un-bolding the
    markdown changes no published number": the join no longer reads a rendered
    ``**A**``-style table at all, so there is no bolding left to strip.
    """
    fake_result = {
        "bindings": [
            {
                "feature": "some.feature",
                "line": 12,
                "identifier": "some-scenario",
                "title": "Some scenario",
                "tags": ["@storyboard-v3.1"],
                "sources": [],
                "findings": [],
                "bucket": "A",
            },
            {
                "feature": "other.feature",
                "line": 34,
                "identifier": "other-scenario",
                "title": "Other scenario",
                "tags": ["@storyboard-v3.1"],
                "sources": [],
                "findings": ["wrong path"],
                "bucket": "C",
            },
        ],
    }

    def fake_audit(repo, adcp):
        return fake_result

    monkeypatch.setattr(storyboard_binding_sweep, "audit", fake_audit)

    result = storyboard_check_index.binding_buckets(tmp_path, tmp_path)

    assert result == {"some-scenario": "A", "other-scenario": "C"}


# --- Zero-join tripwire: build() raises StoryboardAuditError naming an unresolved scenario id ---


@requires_pinned_bundle
def test_build_raises_storyboard_audit_error_naming_an_unresolved_covered_by_scenario(monkeypatch):
    """The real zero-join invariant: build() must name any scenario id a
    covered on-path row claims but the binding-bucket join cannot resolve.

    Replaces the near-vacuous "raise if bindings is empty" originally proposed
    (audit() and coverage_map share a key space by construction, so an empty
    bindings list only happens when nothing was at risk). Here bindings is
    non-empty but simply does not contain the id our synthetic row claims --
    the actual failure mode a silent {} fallback used to hide.
    """
    unresolved_scenario_id = "zzz-nonexistent-scenario-for-the-tripwire-test"
    real_storyboard_rel = "universal/signed-requests.yaml"

    fake_coverage = {
        "pinned_version": storyboard_spec.pinned_version(REPO_ROOT),
        "storyboards": [
            {
                "storyboard": real_storyboard_rel,
                "stem": "signed-requests",
                "status": "ON-PATH",
                "covered_by": [unresolved_scenario_id],
            }
        ],
    }

    monkeypatch.setattr(storyboard_coverage_map, "build", lambda repo, adcp: fake_coverage)
    # A real, non-empty bindings result that simply does not cover the id above --
    # proves the guard fires on a genuine miss, not merely on an empty list.
    monkeypatch.setattr(
        storyboard_binding_sweep,
        "audit",
        lambda repo, adcp: {
            "bindings": [
                {
                    "feature": "unrelated.feature",
                    "line": 1,
                    "identifier": "some-other-covered-scenario",
                    "title": "Unrelated",
                    "tags": [],
                    "sources": [],
                    "findings": [],
                    "bucket": "A",
                }
            ]
        },
    )

    with pytest.raises(storyboard_spec.StoryboardAuditError) as excinfo:
        storyboard_check_index.build(REPO_ROOT, ADCP_HOME)

    assert unresolved_scenario_id in str(excinfo.value)
