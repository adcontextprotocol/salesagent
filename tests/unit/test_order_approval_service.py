"""Unit tests for order approval service."""

import logging
from datetime import UTC, datetime
from unittest.mock import ANY, MagicMock, patch

import pytest

from src.services.order_approval_service import (
    get_active_approvals,
    get_approval_status,
    is_approval_running,
    start_order_approval_background,
)


@pytest.fixture(autouse=True)
def cleanup_approval_registry():
    """Clean up global approval registry before each test."""
    # Import here to avoid issues with module loading
    import src.services.order_approval_service as service

    # Clear the registry before the test (ThreadRegistry API)
    for key in list(service._active_approvals.list_active()):
        service._active_approvals.remove(key)

    yield

    # Note: Don't clear after test - threads may still be running and need to clean up themselves


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("src.services.order_approval_service.get_db_session") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_db.scalars.return_value.first.return_value = None  # No existing approval
        mock_db.scalars.return_value.all.return_value = []
        yield mock_db


@pytest.fixture
def mock_gam_client():
    """Mock GAM client and managers."""
    with (
        patch("src.services.order_approval_service.GAMClientManager") as mock_client_mgr,
        patch("src.services.order_approval_service.GAMOrdersManager") as mock_orders_mgr,
        patch("src.services.order_approval_service.AdapterConfig") as mock_config,
    ):
        # Mock adapter config
        mock_adapter_config = MagicMock()
        mock_adapter_config.gam_network_code = "12345"

        # Mock orders manager
        mock_orders_instance = MagicMock()
        mock_orders_instance.approve_order.return_value = True
        mock_orders_mgr.return_value = mock_orders_instance

        yield {
            "client_manager": mock_client_mgr,
            "orders_manager": mock_orders_mgr,
            "orders_instance": mock_orders_instance,
            "adapter_config": mock_adapter_config,
        }


# test_start_approval_creates_sync_job lived here. It asserted the SyncJob's fields off
# a MagicMock session's call_args (never a persisted row) and left the worker thread
# running past the end of the test, where it reached the real DB and fired a webhook
# into whatever test ran next (found and fixed in GH #1941). Replaced by the real-DB path in
# tests/integration/test_order_approval_background.py, which joins the thread.
#
# Retained from the parallel fix on main (#2091), because the diagnosis is recorded
# nowhere else and explains why a leaked worker is not merely untidy: the stray thread
# ran the true retry path -- order_approval_service.py:406 `time.sleep(2**attempt)`
# behind httpx POSTs at timeout=10.0 -- so it called sleep(1), sleep(2), sleep(4) from
# inside whatever test was running by then. Measured: still alive ~1500 tests later,
# during test_performance_index_behavioral and test_policy_typed_models, and it
# intermittently broke TestWebhookDelivery::test_exponential_backoff_timing, whose
# class-level patch of `src.core.webhook_delivery.time.sleep` is PROCESS-GLOBAL (that
# module does `import time`, so the patch lands on the time module itself and is visible
# to every module and every thread). The stray sleeps inflated mock_sleep.call_count
# past 2. main's fix patched `_run_approval_thread` so the thread never spawns; this
# branch deleted the test instead, because its assertions read a mock rather than a row.


def test_start_approval_rejects_duplicate(mock_db_session):
    """Test that starting approval for same order fails."""
    from src.core.database.models import SyncJob

    # Mock existing approval for this order
    existing_approval = SyncJob(
        sync_id="approval_12345_existing",
        tenant_id="tenant_1",
        adapter_type="google_ad_manager",
        sync_type="order_approval",
        status="running",
        started_at=datetime.now(UTC),
        triggered_by="order_creation",
        triggered_by_id="mb_123",
        progress={"order_id": "12345"},
    )
    mock_db_session.scalars.return_value.all.return_value = [existing_approval]

    # Patched for the same reason as the test above -- an unpatched call leaks a
    # live daemon thread into the rest of the session.
    with (
        patch("src.services.order_approval_service._run_approval_thread"),
        pytest.raises(ValueError, match="Approval already running for order 12345"),
    ):
        start_order_approval_background(
            order_id="12345",
            media_buy_id="mb_123",
            tenant_id="tenant_1",
            principal_id="principal_1",
        )


