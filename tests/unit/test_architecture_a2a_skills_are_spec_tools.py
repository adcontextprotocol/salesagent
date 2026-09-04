"""Every A2A skill must name a tool the pinned AdCP version defines.

tool === skill === REST RPC route. A skill the spec does not define is a private
surface a buyer cannot discover from the spec and another seller will not answer,
so the skill map may hold no name absent from ADCP_TOOL_DEFINITIONS.

This is a forward-lock with a SHRINKING allowlist, not a description of today: the
two entries below are operations this repo implements under a pre-3.1.1 name and
must be renamed onto their spec operation. Adding a row is not an option -- a new
skill either names a spec tool or does not ship.
"""

import pytest
from adcp.server.mcp_tools import ADCP_TOOL_DEFINITIONS

from tests.helpers.a2a_skill_map import registered_skill_names

#: skill name -> the spec operation it must be renamed onto. Entries may only be REMOVED.
_PENDING_SPEC_RENAMES = {
    "update_performance_index": "provide_performance_feedback",
    "list_authorized_properties": "the property-list family (list_property_lists / get_property_list)",
}


def _spec_tool_names() -> set[str]:
    """Tool names the PINNED adcp SDK defines.

    ADCP_TOOL_DEFINITIONS is a LIST OF DICTS, not a mapping -- reading it as one
    silently yields the definitions' keys instead of the tool names, which reports
    every real tool as missing.
    """
    return {t["name"] for t in ADCP_TOOL_DEFINITIONS}


def test_the_map_was_actually_found():
    """Guard the guard: an empty read would make every assertion below vacuous."""
    skills = registered_skill_names()
    assert len(skills) >= 10, f"only found {sorted(skills)} — the AST read is not seeing the map"


def test_every_skill_names_a_spec_tool():
    """No skill may exist that the pinned spec does not define."""
    off_spec = registered_skill_names() - _spec_tool_names() - set(_PENDING_SPEC_RENAMES)
    assert not off_spec, (
        f"A2A skills not defined by the pinned AdCP version: {sorted(off_spec)}. "
        f"tool === skill === REST RPC route — a skill outside the spec is a private surface. "
        f"Rename it onto its spec operation, or drop it."
    )


@pytest.mark.parametrize("skill", sorted(_PENDING_SPEC_RENAMES))
def test_pending_rename_entries_are_not_stale(skill):
    """An allowlisted rename must still be off-spec, and its target must be a real tool."""
    spec = _spec_tool_names()
    assert skill not in spec, f"{skill!r} IS defined by the pinned spec now — remove it from _PENDING_SPEC_RENAMES."
    assert skill in registered_skill_names(), (
        f"{skill!r} is no longer a registered skill — remove it from _PENDING_SPEC_RENAMES."
    )


def test_the_rename_targets_exist_in_the_spec():
    """The rename target for update_performance_index must be a real pinned tool."""
    assert "provide_performance_feedback" in _spec_tool_names(), (
        "the documented rename target is not a tool the pinned SDK defines — "
        "re-check the target before renaming production onto it"
    )
