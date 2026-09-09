"""Meta-tests for AdCPTestClient — the transport-generic dispatch core (the transport-generic client).

``AdCPTestClient.call(tool, payload, transport)`` bypasses every env's
hand-written ``call_a2a``/``call_mcp``/``build_rest_body``/``parse_rest_response``
quartet (design doc §1) and dispatches purely from the derived
``ADDRESS_TABLE`` + the shared ``_run_mcp_client``/``_run_a2a_handler``/
``_prepare_rest_request`` primitives on ``BaseTestEnv``/``IntegrationEnv``.

These tests deliberately use envs that do NOT implement ``call_a2a``/
``call_mcp`` (e.g. ``tests.harness.product_unit.ProductEnv``) to prove the
client does not need those per-env methods at all — the whole point of the
design (§1 "MediaBuyDualEnv is the reductio").
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.harness._base import BaseTestEnv
from tests.harness.address_table import NoAddressForTransport, ToolAddress
from tests.harness.client import AdCPTestClient, _wrap_rest, unwrap_rest_response
from tests.harness.transport import Transport


class TestClientMcpDispatchNoDb:
    """MCP dispatch through the generic client — no per-env call_mcp needed."""

    def test_get_products_via_mcp_succeeds(self):
        from tests.harness.product_unit import ProductEnv

        with ProductEnv() as env:
            env.add_product(product_id="prod_001", name="Display Ad")
            client = AdCPTestClient(env)

            result = client.call("get_products", {"brief": "display ads"}, Transport.MCP)

        assert result.is_success, result.error
        assert result.envelope["transport"] == "mcp"
        assert result.wire_response is not None
        # payload is the pinned GetProductsResponse model, not the raw dict —
        # attribute access, not subscripting.
        product_ids = [p.product_id for p in result.payload.products]
        assert product_ids == ["prod_001"]

    def test_unauthenticated_dispatch_surfaces_auth_required(self):
        """identity=None (EXPLICIT) reaches the server unauthenticated — the same
        convention env._run_mcp_client already gives identity=None (design doc §3
        table). Proves the client's _NO_IDENTITY_OVERRIDE sentinel correctly
        distinguishes "no override" from "explicit unauthenticated"."""

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("list_accounts", {}, Transport.MCP, identity=None)

        assert result.is_error
        # AUTH_MISSING, not the deprecated AUTH_REQUIRED alias: no x-adcp-auth
        # header was presented at all. adcp==6.6.0 (3.1 error-code enum) marks
        # AUTH_REQUIRED "Deprecated — use AUTH_MISSING (no credentials
        # presented) or AUTH_INVALID (credentials presented and rejected)", and
        # the MCP boundary translates AdCPAuthRequiredError to AUTH_MISSING.
        result.assert_wire_error("AUTH_MISSING")


class TestClientA2ADispatchNoDb:
    """A2A dispatch through the generic client — no per-env call_a2a needed."""

    def test_get_products_via_a2a_succeeds(self):
        from tests.harness.product_unit import ProductEnv

        with ProductEnv() as env:
            env.add_product(product_id="prod_001", name="Display Ad")
            client = AdCPTestClient(env)

            result = client.call("get_products", {"brief": "display ads"}, Transport.A2A)

        assert result.is_success, result.error
        assert result.envelope["transport"] == "a2a"
        # payload is the pinned GetProductsResponse model, not the raw dict —
        # attribute access, not subscripting.
        product_ids = [p.product_id for p in result.payload.products]
        assert product_ids == ["prod_001"]


class TestClientNoAddressForTransport:
    """Tools that don't exist on a transport raise, they don't KeyError or hang."""

    def test_a2a_only_skill_on_rest_raises_no_address(self):
        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            with pytest.raises(NoAddressForTransport):
                client.call("approve_creative", {}, Transport.REST)


class TestClientRestWrapPathParamPeeling:
    """Pure-function coverage of the path-param generalization (design doc §4) —
    the rule that replaces MediaBuyDualEnv's hand-coded single-route version."""

    def test_peels_path_param_into_url_and_out_of_body(self):
        address = ToolAddress(
            Transport.REST, name="update_media_buy", path_template="/api/v1/media-buys/{media_buy_id}", method="put"
        )
        wrapped = _wrap_rest(address, {"media_buy_id": "mb_123", "paused": True})

        assert wrapped["url"] == "/api/v1/media-buys/mb_123"
        assert wrapped["body"] == {"paused": True}

    def test_no_path_params_leaves_body_and_url_untouched(self):
        address = ToolAddress(Transport.REST, name="get_products", path_template="/api/v1/products", method="post")
        wrapped = _wrap_rest(address, {"brief": "video ads"})

        assert wrapped["url"] == "/api/v1/products"
        assert wrapped["body"] == {"brief": "video ads"}

    def test_multiple_path_params_all_peeled(self):
        address = ToolAddress(Transport.REST, name="fake_tool", path_template="/api/v1/a/{a_id}/b/{b_id}", method="put")
        wrapped = _wrap_rest(address, {"a_id": "1", "b_id": "2", "extra": "kept"})

        assert wrapped["url"] == "/api/v1/a/1/b/2"
        assert wrapped["body"] == {"extra": "kept"}


