"""Unit tests for get_products transport wrappers — MCP, A2A, REST, _impl.

: Cover MCP/A2A transport wrapper lines in products.py.

Tests the wrapper logic (request construction, error translation,
response serialization, version compat) independent of business logic.
Business logic is mocked via _get_products_impl.

# --- Test Source-of-Truth Audit ---
# Audited: 2026-03-07
#
# SPEC_BACKED (1 test):
#   test_rest_returns_json_response — AdCP get-products-response.json + protocol-envelope.json
#
# ARCH_BACKED (9 tests):
#   test_mcp_wrapper_returns_tool_result — CLAUDE.md #5: MCP returns ToolResult
#   test_mcp_boundary_answers_invalid_request_for_a_validation_error — CLAUDE.md #5 + error-code.json
#   test_mcp_boundary_answers_validation_error_for_a_plain_value_error — CLAUDE.md #5 + error-code.json
#   test_mcp_wrapper_reads_identity_from_ctx_state — CLAUDE.md #5: wrapper resolves identity
#   test_a2a_wrapper_returns_response_model — CLAUDE.md #5 + protocol-envelope.json notes
#   test_a2a_wrapper_passes_identity_to_impl — CLAUDE.md #5: forward all params
#   test_a2a_wrapper_constructs_request_from_params — CLAUDE.md #5: wrapper builds request
#   test_mcp_passes_none_identity_when_no_ctx — CLAUDE.md #5: identity optional
#   test_a2a_passes_none_identity_when_not_provided — CLAUDE.md #5: identity optional
#
# DECISION_BACKED (2 tests):
#   test_a2a_wrapper_no_version_compat — arch decision: compat at handler level
#   test_mcp_wrapper_no_version_compat — arch decision: compat at handler level (parity with A2A)
#
# CHARACTERIZATION (2 tests):
#   test_a2a_wrapper_empty_brief_uses_empty_string — locks: empty brief handling
#   test_rest_applies_version_compat — locks: REST applies compat
# ---
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context

from src.core.schemas import GetProductsRequest, GetProductsResponse
from src.core.tool_error_logging import with_error_logging
from tests.factories import PrincipalFactory
from tests.helpers import assert_envelope_shape
from tests.helpers.capture_wrapper_req import mcp_tool, registry_impl


def _mock_response() -> GetProductsResponse:
    """Build a minimal GetProductsResponse for testing wrapper logic."""
    return GetProductsResponse(products=[])


# ---------------------------------------------------------------------------
# MCP boundary (generated)
# ---------------------------------------------------------------------------
# The brand-shorthand tests that stood here are gone with the builder that applied the
# coercion; the obligation is recorded on salesagent-pt5rn, against the compatibility
# middleware that will own it.
#
# There is no get_products MCP wrapper to test. One generated callable serves every row, so
# these grade THAT -- through get_products, which is the vehicle, not the subject.


class TestMcpGetProductsWrapper:
    """The generated MCP boundary, driven through the get_products row."""

    def test_mcp_wrapper_returns_tool_result(self):
        """The boundary answers with a ToolResult carrying structured_content."""
        mock_ctx = MagicMock(spec=Context)
        mock_ctx.get_state = AsyncMock(return_value=PrincipalFactory.make_identity(protocol="mcp"))

        async def _impl(req, identity=None, **kwargs):
            return _mock_response()

        with registry_impl("get_products", _impl):
            result = asyncio.run(mcp_tool("get_products")(brief="video ads", ctx=mock_ctx))

        assert result.structured_content is not None
        assert "products" in result.structured_content
        assert result.content is not None  # Human-readable text

    def test_mcp_boundary_answers_invalid_request_for_a_validation_error(self):
        """A pydantic rejection earns INVALID_REQUEST and names the field.

        Driven by a request the REAL DTO refuses, rather than by a stubbed model that raises:
        the boundary builds ``spec.dto(**kwargs)``, so an unknown field is a rejection the
        buyer can actually provoke, and the field it names is the one they sent.
        """
        mock_ctx = MagicMock(spec=Context)
        mock_ctx.get_state = AsyncMock(return_value=None)

        with pytest.raises(ToolError) as exc_info:
            asyncio.run(with_error_logging(mcp_tool("get_products"))(brief="ads", no_such_field=1, ctx=mock_ctx))

        envelope = json.loads(str(exc_info.value))
        assert_envelope_shape(envelope, "INVALID_REQUEST", recovery="correctable")
        assert envelope["adcp_error"]["field"] == "no_such_field"

    def test_mcp_boundary_answers_validation_error_for_a_plain_value_error(self):
        """A plain ValueError -- business logic refusing a schema-valid value -- stays VALIDATION_ERROR.

        The distinction the deleted per-tool wrapper used to erase: it caught ValueError and
        re-raised AdCPValidationError, which also swallowed the pydantic ValidationError that
        IS a ValueError, answering a bare VALIDATION_ERROR where INVALID_REQUEST with the
        field was owed. Both halves are graded: this one and the test above it.
        """
        mock_ctx = MagicMock(spec=Context)
        mock_ctx.get_state = AsyncMock(return_value=None)

        async def _impl(req, identity=None, **kwargs):
            raise ValueError("Invalid brand format")

        with registry_impl("get_products", _impl), pytest.raises(ToolError) as exc_info:
            asyncio.run(with_error_logging(mcp_tool("get_products"))(brief="ads", ctx=mock_ctx))

        envelope = json.loads(str(exc_info.value))
        assert_envelope_shape(envelope, "VALIDATION_ERROR", recovery="correctable")

    def test_mcp_wrapper_no_version_compat(self):
        """MCP does NOT apply version compat -- that is the handler's job (parity with A2A)."""
        mock_ctx = MagicMock(spec=Context)
        mock_ctx.get_state = AsyncMock(return_value=PrincipalFactory.make_identity(protocol="mcp"))

        async def _impl(req, identity=None, **kwargs):
            return _mock_response()

        with (
            registry_impl("get_products", _impl),
            patch("src.core.version_compat.apply_version_compat") as mock_compat,
        ):
            asyncio.run(mcp_tool("get_products")(brief="ads", ctx=mock_ctx))

        mock_compat.assert_not_called()

    def test_mcp_wrapper_reads_identity_from_ctx_state(self):
        """The boundary reads identity from ctx.get_state('identity') and hands it to the impl."""
        identity = PrincipalFactory.make_identity(protocol="mcp")
        mock_ctx = MagicMock(spec=Context)
        mock_ctx.get_state = AsyncMock(return_value=identity)
        seen: dict = {}

        async def _impl(req, identity=None, **kwargs):
            seen["identity"] = identity
            return _mock_response()

        with registry_impl("get_products", _impl):
            asyncio.run(mcp_tool("get_products")(brief="video", ctx=mock_ctx))

        mock_ctx.get_state.assert_awaited_once_with("identity")
        assert seen["identity"] is identity


