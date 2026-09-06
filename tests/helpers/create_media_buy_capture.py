"""Shared capture helper for the create_media_buy transport boundary.

Runs create_media_buy through :func:`src.core.tools._boundary.invoke_tool` -- the one path
every transport takes -- with a stub implementation substituted at the registry row, and
returns the ``push_notification_config`` that implementation received.

There used to be two of these, one per transport, because each transport had its own wrapper
and the two could forward different things. They cannot any more: MCP, A2A and REST all reach
the implementation through ``invoke_tool``, so "what MCP forwards" and "what A2A forwards"
are one question with one answer.

Returns the model, not a dict: Epic D lane C3 moved the wire-type conversion out of the
wrappers and into ValidatedWebhookRegistration, so what _impl receives is the typed model and
what persistence receives is plain str.

Used by:
  - tests/unit/test_create_media_buy_behavioral.py  (serialization obligations)
  - tests/unit/test_push_notification_forwarding.py  (forwarding parity)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.core.schemas import CreateMediaBuyRequest
from tests.helpers.adcp_factories import create_test_media_buy_request_dict
from tests.helpers.capture_wrapper_req import registry_impl


async def capture_a2a_forwarded_pnc(pnc: Any) -> Any:
    """Run create_media_buy at the boundary with *pnc* and return what the impl received.

    Args:
        pnc: A PushNotificationConfig model instance or plain dict to place on the request.

    Returns:
        The push_notification_config value received by _impl, or None if _impl
        was not called.
    """
    from src.core.schemas import CreateMediaBuyResult
    from src.core.tools._boundary import invoke_tool

    req_dict = create_test_media_buy_request_dict()
    mock_result = MagicMock(spec=CreateMediaBuyResult)
    mock_result.__str__ = lambda self: "mock_result"

    # tenant_id None keeps this out of the idempotency cache: an identity that resolved no
    # tenant has no (agent, account, key) scope, so the boundary runs the implementation
    # without a DB probe -- which a unit test has no database for.
    mock_identity = MagicMock()
    mock_identity.tenant_id = None

    captured: dict[str, Any] = {}

    async def _capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return mock_result

    with registry_impl("create_media_buy", _capture):
        # Everything, push_notification_config included, travels ON the request -- it is a
        # request FIELD (1f13cca0a), not a kwarg forwarded beside the request.
        await invoke_tool(
            "create_media_buy",
            CreateMediaBuyRequest(
                brand=req_dict["brand"],
                packages=req_dict["packages"],
                start_time=req_dict["start_time"],
                end_time=req_dict["end_time"],
                idempotency_key=req_dict["idempotency_key"],
                account=req_dict.get("account"),
                push_notification_config=pnc,
            ),
            mock_identity,
        )

    # READ OFF THE REQUEST. push_notification_config is a request field, not a kwarg
    # forwarded beside the request, so parity means "the value lands on req", not "both
    # transports pass the same kwarg". Returning the model keeps every caller's comparison
    # unchanged.
    req = captured.get("req")
    return getattr(req, "push_notification_config", None) if req is not None else None