class TestRestRequestKwargsBodilessVerbs:
    """get_adcp_capabilities becoming REST-resolvable
    (GET /api/v1/capabilities, resolved via the route's declared
    operation_id — formerly via address_table.py's REST_TOOL_ALIASES)
    exposed that ``_deliver_rest``/``_deliver_e2e_rest`` sent ``json=`` for
    EVERY verb — a TypeError for GET, since neither starlette
    TestClient.get nor httpx.Client.get accept a ``json`` kwarg. Pins the
    fix at the shared kwargs-building helper, not just end to end."""

    def test_get_omits_json_body(self):
        from tests.harness.client import _rest_request_kwargs

        assert _rest_request_kwargs("get", {"some": "body"}) == {}

    def test_delete_omits_json_body(self):
        from tests.harness.client import _rest_request_kwargs

        assert _rest_request_kwargs("delete", {"some": "body"}) == {}

    def test_post_keeps_json_body(self):
        from tests.harness.client import _rest_request_kwargs

        assert _rest_request_kwargs("post", {"some": "body"}) == {"json": {"some": "body"}}

    def test_put_keeps_json_body(self):
        from tests.harness.client import _rest_request_kwargs

        assert _rest_request_kwargs("put", {"some": "body"}) == {"json": {"some": "body"}}

    def test_extra_kwargs_pass_through_regardless_of_verb(self):
        from tests.harness.client import _rest_request_kwargs

        assert _rest_request_kwargs("get", {}, headers={"X": "1"}) == {"headers": {"X": "1"}}
        assert _rest_request_kwargs("post", {"a": 1}, headers={"X": "1"}) == {
            "json": {"a": 1},
            "headers": {"X": "1"},
        }


class TestClientRestDispatchNoDb:
    """In-process Transport.REST dispatch through the generic client for a
    GET-verb tool. get_rest_client() requires IntegrationEnv (real DB) for a
    genuine end-to-end call, so this proves the narrower, decisive thing at
    unit level without one: DELIVER builds the right call shape (no ``json=``
    for GET) and does not raise TypeError before ever reaching the network."""

    def test_get_dispatch_does_not_pass_json_kwarg(self):
        from tests.harness.client import _deliver_rest

        calls: list[dict[str, Any]] = []

        class _FakeGetClient:
            def get(self, url: str, **kwargs: Any) -> Any:
                calls.append({"url": url, **kwargs})
                return "fake-response"

        class _UnitEnv(BaseTestEnv):
            def get_rest_client(self) -> Any:
                return _FakeGetClient()

            def identity_for(self, transport: Transport) -> Any:
                return None

        address = ToolAddress(
            Transport.REST, name="get_adcp_capabilities", path_template="/api/v1/capabilities", method="get"
        )

        with _UnitEnv() as env:
            result = _deliver_rest(env, address, {"url": "/api/v1/capabilities", "body": {}}, identity=None)

        assert result == "fake-response"
        assert calls == [{"url": "/api/v1/capabilities"}]  # no `json` key — the TypeError this test guards against