# ---------------------------------------------------------------------------
# A2A wrapper: get_products_raw()
# ---------------------------------------------------------------------------


class TestA2AGetProductsRawWrapper:
    """Tests for the A2A wrapper get_products_raw()."""

    def test_a2a_wrapper_returns_response_model(self):
        """A2A wrapper returns GetProductsResponse directly (not ToolResult)."""
        identity = PrincipalFactory.make_identity(protocol="a2a")

        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ):
            from src.core.tools.products import get_products_raw

            result = asyncio.run(get_products_raw(req=GetProductsRequest(brief="display ads"), identity=identity))

        assert isinstance(result, GetProductsResponse)
        assert result.products == []

    def test_a2a_wrapper_passes_identity_to_impl(self):
        """A2A wrapper forwards identity to _get_products_impl."""
        identity = PrincipalFactory.make_identity(protocol="a2a")

        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ) as mock_impl:
            from src.core.tools.products import get_products_raw

            asyncio.run(get_products_raw(req=GetProductsRequest(brief="video"), identity=identity))

        mock_impl.assert_awaited_once()
        _, call_identity = mock_impl.call_args.args
        assert call_identity is identity

    def test_a2a_wrapper_constructs_request_from_params(self):
        """A2A wrapper constructs GetProductsRequest from its parameters."""
        identity = PrincipalFactory.make_identity(protocol="a2a")

        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ) as mock_impl:
            from src.core.tools.products import get_products_raw

            asyncio.run(
                get_products_raw(
                    req=GetProductsRequest(
                        brief="sports ads",
                        filters={"delivery_types": ["guaranteed"]},
                    ),
                    identity=identity,
                )
            )

        req = mock_impl.call_args.args[0]
        assert req.brief == "sports ads"
        assert req.filters is not None

    def test_a2a_wrapper_no_version_compat(self):
        """A2A wrapper does NOT apply version compat — that's the A2A handler's job."""
        identity = PrincipalFactory.make_identity(protocol="a2a")

        with (
            patch(
                "src.core.tools.products._get_products_impl",
                new_callable=AsyncMock,
                return_value=_mock_response(),
            ),
            patch("src.core.version_compat.apply_version_compat") as mock_compat,
        ):
            from src.core.tools.products import get_products_raw

            asyncio.run(get_products_raw(req=GetProductsRequest(brief="ads"), identity=identity))

        mock_compat.assert_not_called()

    def test_a2a_wrapper_empty_brief_uses_empty_string(self):
        """A2A wrapper passes empty string when brief is empty."""
        identity = PrincipalFactory.make_identity(protocol="a2a")

        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ) as mock_impl:
            from src.core.tools.products import get_products_raw

            asyncio.run(get_products_raw(req=GetProductsRequest(brief=""), identity=identity))

        req = mock_impl.call_args.args[0]
        # brief="" → GetProductsRequest normalizes to None
        assert req.brief is None or req.brief == ""


