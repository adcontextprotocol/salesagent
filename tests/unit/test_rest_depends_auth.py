"""Regression tests for REST Depends-based auth resolution.

Validates that REST routes use FastAPI Depends() for identity resolution
instead of manual _resolve_auth/_require_auth calls inside handler bodies.

Core invariant: Identity resolution for REST routes is declared in function
signatures via FastAPI Depends, never called manually inside handler bodies.

"""

import inspect

from fastapi.params import Depends


class TestResolveAuthDependencyExists:
    """auth_context.py should export resolve_auth and require_auth Depends."""

    def test_resolve_auth_exists_in_auth_context(self):
        """resolve_auth should be exported from auth_context."""
        from src.core.auth_context import resolve_auth

        assert resolve_auth is not None

    def test_require_auth_exists_in_auth_context(self):
        """require_auth should be exported from auth_context."""
        from src.core.auth_context import require_auth

        assert require_auth is not None

    def test_resolve_auth_is_depends_instance(self):
        """resolve_auth should be a FastAPI Depends instance."""
        from src.core.auth_context import resolve_auth

        assert isinstance(resolve_auth, Depends), f"resolve_auth is {type(resolve_auth).__name__}, expected Depends"

    def test_require_auth_is_depends_instance(self):
        """require_auth should be a FastAPI Depends instance."""
        from src.core.auth_context import require_auth

        assert isinstance(require_auth, Depends), f"require_auth is {type(require_auth).__name__}, expected Depends"


class TestApiV1NoManualAuthCalls:
    """api_v1.py should not have _resolve_auth or _require_auth helpers."""

    def test_no_resolve_auth_in_api_v1(self):
        """_resolve_auth should not exist in api_v1 (moved to auth_context Depends)."""
        import src.routes.api_v1 as api_v1_mod

        assert not hasattr(api_v1_mod, "_resolve_auth"), (
            "_resolve_auth still exists in api_v1.py — should be replaced by Depends"
        )

    def test_no_require_auth_in_api_v1(self):
        """_require_auth should not exist in api_v1 (moved to auth_context Depends)."""
        import src.routes.api_v1 as api_v1_mod

        assert not hasattr(api_v1_mod, "_require_auth"), (
            "_require_auth still exists in api_v1.py — should be replaced by Depends"
        )


class TestRouteSignaturesUseDependsForIdentity:
    """Every generated REST route declares identity via Depends, and takes no raw Request.

    Over the LIVE routes, not a hand-written list of nine names -- two of which named tools
    that no longer exist, and none of which would have covered a tool added tomorrow. The
    routes are generated from TOOLS by one handler factory, so iterating what the app
    actually registered is both shorter and stronger than repeating one assertion per row.
    """

    @staticmethod
    def _rest_routes():
        from src.app import app
        from src.core.tools.registry import TOOLS

        rest_tools = {name for name, spec in TOOLS.items() if spec.rest is not None}
        routes = [r for r in app.routes if getattr(r, "name", None) in rest_tools]
        assert routes, "no REST routes registered -- the derivation produced nothing"
        return routes

    def test_every_rest_route_resolves_identity_through_depends(self):
        for route in self._rest_routes():
            param = inspect.signature(route.endpoint).parameters.get("identity")
            assert param is not None, f"{route.name} should have an 'identity' parameter"
            assert isinstance(param.default, Depends), f"{route.name} identity should use Depends"

    def test_no_route_takes_a_raw_request(self):
        """A handler reading Request itself would be resolving auth by hand again."""
        for route in self._rest_routes():
            params = inspect.signature(route.endpoint).parameters
            assert "request" not in params, f"{route.name} should not take a raw Request"