class TestUnwrapRestResponse:
    """``unwrap_rest_response`` — the one REST unwrap
    shared by ``RestDispatcher``, ``RestE2EDispatcher``
    (``tests/harness/dispatchers.py``) and the generic client's
    ``_unwrap_rest``. Before this consolidation, the generic client core's
    REST unwrap aliased ``payload`` and ``wire_response`` to the SAME dict
    object, dropping the #1417 pristine-wire deepcopy rule."""

    class _FakeRestResponse:
        def __init__(self, status_code: int, body: dict) -> None:
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self._body = body

        def json(self):
            return self._body

    def test_payload_and_wire_response_do_not_alias(self):
        raw = self._FakeRestResponse(200, {"products": [{"product_id": "prod_001"}]})

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            result = unwrap_rest_response(env, raw, Transport.REST, lambda body: body)

        assert result.payload is not result.wire_response
        result.payload["products"].append({"product_id": "injected"})
        assert result.wire_response["products"] == [{"product_id": "prod_001"}]

    def test_tag_derived_from_transport_enum_not_a_literal(self):
        raw = self._FakeRestResponse(200, {})

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            rest_result = unwrap_rest_response(env, raw, Transport.REST, lambda body: body)
            e2e_result = unwrap_rest_response(env, raw, Transport.E2E_REST, lambda body: body)

        assert rest_result.envelope["transport"] == "rest"
        assert e2e_result.envelope["transport"] == "e2e_rest"

    def test_typed_parse_policy_gets_its_own_deepcopy(self):
        """Dispatchers pass env.parse_rest_response (a typed parser) as
        parse_policy — it must receive a deep copy too, not the dict backing
        wire_response, so an in-place-mutating parser (e.g.
        _parse_update_rest_response popping "status", #1417) never corrupts
        the stashed wire capture."""
        raw = self._FakeRestResponse(200, {"status": "accepted", "media_buy_id": "mb_1"})

        def _mutating_parser(data: dict) -> dict:
            data.pop("status", None)
            return data

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            result = unwrap_rest_response(env, raw, Transport.REST, _mutating_parser)

        assert result.payload == {"media_buy_id": "mb_1"}
        assert result.wire_response == {"status": "accepted", "media_buy_id": "mb_1"}


class TestClientE2eRestDelivery:
    """E2E_REST DELIVER (``_deliver_e2e_rest``, the wire-grading work) — real
    HTTP through nginx to a live Docker stack. Mocks ``httpx.Client`` so
    coverage does not require a live server; genuine e2e-with-real-server
    verification happens in ``tests/e2e/``."""

    def _make_env_with_e2e_config(self):
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        return _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack.test", postgres_url="postgresql://x/y"))

    def test_e2e_rest_delivery_sends_real_http_request(self, monkeypatch):
        import httpx

        from tests.factories.principal import PrincipalFactory

        captured = {}

        class _FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"products": []}

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                captured["base_url"] = base_url
                captured["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="rest", auth_token="tok_abc"
        )

        with self._make_env_with_e2e_config() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_REST, identity=identity)

        assert result.is_success, result.error
        assert captured["base_url"] == "http://e2e-stack.test"
        assert captured["url"] == "/api/v1/products"
        assert captured["json"] == {"brief": "video ads"}
        assert captured["headers"]["x-adcp-auth"] == "tok_abc"
        assert captured["headers"]["x-adcp-tenant"] == identity.tenant["subdomain"]

    def test_e2e_rest_delivery_sends_same_header_set_the_deleted_inline_code_did(self, monkeypatch):
        """``_deliver_e2e_rest`` (via ``e2e_identity_headers``)
        must emit the SAME x-adcp-auth / x-adcp-tenant / x-dry-run header set that
        ``RestE2EDispatcher`` used to build inline, before commit 4363757dc
        deleted that code and routed delivery through this shared function
        instead — e2e_rest is a live caller (real HTTP to the Docker stack), so a
        regression here silently drops a header a real server request depends on.
        The auth/tenant pair already has coverage above; this is the one place
        x-dry-run (the third header the deleted code built) is checked."""
        import httpx

        from tests.factories.principal import PrincipalFactory

        captured = {}

        class _FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"products": []}

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="rest", auth_token="tok_dry", dry_run=True
        )

        with self._make_env_with_e2e_config() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_REST, identity=identity)

        assert result.is_success, result.error
        assert captured["headers"] == {
            "Content-Type": "application/json",
            "x-adcp-auth": "tok_dry",
            "x-adcp-tenant": identity.tenant["subdomain"],
            "x-dry-run": "true",
        }

    def test_e2e_rest_delivery_unauthenticated_omits_auth_header(self, monkeypatch):
        import httpx

        from src.core.exceptions import AdCPAuthRequiredError, build_two_layer_error_envelope

        wire_body = build_two_layer_error_envelope(AdCPAuthRequiredError("no credentials"))
        captured = {}

        class _FakeResponse:
            status_code = 401
            headers = {"content-type": "application/json"}
            text = '{"errors": [{"code": "AUTH_REQUIRED"}]}'

            def json(self):
                return wire_body

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        with self._make_env_with_e2e_config() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_REST, identity=None)

        assert "x-adcp-auth" not in captured["headers"]
        assert result.is_error
        # The asserted body is wire_body above — built by production's
        # build_two_layer_error_envelope(AdCPAuthRequiredError(...)), which
        # emits AUTH_MISSING (no credentials presented) rather than the
        # deprecated AUTH_REQUIRED alias. Not AUTH_INVALID: no header was sent.
        result.assert_wire_error("AUTH_MISSING")

    def test_e2e_rest_delivery_requires_e2e_config(self):
        from tests.harness.address_table import ToolAddress
        from tests.harness.client import _deliver_e2e_rest

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            address = ToolAddress(Transport.E2E_REST, name="/api/v1/products", method="post")
            with pytest.raises(RuntimeError, match="e2e_config"):
                _deliver_e2e_rest(env, address, {"url": "/api/v1/products", "body": {}}, None)


