"""``TOOLS`` must agree with all three live declarations of every tool.

``src/core/tools/registry.py`` is hand-written today. It stops being hand-written when the
migration in ``docs/design/one-tool-registry.md`` generates MCP registration, the A2A card
and dispatch, and the REST routes FROM it -- until then a row can be wrong, and nothing
about reviewing a table of sixteen entries catches that. This does.

Every axis is compared against the object PRODUCTION ROUTES REAL TRAFFIC THROUGH:
``mcp.list_tools()`` is what an MCP client sees, ``create_agent_card().skills`` is what an
A2A buyer's discovery request receives, ``skill_handlers`` is what A2A dispatch consults,
and ``app.routes`` is FastAPI's own dispatch table. Nothing here re-reads a hand-maintained
copy of any of them, because a check against a second copy grades the copy.

**There is no per-row exception anywhere below, and adding one would defeat the file.** A
hand-written carve-out inside the thing that proves the rows are right is the same defect,
one level up -- it is how a wrong row survives review. When a row was awkward to express,
the answer was to change what is declared, not what is checked: ``GET /capabilities`` could
not be a ``RestBinding``, so the route was deleted; the three task tools have no REST route,
so their rows say ``rest=None`` rather than the assertion learning to expect three misses.

The one thing this file records rather than grades is
:func:`test_list_accounts_is_the_only_tool_whose_auth_declarations_disagree` -- a pin, not an
exemption: the ROW is graded like every other row, and the pin fails the moment a second
tool diverges or the first stops diverging.
"""

import asyncio
import inspect
import re
from typing import Any

import pytest

from src.a2a_server.adcp_a2a_server import DISCOVERY_SKILLS, create_agent_card
from src.core.auth_context import require_auth, resolve_auth
from src.core.main import mcp
from src.core.mcp_auth_middleware import AUTH_OPTIONAL_TOOLS
from src.core.tools._announced_shape import impl_for, request_model_for
from src.core.tools.registry import TOOLS
from src.routes.api_v1 import router
from tests.harness.address_table import ADDRESS_TABLE
from tests.harness.transport import Transport
from tests.helpers.a2a_skill_map import registered_skill_names

#: The one tool whose four auth declarations do not agree. See the pin at the bottom.
_AUTH_DIVERGENT = "list_accounts"


def _registered_wrappers() -> dict[str, Any]:
    """tool name -> the function ``_register_tool`` registered, with error logging unwrapped.

    ``_register_tool`` registers ``with_error_logging(fn)``, whose bytecode names only the
    error handler -- so every derivation below would resolve nothing at all if it read the
    registered object directly. Unwrapping is what makes the reads see the tool.
    """
    return {t.name: getattr(t.fn, "__wrapped__", t.fn) for t in asyncio.run(mcp.list_tools())}


def _names_the_same(declared: Any, derived: Any) -> bool:
    """Whether a row and a derivation name the SAME function or class.

    By ``__module__``/``__qualname__`` rather than by ``is``, because
    ``importlib.reload`` builds fresh objects for every function in a module and leaves
    earlier references pointing at the originals -- ``tests/unit/test_budget_guardrails.py``
    reloads ``src.core.tools.media_buy_update`` to test an env override, so under a random
    test order the row and the live registration hold two ``_update_media_buy_impl`` objects
    that differ only in address.

    This grades exactly as strictly: a row naming the wrong callable names a different
    qualname, and a row naming a same-named callable from another module names a different
    module. What it stops grading is object churn, which was never the obligation.
    """
    return (declared.__module__, declared.__qualname__) == (derived.__module__, derived.__qualname__)


def _rest_routes_by_path() -> dict[str, Any]:
    """REST path template -> route, joined on PATH rather than on handler name.

    Handler names are not tool names (``post_capabilities`` implements
    ``get_adcp_capabilities``), and resolving that identity is
    ``tests/harness/address_table.py``'s job, done once, for everyone. Joining here on the
    path template means this file never learns a handler name and cannot disagree with the
    address table about which route is which tool.
    """
    return {r.path: r for r in router.routes if getattr(r, "endpoint", None)}


# ---------------------------------------------------------------------------
# Guard the guard: every assertion below derives from one of these four reads,
# so a read that silently returns nothing would make the whole file vacuous.
# ---------------------------------------------------------------------------


def test_the_four_live_reads_see_something():
    assert len(_registered_wrappers()) == len(TOOLS), "MCP read is not seeing the registered tools"
    assert len(create_agent_card().skills) >= 10, "agent card read is not seeing the skills"
    assert len(registered_skill_names()) >= 10, "skill_handlers AST read is not seeing the map"
    assert len(ADDRESS_TABLE.all_tools(Transport.REST)) >= 10, "REST read is not seeing the routes"


# ---------------------------------------------------------------------------
# MCP: the registered tool set, each tool's DTO, and each tool's implementation
# ---------------------------------------------------------------------------


def test_the_registry_holds_exactly_the_registered_tools():
    """A tool registered on MCP and absent from TOOLS is a tool nothing can derive."""
    assert set(TOOLS) == set(_registered_wrappers())


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_row_names_the_dto_its_tool_announces(tool):
    """``dto`` must be the model ``_register_tool`` resolved -- the announced shape."""
    wrapper = _registered_wrappers()[tool]
    assert _names_the_same(TOOLS[tool].dto, request_model_for(wrapper))


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_row_names_the_callable_its_wrapper_dispatches_to(tool):
    """``impl`` must be what the registered wrapper actually reaches, read from bytecode."""
    wrapper = _registered_wrappers()[tool]
    assert _names_the_same(TOOLS[tool].impl, impl_for(wrapper))


