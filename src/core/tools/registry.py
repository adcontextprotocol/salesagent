"""The one place a tool's WIRING is declared: which transports reach it, and what runs it.

A tool is declared between three and four times today -- ``_register_tool`` in
``src/core/main.py``, an ``AgentSkill`` literal plus a ``skill_handlers`` row in the A2A
server, and a ``@router.post``/``@router.put`` decorator in ``src/routes/api_v1.py`` -- and
each declaration can disagree with the others. :data:`TOOLS` is the single declaration those
three become derived from; ``docs/design/one-tool-registry.md`` is the design, and its
"Migration order" is the sequence: this module is step 1 and changes no behaviour, because
registration still lives where it always did. Steps 6-8 delete the three hand-written
declarations and generate them from here.

Until they do, these rows are hand-written and therefore capable of being wrong. What makes
them right is not review: ``tests/unit/test_architecture_tool_registry_agrees.py`` compares
every axis of every row against the LIVE registration objects the three transports route
real traffic through. A row that disagrees is a defect in the ROW.

:class:`ToolSpec` says where a tool is reachable and what runs it. It says nothing about the
tool's SHAPE -- the DTO says that itself, which is why ``dto`` is a reference to a model and
not a description of one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from adcp.types import GetAdcpCapabilitiesRequest as LibraryGetAdcpCapabilitiesRequest
from adcp.types import ListTasksRequest as LibraryListTasksRequest
from pydantic import BaseModel

from src.core.schemas import (
    CompleteTaskRequestLocal,
    CreateMediaBuyRequest,
    GetMediaBuyDeliveryRequest,
    GetMediaBuysRequest,
    GetProductsRequest,
    GetTaskRequest,
    ListAccountsRequest,
    ListAuthorizedPropertiesRequest,
    ListCreativeFormatsRequest,
    ListCreativesRequest,
    SyncAccountsRequest,
    SyncCreativesRequest,
    UpdateMediaBuyRequest,
    UpdatePerformanceIndexRequest,
)
from src.core.tools.accounts import _list_accounts_impl, _sync_accounts_impl
from src.core.tools.capabilities import _get_adcp_capabilities_impl
from src.core.tools.creative_formats import _list_creative_formats_impl
from src.core.tools.creatives._sync import _sync_creatives_impl
from src.core.tools.creatives.listing import _list_creatives_impl
from src.core.tools.media_buy_create import _create_media_buy_impl
from src.core.tools.media_buy_delivery import _get_media_buy_delivery_impl
from src.core.tools.media_buy_list import _get_media_buys_impl
from src.core.tools.media_buy_update import _update_media_buy_impl
from src.core.tools.performance import _update_performance_index_impl
from src.core.tools.products import _get_products_impl
from src.core.tools.properties import _list_authorized_properties_impl
from src.core.tools.task_management import complete_task, get_task, list_tasks


@dataclass(frozen=True)
class RestBinding:
    """How one tool is reached over REST.

    ``verb`` is deliberately narrow. REST is this project's own surface, not AdCP's, and an
    AdCP tool call carries a request body -- so a verb that cannot is not a shape this
    registry can express. ``GET /capabilities`` was the one route that needed it, and the
    answer was deleting the route (design doc, "Decisions this forces"), not widening the
    type: it was a
    second shape for a tool that already had one, taking no body, so a buyer could not send
    ``protocols``, ``context`` or ``ext`` that the same tool accepted everywhere else.

    ``path`` is written WITHOUT the router's ``/api/v1`` prefix -- the prefix belongs to the
    router, is declared there once, and repeating it on thirteen rows would be thirteen more
    places for it to drift.
    """

    verb: Literal["POST", "PUT"]
    path: str
    path_fields: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolSpec:
    """One tool's wiring: what runs it, what shape it takes, and where it is reachable."""

    dto: type[BaseModel]
    impl: Callable[..., Any]
    rest: RestBinding | None
    a2a: bool
    #: Whether a request reaches the implementation without an authenticated caller. A
    #: property of the TOOL, not of a transport: it cannot be true that a tool needs a
    #: caller over REST and not over MCP. Today it is declared four times -- the REST
    #: route's auth dependency, ``require_valid_token`` in the raw wrapper,
    #: ``AUTH_OPTIONAL_TOOLS`` and ``DISCOVERY_SKILLS`` -- and for ``list_accounts`` they
    #: disagree; see the divergence pin in the agreement test.
    auth: Literal["required", "optional"] = "required"
    #: Reserved for the three transport-derived values the boundary supplies and a buyer
    #: never can (``context_id``, ``raw_wire_payload``, ``request_hash``). Empty until step
    #: 6 generates the call, and a closed set by then -- an open ``**kwargs`` at that seam
    #: would let a transport hand an implementation anything at all.
    transport_derived: frozenset[str] = field(default_factory=frozenset)