class TestRestE2EDispatcherIdentityDefault:
    """``RestE2EDispatcher`` (``tests/harness/dispatchers.py``) -- the legacy
    ``env.call_via(Transport.E2E_REST, **kwargs)`` entry point. Regression
    coverage for: omitting ``identity=`` entirely (not
    ``identity=None``) must fall back to ``env.identity_for(Transport.E2E_REST)``
    inside ``_deliver_e2e_rest`` -- before the fix, ``kwargs.pop("identity",
    None)`` forwarded a bare ``None`` on omission, which ``_deliver_e2e_rest``
    cannot distinguish from an explicit unauthenticated request."""

    def test_omitted_identity_falls_back_to_env_identity_for(self, monkeypatch):
        import httpx

        from tests.harness.dispatchers import RestE2EDispatcher
        from tests.harness.transport import E2EConfig, Transport

        captured = {}

        class _FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {}

        class _FakeClient:
            def __init__(self, *, base_url, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def post(self, url, *, json, headers):
                captured["headers"] = headers
                return _FakeResponse()

        monkeypatch.setattr(httpx, "Client", _FakeClient)

        class _RestUnitEnv(BaseTestEnv):
            REST_ENDPOINT = "/api/v1/products"

            def parse_rest_response(self, data):
                return data

        env = _RestUnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack.test", postgres_url="postgresql://x/y"))
        expected_tenant = env.identity_for(Transport.E2E_REST).tenant["subdomain"]

        # No identity= kwarg at all -- the omission case, not identity=None.
        result = RestE2EDispatcher().dispatch(env)

        assert result.is_success, result.error
        assert captured["headers"]["x-adcp-tenant"] == expected_tenant


class TestClientE2eMcpDelivery:
    """Real e2e MCP DELIVER — mocks the fastmcp
    ``Client``/HTTP transport layer for unit-level coverage. Genuine
    e2e-with-a-real-server verification happens in ``tests/e2e/`` via
    ``./run_all_tests.sh`` (no Docker stack available in this worktree)."""

    class _FakeToolResult:
        def __init__(self, structured_content: dict) -> None:
            self.structured_content = structured_content

    class _FakeMcpClient:
        """Records the transport it was built with and the tool_name/arguments
        of the last call_tool — enough to assert DELIVER built the real HTTP
        transport with the right URL/headers and dispatched the right tool."""

        instances: list = []

        def __init__(self, transport=None):
            self.transport = transport
            self.calls: list[tuple[str, dict]] = []
            type(self).instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            # Empty products list — a full Product needs many required nested
            # fields (publisher_properties, pricing_options,
            # reporting_capabilities, ...) irrelevant to what these tests
            # verify (transport wiring / headers / delegation); an empty list
            # still round-trips through GetProductsResponse
            # (the spec_response_model parse-back).
            return TestClientE2eMcpDelivery._FakeToolResult({"products": []})

    def test_e2e_mcp_dispatch_builds_real_http_transport_and_succeeds(self, monkeypatch):
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        self._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", self._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)

        result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_MCP, identity=None)

        assert result.is_success, result.error
        # Tag derived from Transport.E2E_MCP.value ("e2e_mcp") — before
        # this incorrectly pinned the in-process "mcp"
        # tag on an E2E dispatch (client.py's _unwrap_mcp_success is shared
        # by both Transport.MCP and Transport.E2E_MCP).
        assert result.envelope["transport"] == "e2e_mcp"
        assert result.wire_response == {"products": []}

        fake_client = self._FakeMcpClient.instances[0]
        assert fake_client.transport.url == "http://e2e-host:9000/mcp/"
        assert fake_client.transport.headers == {}  # identity=None -> no auth headers
        assert fake_client.calls == [("get_products", {"brief": "video ads"})]

    def test_e2e_mcp_dispatch_sends_auth_headers_from_identity(self, monkeypatch):
        from tests.factories.principal import PrincipalFactory
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        self._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", self._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)
        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="mcp", auth_token="tok_123"
        )

        client.call("get_products", {"brief": "video ads"}, Transport.E2E_MCP, identity=identity)

        fake_client = self._FakeMcpClient.instances[0]
        assert fake_client.transport.headers["x-adcp-auth"] == "tok_123"

    def test_e2e_mcp_dispatch_requires_e2e_config(self):
        """Missing env.e2e_config is a genuine precondition failure (mirrors
        RestE2EDispatcher.dispatch's own check) — caught by
        AdCPTestClient.call()'s generic except and surfaced as an error
        TransportResult, same as any other DELIVER-raised Exception (NOT the
        NotImplementedError special-case that re-raises loudly)."""
        from tests.harness._base import BaseTestEnv

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_MCP, identity=None)

        assert result.is_error
        assert "e2e_config" in str(result.error)

    def test_e2e_mcp_dispatch_tool_error_unwraps_to_adcp_error(self, monkeypatch):
        from fastmcp.exceptions import ToolError

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        class _FailingMcpClient(self._FakeMcpClient):
            async def call_tool(self, name, arguments):
                raise ToolError(
                    '{"errors": [{"code": "AUTH_REQUIRED", "message": "no auth", "recovery": "correctable"}], '
                    '"adcp_error": {"code": "AUTH_REQUIRED", "message": "no auth", "recovery": "correctable"}}'
                )

        monkeypatch.setattr("fastmcp.Client", _FailingMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        client = AdCPTestClient(env)

        result = client.call("get_products", {"brief": "x"}, Transport.E2E_MCP, identity=None)

        assert result.is_error
        result.assert_wire_error("AUTH_REQUIRED")


class TestClientE2eA2aDelivery:
    """``_deliver_e2e_a2a`` (the wire-grading work) — real JSON-RPC
    ``message/send`` HTTP delivery, HTTP layer mocked (unit-level; genuine
    e2e-with-real-server verification happens in tests/e2e/ against a live
    Docker stack, per this task's scope)."""

    @staticmethod
    def _rpc_success_body(*, task_id: str = "task_abc123", state: str = "TASK_STATE_COMPLETED", artifact_data: dict):
        return {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": task_id,
                    "contextId": "ctx_1",
                    "status": {"state": state},
                    "artifacts": [{"artifactId": "art-1", "parts": [{"data": artifact_data}]}],
                }
            },
        }

    def test_success_posts_jsonrpc_and_returns_stripped_artifact_data(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        # Empty products list — a full Product needs many required nested
        # fields (publisher_properties, pricing_options, reporting_capabilities,
        # ...) that are irrelevant to what this test actually verifies (the
        # JSON-RPC envelope shape and the artifact-stripping behavior below);
        # an empty list still round-trips through GetProductsResponse
        # (the spec_response_model parse-back) without
        # hand-maintaining an unrelated fixture of the full Product schema.
        artifact_data = {"products": [], "message": "ok", "success": True}
        rpc_response = self._rpc_success_body(artifact_data=artifact_data)

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "video ads"}, Transport.E2E_A2A)

        assert result.is_success, result.error
        # payload is the pinned GetProductsResponse model, not the raw dict —
        # attribute access, not subscripting.
        assert result.payload.products == []
        assert result.wire_response == artifact_data  # unstripped — captured before pop

        # POST went to the real A2A JSON-RPC endpoint with a well-formed envelope.
        call_args = mock_post.call_args
        assert call_args.args[0] == "/a2a"
        rpc_body = call_args.kwargs["json"]
        assert rpc_body["jsonrpc"] == "2.0"
        assert rpc_body["method"] == "SendMessage"
        skill_part = rpc_body["params"]["message"]["parts"][0]["data"]
        assert skill_part["skill"] == "get_products"
        assert skill_part["parameters"] == {"brief": "video ads"}

    def test_identity_maps_to_auth_and_tenant_headers(self):
        from unittest.mock import MagicMock, patch

        from tests.factories.principal import PrincipalFactory
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        identity = PrincipalFactory.make_identity(
            principal_id="p1", tenant_id="t1", protocol="a2a", auth_token="tok_123"
        )
        rpc_response = self._rpc_success_body(artifact_data={"message": "ok", "success": True})

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A, identity=identity)

        assert result.is_success, result.error
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["x-adcp-auth"] == "tok_123"
        assert headers["x-adcp-tenant"] == identity.tenant["subdomain"]

    def test_unauthenticated_dispatch_sends_no_auth_header(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = self._rpc_success_body(artifact_data={"message": "ok", "success": True})

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                client.call("get_products", {"brief": "x"}, Transport.E2E_A2A, identity=None)

        headers = mock_post.call_args.kwargs["headers"]
        assert "x-adcp-auth" not in headers
        assert "x-adcp-tenant" not in headers

    def test_task_state_failed_reconstructs_wire_error(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        envelope = {"adcp_error": {"code": "PRODUCT_NOT_FOUND", "message": "no such product", "recovery": "retry"}}
        rpc_response = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": "task_fail",
                    "status": {"state": "TASK_STATE_FAILED"},
                    "artifacts": [{"artifactId": "art-1", "parts": [{"data": envelope}]}],
                }
            },
        }

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A)

        assert result.is_error
        assert result.wire_error_envelope == envelope

    def test_task_state_submitted_synthesizes_submitted_wire(self):
        """``create_media_buy`` is the named no-pinned-response-model case
        : its SDK response type is a ``Union`` of
         outcome variants (``spec_response_model`` returns ``None`` for it, see
         that function's docstring), so UNWRAP cannot pick a single class to
         parse the synthesized "submitted" wire into. ``payload`` stays
         explicitly ``None`` — ``result.error is None`` (not ``is_success``,
         which requires a non-``None`` payload) is the correct success check
         here — and ``wire_response`` carries the raw dict, exactly as
         production callers that only read the wire body already expect."""
        from unittest.mock import MagicMock, patch

        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "task": {
                    "id": "task_submitted_1",
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                }
            },
        }

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("create_media_buy", {"buyer_ref": "x"}, Transport.E2E_A2A)

        assert result.error is None, result.error
        assert result.payload is None
        assert result.wire_response == {"status": "submitted", "task_id": "task_submitted_1"}

    def test_http_error_status_still_surfaces_the_wire_error_envelope(self):
        """An A2A response with an HTTP error status must NOT discard its body.

        change-set B4 : ``_deliver_e2e_a2a``
        calls ``response.raise_for_status()`` BEFORE ``response.json()``, so on
        any >=400 the JSON-RPC error body — the only place the AdCP two-layer
        envelope exists on this leg — is thrown away and the caller gets a bare
        ``httpx.HTTPStatusError``. ``unwrap_a2a_error``
        (``tests/harness/client.py``) then has nothing to read, so
        ``wire_error_envelope`` is ``None`` and every error-path Then step that
        asserts on the wire (``tests/CLAUDE.md`` § Error Verification Policy —
        the wire envelope is the primary authority, reconstructed exceptions
        are lossy) fails for a reason unrelated to the behavior under test.

        The REST sibling already gets this right: ``unwrap_rest_response``
        parses the body on ``status_code >= 400`` and hands it out as
        ``wire_error_envelope``. B4 makes A2A match — parse the body first,
        then let the existing ``"error" in body`` branch reconstruct through
        ``_envelope_to_adcp_error``, which stashes the real envelope on the
        exception for ``_wire_envelope_from_exception`` to pick up.

        Lives here beside the other ``_deliver_e2e_a2a`` graders (same mocked
        -httpx convention, same ``TestClientE2eA2aDelivery`` fixtures) because
        the HTTP-error branch of this DELIVER function is not reachable from a
        BDD scenario without a live Docker stack; the live-stack sibling
        obligation is graded by
        ``tests/integration/test_harness_client_transport_parity.py``
        ``TestEnvVsClientEquivalenceE2E::test_e2e_a2a_success_and_error_equivalence``.
        """
        from unittest.mock import MagicMock, patch

        import httpx

        from tests.harness.transport import E2EConfig
        from tests.helpers import assert_envelope_shape

        class _UnitEnv(BaseTestEnv):
            pass

        envelope = {
            "adcp_error": {
                "code": "AUTH_REQUIRED",
                "message": "authentication required",
                "recovery": "correctable",
            },
            "errors": [
                {
                    "code": "AUTH_REQUIRED",
                    "message": "authentication required",
                    "recovery": "correctable",
                }
            ],
        }
        rpc_error_body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "error": {"code": -32600, "message": "authentication required", "data": envelope},
        }

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            client = AdCPTestClient(env)
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_error_body))
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Client error '401 Unauthorized'",
                    request=httpx.Request("POST", "http://e2e-stack:8080/a2a"),
                    response=httpx.Response(401),
                )
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A, identity=None)

        assert result.is_error, f"a 401 must be an error result, got payload {result.payload!r}"
        assert_envelope_shape(
            result.wire_error_envelope,
            "AUTH_REQUIRED",
            recovery="correctable",
            message_substr="authentication required",
        )

    def test_missing_e2e_config_raises(self):
        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            client = AdCPTestClient(env)
            result = client.call("get_products", {"brief": "x"}, Transport.E2E_A2A)

        assert result.is_error
        assert "e2e_config" in str(result.error)


