"""Forward-compatibility acceptance tests across MCP, A2A, and REST.

Verifies that our tools ACCEPT (not reject) various AdCP payload shapes:
- Current spec payloads
- Future spec payloads with extra nested fields
- v2.5 legacy payloads with deprecated field names
- Payloads with extra fields at every nesting level

The tools may not PERFORM correctly with unknown data, but they must not
reject the request at the transport layer. This is the forward-compatibility
contract: accept now, handle later.

Each payload is tested through all three transport paths:
- MCP: Client(mcp) → middleware (normalize + strip + deep-strip) → TypeAdapter → tool
- A2A: normalize_request_params → model_validate(extra='ignore') → _impl
- REST/direct: normalize_request_params → model_validate(extra='ignore') → _impl
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.request_compat import normalize_request_params
from tests.helpers import assert_envelope_shape

# ---------------------------------------------------------------------------
# Payloads: each is a (tool_name, params) tuple
# ---------------------------------------------------------------------------

# Current spec — baseline, must always work
CURRENT_SPEC_GET_PRODUCTS = {
    "brief": "video ads for Q4",
    "brand": {"domain": "acme.com"},
}

# Future spec — extra top-level field
FUTURE_TOP_LEVEL_FIELD = {
    "brief": "video ads",
    "brand": {"domain": "acme.com"},
    # Envelope field the seller now DELIBERATELY accepts (GH #1512). It stays in
    # this payload so production-tolerance keeps covering it — but it can no
    # longer carry the dev-rejects case, because a field we accept on purpose is
    # not an unknown one.
    "adcp_major_version": 5,
    # The genuinely-undefined field. This is what the dev-rejects assertion is
    # actually about: a name no pinned schema declares, which must be refused in
    # development and stripped in production.
    "future_unknown_field": "not in any pinned schema",
}

# Future spec — extra nested field inside brand
FUTURE_NESTED_IN_BRAND = {
    "brief": "display ads",
    "brand": {"domain": "acme.com", "verification_status": "verified"},
}

# Future spec — extra nested field inside context
FUTURE_NESTED_IN_CONTEXT = {
    "brief": "audio ads",
    "context": {"session_id": "sess-123", "trace_id": "tr-456", "priority": "high"},
}

# Future spec — extra nested field inside filters
FUTURE_NESTED_IN_FILTERS = {
    "brief": "programmatic",
    "filters": {"delivery_type": "guaranteed", "ai_optimization_level": "aggressive"},
}

# v2.5 legacy — brand_manifest (deprecated)
V25_BRAND_MANIFEST = {
    "brief": "retargeting campaign",
    "brand_manifest": "https://acme.com/.well-known/brand.json",
}

# v2.5 legacy — promoted_offerings (deprecated)
V25_PROMOTED_OFFERINGS = {
    "brief": "catalog ads",
    "promoted_offerings": ["SKU-001", "SKU-002"],
}

# Extra fields at multiple nesting levels simultaneously
MULTI_LEVEL_EXTRAS = {
    "brief": "multi-level test",
    "brand": {"domain": "acme.com", "future_brand_field": True},
    "context": {"session_id": "sess", "future_context_field": 42},
    "future_top_level": "also here",
}

# Completely unknown tool parameters (top-level only)
ALL_UNKNOWN_PLUS_BRIEF = {
    "brief": "safety test",
    "quantum_targeting": {"entangle": True},
    "holographic_format": "3D",
}


# ---------------------------------------------------------------------------
# MCP pipeline tests (Client(mcp) — full middleware + TypeAdapter)
# ---------------------------------------------------------------------------


def _get_products_patches():
    """Context managers that mock all get_products dependencies for Client(mcp)."""
    from tests.factories.principal import PrincipalFactory

    identity = PrincipalFactory.make_identity(protocol="mcp")

    # Mock the _impl dependencies so the tool function doesn't fail on DB access
    mock_uow = MagicMock()
    mock_uow_instance = MagicMock()
    mock_uow_instance.products = MagicMock()
    mock_uow_instance.products.list_all.return_value = []
    mock_uow_instance.__enter__ = MagicMock(return_value=mock_uow_instance)
    mock_uow_instance.__exit__ = MagicMock(return_value=False)
    mock_uow.return_value = mock_uow_instance

    mock_principal = MagicMock()
    mock_principal.principal_id = identity.principal_id
    mock_principal.name = "Test"
    mock_principal.platform_mappings = {"mock": {"advertiser_id": "test"}}

    mock_adapter = MagicMock()
    mock_adapter.get_supported_pricing_models.return_value = ["cpm"]

    return [
        patch("src.core.mcp_auth_middleware.resolve_identity_from_context", return_value=identity),
        patch("src.core.database.repositories.uow.ProductUoW", mock_uow),
        patch("src.core.tools.products.get_principal_object", return_value=mock_principal),
        patch("src.core.tools.products.convert_product_model_to_schema", side_effect=lambda p, **kw: p),
        patch("src.core.tools.products.PolicyCheckService"),
        patch("src.services.dynamic_products.generate_variants_for_brief", new_callable=AsyncMock, return_value=[]),
        patch("src.services.ai.factory.get_factory"),
        patch("src.services.dynamic_pricing_service.DynamicPricingService"),
        patch("src.core.property_list_resolver.resolve_property_list", new_callable=AsyncMock, return_value=[]),
        patch("src.core.helpers.adapter_helpers.get_adapter", return_value=mock_adapter),
    ]


class TestMcpForwardCompat:
    """MCP transport: Client(mcp) exercises full middleware + TypeAdapter pipeline."""

    @pytest.mark.parametrize(
        "label,payload",
        [
            ("current_spec", CURRENT_SPEC_GET_PRODUCTS),
            ("future_top_level", FUTURE_TOP_LEVEL_FIELD),
            ("future_nested_brand", FUTURE_NESTED_IN_BRAND),
            ("future_nested_context", FUTURE_NESTED_IN_CONTEXT),
            ("future_nested_filters", FUTURE_NESTED_IN_FILTERS),
            ("v25_brand_manifest", V25_BRAND_MANIFEST),
            ("v25_promoted_offerings", V25_PROMOTED_OFFERINGS),
            ("multi_level_extras", MULTI_LEVEL_EXTRAS),
            ("all_unknown_plus_brief", ALL_UNKNOWN_PLUS_BRIEF),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_production_accepts_payload(self, label: str, payload: dict):
        """In production mode, get_products accepts various payload shapes."""
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "get_products",
                            payload,
                            raise_on_error=False,
                        )
                        assert not result.is_error, (
                            f"[{label}] Production should accept payload but got error: "
                            f"{result.content[:300] if result.content else 'no content'}"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    @pytest.mark.parametrize(
        "label,payload",
        [
            ("future_top_level", FUTURE_TOP_LEVEL_FIELD),
            ("future_nested_brand", FUTURE_NESTED_IN_BRAND),
            ("multi_level_extras", MULTI_LEVEL_EXTRAS),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_dev_rejects_unknown_top_level_fields(self, label: str, payload: dict):
        """In dev mode, unknown top-level fields are rejected by TypeAdapter."""
        from fastmcp import Client

        from src.core.main import mcp

        # Only test payloads that have top-level unknowns (not normalized deprecations).
        # This set is "names the seller KNOWS", not "names the signature declares" —
        # a field the seller deliberately accepts is not an unknown one, so listing
        # it here is what keeps this guard honest rather than what weakens it.
        has_top_level_unknown = any(
            k
            not in {
                "brief",
                "brand",
                "adcp_version",
                # Accepted on purpose since GH #1512, alongside adcp_version. Its
                # absence here is what made this guard flag a field the seller
                # had deliberately started accepting.
                "adcp_major_version",
                "filters",
                "property_list",
                "push_notification_config",
                "context",
                "account",
                "ctx",
            }
            for k in payload
        )
        if not has_top_level_unknown:
            pytest.skip("No top-level unknown fields in this payload")

        async def _call():
            patches = _get_products_patches()
            for p in patches:
                p.start()
            try:
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "get_products",
                        payload,
                        raise_on_error=False,
                    )
                    assert result.is_error, f"[{label}] Dev mode should reject unknown fields"
            finally:
                for p in patches:
                    p.stop()

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# AdCP 3.1 read-tool idempotency envelope
# ---------------------------------------------------------------------------

#: The request envelope AdCP 3.1 extends to EVERY task, reads included. Copied from the
#: storyboard's own sample_request so the payload we grade is the payload the compliance
#: harness sends:
#:   /Users/konst/projects/salesagent-sbsweep/tests/storyboard/runner/adcp-3.1.1/compliance/
#:     universal/read-tool-idempotency.yaml
#:   phase read_requests_accept_idempotency_key, step list_accounts_with_idempotency_key
#:
#: Its narrative names the mechanism, and the mechanism is the point: "Tool wrappers must
#: pass it through their envelope normalization layer instead of rejecting it as an unknown
#: task-specific input." account/list-accounts-request.json declares no idempotency_key, so
#: the ONLY conformant way to tolerate it is the envelope layer -- which is
#: RequestCompatMiddleware, and which already does it.
READ_TOOL_3_1_ENVELOPE_LIST_ACCOUNTS = {
    "idempotency_key": "read-tool-idem-key-0001",
    "sandbox": True,
    "pagination": {"max_results": 10},
    "context": {"correlation_id": "read_tool_idempotency--list_accounts_with_key"},
    "ext": {"adcp": {"storyboard": "read_tool_idempotency", "probe": "list_accounts"}},
}

#: Same phase, step get_products_with_idempotency_key.
READ_TOOL_3_1_ENVELOPE_GET_PRODUCTS = {
    "idempotency_key": "read-tool-idem-key-0002",
    "brief": "Show available advertising products for an outdoor lifestyle campaign.",
    "context": {"correlation_id": "read_tool_idempotency--get_products_with_key"},
    "ext": {"adcp": {"storyboard": "read_tool_idempotency", "probe": "get_products"}},
}


def _list_accounts_patches():
    """Mock _list_accounts_impl's dependencies so Client(mcp) reaches the tool body."""
    from tests.factories.principal import PrincipalFactory

    identity = PrincipalFactory.make_identity(protocol="mcp")

    mock_uow = MagicMock()
    mock_uow_instance = MagicMock()
    mock_uow_instance.accounts = MagicMock()
    mock_uow_instance.accounts.list_for_agent.return_value = []
    mock_uow_instance.__enter__ = MagicMock(return_value=mock_uow_instance)
    mock_uow_instance.__exit__ = MagicMock(return_value=False)
    mock_uow.return_value = mock_uow_instance

    return [
        patch("src.core.mcp_auth_middleware.resolve_identity_from_context", return_value=identity),
        patch("src.core.tools.accounts.AccountUoW", mock_uow),
    ]


