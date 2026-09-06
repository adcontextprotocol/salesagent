"""Guard: an implementation may declare only parameters the boundary can supply.

Every transport reaches an implementation through :func:`src.core.tools._boundary.invoke`,
which calls it as ``impl(req=..., identity=..., **extra)``. ``extra`` is not open: it carries
the transport-derived values the boundary knows how to obtain, and today that is
``context_id`` alone. A parameter outside that set can never be filled by a buyer's request,
so it silently takes its default on every call -- the tool accepts something no caller can
send.

This used to scan each ``*_raw`` and MCP wrapper for the arguments it forwarded to its
``_impl``, because there were fifteen wrappers and each could drop a parameter the others
passed. There are none: one call site passes one argument list, so "does the wrapper forward
everything" is answered by construction and the only question left is whether the
implementation asks for something no wrapper exists to give it.

The previous form is also the reason this rule needs a guard at all. Its wrapper lookup
returned None when it could not find a wrapper, and returning None meant "nothing to check",
so the day the wrappers were deleted it went green while grading nothing.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.tools.registry import TOOLS

#: What :func:`src.core.tools._boundary.invoke` passes. ``req`` and ``identity`` are
#: unconditional; ``context_id`` is the one member of ``extra``, read from MCP's context state
#: by ``main._call_tool`` for the implementations that declare it.
BOUNDARY_SUPPLIED_PARAMS = frozenset({"req", "identity", "context_id"})


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_impl_declares_only_boundary_supplied_parameters(tool_name: str) -> None:
    declared = set(inspect.signature(TOOLS[tool_name].impl).parameters)
    unfillable = declared - BOUNDARY_SUPPLIED_PARAMS
    assert unfillable == set(), (
        f"{tool_name}'s implementation declares {sorted(unfillable)}, which no transport "
        f"supplies: the boundary calls impl(req=..., identity=..., **extra) and extra carries "
        f"only {sorted(BOUNDARY_SUPPLIED_PARAMS - {'req', 'identity'})}. Put the value on the "
        f"request DTO if a buyer sends it, or teach the boundary to derive it if a transport "
        f"knows it."
    )


@pytest.mark.parametrize("tool_name", sorted(TOOLS))
def test_impl_accepts_the_request_and_the_identity(tool_name: str) -> None:
    """The two the boundary always passes must be accepted, by these names."""
    declared = set(inspect.signature(TOOLS[tool_name].impl).parameters)
    missing = {"req", "identity"} - declared
    assert missing == set(), (
        f"{tool_name}'s implementation does not accept {sorted(missing)}. The boundary passes "
        f"both by keyword on every call, so an implementation missing either raises TypeError "
        f"on the first request."
    )