class TestA2AE2EDispatcher:
    """``A2AE2EDispatcher`` (the wire-grading work) — the legacy
    ``env.call_via(Transport.E2E_A2A, ...)`` entry point, delegating to
    ``AdCPTestClient``/``_deliver_e2e_a2a`` under the hood."""

    def test_dispatch_requires_a_tool_name(self):
        from tests.harness.dispatchers import A2AE2EDispatcher
        from tests.harness.transport import E2EConfig, MissingToolNameError

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            # MissingToolNameError subclasses NotImplementedError, so this stays
            # the "hard wiring failure" _dispatch_core re-raises rather than
            # downgrading into an error TransportResult -- pinning the exact
            # unified type instead of the bare parent.
            with pytest.raises(MissingToolNameError, match="tool_name"):
                A2AE2EDispatcher().dispatch(env, brief="video ads")

    def test_dispatch_with_tool_name_delegates_to_client(self):
        from unittest.mock import MagicMock, patch

        from tests.harness.dispatchers import A2AE2EDispatcher
        from tests.harness.transport import E2EConfig

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = TestClientE2eA2aDelivery._rpc_success_body(
            artifact_data={"products": [], "message": "ok", "success": True}
        )

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                result = A2AE2EDispatcher().dispatch(env, tool_name="get_products", brief="video ads")

        assert result.is_success, result.error
        skill_part = mock_post.call_args.kwargs["json"]["params"]["message"]["parts"][0]["data"]
        assert skill_part["skill"] == "get_products"
        assert skill_part["parameters"] == {"brief": "video ads"}

    def test_omitted_identity_falls_back_to_env_identity_for(self):
        """Consistency/regression coverage for the identity-default reconciliation
        : A2AE2EDispatcher already handled omission
         correctly before this ticket (its own local ``_NO_OVERRIDE``), so this
         proves the refactor onto the shared ``NO_IDENTITY_OVERRIDE`` sentinel +
         ``_dispatch_core`` preserves that behavior — the sibling assertion to
         McpE2EDispatcher's/RestE2EDispatcher's genuine bug-fix regression tests
         (acceptance criterion: identical call_via omissions authenticate
         identically on every transport)."""
        from unittest.mock import MagicMock, patch

        from tests.harness.dispatchers import A2AE2EDispatcher
        from tests.harness.transport import E2EConfig, Transport

        class _UnitEnv(BaseTestEnv):
            pass

        rpc_response = TestClientE2eA2aDelivery._rpc_success_body(
            artifact_data={"products": [], "message": "ok", "success": True}
        )

        with _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-stack:8080", postgres_url="postgresql://x")) as env:
            expected_tenant = env.identity_for(Transport.E2E_A2A).tenant["subdomain"]

            with patch("httpx.Client") as mock_client_cls:
                mock_response = MagicMock()
                mock_response.json.side_effect = lambda: json.loads(json.dumps(rpc_response))
                mock_response.raise_for_status.return_value = None
                mock_post = mock_client_cls.return_value.__enter__.return_value.post
                mock_post.return_value = mock_response

                # No identity= kwarg at all -- the omission case, not identity=None.
                result = A2AE2EDispatcher().dispatch(env, tool_name="get_products", brief="video ads")

        assert result.is_success, result.error
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["x-adcp-tenant"] == expected_tenant