# ---------------------------------------------------------------------------
# REST wrapper: /api/v1/products
# ---------------------------------------------------------------------------


class TestRestGetProductsWrapper:
    """Tests for the REST endpoint POST /api/v1/products."""

    def test_rest_returns_json_response(self):
        """REST endpoint returns JSON with products array."""
        identity = PrincipalFactory.make_identity(protocol="rest")

        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ):
            from starlette.testclient import TestClient

            from src.app import app
            from src.core.auth_context import _require_auth_dep, _resolve_auth_dep

            app.dependency_overrides[_require_auth_dep] = lambda: identity
            app.dependency_overrides[_resolve_auth_dep] = lambda: identity
            try:
                client = TestClient(app)
                response = client.post(
                    "/api/v1/products",
                    json={"brief": "video ads"},
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "products" in data

    def test_rest_applies_version_compat(self):
        """REST endpoint applies version compat based on adcp_version in body."""
        identity = PrincipalFactory.make_identity(protocol="rest")

        with (
            patch(
                "src.core.tools.products._get_products_impl",
                new_callable=AsyncMock,
                return_value=_mock_response(),
            ),
            patch("src.routes.api_v1.apply_version_compat") as mock_compat,
        ):
            mock_compat.return_value = {"products": [], "legacy": True}

            from starlette.testclient import TestClient

            from src.app import app
            from src.core.auth_context import _require_auth_dep, _resolve_auth_dep

            app.dependency_overrides[_require_auth_dep] = lambda: identity
            app.dependency_overrides[_resolve_auth_dep] = lambda: identity
            try:
                client = TestClient(app)
                response = client.post(
                    "/api/v1/products",
                    # MAJOR.MINOR: core/adcp-version.json pins ^\\d+\\.\\d+(-...)?$, so a
                    # three-part "2.0.0" is INVALID_REQUEST and never reaches compat at all.
                    json={"brief": "ads", "adcp_version": "2.0"},
                )
            finally:
                app.dependency_overrides.clear()

        mock_compat.assert_called_once()
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# _impl direct: wrapper passes identity correctly
# ---------------------------------------------------------------------------


class TestImplDirectIdentity:
    """Tests that wrappers correctly pass identity to _get_products_impl."""

    def test_mcp_passes_none_identity_when_no_ctx(self):
        """The MCP boundary passes identity=None when ctx is not a Context."""
        seen: dict = {}

        async def _impl(req, identity=None, **kwargs):
            seen["identity"] = identity
            return _mock_response()

        with registry_impl("get_products", _impl):
            asyncio.run(mcp_tool("get_products")(brief="test", ctx=None))

        assert seen["identity"] is None

    def test_a2a_passes_none_identity_when_not_provided(self):
        """A2A wrapper passes None identity when not explicitly provided."""
        with patch(
            "src.core.tools.products._get_products_impl",
            new_callable=AsyncMock,
            return_value=_mock_response(),
        ) as mock_impl:
            from src.core.tools.products import get_products_raw

            asyncio.run(get_products_raw(req=GetProductsRequest(brief="test")))

        _, identity = mock_impl.call_args.args
        assert identity is None