#: Every tool this seller implements, keyed by its AdCP tool name.
#:
#: ``rest=None`` on the three task tools records today's REST surface, which is what the
#: agreement assertion grades against. It is NOT a statement that they should stay off
#: REST: every tool is meant to be reachable over REST, and they acquire a ``RestBinding``
#: at the migration step that GENERATES routes from tool names, so the row
#: and the route appear together. Declaring the binding here first would make the registry
#: disagree with the live routes by three, and the only way to keep the assertion green
#: would be a hand-written three-row exception inside the very thing that proves the rows
#: are right. Writing the routes by hand instead is the duplication this registry deletes.
TOOLS: Mapping[str, ToolSpec] = {
    "get_adcp_capabilities": ToolSpec(
        dto=LibraryGetAdcpCapabilitiesRequest,
        impl=_get_adcp_capabilities_impl,
        rest=RestBinding("POST", "/capabilities"),
        a2a=True,
        auth="optional",
    ),
    "get_products": ToolSpec(
        dto=GetProductsRequest,
        impl=_get_products_impl,
        rest=RestBinding("POST", "/products"),
        a2a=True,
        auth="optional",
    ),
    "list_creative_formats": ToolSpec(
        dto=ListCreativeFormatsRequest,
        impl=_list_creative_formats_impl,
        rest=RestBinding("POST", "/creative-formats"),
        a2a=True,
        auth="optional",
    ),
    "list_authorized_properties": ToolSpec(
        dto=ListAuthorizedPropertiesRequest,
        impl=_list_authorized_properties_impl,
        rest=RestBinding("POST", "/authorized-properties"),
        a2a=True,
        auth="optional",
    ),
    # auth="required" against three declarations that say optional. The tool rejects an
    # unauthenticated caller on every transport -- AdCP 3.1.1 BR-UC-011 @T-UC-011-list-unauth
    # requires AUTH_MISSING, and _list_accounts_impl raises it via require_principal_id. The
    # three that say otherwise are wrong and are pinned as such by the agreement test.
    "list_accounts": ToolSpec(
        dto=ListAccountsRequest,
        impl=_list_accounts_impl,
        rest=RestBinding("POST", "/accounts"),
        a2a=True,
    ),
    "sync_accounts": ToolSpec(
        dto=SyncAccountsRequest,
        impl=_sync_accounts_impl,
        rest=RestBinding("POST", "/accounts/sync"),
        a2a=True,
    ),
    "create_media_buy": ToolSpec(
        dto=CreateMediaBuyRequest,
        impl=_create_media_buy_impl,
        rest=RestBinding("POST", "/media-buys"),
        a2a=True,
    ),
    "update_media_buy": ToolSpec(
        dto=UpdateMediaBuyRequest,
        impl=_update_media_buy_impl,
        rest=RestBinding("PUT", "/media-buys/{media_buy_id}", frozenset({"media_buy_id"})),
        a2a=True,
    ),
    "get_media_buys": ToolSpec(
        dto=GetMediaBuysRequest,
        impl=_get_media_buys_impl,
        rest=RestBinding("POST", "/media-buys/query"),
        a2a=True,
    ),
    "get_media_buy_delivery": ToolSpec(
        dto=GetMediaBuyDeliveryRequest,
        impl=_get_media_buy_delivery_impl,
        rest=RestBinding("POST", "/media-buys/delivery"),
        a2a=True,
    ),
    "sync_creatives": ToolSpec(
        dto=SyncCreativesRequest,
        impl=_sync_creatives_impl,
        rest=RestBinding("POST", "/creatives/sync"),
        a2a=True,
    ),
    "list_creatives": ToolSpec(
        dto=ListCreativesRequest,
        impl=_list_creatives_impl,
        rest=RestBinding("POST", "/creatives"),
        a2a=True,
    ),
    "update_performance_index": ToolSpec(
        dto=UpdatePerformanceIndexRequest,
        impl=_update_performance_index_impl,
        rest=RestBinding("POST", "/performance-index"),
        a2a=True,
    ),
    # The three task tools implement themselves: their MCP wrapper reaches no ``_impl``,
    # so the wrapper IS the implementation. Step 6 is where that stops being true.
    "list_tasks": ToolSpec(dto=LibraryListTasksRequest, impl=list_tasks, rest=None, a2a=False),
    "get_task": ToolSpec(dto=GetTaskRequest, impl=get_task, rest=None, a2a=False),
    "complete_task": ToolSpec(dto=CompleteTaskRequestLocal, impl=complete_task, rest=None, a2a=False),
}