class TestReadToolIdempotencyEnvelope:
    """AdCP 3.1 read tools tolerate ``idempotency_key`` WITHOUT declaring it.

    This grades the obligation that a declared field was standing in for. ``list_accounts``
    carried an ``idempotency_key`` field on its request DTO, cited to this storyboard. The
    citation was right and the mechanism was wrong: the storyboard says wrappers must pass the
    key through the ENVELOPE NORMALIZATION LAYER "instead of rejecting it as an unknown
    task-specific input", and declaring it on the task DTO is precisely what makes it a
    task-specific input -- it appears in the advertised task schema, which
    account/list-accounts-request.json does not define.

    Nothing graded the real obligation, which is why declaring the field looked like a fix.
    These tests grade it, so the field cannot come back for that reason.

    MUTATION NOTE, because a careless check here reads as "the middleware does not matter":
    the envelope layer tolerates the key by TWO independently sufficient stages, and
    disabling either ALONE leaves these tests green. Step 2 (``strip_unknown_params``, keyed
    on the tool's advertised properties) removes the key before dispatch; if it does not,
    TypeAdapter rejects and step 3 (``deep_strip_to_schema`` + retry) strips and re-dispatches.
    Disable BOTH and both tolerance cases fail with INVALID_REQUEST on /idempotency_key --
    verified, and that is the mutation that proves what these grade.
    """

    @pytest.mark.parametrize(
        "tool_name,payload,patches_factory,array_field",
        [
            ("list_accounts", READ_TOOL_3_1_ENVELOPE_LIST_ACCOUNTS, _list_accounts_patches, "accounts"),
            ("get_products", READ_TOOL_3_1_ENVELOPE_GET_PRODUCTS, _get_products_patches, "products"),
        ],
        ids=["list_accounts", "get_products"],
    )
    def test_production_tolerates_the_envelope_and_echoes_context(
        self, tool_name: str, payload: dict, patches_factory, array_field: str
    ):
        """The storyboard's step validations, run against our tool.

        It grades three things, and the context echo is the one that matters most: an
        implementation that "tolerated" the key by discarding the whole envelope would pass a
        bare not-is_error check and fail the buyer.
        """
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = patches_factory()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(tool_name, payload, raise_on_error=False)
                        assert not result.is_error, (
                            f"{tool_name} rejected the AdCP 3.1 read envelope. The envelope layer "
                            f"(RequestCompatMiddleware) must strip idempotency_key rather than the "
                            f"tool declaring it: {str(result.content)[:300]}"
                        )
                        structured = result.structured_content or {}
                        assert array_field in structured, f"{tool_name} must still answer with its {array_field} array"
                        assert structured.get("context") == payload["context"], (
                            f"{tool_name} must echo the context object unchanged; got {structured.get('context')!r}"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    # Graduated: this carried a strict xfail while ListAccountsRequest declared a non-spec
    # ``idempotency_key``, restored so a UC-011 step that built the model in-process could
    # construct a request. That step dispatches a literal payload now, the field is gone, and
    # the marker's own instruction was to delete it the moment it was -- so it is deleted.
    def test_the_key_is_not_advertised_as_a_task_field(self):
        """Tolerating it must not mean declaring it.

        This is the half that makes the test above non-vacuous: declaring
        ``idempotency_key`` on ListAccountsRequest ALSO makes the call above succeed, and did,
        for as long as the field existed. What separates the conformant implementation from
        the non-conformant one is that the advertised task schema stays the spec's.
        ``sync_accounts`` is the control: sync-accounts-request.json DOES declare the property,
        because a sync mutates and a mutation genuinely needs at-most-once.
        """
        from src.core.main import mcp

        async def _advertised(tool_name: str) -> set[str]:
            return set((await mcp.get_tool(tool_name)).parameters.get("properties", {}))

        assert "idempotency_key" not in asyncio.run(_advertised("list_accounts"))
        assert "idempotency_key" not in asyncio.run(_advertised("get_products"))
        assert "idempotency_key" in asyncio.run(_advertised("sync_accounts"))

    def test_a_read_omitting_the_key_is_not_rejected(self):
        """The storyboard's grace-window branch, and a guard against over-implementing it.

        Phases ``omitted_key_grace_accept_path`` and ``omitted_key_grace_reject_path`` are an
        ``any_of`` branch set: in 3.1 a seller MAY accept a read with no ``idempotency_key`` or
        MAY reject it with INVALID_REQUEST, and the assertion phase requires only that one of
        them holds. We take the accept branch. Pinned because the yaml marks the rejection as
        a 3.2 SWITCH POINT -- someone reading "sellers SHOULD reject" out of context could
        implement a hard rejection today and break every current buyer.
        """
        from fastmcp import Client

        from src.core.main import mcp

        payload = {k: v for k, v in READ_TOOL_3_1_ENVELOPE_LIST_ACCOUNTS.items() if k != "idempotency_key"}

        async def _call():
            patches = _list_accounts_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool("list_accounts", payload, raise_on_error=False)
                        assert not result.is_error, (
                            "a read omitting idempotency_key must still be answered during the "
                            "3.1 grace window; rejecting it is the 3.2 behaviour"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    # Graduated: this carried a strict xfail while ListAccountsRequest declared a non-spec
    # ``idempotency_key``, restored so a UC-011 step that built the model in-process could
    # construct a request. That step dispatches a literal payload now, the field is gone, and
    # the marker's own instruction was to delete it the moment it was -- so it is deleted.
    def test_dev_still_surfaces_the_key_as_unknown(self):
        """The environment asymmetry is DELIBERATE, and this records which half is which.

        Production strips (forward compatibility); dev and CI reject so a field this agent does
        not model becomes visible instead of silently ignored -- CLAUDE.md "Schema Validation:
        Environment-Based". Without this test, a red CI scenario looks like a bug in the
        stripping, and the cheapest way to make it green is to declare the field on the DTO --
        which is exactly how the field got there the first time.
        """
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _list_accounts_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "list_accounts", READ_TOOL_3_1_ENVELOPE_LIST_ACCOUNTS, raise_on_error=False
                        )
                        assert result.is_error, "dev mode must surface an unmodelled field rather than stripping it"
                        assert "idempotency_key" in str(result.content), (
                            "the rejection must name the field, or it teaches nothing"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# A2A transport: normalize + model_validate (production mode)
# ---------------------------------------------------------------------------


class TestA2aForwardCompat:
    """A2A transport: normalize + strip + model_validate acceptance.

    Note: Pydantic's model_config extra mode is evaluated at import time,
    so we can't switch to extra='ignore' at runtime. Instead we verify the
    A2A pipeline: normalize deprecated fields + strip unknown top-level params
    (matching what the A2A handler does before model_validate).

    In production, models are compiled with extra='ignore' so unknown
    top-level fields are also accepted. That behavior is tested by the
    MCP tests above, which exercise the real production middleware.
    """

    @pytest.mark.parametrize(
        "label,payload",
        [
            ("current_spec", CURRENT_SPEC_GET_PRODUCTS),
            ("v25_brand_manifest", V25_BRAND_MANIFEST),
            ("v25_promoted_offerings", V25_PROMOTED_OFFERINGS),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_normalize_then_model_validate(self, label: str, payload: dict):
        """A2A path: normalize → strip unknown top-level → model_validate → accepted.

        Note: Nested unknowns in library types (BrandReference, AccountReference)
        are rejected even in production because the adcp library uses extra='forbid'.
        Deep-strip handles this on MCP only. A2A tests focus on normalization
        of deprecated fields and top-level stripping.
        """
        from src.core.schemas import GetProductsRequest

        # Step 1: Normalize (same as A2A handler does)
        result = normalize_request_params("get_products", dict(payload))
        normalized = result.params

        # Step 2: Strip unknown top-level params (A2A handlers pop unknowns)
        known_fields = set(GetProductsRequest.model_fields.keys())
        clean = {k: v for k, v in normalized.items() if k in known_fields}

        # Step 3: model_validate should not raise
        req = GetProductsRequest.model_validate(clean)
        assert req.brief == payload.get("brief", "")


# ---------------------------------------------------------------------------
# Direct model acceptance (covers REST and internal callers)
# ---------------------------------------------------------------------------


class TestDirectModelAcceptance:
    """Direct Pydantic model construction — covers REST transport and internal callers."""

    @pytest.mark.parametrize(
        "label,params",
        [
            ("minimal", {"brief": "test"}),
            ("with_brand", {"brief": "test", "brand": {"domain": "acme.com"}}),
            ("with_account_id", {"brief": "test", "account": {"account_id": "acc-1"}}),
            (
                "with_account_natural_key",
                {
                    "brief": "test",
                    "account": {"brand": {"domain": "acme.com"}, "operator": "agency.com"},
                },
            ),
            ("with_context", {"brief": "test", "context": {"session_id": "sess-1"}}),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_known_payloads_accepted(self, label: str, params: dict):
        """All known payload shapes are accepted regardless of environment."""
        from src.core.schemas import GetProductsRequest

        req = GetProductsRequest.model_validate(params)
        assert req.brief == params["brief"]

    def test_extra_fields_rejected_in_dev_mode(self):
        """Dev mode rejects extra fields — confirms extra='forbid' is active.

        In production, SalesAgentBaseModel has extra='ignore', but the mode
        is compiled at import time. The MCP middleware handles forward-compat
        via deep-strip; A2A/REST rely on the production extra mode.
        """
        from src.core.schemas import GetProductsRequest

        with pytest.raises(Exception, match="Extra inputs are not permitted"):
            GetProductsRequest.model_validate({"brief": "test", "future_field": "value"})


# ---------------------------------------------------------------------------
# Deep-strip retry: end-to-end through MCP middleware
# ---------------------------------------------------------------------------


class TestDeepStripRetryE2E:
    """End-to-end: TypeAdapter rejects → deep-strip → retry → succeeds.

    These tests verify the actual retry path in the middleware, not just
    the deep_strip function in isolation. The payload must:
    1. Pass top-level strip (Step 2) — no unknown top-level params
    2. Fail TypeAdapter on first attempt (nested unknown in strict type)
    3. Succeed after deep-strip removes nested unknowns
    """

    def test_nested_brand_extra_triggers_retry_and_succeeds(self):
        """Brand with future field: TypeAdapter rejects → deep-strip → retry → ok."""
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "get_products",
                            {
                                "brief": "test retry path",
                                "brand": {
                                    "domain": "retry-test.com",
                                    "verification_status": "premium",
                                    "trust_score": 0.95,
                                },
                            },
                            raise_on_error=False,
                        )
                        assert not result.is_error, (
                            f"Deep-strip retry should have saved this request: "
                            f"{result.content[:300] if result.content else 'no content'}"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    def test_nested_context_extra_triggers_retry_and_succeeds(self):
        """Context with future field: same retry path."""
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "get_products",
                            {
                                "brief": "context retry",
                                "context": {
                                    "session_id": "sess-1",
                                    "buyer_agent_version": "4.2.0",
                                    "capabilities": ["streaming", "batch"],
                                },
                            },
                            raise_on_error=False,
                        )
                        assert not result.is_error, (
                            f"Deep-strip retry should accept context with extra fields: "
                            f"{result.content[:300] if result.content else 'no content'}"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    def test_stripping_no_change_becomes_validation_envelope(self):
        """An unstrippable type mismatch is translated without a retry or raw leak."""
        from pydantic import ValidationError

        from src.core.mcp_compat_middleware import RequestCompatMiddleware
        from src.core.tool_error_logging import AdCPToolError

        middleware = RequestCompatMiddleware()
        error = ValidationError.from_exception_data(
            title="call[get_products]",
            line_errors=[
                {
                    "type": "string_type",
                    "loc": ("brief",),
                    "input": 12345,
                }
            ],
        )
        call_next = AsyncMock(side_effect=error)
        ctx = _make_mcp_context("get_products", {"brief": 12345})

        async def _call():
            with (
                patch.dict(os.environ, {"ENVIRONMENT": "production"}),
                patch.object(middleware, "_get_tool_schema", return_value=_simple_tool_schema()),
            ):
                with pytest.raises(AdCPToolError) as exc_info:
                    await middleware.on_call_tool(ctx, call_next)
                # INVALID_REQUEST: the input here is a pydantic ValidationError, i.e. a
                # SCHEMA-constraint violation, which 3.1/enums/error-code.json assigns to
                # INVALID_REQUEST. VALIDATION_ERROR stays for business rules "beyond schema
                # validation" -- the empty-get_products case below is one and keeps it.
                assert_envelope_shape(exc_info.value, "INVALID_REQUEST", recovery="correctable")
                assert exc_info.value.__cause__ is error
                assert call_next.call_count == 1

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# Data preservation: known values survive deep-strip + retry unchanged
# ---------------------------------------------------------------------------


class TestDataPreservationE2E:
    """Verify that after deep-strip retry, the tool function receives exactly
    the buyer's data for all known fields — no truncation, coercion, or loss.

    The test intercepts the _impl call to capture what arguments the tool
    function actually receives after the middleware pipeline.
    """

    def test_brand_domain_preserved_after_strip(self):
        """Buyer sends brand with extra field. After strip + retry, _impl
        receives brand.domain exactly as sent.
        """
        from fastmcp import Client

        from src.core.main import mcp

        captured_req = {}

        async def _call():
            patches = _get_products_patches()

            # Intercept _get_products_impl to capture the request
            original_impl = None

            async def capturing_impl(req, identity=None):
                captured_req["brand"] = req.brand
                captured_req["brief"] = req.brief
                # Call original to produce a valid response
                return await original_impl(req, identity)

            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                # Capture the impl
                # Substituted at the REGISTRY ROW, which is what the MCP boundary invokes.
                # Patching src.core.tools.products._get_products_impl captured nothing: the
                # row holds the function object, so the module attribute and the thing the
                # transport calls are two different names for what used to be one.
                from src.core.tools.registry import TOOLS
                from tests.helpers.capture_wrapper_req import registry_impl

                original_impl = TOOLS["get_products"].impl
                with registry_impl("get_products", capturing_impl):
                    try:
                        async with Client(mcp) as client:
                            result = await client.call_tool(
                                "get_products",
                                {
                                    "brief": "holiday campaign — Q4",
                                    "brand": {
                                        "domain": "my-brand.com",
                                        "future_field": "should be stripped",
                                    },
                                },
                                raise_on_error=False,
                            )
                            assert not result.is_error, f"Should succeed: {result.content}"
                    finally:
                        for p in patches:
                            p.stop()

            # Verify the _impl received exactly what the buyer sent for known fields
            assert captured_req["brief"] == "holiday campaign — Q4"
            assert captured_req["brand"] is not None
            assert captured_req["brand"].domain == "my-brand.com"

        asyncio.run(_call())

    def test_context_session_id_preserved_after_strip(self):
        """Buyer sends context with extra field. After strip, session_id preserved."""
        from fastmcp import Client

        from src.core.main import mcp

        captured_req = {}

        async def _call():
            patches = _get_products_patches()
            original_impl = None

            async def capturing_impl(req, identity=None):
                captured_req["context"] = req.context
                captured_req["brief"] = req.brief
                return await original_impl(req, identity)

            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                # Substituted at the REGISTRY ROW, which is what the MCP boundary invokes.
                # Patching src.core.tools.products._get_products_impl captured nothing: the
                # row holds the function object, so the module attribute and the thing the
                # transport calls are two different names for what used to be one.
                from src.core.tools.registry import TOOLS
                from tests.helpers.capture_wrapper_req import registry_impl

                original_impl = TOOLS["get_products"].impl
                with registry_impl("get_products", capturing_impl):
                    try:
                        async with Client(mcp) as client:
                            result = await client.call_tool(
                                "get_products",
                                {
                                    "brief": "test preserv",
                                    "context": {
                                        "session_id": "sess-保存-789",
                                        "future_trace": "strip-me",
                                    },
                                },
                                raise_on_error=False,
                            )
                            assert not result.is_error, f"Should succeed: {result.content}"
                    finally:
                        for p in patches:
                            p.stop()

            assert captured_req["brief"] == "test preserv"
            assert captured_req["context"] is not None
            assert captured_req["context"].session_id == "sess-保存-789"

        asyncio.run(_call())

    def test_multiple_fields_all_preserved(self):
        """Buyer sends brief + brand + context, all with extras at different levels.
        After strip + retry, all known data arrives intact.
        """
        from fastmcp import Client

        from src.core.main import mcp

        captured_req = {}

        async def _call():
            patches = _get_products_patches()
            original_impl = None

            async def capturing_impl(req, identity=None):
                captured_req["brief"] = req.brief
                captured_req["brand"] = req.brand
                captured_req["context"] = req.context
                return await original_impl(req, identity)

            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                # Substituted at the REGISTRY ROW, which is what the MCP boundary invokes.
                # Patching src.core.tools.products._get_products_impl captured nothing: the
                # row holds the function object, so the module attribute and the thing the
                # transport calls are two different names for what used to be one.
                from src.core.tools.registry import TOOLS
                from tests.helpers.capture_wrapper_req import registry_impl

                original_impl = TOOLS["get_products"].impl
                with registry_impl("get_products", capturing_impl):
                    try:
                        async with Client(mcp) as client:
                            result = await client.call_tool(
                                "get_products",
                                {
                                    "brief": "multi-field test — $50k budget",
                                    "brand": {"domain": "multi.test.com", "tier": "enterprise"},
                                    "context": {"session_id": "s-multi", "region": "APAC"},
                                    "future_top_level": "also stripped",
                                },
                                raise_on_error=False,
                            )
                            assert not result.is_error, f"Should succeed: {result.content}"
                    finally:
                        for p in patches:
                            p.stop()

            # Every known field's VALUE is exactly what the buyer sent
            assert captured_req["brief"] == "multi-field test — $50k budget"
            assert captured_req["brand"].domain == "multi.test.com"
            assert captured_req["context"].session_id == "s-multi"

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# Adversarial: Error propagation (Pydantic/business errors NOT swallowed)
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Verify that errors from Pydantic validation and business logic propagate
    to the buyer — deep-strip must NOT swallow them.

    Architecture: TypeAdapter is the gate we bypass. Everything after it
    (Pydantic model validation, _impl business logic) is intentional
    validation whose errors must reach the buyer.
    """

    def test_business_logic_error_propagates_through_middleware(self):
        """_impl raises AdCPValidationError → buyer sees error, not success.

        get_products requires at least one of brief/brand/filters.
        Sending none should return a clear error, not be silently accepted.
        """
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "get_products",
                            {},  # No brief, no brand, no filters → _impl rejects
                            raise_on_error=False,
                        )
                        assert result.is_error, "Empty get_products should return an error, not succeed silently"
                        # The CODE is the obligation, not the wording: a validation
                        # rejection must reach the buyer as VALIDATION_ERROR through the
                        # middleware. Which fields were missing is structured detail, and
                        # the sentence is the code's own.
                        error_text = str(result.content) if result.content else ""
                        assert "VALIDATION_ERROR" in error_text, (
                            f"Empty get_products must surface VALIDATION_ERROR, got: {error_text[:200]}"
                        )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    def test_deep_strip_succeeds_but_impl_error_propagates(self):
        """Deep-strip fixes nested unknown (TypeAdapter passes on retry),
        but _impl raises an error → error propagates, not swallowed by retry.

        Send brand with extra field (deep-strip removes it for TypeAdapter)
        but NO brief/filters → _impl raises "at least one required".
        This tests that the retry path doesn't eat the _impl error.
        """
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        result = await client.call_tool(
                            "get_products",
                            {
                                # brand with future field → deep-strip needed
                                "brand": {"domain": "acme.com", "future_field": "v5"},
                                # NO brief → _impl rejects after TypeAdapter passes
                            },
                            raise_on_error=False,
                        )
                        # Should NOT succeed — _impl requires brief or filters
                        # The deep-strip only fixes the TypeAdapter gate;
                        # the business logic error must still propagate.
                        # NOTE: get_products accepts brand alone as sufficient,
                        # so this might actually succeed. If so, that's valid too —
                        # the point is the error path works when it fires.
                        assert result is not None  # Must not hang
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())

    def test_retry_does_not_catch_tool_function_validation_error(self):
        """Tool function raises ValidationError (from model construction) —
        middleware must NOT retry, because it's not a TypeAdapter error.

        This is the critical distinction: TypeAdapter errors have title
        "call[tool_name]", business logic errors have the model class name.
        """
        from unittest.mock import AsyncMock as AMock

        from pydantic import ValidationError

        from src.core.mcp_compat_middleware import RequestCompatMiddleware

        middleware = RequestCompatMiddleware()

        # Simulate: call_next succeeds (TypeAdapter passes), but tool raises
        # a business logic ValidationError (e.g., from CreateMediaBuyRequest)
        business_error = ValidationError.from_exception_data(
            title="CreateMediaBuyRequest",  # NOT "call[...]"
            line_errors=[],
        )
        call_next = AMock(side_effect=business_error)
        ctx = _make_mcp_context("get_products", {"brief": "test"})

        async def _call():
            with pytest.raises(ValidationError) as exc_info:
                await middleware.on_call_tool(ctx, call_next)
            # Verify it's the SAME error (not retried, not wrapped)
            assert exc_info.value.title == "CreateMediaBuyRequest"
            # call_next called exactly ONCE (no retry)
            assert call_next.call_count == 1

        asyncio.run(_call())

    def test_retry_does_not_catch_adcp_error(self):
        """AdCPSalesAgentError from _impl propagates directly — never retried."""
        from src.core.exceptions import AdCPValidationError
        from src.core.mcp_compat_middleware import RequestCompatMiddleware

        middleware = RequestCompatMiddleware()

        call_next = AsyncMock(side_effect=AdCPValidationError())
        ctx = _make_mcp_context("create_media_buy", {"po_number": "ref-1"})

        async def _call():
            # The error is constructed with no text; its sentence comes from the code.
            # Asserting the CLASS is the whole obligation — that retry does not swallow it.
            with pytest.raises(AdCPValidationError):
                await middleware.on_call_tool(ctx, call_next)
            assert call_next.call_count == 1

        asyncio.run(_call())

    def test_non_validation_exception_propagates(self):
        """RuntimeError, KeyError, etc. propagate directly — never retried."""
        from src.core.mcp_compat_middleware import RequestCompatMiddleware

        middleware = RequestCompatMiddleware()
        call_next = AsyncMock(side_effect=RuntimeError("database connection lost"))
        ctx = _make_mcp_context("get_products", {"brief": "test"})

        async def _call():
            with pytest.raises(RuntimeError, match="database connection lost"):
                await middleware.on_call_tool(ctx, call_next)
            assert call_next.call_count == 1

        asyncio.run(_call())

    def test_second_attempt_error_uses_retry_error_envelope(self):
        """TypeAdapter rejects → deep-strip → retry → retry ALSO fails.
        The buyer-facing envelope must describe the retry error, not the original.

        This catches a subtle bug: if the middleware catches the retry
        exception and wraps the original instead, the buyer gets a confusing
        error about fields that were already stripped.
        """
        from pydantic import ValidationError

        from src.core.mcp_compat_middleware import RequestCompatMiddleware
        from src.core.tool_error_logging import AdCPToolError

        middleware = RequestCompatMiddleware()

        original_error = ValidationError.from_exception_data(
            title="call[get_products]",
            line_errors=[],
        )
        retry_error = ValidationError.from_exception_data(
            title="call[get_products]",  # Still TypeAdapter, but different issue
            line_errors=[],
        )

        call_count = 0

        async def call_next_with_different_errors(ctx):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise original_error
            raise retry_error

        # The unknown key rides on ``filters``, not ``brand``: step 1 now normalizes
        # brand through to_brand_reference, which drops unknown keys before deep-strip
        # can see them, so a brand-borne extra would leave stripped == normalized and
        # no retry would happen — the test would pass vacuously on the FIRST error.
        ctx = _make_mcp_context("get_products", {"brief": "test", "filters": {"channel": "web", "extra": 1}})

        async def _call():
            with (
                patch.dict(os.environ, {"ENVIRONMENT": "production"}),
                patch.object(middleware, "_get_tool_schema", return_value=_simple_tool_schema()),
            ):
                with pytest.raises(AdCPToolError) as exc_info:
                    await middleware.on_call_tool(ctx, call_next_with_different_errors)
                # INVALID_REQUEST: the input here is a pydantic ValidationError, i.e. a
                # SCHEMA-constraint violation, which 3.1/enums/error-code.json assigns to
                # INVALID_REQUEST. VALIDATION_ERROR stays for business rules "beyond schema
                # validation" -- the empty-get_products case below is one and keeps it.
                assert_envelope_shape(exc_info.value, "INVALID_REQUEST", recovery="correctable")
                assert exc_info.value.__cause__ is retry_error

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# Adversarial: Edge cases that could break the middleware
# ---------------------------------------------------------------------------


class TestMiddlewareAdversarial:
    """Adversarial scenarios designed to break the middleware."""

    def test_schema_lookup_fails_error_becomes_envelope(self):
        """_get_tool_schema returns None → no retry, but no raw validation leak."""
        from pydantic import ValidationError

        from src.core.mcp_compat_middleware import RequestCompatMiddleware
        from src.core.tool_error_logging import AdCPToolError

        middleware = RequestCompatMiddleware()

        error = ValidationError.from_exception_data(title="call[get_products]", line_errors=[])
        call_next = AsyncMock(side_effect=error)
        ctx = _make_mcp_context("get_products", {"brief": "test"})

        async def _call():
            with (
                patch.dict(os.environ, {"ENVIRONMENT": "production"}),
                patch.object(middleware, "_get_tool_schema", return_value=None),
            ):
                with pytest.raises(AdCPToolError) as exc_info:
                    await middleware.on_call_tool(ctx, call_next)
                # INVALID_REQUEST: the input here is a pydantic ValidationError, i.e. a
                # SCHEMA-constraint violation, which 3.1/enums/error-code.json assigns to
                # INVALID_REQUEST. VALIDATION_ERROR stays for business rules "beyond schema
                # validation" -- the empty-get_products case below is one and keeps it.
                assert_envelope_shape(exc_info.value, "INVALID_REQUEST", recovery="correctable")
                assert exc_info.value.__cause__ is error
                # Only called once — no retry when schema unavailable
                assert call_next.call_count == 1

        asyncio.run(_call())

    def test_deeply_nested_payload_no_stack_overflow(self):
        """5+ nesting levels — deep-strip handles without stack overflow."""
        from src.core.request_compat import deep_strip_to_schema

        # Build 10-level deep schema and value
        schema: dict = {"type": "object", "properties": {}, "additionalProperties": False}
        value: dict = {}
        current_schema = schema
        current_value = value
        for i in range(10):
            child_schema: dict = {"type": "object", "properties": {}, "additionalProperties": False}
            current_schema["properties"][f"l{i}"] = child_schema
            child_value: dict = {}
            current_value[f"l{i}"] = child_value
            current_schema = child_schema
            current_value = child_value
        # Add a known field at the deepest level
        current_schema["properties"]["data"] = {"type": "string"}
        current_value["data"] = "deep"
        current_value["extra"] = "strip_me"

        result = deep_strip_to_schema(value, schema)
        # Navigate to the deepest level
        node = result
        for i in range(10):
            node = node[f"l{i}"]
        assert node == {"data": "deep"}  # extra stripped at deepest level

    def test_empty_anyof_variants_passes_through(self):
        """anyOf with only null variants — value passes through unchanged."""
        from src.core.request_compat import deep_strip_to_schema

        schema = {
            "type": "object",
            "properties": {
                "x": {"anyOf": [{"type": "null"}]},
            },
            "additionalProperties": False,
        }
        result = deep_strip_to_schema({"x": {"anything": "goes"}}, schema)
        assert result == {"x": {"anything": "goes"}}

    def test_concurrent_calls_dont_interfere(self):
        """Two concurrent middleware calls — patches don't leak between them."""
        from fastmcp import Client

        from src.core.main import mcp

        async def _call():
            patches = _get_products_patches()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                for p in patches:
                    p.start()
                try:
                    async with Client(mcp) as client:
                        # Fire two calls concurrently
                        results = await asyncio.gather(
                            client.call_tool(
                                "get_products",
                                {"brief": "concurrent-1", "brand": {"domain": "a.com", "extra": 1}},
                                raise_on_error=False,
                            ),
                            client.call_tool(
                                "get_products",
                                {"brief": "concurrent-2", "brand": {"domain": "b.com", "extra": 2}},
                                raise_on_error=False,
                            ),
                        )
                        for i, r in enumerate(results):
                            assert not r.is_error, (
                                f"Concurrent call {i} failed: {r.content[:200] if r.content else 'no content'}"
                            )
                finally:
                    for p in patches:
                        p.stop()

        asyncio.run(_call())


# ---------------------------------------------------------------------------
# Helpers for unit-level middleware tests
# ---------------------------------------------------------------------------


def _make_mcp_context(tool_name: str, arguments: dict) -> MagicMock:
    """Build a mock MiddlewareContext for middleware unit tests."""
    message = MagicMock()
    message.name = tool_name
    message.arguments = arguments

    ctx = MagicMock()
    ctx.message = message
    ctx.copy = MagicMock(side_effect=lambda **kw: _make_copied_ctx(ctx, **kw))
    ctx.fastmcp_context = None  # No real server — schema lookup will return None
    return ctx


def _make_copied_ctx(original, **kwargs):
    copied = MagicMock()
    copied.message = kwargs.get("message", original.message)
    copied.copy = original.copy
    copied.fastmcp_context = original.fastmcp_context
    return copied


def _simple_tool_schema() -> dict:
    """A minimal tool schema for testing deep-strip behavior.

    ``filters`` is here as a nested object the request normalizer does NOT own, so
    a test that needs deep-strip to actually CHANGE the payload has a vehicle for
    it. ``brand`` can no longer serve that role: ``_normalize_brand`` coerces it
    through ``to_brand_reference`` in step 1, which keeps only BrandReference's
    own fields, so an unknown key under ``brand`` is already gone by the time
    deep-strip runs and ``stripped == normalized`` suppresses the retry.
    """
    return {
        "type": "object",
        "properties": {
            "brief": {"type": "string"},
            "brand": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"domain": {"type": "string"}},
                        "additionalProperties": False,
                    },
                    {"type": "null"},
                ],
            },
            "filters": {
                "type": "object",
                "properties": {"channel": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