def test_the_tools_that_implement_themselves_reach_no_implementation():
    """Pin the degenerate branch of the ``impl`` walk from the DERIVED side.

    Three rows name their own wrapper as ``impl``. That is the walk terminating, not an
    exception -- but it is also the branch a broken derivation falls into silently, so the
    count and the reason are both fixed here: a row lands in it only by reaching no
    ``_impl`` at all, and a fourth arrival means a wrapper stopped dispatching.
    """
    wrappers = _registered_wrappers()
    self_implementing = {t for t, spec in TOOLS.items() if _names_the_same(spec.impl, wrappers[t])}
    assert self_implementing == {"list_tasks", "get_task", "complete_task"}
    for tool in self_implementing:
        named = [n for n in wrappers[tool].__code__.co_names if re.match(r"^\w+_raw$|^_\w+_impl$", n)]
        assert not named, f"{tool} names dispatch steps {named} — it does not implement itself"


# ---------------------------------------------------------------------------
# A2A: the agent card AND the dispatch map, which are two declarations
# ---------------------------------------------------------------------------


def test_the_a2a_rows_are_exactly_the_advertised_skills():
    assert {t for t, spec in TOOLS.items() if spec.a2a} == {s.id for s in create_agent_card().skills}


def test_the_a2a_rows_are_exactly_the_dispatchable_skills():
    """The card and the dispatch map are declared separately and can disagree with each
    other; the row has to match both, which is what makes it the single declaration."""
    assert {t for t, spec in TOOLS.items() if spec.a2a} == registered_skill_names()


# ---------------------------------------------------------------------------
# REST: which tools are routed, and with what verb, path and path fields
# ---------------------------------------------------------------------------


def test_the_rest_rows_are_exactly_the_routed_tools():
    assert {t for t, spec in TOOLS.items() if spec.rest} == ADDRESS_TABLE.all_tools(Transport.REST)


@pytest.mark.parametrize("tool", sorted(t for t, s in TOOLS.items() if s.rest))
def test_each_rest_row_matches_its_live_route(tool):
    """Verb, full path and path fields, against FastAPI's own dispatch table."""
    binding = TOOLS[tool].rest
    address = ADDRESS_TABLE.resolve(tool, Transport.REST)
    assert binding.verb == address.method.upper()
    assert router.prefix + binding.path == address.path_template
    assert binding.path_fields == frozenset(address.path_params)


# ---------------------------------------------------------------------------
# Auth: a property of the tool, declared today on the route and in two sets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", sorted(t for t, s in TOOLS.items() if s.rest))
def test_each_rest_row_matches_the_auth_its_route_requires(tool):
    """``auth`` against the REST route's dependency -- compared by IDENTITY.

    ``resolve_auth`` and ``require_auth`` are ``Depends`` singletons; equality on them is
    not defined, so ``==`` would compare two distinct objects and pass for neither.
    """
    route = _rest_routes_by_path()[ADDRESS_TABLE.resolve(tool, Transport.REST).path_template]
    dependency = inspect.signature(route.endpoint).parameters["identity"].default
    assert dependency is (resolve_auth if TOOLS[tool].auth == "optional" else require_auth)


@pytest.mark.parametrize("tool", sorted(set(TOOLS) - {_AUTH_DIVERGENT}))
def test_each_row_matches_the_auth_mcp_enforces(tool):
    """``auth`` against ``AUTH_OPTIONAL_TOOLS`` -- the one declaration covering all 16."""
    assert TOOLS[tool].auth == ("optional" if tool in AUTH_OPTIONAL_TOOLS else "required")


@pytest.mark.parametrize("tool", sorted(t for t, s in TOOLS.items() if s.a2a and t != _AUTH_DIVERGENT))
def test_each_a2a_row_matches_the_auth_a2a_enforces(tool):
    """``auth`` against ``DISCOVERY_SKILLS``, which gates A2A dispatch the same way."""
    assert TOOLS[tool].auth == ("optional" if tool in DISCOVERY_SKILLS else "required")


def test_list_accounts_is_the_only_tool_whose_auth_declarations_disagree():
    """``list_accounts`` is declared auth-optional three times and auth-required once.

    The row says ``required`` and is graded as such by
    :func:`test_each_rest_row_matches_the_auth_its_route_requires`; it is the three optional
    declarations that are wrong. The tool rejects an unauthenticated caller on every
    transport -- AdCP 3.1.1 ``BR-UC-011-manage-accounts.feature`` ``@T-UC-011-list-unauth``
    requires an error variant with ``AUTH_MISSING``, and ``_list_accounts_impl`` raises it
    through ``require_principal_id`` before reading anything.

    Fixing the three is a wire change (the identical rejection moves from the implementation
    up to the middleware) and belongs to the migration steps that make MCP and A2A derive
    their auth from ``ToolSpec.auth``, at which point the two sets stop existing. Recording
    it here rather than exempting it keeps the divergence loud and BOUNDED: this fails if a
    second tool joins, and it fails when the first one is fixed.
    """
    divergent = {tool for tool, spec in TOOLS.items() if (spec.auth == "optional") != (tool in AUTH_OPTIONAL_TOOLS)}
    assert divergent == {_AUTH_DIVERGENT}
    assert _AUTH_DIVERGENT in DISCOVERY_SKILLS
    assert TOOLS[_AUTH_DIVERGENT].auth == "required"