class TestResolveAuthDepBehavior:
    """Test the resolve_auth dependency function behavior directly."""

    def test_returns_identity_without_token(self):
        """resolve_auth dep must still return a ResolvedIdentity (not bare None)
        when no auth token is present (salesagent-zna9) — matching
        resolve_identity_from_context()'s MCP/A2A contract, so header-based
        tenant detection (Host / x-adcp-tenant) always runs for discovery
        endpoints regardless of credential presence.

        Mocks resolve_identity() (unit test, no DB) — the real header-based
        DB resolution is covered by
        tests/integration/test_rest_auth_optional_tenant_resolution.py.
        """
        from unittest.mock import patch

        from src.core.auth_context import AuthContext, _resolve_auth_dep
        from src.core.resolved_identity import ResolvedIdentity
        from tests.factories.principal import PrincipalFactory

        auth_ctx = AuthContext.unauthenticated()
        mock_identity = PrincipalFactory.make_identity(principal_id=None, tenant_id=None, tenant=None, protocol="rest")

        with patch("src.core.resolved_identity.resolve_identity", return_value=mock_identity) as mock_resolve:
            result = _resolve_auth_dep(auth_ctx)

        mock_resolve.assert_called_once_with(headers={}, auth_token=None, require_valid_token=False, protocol="rest")
        assert isinstance(result, ResolvedIdentity)
        assert result.principal_id is None

    def test_returns_identity_with_valid_token(self):
        """resolve_auth dep should return ResolvedIdentity with valid token."""
        from unittest.mock import patch

        from src.core.auth_context import AuthContext, _resolve_auth_dep
        from src.core.resolved_identity import ResolvedIdentity

        auth_ctx = AuthContext(
            auth_token="test-token",
            headers={"x-adcp-auth": "test-token"},
        )

        mock_identity = ResolvedIdentity(
            principal_id="test_principal",
            tenant_id="default",
            tenant={"tenant_id": "default"},
            protocol="rest",
        )

        with patch("src.core.resolved_identity.resolve_identity", return_value=mock_identity):
            result = _resolve_auth_dep(auth_ctx)

        assert isinstance(result, ResolvedIdentity)
        assert result.principal_id == "test_principal"

    def test_passes_auth_token_to_resolve_identity(self):
        """resolve_auth dep should pass pre-extracted token to avoid redundant extraction."""
        from tests.helpers import assert_resolve_auth_dep_passes_token

        assert_resolve_auth_dep_passes_token()


class TestRequireAuthDepBehavior:
    """Test the require_auth dependency function behavior directly."""

    def test_raises_auth_missing_without_token(self):
        """No credential presented -> AUTH_MISSING / correctable.

        Asserted on the wire envelope, not on the exception class:
        ``AdCPAuthRequiredError`` (AUTH_MISSING) is a SUBCLASS of
        ``AdCPAuthenticationError`` (AUTH_INVALID), so ``pytest.raises`` on the
        parent passes for either code and cannot tell the two rejections apart —
        which is the whole distinction the v3.1.1 enum draws.
        """
        import pytest

        from src.core.auth_context import AuthContext, _require_auth_dep
        from src.core.exceptions import AdCPSalesAgentError, build_two_layer_error_envelope
        from tests.helpers import assert_envelope_shape

        auth_ctx = AuthContext.unauthenticated()
        with pytest.raises(AdCPSalesAgentError) as exc_info:
            _require_auth_dep(auth_ctx)

        assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "AUTH_MISSING", recovery="correctable")

    def test_raises_auth_invalid_when_presented_credential_resolves_to_no_principal(self):
        """A credential WAS presented but resolved to no principal -> AUTH_INVALID / terminal.

        Grades the dependency's second guard. ``resolve_identity`` normally
        raises AUTH_INVALID itself for an unresolvable token, so this branch is
        a backstop — and a backstop is exactly what must be shaped correctly,
        because when it does fire it is answering a buyer who DID send a
        credential. It previously raised AUTH_MISSING "for parity with the guard
        above"; the two guards answer different questions (absent vs
        unresolvable), so parity was the defect.

        The v3.1.1 enum keys the split on header presence: AUTH_MISSING is for
        "no ``Authorization`` header was included", AUTH_INVALID for "an
        ``Authorization`` header was present but verification failed"
        (adcp 6.6.0, _schemas/3.1/enums/error-code.json).
        """
        from unittest.mock import patch

        import pytest

        from src.core.auth_context import AuthContext, _require_auth_dep
        from src.core.exceptions import AdCPSalesAgentError, build_two_layer_error_envelope
        from tests.factories.principal import PrincipalFactory
        from tests.helpers import assert_envelope_shape

        auth_ctx = AuthContext(auth_token="presented-token", headers={"x-adcp-auth": "presented-token"})
        principal_less = PrincipalFactory.make_identity(
            principal_id=None,
            tenant_id="default",
            auth_token="presented-token",
            protocol="rest",
        )

        with patch("src.core.resolved_identity.resolve_identity", return_value=principal_less):
            with pytest.raises(AdCPSalesAgentError) as exc_info:
                _require_auth_dep(auth_ctx)

        assert_envelope_shape(build_two_layer_error_envelope(exc_info.value), "AUTH_INVALID", recovery="terminal")

    def test_returns_identity_with_valid_token(self):
        """require_auth dep should return ResolvedIdentity with valid token."""
        from unittest.mock import patch

        from src.core.auth_context import AuthContext, _require_auth_dep
        from src.core.resolved_identity import ResolvedIdentity

        auth_ctx = AuthContext(
            auth_token="test-token",
            headers={"x-adcp-auth": "test-token"},
        )

        mock_identity = ResolvedIdentity(
            principal_id="test_principal",
            tenant_id="default",
            tenant={"tenant_id": "default"},
            protocol="rest",
        )

        with patch("src.core.resolved_identity.resolve_identity", return_value=mock_identity):
            result = _require_auth_dep(auth_ctx)

        assert isinstance(result, ResolvedIdentity)
        assert result.principal_id == "test_principal"