def test_approval_thread_tracks_in_registry(mock_db_session):
    """Test that approval thread is tracked in global registry.

    Uses a blocking mock so the worker stays alive while the test
    inspects the registry — the dead-thread reaper added in the
    production memory-leak fix drops dead-thread entries on read, so
    a no-op mock that exits immediately would race the reaper.
    """
    import threading

    keep_alive = threading.Event()
    with patch(
        "src.services.order_approval_service._run_approval_thread",
        side_effect=lambda *args, **kwargs: keep_alive.wait(timeout=2.0),
    ):
        approval_id = start_order_approval_background(
            order_id="12345",
            media_buy_id="mb_123",
            tenant_id="tenant_1",
            principal_id="principal_1",
        )
        try:
            active_approvals = get_active_approvals()
            assert approval_id in active_approvals, f"Expected {approval_id} in {active_approvals}"
            assert is_approval_running(approval_id)
        finally:
            keep_alive.set()


def test_get_approval_status(mock_db_session):
    """Test getting approval status."""
    from src.core.database.models import SyncJob

    # Mock existing approval
    approval = SyncJob(
        sync_id="approval_12345_test",
        tenant_id="tenant_1",
        adapter_type="google_ad_manager",
        sync_type="order_approval",
        status="running",
        started_at=datetime.now(UTC),
        triggered_by="order_creation",
        triggered_by_id="mb_123",
        progress={"order_id": "12345", "attempts": 3},
    )
    mock_db_session.scalars.return_value.first.return_value = approval

    status = get_approval_status("approval_12345_test")

    assert status is not None
    assert status["approval_id"] == "approval_12345_test"
    assert status["status"] == "running"
    assert status["progress"]["order_id"] == "12345"
    assert status["progress"]["attempts"] == 3


def test_get_approval_status_not_found(mock_db_session):
    """Test getting approval status for non-existent approval."""
    mock_db_session.scalars.return_value.first.return_value = None

    status = get_approval_status("nonexistent")
    assert status is None


# ─────────────────────────────────────────────────────────────────────────────
# Two webhook unit tests that lived here were REMOVED, not repaired, when
# ``_send_approval_webhook`` stopped speaking httpx and started handing the URL
# to the egress seam (``src.core.security.outbound_http.send``):
#
#   * ``test_webhook_notification_sent_on_success`` claimed: the payload carries
#     event/media_buy_id/status/order_id/attempts, and a stored bearer
#     PushNotificationConfig becomes ``Authorization: Bearer <token>``. It read
#     those off a substituted ``httpx.Client``, plus (from #1697)
#     ``httpx.Client(timeout=10.0, follow_redirects=False)`` — a constructor the
#     module no longer calls at all. Regraded against a real origin in
#     ``tests/integration/test_order_approval_webhook.py``
#     (``TestDeliveredPayload``, ``TestStoredCredential`` — which also covers the
#     no-config direction the old test only hit incidentally).
#   * ``test_webhook_retries_on_failure`` claimed: a failing POST is retried to
#     three attempts. The hand-rolled ``for attempt in range(...)`` /
#     ``time.sleep(2 ** attempt)`` loop it patched no longer exists; the seam owns
#     attempt count, retry classification and BR-RULE-029 backoff. Regraded in
#     ``tests/integration/test_order_approval_webhook.py``
#     (``TestRetryClassification``, ``TestExhaustedDeliveryIsSilent``) and, for
#     the spacing, once in ``tests/integration/test_outbound_http.py``.
#
# The SSRF obligation from #1697 stays here because it is a claim about THIS
# call site — that the order-approval sender shares the gate — which the seam's
# own suite cannot make on its behalf.
# ─────────────────────────────────────────────────────────────────────────────


