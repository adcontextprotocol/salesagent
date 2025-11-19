"""End-to-end blueprint for delivery webhook flow.

This follows the reference E2E patterns and calls real MCP tools:

1. get_products
2. create_media_buy (with reporting_webhook)
3. get_media_buy_delivery for an explicit period
4. Wait for scheduled delivery_report webhook and inspect payload

All TODOs are left for you to fill in assertions and any spec-specific checks.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from time import sleep

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.e2e.adcp_request_builder import (
    build_adcp_media_buy_request,
    get_test_date_range,
    parse_tool_result,
)


class DeliveryWebhookReceiver(BaseHTTPRequestHandler):
    """Simple webhook receiver to capture delivery_report notifications."""

    received_webhooks = []

    def do_POST(self):
        """Handle POST requests (webhook notifications)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8"))
            self.received_webhooks.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "received"}')
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        """Silence HTTP server logs during tests."""
        pass


@pytest.fixture
def delivery_webhook_server():
    """Start a local HTTP server to receive delivery_report webhooks."""
    import socket

    # Find an available port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    server = HTTPServer(("127.0.0.1", port), DeliveryWebhookReceiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    webhook_url = f"http://127.0.0.1:{port}/webhook"

    yield {
        "url": webhook_url,
        "server": server,
        "received": DeliveryWebhookReceiver.received_webhooks,
    }

    server.shutdown()
    DeliveryWebhookReceiver.received_webhooks.clear()


class TestDailyDeliveryWebhookFlow:
    """Blueprint E2E test for daily delivery webhooks."""

    @pytest.mark.asyncio
    async def test_daily_delivery_webhook_end_to_end(
        self,
        docker_services_e2e,
        live_server,
        test_auth_token,
        delivery_webhook_server,
    ):
        """
        End-to-end blueprint:

        1. Discover a product (get_products)
        2. Create media buy with reporting_webhook.frequency = "daily"
        3. Get delivery metrics explicitly via get_media_buy_delivery
        4. Wait for scheduled delivery_report webhook and inspect payload

        TODOs are left for you to define exact assertions and spec expectations.
        """
        # ------------------------------------------------------------------
        # MCP client setup (same pattern as reference implementation)
        # ------------------------------------------------------------------
        headers = {
            "x-adcp-auth": test_auth_token,
            "x-adcp-tenant": "ci-test",  # Explicit tenant selection for E2E
        }
        transport = StreamableHttpTransport(url=f"{live_server['mcp']}/mcp/", headers=headers)

        async with Client(transport=transport) as client:
            # ==============================================================
            # PHASE 1: Product discovery (get_products)
            # ==============================================================
            products_result = await client.call_tool(
                "get_products",
                {
                    "brand_manifest": {"name": "Daily Delivery Webhook Test"},
                    "brief": "display advertising",
                    "context": {"e2e": "delivery_webhook_get_products"},
                },
            )
            products_data = parse_tool_result(products_result)

            # TODO: Assert products_data structure (e.g. "products" key, non-empty list)
            # TODO: Assert context echo if desired

            # Pick first product
            product = products_data["products"][0]
            product_id = product["product_id"]

            # ==============================================================
            # PHASE 2: Create media buy with reporting_webhook (create_media_buy)
            # ==============================================================
            start_time, end_time = get_test_date_range(days_from_now=1, duration_days=7)

            media_buy_request = build_adcp_media_buy_request(
                product_ids=[product_id],
                total_budget=2000.0,
                start_time=start_time,
                end_time=end_time,
                brand_manifest={"name": "Daily Delivery Webhook Test"},
                webhook_url=delivery_webhook_server["url"],
                # Explicitly configure daily reporting frequency
                reporting_webhook_extra={
                    "frequency": "daily",
                    # TODO: Add authentication config here if you want to test HMAC/Bearer
                },
                context={"e2e": "delivery_webhook_create_media_buy"},
            )

            create_result = await client.call_tool("create_media_buy", media_buy_request)
            create_data = parse_tool_result(create_result)

            # TODO: Assert shape of create_data (media_buy_id / buyer_ref / status)
            # TODO: Assert context echo for create_media_buy

            media_buy_id = create_data.get("media_buy_id")
            buyer_ref = create_data.get("buyer_ref")

            # If async-only, you may need to derive media_buy_id differently or
            # skip the direct get_media_buy_delivery step.
            # TODO: Decide how you want to handle async-only create responses.
            assert media_buy_id or buyer_ref  # Blueprint sanity check

            # ==============================================================
            # PHASE 3: Explicit delivery request (get_media_buy_delivery)
            # ==============================================================
            # Use media_buy_id if available; otherwise you might use buyer_ref-based lookup
            if media_buy_id:
                delivery_period = {
                    # Example: use the campaign start/end dates; adjust as needed
                    "start_date": start_time.split("T")[0],
                    "end_date": end_time.split("T")[0],
                }

                delivery_result = await client.call_tool(
                    "get_media_buy_delivery",
                    {
                        "media_buy_ids": [media_buy_id],
                        **delivery_period,
                        "context": {"e2e": "delivery_webhook_get_media_buy_delivery"},
                    },
                )
                delivery_data = parse_tool_result(delivery_result)

                # TODO: Assert delivery_data structure (e.g. "deliveries" or "media_buy_deliveries")
                # TODO: Assert context echo for get_media_buy_delivery
                # TODO: Optionally assert that the requested period was applied as expected

            # ==============================================================
            # PHASE 4: Scheduled delivery webhook (delivery_report)
            # ==============================================================
            # At this point, the DeliveryWebhookScheduler (running in the MCP process)
            # should eventually send a "delivery_report" webhook to
            # delivery_webhook_server["url"].
            #
            # Because the scheduler runs on an hourly cadence in the real app, you may
            # want to:
            # - run this test in an environment where the interval is shortened, OR
            # - explicitly trigger a one-off run via a direct call to the scheduler
            #   implementation in a separate integration test (see
            #   tests/integration/test_delivery_webhooks_integration.py).
            #
            # Here we just provide a polling blueprint you can adapt.

            received = delivery_webhook_server["received"]

            # Wait a bit for at least one webhook; tune timeout/poll interval as needed.
            # In CI you may want to replace this with a deterministic trigger instead.
            timeout_seconds = 60
            poll_interval = 2

            elapsed = 0
            while elapsed < timeout_seconds and not received:
                sleep(poll_interval)
                elapsed += poll_interval

            # TODO: Replace this with real assertions once you are comfortable with timing:
            # assert received, "Expected at least one delivery_report webhook"

            if received:
                webhook_payload = received[0]
                # TODO: Assert shape of webhook_payload:
                # - webhook_payload["task_type"] == "delivery_report"
                # - webhook_payload["status"] == "completed"
                # - webhook_payload["result"]["media_buy_id"] == media_buy_id
                # - webhook_payload["result"]["next_expected_at"] is an ISO timestamp
                # - webhook_payload["result"]["sequence_number"] starts at 1, etc.
                #
                # Example skeleton:
                # assert webhook_payload["task_type"] == "delivery_report"
                # assert webhook_payload["status"] == "completed"
                # result = webhook_payload.get("result") or {}
                # assert result.get("media_buy_id") == media_buy_id
                # assert "next_expected_at" in result

            # TODO: Optionally add a second phase where you:
            # - wait for another scheduler run
            # - assert sequence_number increments
            # - or assert only one webhook per reporting period, etc.


