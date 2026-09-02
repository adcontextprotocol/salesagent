"""MediaBuyListEnv — integration test environment for _get_media_buys_impl.

Minimal harness — list operation has no adapter calls, just DB queries.
No patches needed (pure DB read).

Requires: integration_db fixture + existing media buys in the DB.

The dispatch itself lives in ``MediaBuyListDispatchMixin`` so a composite env can
reuse it verbatim: ``MediaBuyCreateListEnv`` (tests/harness/media_buy_create_list.py)
needs the SAME get_media_buys dispatch alongside the create path, and a second copy
of these four bodies would be a DRY violation — the next fix to the list dispatch
would land in one copy only.

GH #1335, GH #1900
"""

from __future__ import annotations

from typing import Any

from src.core.schemas._base import GetMediaBuysRequest, GetMediaBuysResponse
from tests.harness._base import IntegrationEnv


class MediaBuyListDispatchMixin:
    """get_media_buys dispatch across impl/A2A/MCP/REST.

    Deliberately named ``_call_list_*`` rather than ``call_*``: the composite env
    inherits create dispatch from ``MediaBuyCreateEnv`` under those public names
    and routes to these explicitly, so neither tool's dispatch can shadow the
    other's by MRO accident.
    """

    def _call_list_impl(self, **kwargs: Any) -> GetMediaBuysResponse:
        """Call _get_media_buys_impl with real DB."""
        from src.core.tools.media_buy_list import _get_media_buys_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)
        include_snapshot = kwargs.pop("include_snapshot", False)

        req = kwargs.pop("req", None)
        if req is None:
            req = GetMediaBuysRequest(**kwargs)

        return _get_media_buys_impl(req=req, identity=identity, include_snapshot=include_snapshot)

    def _call_list_a2a(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL A2A pipeline (on_message_send).

        The production A2A path is ``_handle_get_media_buys_skill`` —
        ``get_media_buys_raw`` has ZERO production callers, so dispatching to it
        here gave false confidence (#1417): a boundary fix on the raw
        wrapper made 'A2A' tests green while the real skill handler still
        leaked bare ValidationErrors.
        """
        return self._run_a2a_handler("get_media_buys", GetMediaBuysResponse, **kwargs)

    def _call_list_mcp(self, **kwargs: Any) -> Any:
        """Dispatch get_media_buys through the REAL FastMCP ``Client`` pipeline.

        Was ``_run_mcp_wrapper``, which is deprecated precisely because it hand-builds
        a mock Context and calls the wrapper directly: it skips the middleware,
        TypeAdapter validation and the token→DB→identity auth chain, and — the reason
        it had to change here — it stashes NO ``wire_response``. Every MCP assertion
        on this tool therefore graded a re-serialized typed payload rather than the
        bytes a buyer receives, which is exactly the blind spot GH #1900 slipped
        through. ``_run_mcp_client`` stashes ``structured_content``, the real MCP wire.
        """
        return self._run_mcp_client("get_media_buys", GetMediaBuysResponse, **kwargs)


class MediaBuyListEnv(MediaBuyListDispatchMixin, IntegrationEnv):
    """Integration test environment for _get_media_buys_impl.

    No patches — list is read-only, no external service calls.
    """

    EXTERNAL_PATCHES: dict[str, str] = {}
    # No REST_ENDPOINT, deliberately: get_media_buys has NO REST route. One was
    # declared here for a path that does not exist anywhere in src/, with a body
    # builder and a response parser hanging off it — so the machinery read as though
    # the transport were available, and a REST parametrization would have failed as
    # if production were broken rather than as if the route were absent. The sibling
    # env states the same fact as a loud refusal
    # (`media_buy_create_list.py::build_rest_body`), which covers callers that ask.

    def _configure_mocks(self) -> None:
        """No mocks needed for read-only list operation."""

    def call_impl(self, **kwargs: Any) -> GetMediaBuysResponse:
        return self._call_list_impl(**kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        return self._call_list_a2a(**kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        return self._call_list_mcp(**kwargs)
