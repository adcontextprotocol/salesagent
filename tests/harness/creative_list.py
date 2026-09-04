"""CreativeListEnv — integration test environment for _list_creatives_impl.

Patches: audit logger ONLY.
Real: get_db_session, CreativeRepository, all query building (all hit real DB).

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CreativeListEnv() as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="p1")
            creative = CreativeFactory(tenant=tenant, principal=principal)

            response = env.call_impl()
            assert len(response.creatives) == 1

Available mocks via env.mock:
    "audit_logger" -- get_audit_logger (module-level import in listing.py)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.core.schemas import ListCreativesResponse
from tests.harness._base import IntegrationEnv


class CreativeListEnv(IntegrationEnv):
    """Integration test environment for _list_creatives_impl.

    Only mocks the audit logger. Everything else is real:
    - Real get_db_session -> real DB queries
    - Real CreativeRepository -> real DB reads
    - Real query building, filtering, pagination
    """

    # Dispatch declaration: the base owns call_mcp/call_a2a.
    MCP_TOOL = "list_creatives"
    A2A_SKILL = "list_creatives"
    RESPONSE_MODEL = ListCreativesResponse

    EXTERNAL_PATCHES = {
        "audit_logger": "src.core.tools.creatives.listing.get_audit_logger",
    }
    REST_ENDPOINT = "/api/v1/creatives"

    def _configure_mocks(self) -> None:
        """Set up happy-path defaults for audit logger."""
        mock_logger = MagicMock()
        self.mock["audit_logger"].return_value = mock_logger

    def call_impl(self, **kwargs: Any) -> ListCreativesResponse:
        """Call _list_creatives_impl with real DB.

        ``_list_creatives_impl`` takes ``(req, identity)`` and nothing else, so this method
        has no out-of-band bag to keep: ``include_performance`` / ``include_sub_assets`` are
        gone (adcp 3.10 removed both from the spec and nothing read them), and ``format`` /
        ``page`` are ListCreativesInternal fields set on the built model below. Accepts
        either a pre-built ``req=`` or the request fields to build one from (matching
        MediaBuyCreateEnv).
        """
        from src.core.tools.creatives.listing import _build_list_creatives_request, _list_creatives_impl

        self._commit_factory_data()
        identity = kwargs.pop("identity", self.identity)

        req = kwargs.pop("req", None)
        if req is None:
            # ``format`` and ``page`` are NOT builder parameters. They are
            # ListCreativesInternal fields, and the builder's signature is the only thing
            # keeping them off the REST body and the A2A parameter bag (both derive from
            # DTO fields INTERSECT those parameters). A caller that drives the reader sets
            # them on the model the builder returns, which is what this does -- so the
            # harness exercises the same seam an internal caller in ``src/`` would.
            internal = {name: kwargs.pop(name) for name in ("format", "page") if name in kwargs}
            req = _build_list_creatives_request(**kwargs)
            if internal:
                req = req.model_copy(update=internal)

        return _list_creatives_impl(req=req, identity=identity)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to ListCreativesBody shape for REST POST.

        The carried key set is sourced from the ARTIFACT — ``ListCreativesBody``'s
        own ``model_fields`` — not from a hand-list. The hand-list this replaces
        named four keys (media_buy_id, media_buy_ids, status, format) plus filters,
        so every other field the REST route genuinely accepts (tags, search, dates,
        fields, include_assignments, page/limit, sort_by/sort_order) was dropped
        BEFORE the request left the harness: a scenario sending them graded MCP and
        A2A for real and graded nothing on REST. Deriving the set from the body model
        means a field added to the route is carried here without a harness edit.

        The structured ``filters`` object travels as an already-serialized JSON dict
        (the body field is typed ``dict`` and coerced to CreativeFilters server-side);
        it needs no special case beyond being one of the model's fields.
        """
        from src.routes.api_v1 import ListCreativesBody

        return {
            key: value for key, value in kwargs.items() if key in ListCreativesBody.model_fields and value is not None
        }

    def parse_rest_response(self, data: dict[str, Any]) -> ListCreativesResponse:
        """Parse REST JSON into ListCreativesResponse."""
        return ListCreativesResponse(**data)
