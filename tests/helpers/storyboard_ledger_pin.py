"""The pinned contents of the storyboard-conformance known-failures ledger.

``tests/storyboard/known_failures.txt`` is pinned in exactly one place, and two
suites grade against that pin: ``tests/unit/test_storyboard_ledger_state.py``
(the lock test — the ledger file must equal the pin) and
``tests/integration/test_storyboard_ledger_fitness_real_session.py`` (the
fitness function — its three cases are vacuous unless the ledger it drives a
real session with is the pinned one).

The pin used to live in the unit lock test and be imported out of it, which made
a module whose job is to BE a test double as a helper library — the disease
``tests/unit/test_architecture_no_cross_test_module_imports.py`` forbids:
renaming or splitting the lock test would break an unrelated suite, and the
breakage would surface as a collection error in a file nobody touched. Same fix
shape, and same home rationale, as ``tests/unit/_run_all_tests_helpers.py``,
except that these two consumers sit in DIFFERENT suites (unit + integration), so
a suite-local ``_*_helpers.py`` would just move the cross-suite reach rather
than remove it. ``tests/helpers/**`` is the cross-suite home, alongside
``tests/helpers/ledger.py`` — the shared parser both consumers already use.

RE-SEEDING is a standing rule, not a one-off: whenever a run seeds or retires
entries, update ``tests/storyboard/known_failures.txt`` AND ``EXPECTED_LEDGER``
below in the same change. A removed entry that creeps back is a graduation
regression; a genuine-gap entry deleted without landing the underlying fix is a
silent gap-hiding regression.
"""

from __future__ import annotations

from pathlib import Path

#: Repo root, computed once from this module's path.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The ledger file whose exact contents ``EXPECTED_LEDGER`` pins.
LEDGER_PATH = REPO_ROOT / "tests" / "storyboard" / "known_failures.txt"

# --- ledger pin ---
# RE-SEEDED from a real in-network CI run of THIS tree: run 32478296091, job
# 96759107129, head_sha 0ec6637dd (2026-08-21). Measured, not derived --
# 96 collected, 13 failed, 1 passed, 13 skipped, 69 xfailed, 0 xpassed.
#
# Current total, through scripts.audit.ledger.load: 81 entries (80 mcp + 1 a2a).
#
# mcp (80) = the 69 previously-ledgered entries, ALL of which xfailed at this
# head (zero graduations), plus the 11 measured un-ledgered failures. Every one
# of the 11 carries `VALIDATION_ERROR: Unexpected keyword argument` -- #1512
# (adcp_version rejected). Four of them (the wholesale_feed family) were not in
# the previous seed run's collection set at all: collection grew 83 -> 96, so
# they are newly gradable rather than newly broken.
#
# a2a (1) = `a2a::_runner::agent_reachability::graded_checks_produced`, the
# `_no_graded_checks` synthetic. The axis grades ZERO checks at this head: the
# card-discovery fix was a production change and 19116bf7e reverted every one
# (#1440). The 32 per-check a2a entries seeded pre-revert were REMOVED -- they
# resolved to no collected check, graded nothing, and made
# ledger/fitness::stale_entries a permanent hard failure. "Not measured" is
# still not "graduated", and this single entry is how the file says so: it
# XPASSes the day the card is fixed, and the axis's real checks then arrive
# un-ledgered and redden CI until triaged.
EXPECTED_LEDGER: frozenset[str] = frozenset(
    (
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[a2a::_runner::agent_reachability::graded_checks_produced]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::capability_discovery::get_capabilities_filtered]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_event_scope::sync_accounts_rejects_scheduled_account_notification]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_lifecycle::sync_accounts_create_paused_notification_config]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::notification_config_rejections::sync_accounts_rejects_duplicate_subscriber_id]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::assert_omitted_key_grace_handled]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_accept]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_capabilities_without_idempotency_key_3_1_reject]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::get_products_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_accounts_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creative_formats_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::read_tool_idempotency::list_creatives_with_idempotency_key]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::v3_envelope_integrity::no_legacy_status_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::version_negotiation::get_capabilities_with_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::assert_webhook_signing_key_present]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::fetch_brand_json]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_idempotent_webhook_initial]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_operation_id_echo]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_retry_scenario]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_signed_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::webhook_emission::trigger_webhook_operation]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::core::wholesale_feed_bulk_webhooks::register_bulk_change_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::billing_gate_dispatch::sync_accounts_passthrough_rejects_agent]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::missing_fields]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::nonexistent_product]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::reversed_dates_error]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::supported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_major_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::error_compliance::unsupported_release_version]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::stale_response_advisory::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::error_handling::stale_response_advisory::no_stale_on_healthy_upstream]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::wholesale_feed_product_webhooks::register_product_pricing_webhook]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::media_buy::wholesale_feed_products::bootstrap_products]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::assert_mechanism]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security::security_baseline::probe_unauth]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::get_capabilities]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-001-no-signature-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-002-wrong-tag]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-003-expired-signature]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-004-window-too-long]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-005-alg-not-allowed]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-006-missing-covered-component]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-007-missing-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-008-unknown-keyid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-009-key-ops-missing-verify]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-010-content-digest-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-011-malformed-header]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-012-missing-expires-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-013-expires-le-created]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-014-missing-nonce-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-015-signature-invalid]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-016-replayed-nonce]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-017-key-revoked]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-018-digest-covered-when-forbidden]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-019-signature-without-signature-input]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-020-rate-abuse]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-021-duplicate-signature-input-label]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-022-multi-valued-content-type]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-023-multi-valued-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-024-unquoted-string-param]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-025-jwk-alg-crv-mismatch]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-027-webhook-registration-authentication-unsigned]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::negative-028-unsigned-protocol-method-required]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-001-basic-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-002-post-with-content-digest]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-003-es256-post]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-004-multiple-signature-labels]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-005-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-006-dot-segment-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-007-query-byte-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-008-percent-encoded-path]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-009-percent-encoded-unreserved-decoded]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-010-percent-encoded-slash-preserved]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-011-ipv6-authority]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::security_transport::signed_requests::positive-012-ipv6-authority-default-port-stripped]",
        "tests/storyboard/test_storyboard_conformance.py::test_storyboard_check[mcp::signals::wholesale_feed_signal_webhooks::register_signal_pricing_webhook]",
    )
)