class TestMcpE2EDispatcherDelegation:
    """``McpE2EDispatcher`` (``tests/harness/dispatchers.py``) is the legacy
    ``env.call_via(Transport.E2E_MCP, **kwargs)`` entry point — it must
    delegate to ``AdCPTestClient`` rather than reimplement ADDRESS/WRAP/
    DELIVER/UNWRAP a second time."""

    def test_requires_tool_name(self):
        from tests.harness._base import BaseTestEnv
        from tests.harness.dispatchers import McpE2EDispatcher
        from tests.harness.transport import MissingToolNameError

        class _UnitEnv(BaseTestEnv):
            pass

        with _UnitEnv() as env:
            # MissingToolNameError (tests.harness.transport) is the ONE missing-
            # tool-name exception type -- it used to be a
            # per-dispatcher fork (TypeError here, NotImplementedError on
            # A2AE2EDispatcher below).
            with pytest.raises(MissingToolNameError, match="tool_name"):
                McpE2EDispatcher().dispatch(env, identity=None)

    def test_delegates_to_client_with_flattened_req(self, monkeypatch):
        from tests.harness._base import BaseTestEnv
        from tests.harness.dispatchers import McpE2EDispatcher
        from tests.harness.transport import E2EConfig

        TestClientE2eMcpDelivery._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", TestClientE2eMcpDelivery._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        class _FakeReq:
            def model_dump(self, **kwargs):
                return {"brief": "video ads"}

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))

        result = McpE2EDispatcher().dispatch(env, tool_name="get_products", req=_FakeReq(), identity=None)

        assert result.is_success, result.error
        fake_client = TestClientE2eMcpDelivery._FakeMcpClient.instances[0]
        assert fake_client.calls == [("get_products", {"brief": "video ads"})]

    def test_omitted_identity_falls_back_to_env_identity_for(self, monkeypatch):
        """The regression this ticket fixes: omitting
        ``identity=`` entirely (not passing ``identity=None``) must fall back
        to ``env.identity_for(transport)`` — same as every other transport's
        omission semantics — not force unauthenticated dispatch.

        Only observable by calling ``.dispatch()`` directly: the legacy
        ``env.call_via(...)`` entry point already injects
        ``kwargs.setdefault("identity", self.identity_for(transport))`` before
        any dispatcher runs (``_base.py:538``), which masks the bug for every
        caller that goes through it.

        A unit env's ``identity_for()`` never carries a real ``auth_token``
        (only integration mode resolves one, ``_base.py:450-453``), so the
        ``x-adcp-auth`` header cannot distinguish the two cases here — the
        ``x-adcp-tenant`` header (set unconditionally from
        ``identity.tenant["subdomain"]``) is the signal that actually moves.
        """
        from tests.harness._base import BaseTestEnv
        from tests.harness.dispatchers import McpE2EDispatcher
        from tests.harness.transport import E2EConfig, Transport

        TestClientE2eMcpDelivery._FakeMcpClient.instances = []
        monkeypatch.setattr("fastmcp.Client", TestClientE2eMcpDelivery._FakeMcpClient)

        class _UnitEnv(BaseTestEnv):
            pass

        env = _UnitEnv(e2e_config=E2EConfig(base_url="http://e2e-host:9000", postgres_url="postgresql://x/y"))
        expected_tenant = env.identity_for(Transport.E2E_MCP).tenant["subdomain"]

        result = McpE2EDispatcher().dispatch(env, tool_name="get_products", brief="video ads")

        assert result.is_success, result.error
        fake_client = TestClientE2eMcpDelivery._FakeMcpClient.instances[0]
        assert fake_client.transport.headers["x-adcp-tenant"] == expected_tenant
