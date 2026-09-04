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
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from src.core.schemas import (
    CompleteTaskRequest,
    CreateMediaBuyRequest,
    GetAdcpCapabilitiesRequest,
    GetMediaBuyDeliveryRequest,
    GetMediaBuysRequest,
    GetProductsRequest,
    GetTaskRequest,
    ListAccountsRequest,
    ListCreativeFormatsRequest,
    ListCreativesRequest,
    ListTasksRequest,
    SyncAccountsRequest,
    SyncCreativesRequest,
    UpdateMediaBuyRequest,
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
from src.core.tools.products import _get_products_impl
from src.core.tools.task_management import _complete_task_impl, _get_task_impl, _list_tasks_impl


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
    a2a: bool = True
    #: Whether a request reaches the implementation without an authenticated caller. A
    #: property of the TOOL, not of a transport: it cannot be true that a tool needs a
    #: caller over REST and not over MCP. Today it is declared four times -- the REST
    #: route's auth dependency, ``require_valid_token`` in the raw wrapper,
    #: ``AUTH_OPTIONAL_TOOLS`` and ``DISCOVERY_SKILLS`` -- and for ``list_accounts`` they
    #: disagree; see the divergence pin in the agreement test.
    auth: Literal["required", "optional"] = "required"


#: Every tool this seller implements, keyed by its AdCP tool name.
TOOLS: Mapping[str, ToolSpec] = {
    "get_adcp_capabilities": ToolSpec(
        dto=GetAdcpCapabilitiesRequest,
        impl=_get_adcp_capabilities_impl,
        rest=RestBinding("POST", "/capabilities"),
        auth="optional",
    ),
    "get_products": ToolSpec(
        dto=GetProductsRequest,
        impl=_get_products_impl,
        rest=RestBinding("POST", "/products"),
        auth="optional",
    ),
    "list_creative_formats": ToolSpec(
        dto=ListCreativeFormatsRequest,
        impl=_list_creative_formats_impl,
        rest=RestBinding("POST", "/creative-formats"),
        auth="optional",
    ),
    "list_accounts": ToolSpec(
        dto=ListAccountsRequest,
        impl=_list_accounts_impl,
        rest=RestBinding("POST", "/accounts"),
    ),
    "sync_accounts": ToolSpec(
        dto=SyncAccountsRequest,
        impl=_sync_accounts_impl,
        rest=RestBinding("POST", "/accounts/sync"),
    ),
    "create_media_buy": ToolSpec(
        dto=CreateMediaBuyRequest,
        impl=_create_media_buy_impl,
        rest=RestBinding("POST", "/media-buys"),
    ),
    "update_media_buy": ToolSpec(
        dto=UpdateMediaBuyRequest,
        impl=_update_media_buy_impl,
        rest=RestBinding("PUT", "/media-buys/{media_buy_id}", frozenset({"media_buy_id"})),
    ),
    "get_media_buys": ToolSpec(
        dto=GetMediaBuysRequest,
        impl=_get_media_buys_impl,
        rest=RestBinding("POST", "/media-buys/query"),
    ),
    "get_media_buy_delivery": ToolSpec(
        dto=GetMediaBuyDeliveryRequest,
        impl=_get_media_buy_delivery_impl,
        rest=RestBinding("POST", "/media-buys/delivery"),
    ),
    "sync_creatives": ToolSpec(
        dto=SyncCreativesRequest,
        impl=_sync_creatives_impl,
        rest=RestBinding("POST", "/creatives/sync"),
    ),
    "list_creatives": ToolSpec(
        dto=ListCreativesRequest,
        impl=_list_creatives_impl,
        rest=RestBinding("POST", "/creatives"),
    ),
    "list_tasks": ToolSpec(
        dto=ListTasksRequest,
        impl=_list_tasks_impl,
        rest=RestBinding("POST", "/tasks/query"),
    ),
    "get_task": ToolSpec(
        dto=GetTaskRequest,
        impl=_get_task_impl,
        rest=RestBinding("POST", "/tasks/{task_id}", frozenset({"task_id"})),
    ),
    "complete_task": ToolSpec(
        dto=CompleteTaskRequest,
        impl=_complete_task_impl,
        rest=RestBinding("POST", "/tasks/{task_id}/complete", frozenset({"task_id"})),
    ),
}
