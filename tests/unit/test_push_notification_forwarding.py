"""
Regression test: MCP and A2A create_media_buy wrappers must forward
push_notification_config to _create_media_buy_impl.

Both wrappers must forward push_notification_config identically
(transport parity invariant). The _impl function accepts dict|None, so:
- MCP wrapper (receives PushNotificationConfig model from FastMCP) must serialize to dict
- A2A wrapper (receives dict from JSON) passes through directly
"""

from __future__ import annotations

import pytest
from adcp.types import PushNotificationConfig

from tests.helpers.create_media_buy_capture import capture_a2a_forwarded_pnc, capture_mcp_forwarded_pnc


class TestMCPForwardsPushNotificationConfig:
    """MCP wrapper must forward push_notification_config to _impl."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper_forwards_push_notification_config(self):
        """When push_notification_config is provided, MCP wrapper forwards it to _impl as a dict."""
        from adcp import PushNotificationConfig

        pnc = PushNotificationConfig(
            url="https://example.com/webhook",
            authentication={"credentials": "a" * 32, "schemes": ["Bearer"]},
        )
        forwarded = await capture_mcp_forwarded_pnc(pnc)

        assert forwarded is not None, (
            "MCP wrapper does not forward push_notification_config to _impl. This is a transport parity violation."
        )
        # Epic D lane C3: _impl now takes the TYPED model, so "forwarded" is a
        # PushNotificationConfig rather than a dumped dict. The obligation is
        # unchanged — the wrapper must forward the buyer's registration, not drop
        # it — only its shape moved.
        assert isinstance(forwarded, PushNotificationConfig), (
            f"push_notification_config must be forwarded as dict, got {type(forwarded).__name__}"
        )
        assert str(forwarded.url) == "https://example.com/webhook"


class TestA2AForwardsPushNotificationConfig:
    """A2A wrapper must forward push_notification_config to _impl (parity check)."""

    @pytest.mark.asyncio
    async def test_a2a_wrapper_forwards_push_notification_config(self):
        """When push_notification_config is provided, A2A wrapper forwards it to _impl."""
        pnc_dict = {
            "url": "https://example.com/webhook",
            "authentication": {"credentials": "a" * 32, "schemes": ["Bearer"]},
        }
        forwarded = await capture_a2a_forwarded_pnc(pnc_dict)

        assert forwarded is not None, "A2A wrapper does not forward push_notification_config to _impl"
        assert isinstance(forwarded, PushNotificationConfig)
        assert str(forwarded.url) == "https://example.com/webhook"