def test_approval_webhook_rejects_metadata_url_without_post(caplog):
    """Order-approval sender must share the outbound SSRF gate (no open redirect).

    Repointed off ``patch("httpx.Client")``: the sender does not speak httpx any
    more, so a mock standing in for it would grade a transport this module never
    touches. ``send`` is spied with ``wraps=`` instead, so the REAL validation
    runs — the link-local metadata address is refused inside the seam before any
    connection is attempted (and stays refused even with the private/insecure
    escape hatches on), and production swallows the refusal as a log line.

    Both halves are asserted: the raw URL reached the gate under the attempt
    budget this call site asks for, and the gate refused it — which is what
    "nothing was POSTed" means once no local transport exists to count.
    """
    from src.core.security.outbound_http import send as real_send
    from src.services.order_approval_service import _send_approval_webhook

    metadata_url = "http://169.254.169.254/latest/meta-data/"

    with (
        patch("src.services.order_approval_service.get_db_session") as mock_db,
        # The seam call now lives one layer down, inside deliver_webhook
        # (src.core.security.webhook_egress) -- the shared delivery function every
        # webhook sender routes through since #1802.
        patch("src.core.security.webhook_egress.send", wraps=real_send) as spy_send,
        caplog.at_level(logging.WARNING, logger="src.services.order_approval_service"),
    ):
        mock_db_instance = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_instance
        mock_db_instance.scalars.return_value.first.return_value = None

        _send_approval_webhook(
            webhook_url=metadata_url,
            tenant_id="tenant_1",
            principal_id="principal_1",
            media_buy_id="mb_123",
            status="approved",
            message="Order approved successfully",
        )

    # content=, not json=: deliver_webhook serializes once (via
    # prepare_signed_request) and transmits those exact bytes via content=, never
    # json= (#1802's Core Invariant -- no webhook sender may reach
    # json= on the egress seam).
    spy_send.assert_called_once_with(metadata_url, content=ANY, headers=ANY, timeout=10.0, max_attempts=3)
    assert "was refused by egress policy" in caplog.text


def test_a_started_approval_thread_can_be_cancelled(mock_db_session):
    """A caller can cancel a started approval thread, and it stops promptly.

    The defect (#2056): `_active_approvals` holds the thread but exposes no way
    to stop it. A started thread runs the real webhook retry path -- backoff
    behind HTTP POSTs that time out after 10 s -- so it outlives the request,
    and the test, by tens of seconds. Measured: a thread from
    `test_start_approval_creates_sync_job` called sleep(1) and sleep(2) during
    `test_performance_index_behavioral` and `test_policy_typed_models`, roughly
    1500 tests later, landing inside another test's mock because
    `src/core/webhook_delivery.py` imports `time` and patching
    `src.core.webhook_delivery.time.sleep` replaces it process-wide.

    `delivery_simulator.stop_simulation` and gam/managers/reporting already
    solve this with a parallel `_stop_signals` Event dict beside the registry;
    this service is the third site and never got one.

    What this test grades is the registry half, and that half is unchanged by
    the move of outbound HTTP behind the egress seam: a started approval must
    expose a stop signal, a caller must be able to set it, and the thread must
    be joinable once it is set. The seam owns the backoff now and offers no
    cancellation hook, so production checks the signal before handing a
    delivery over rather than inside a loop it no longer has -- which is why
    the worker below is substituted, and no HTTP path is exercised here.

    The import is inside the test on purpose: in the red state it fails here,
    before any thread is started, so a failing run does not itself leak the
    thread this test exists to bound.
    """
    import threading

    from src.services.order_approval_service import (
        _active_approvals,
        cancel_order_approval,
        get_approval_stop_signal,
    )

    started = threading.Event()
    observed_stop: dict[str, threading.Event | None] = {"signal": None}

    def _blocking_worker(*args, **kwargs):
        # Stand in for the real worker: wait on the stop signal the way a
        # cancellable wait must, rather than sleeping blind. approval_id comes
        # from args[0], as production's _run_approval_thread receives it — NOT
        # from a variable the caller assigns after start_order_approval_background
        # returns, which the worker races.
        signal = get_approval_stop_signal(args[0])
        observed_stop["signal"] = signal
        started.set()
        signal.wait(timeout=30.0)

    approval_id_holder: dict[str, str] = {}
    with patch("src.services.order_approval_service._run_approval_thread", side_effect=_blocking_worker):
        approval_id_holder["id"] = start_order_approval_background(
            order_id="12345",
            media_buy_id="mb_123",
            tenant_id="tenant_1",
            principal_id="principal_1",
        )
        approval_id = approval_id_holder["id"]
        assert started.wait(timeout=5.0), "worker never started"
        assert is_approval_running(approval_id)

        cancel_order_approval(approval_id)

        thread = _active_approvals.get(approval_id)
        assert thread is not None
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "cancel did not stop the approval thread within 5 s"
        assert observed_stop["signal"] is not None and observed_stop["signal"].is_set()
