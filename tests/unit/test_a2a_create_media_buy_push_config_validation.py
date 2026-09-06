"""A2A create_media_buy validates push_notification_config AS PART OF the request.

``push_notification_config`` is a REQUEST FIELD, built through
``CreateMediaBuyRequest`` like every other field.

THIS REVERSES gh-#1299's ORIGINAL RESOLUTION, deliberately. That issue kept the config out of
the request because the adcp ``Authentication.credentials`` MinLen(32) constraint would then
apply to the whole create_media_buy, diverting a short-credential request away from the
manual-approval gate. The bypass cost more than it bought: one field ended up announced by
three separate mechanisms -- the MCP wrapper declaring it, a REST ``extra_fields`` patch, and
a duplicate ``_impl`` parameter -- which could drift apart silently, and did.

Owner ruling: there is a schema and there is a non-conformant payload against it, so the
schema refuses it. The test that asserted a short credential must NOT block create_media_buy
was deleted with the behaviour it pinned; the schema is what states that contract now.

What remains here is the positive control: a conformant no-auth config must survive onto the
request untouched.
"""

import pytest

from src.core.schemas import CreateMediaBuyResult
from tests.helpers.capture_wrapper_req import stub_impl


def _valid_packages_params() -> dict:
    """Minimal spec-valid create_media_buy parameters (no push config)."""
    return {
        "brand": {"domain": "testbrand.com"},
        "packages": [
            {
                "product_id": "prod_1",
                "budget": 50000.0,
                "pricing_option_id": "po_default",
            }
        ],
        "start_time": "2099-01-01T00:00:00Z",
        "end_time": "2099-01-31T23:59:59Z",
        "idempotency_key": "unit-test-key-a2a-pushcfg-0001",
        "account": {"account_id": "acct_test"},
        "context": {"e2e": "push_config_validation"},
    }


@pytest.mark.asyncio
async def test_no_auth_push_config_still_works():
    """Control: a no-auth push_notification_config must keep working (the bug
    only manifests when the authentication block forces the MinLen(32) check)."""
    from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
    from tests.factories.principal import PrincipalFactory

    handler = AdCPRequestHandler()
    identity = PrincipalFactory.make_identity(
        principal_id="test-principal",
        tenant_id="test-tenant",
        tenant={"tenant_id": "test-tenant"},
        protocol="a2a",
    )

    params = _valid_packages_params()
    params["push_notification_config"] = {"url": "http://localhost:9999/webhook"}

    submitted_result = CreateMediaBuyResult(
        # confirmed_at/revision are schema-required and carry no model default:
        # the response reports the persisted row, so a construction must state them.
        response={
            "media_buy_id": "mb_test",
            "packages": [],
            "confirmed_at": "2026-03-15T12:00:00Z",
            "revision": 1,
        },
        status="submitted",
    )

    captured: dict = {}

    async def fake_tool(**kwargs):
        captured.update(kwargs)
        return submitted_result

    with stub_impl("create_media_buy", side_effect=fake_tool):
        result = await handler._handle_create_media_buy_skill(params, identity)

    assert captured, "create_media_buy's implementation was never reached for a no-auth config"
    # ON THE REQUEST, not beside it. A no-auth config carries no credentials, so no
    # MinLen(32) constraint applies and it passes the schema untouched.
    built = captured["req"].push_notification_config
    assert built is not None, "a no-auth push_notification_config must survive onto the request"
    assert str(built.url) == "http://localhost:9999/webhook", f"url not preserved: {built.url!r}"
    status = result.get("status") if isinstance(result, dict) else result.status
    assert status == "submitted"
