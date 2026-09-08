"""A registration that asked for HMAC is DELIVERED signed — on every surface.

Epic D lane C2. ``tests/integration/test_webhook_sender_auth_contract.py``
already grades what a sender does with a STORED row, and
``tests/integration/test_webhook_hmac_credentials_ingest_refusal.py`` grades what
ingest does with an unusable registration. Between them sits the gap this file
grades: a registration that was accepted, and a sender that would have signed
it, still deliver UNSIGNED if the credential half is lost in the HANDOFF — the
protocol stash on the A2A path, the workflow-step stash on the media-buy paths.
Nothing on either side can see that, because each end is individually correct.

Three producers reach that handoff; each gets a case, and each case gets a
reverse-TDD control that drops the credential half from the stash and shows the
delivery arrives unsigned. The control is what makes the primary case a grader
rather than a green mark: a case that cannot go red under the exact damage it
exists to detect is grading nothing, and this whole lane is a change to how
that handoff is represented.

Why the signature and not the stash's shape: the lane rewrites the intermediate
representation (raw dict / raw protobuf today, a validated value tomorrow), so
any assertion about the stash would have to be rewritten by the change it is
supposed to be guarding. What the buyer's endpoint receives is invariant across
that rewrite — and it is also the only thing a buyer can act on.

Why integration and not BDD: two of the three deliveries are fired by a
workflow-step status change and the third by a task reaching a terminal state,
both after the buyer's call has returned. There is no wire envelope for a
``Then`` step to assert on. The identical rationale is recorded at
``tests/integration/test_order_approval_webhook.py`` and
``tests/bdd/features/local-egress-ssrf-refusal.feature:45-51``.

MUST STAY GREEN untouched, and deliberately not modified here:
``tests/integration/test_webhook_sender_auth_contract.py``,
``tests/integration/test_order_approval_webhook.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.exceptions import AdCPValidationError
from tests.harness import A2APushRegistrationEnv, MediaBuyPushRegistrationEnv
from tests.helpers import assert_delivered_unsigned, assert_signature_verifies_over_wire_body

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The pinned AdCP 3.1.1 ``AuthenticationScheme`` spelling every writer in
# ``src/`` persists. A constant, not a literal per case: a regression that
# changed the spelling production compares against must fail these cases rather
# than be quietly re-typed into them.
HMAC_SCHEME = "HMAC-SHA256"

# At least 32 characters because the pinned AdCP 3.1.1
# ``core/push-notification-config.json`` puts ``minLength: 32`` on
# ``authentication.credentials``, and these registrations are made through the
# real tool wire where that constraint is enforced. (The sibling sender tests
# use a short secret precisely because they write the ORM column directly and
# never cross that schema — the column carries no length requirement.)
STRONG_SECRET = "buyer-shared-secret-32-chars-or-more"


def _tool_auth_block() -> dict[str, Any]:
    """The AdCP tool shape: a ``schemes`` LIST plus ``credentials``."""
    return {"schemes": [HMAC_SCHEME], "credentials": STRONG_SECRET}


def _a2a_auth_block() -> dict[str, Any]:
    """The A2A protobuf shape: a SINGULAR free-form ``scheme``.

    Not the same object as the tool shape and deliberately not derived from it —
    ``AuthenticationInfo`` is a protobuf message with no enum behind it, and a
    helper that papered over the difference would hide the very divergence that
    makes a non-canonical spelling REFUSE at the seam rather than authenticate.
    """
    return {"scheme": HMAC_SCHEME, "credentials": STRONG_SECRET}


def _assert_delivered_signed(env: Any) -> None:
    """Exactly one delivery arrived, and its signature verifies over the wire body."""
    assert env.delivery_attempts == 1, (
        f"expected exactly one delivery, saw {env.delivery_attempts} — "
        f"a registration that never reached the sender cannot be graded for signing"
    )
    assert_signature_verifies_over_wire_body(env.last_delivery, STRONG_SECRET)


def _register_via_create(env: MediaBuyPushRegistrationEnv, *, with_push_config: bool) -> Any:
    """Run a real create_media_buy over MCP, optionally registering the webhook.

    ``with_push_config=False`` is how the update case gets a media buy to
    update without also registering anything — the update case must grade its
    OWN producer, not one create already made correct.
    """
    tenant, _principal, product, pricing_option = env.setup_media_buy_data()
    kwargs = env.minimal_create_kwargs(product, pricing_option)
    if with_push_config:
        kwargs["push_notification_config"] = {
            "url": env.webhook_url,
            "authentication": _tool_auth_block(),
        }
    return env.call_mcp(**kwargs)


class TestA2AProtocolRegistrationDeliversSigned:
    """``message/send`` registers in the PROTOCOL envelope; the task webhook is signed.

    The A2A handler holds this registration in memory for the life of the task
    (``_task_push_configs``) and hands it to ``ProtocolWebhookService`` when the
    task completes. Today it hands over a fabricated detached ORM row built from
    the raw protobuf — the laundering this lane deletes.
    """

    def test_completed_task_webhook_carries_the_registered_signature(self, integration_db):
        with A2APushRegistrationEnv() as env:
            env.setup_default_data()
            env.set_http_status(200)

            env.call_a2a_with_push_config(
                {"url": env.webhook_url, "authentication": _a2a_auth_block()},
                brief="a registration made in the protocol envelope",
            )

            _assert_delivered_signed(env)

    def test_control_the_delivery_goes_unsigned_when_the_stash_loses_the_credentials(self, integration_db):
        """Reverse-TDD: damage only the stash, and the case above must go red.

        Asserts an UNSIGNED delivery, not a refusal, and the distinction is the
        spec's own: this mutation removes the ENTIRE ``authentication`` block, and
        the pinned schema says "absence selects 9421" — an absent block is a
        deliberate choice of the default profile, not a malformed one. So the row
        still delivers, just without a signature, which is precisely what makes it a
        control for the signed case above.

        Contrast the refusals Epic D lane C4 introduced: those are blocks that are
        PRESENT but do not conform (a scheme outside the pinned enum, a missing or
        sub-32 credential, more than one scheme). Present-and-broken refuses;
        absent-by-choice delivers plain. Conflating the two would have made this
        control assert the wrong thing.
        """
        with A2APushRegistrationEnv() as env:
            env.setup_default_data()
            env.set_http_status(200)

            with env.stash_drops_the_credential_half():
                env.call_a2a_with_push_config(
                    {"url": env.webhook_url, "authentication": _a2a_auth_block()},
                    brief="a registration made in the protocol envelope",
                )

            assert_delivered_unsigned(env)


class TestCreateMediaBuyRegistrationDeliversSigned:
    """``create_media_buy`` registers; the workflow step's status change delivers signed."""

    def test_workflow_step_webhook_carries_the_registered_signature(self, integration_db):
        with MediaBuyPushRegistrationEnv() as env:
            _register_via_create(env, with_push_config=True)
            env.set_http_status(200)

            env.complete_step(env.push_step("create_media_buy"))

            _assert_delivered_signed(env)

    def test_control_the_delivery_goes_unsigned_when_the_stash_loses_the_credentials(self, integration_db):
        """Reverse-TDD: damage only the stash, and the case above must go red."""
        with MediaBuyPushRegistrationEnv() as env:
            _register_via_create(env, with_push_config=True)
            env.set_http_status(200)

            step = env.push_step("create_media_buy")
            env.drop_stashed_credential_half(step)
            env.complete_step(step)

            assert_delivered_unsigned(env)


class TestUpdateMediaBuyRegistrationDeliversSigned:
    """``update_media_buy`` registers; its workflow step delivers signed.

    The producer two solution-review passes singled out. ``update_media_buy``
    writes ``request_data["push_notification_config"]`` by model-dumping the
    request — the same key ``ContextManager._send_push_notifications`` reads —
    without going through ``create_media_buy``'s stash writer at all. A stash
    format chosen to suit the create path alone therefore resolves this
    registration to "unauthenticated" and delivers an HMAC config UNSIGNED,
    which is the state Epic D declares unconstructible. Nothing else in the
    lane's grader set touches this producer.

    The webhook row is registered separately (by an earlier
    ``create_media_buy``, in production) because ``update_media_buy`` never
    upserts one: the DB row is what makes the delivery happen at all, while the
    STASH is what decides whether it is signed. Exactly one row, so exactly one
    delivery.
    """

    def test_workflow_step_webhook_carries_the_registered_signature(self, integration_db):
        from src.core.schemas import UpdateMediaBuyRequest

        with MediaBuyPushRegistrationEnv() as env:
            created = _register_via_create(env, with_push_config=False)
            env.register_delivery_target()
            env.set_http_status(200)

            env.call_mcp(
                req=UpdateMediaBuyRequest(media_buy_id=created.response.media_buy_id),
                push_notification_config={
                    "url": env.webhook_url,
                    "authentication": _tool_auth_block(),
                },
            )

            env.complete_step(env.push_step("update_media_buy"))

            _assert_delivered_signed(env)

    def test_control_the_delivery_goes_unsigned_when_the_stash_loses_the_credentials(self, integration_db):
        """Reverse-TDD: damage only the stash, and the case above must go red."""
        from src.core.schemas import UpdateMediaBuyRequest

        with MediaBuyPushRegistrationEnv() as env:
            created = _register_via_create(env, with_push_config=False)
            env.register_delivery_target()
            env.set_http_status(200)

            env.call_mcp(
                req=UpdateMediaBuyRequest(media_buy_id=created.response.media_buy_id),
                push_notification_config={
                    "url": env.webhook_url,
                    "authentication": _tool_auth_block(),
                },
            )

            step = env.push_step("update_media_buy")
            env.drop_stashed_credential_half(step)
            env.complete_step(step)

            assert_delivered_unsigned(env)


class TestRefusedStashCostsTheWebhookNotTheTransition:
    """A stash the gate REFUSES must cost that webhook only.

    Grades the fail-closed OUTCOME of design revision #2: rehydration re-runs the
    ingest gate, so a stash that no longer passes it raises inside a status
    update. The obligation is that the buyer loses the notification, never the
    state transition.

    Honest scope: this asserts the OUTCOME, and the outcome is defended twice —
    by the per-webhook ``except AdCPValidationError: continue`` arm and by the
    pre-existing outer ``except Exception`` net. So it does not redden if only
    the arm is reverted; it reddens if BOTH nets go. The arm's marginal value
    over the outer net is that it refuses one webhook explicitly instead of
    unwinding out of both loops with a traceback, which is a logging and
    sibling-preservation property rather than a delivery-outcome one.
    """

    def test_a_gate_refusing_stash_delivers_nothing_and_still_completes(self, integration_db):
        with MediaBuyPushRegistrationEnv() as env:
            _register_via_create(env, with_push_config=True)
            env.set_http_status(200)

            step = env.push_step("create_media_buy")
            env.poison_stashed_registration(step)
            env.complete_step(step)

            assert env.delivery_attempts == 0, (
                f"a stash the ingest gate refuses produced {env.delivery_attempts} delivery attempts — "
                f"an unreceipted registration reached the sender"
            )
            assert env.step_status(step) == "completed", (
                "the status transition did not survive an undeliverable stash — "
                "a refused webhook must cost the notification, not the workflow state"
            )


class TestBlankUrlRegistrationIsNotPersisted:
    """A whitespace-only URL must never become a stored config row.

    The obligation is stable across two lanes; only WHO refuses has changed, and
    each change made the answer stronger:

    - Lane C2 gave ``_impl`` a write guard keyed on ``registration.url.strip()``.
      That mattered because the registration gate is a documented no-op on blank
      URLs, so ``accept_push_notification_config`` RETURNS a value for
      ``url="   "``; keying the write on the value's PRESENCE persisted a row with
      a whitespace url (measured: ``('   ', 'HMAC-SHA256')``), and C2 also deleted
      the repository ValueError that used to catch it downstream.
    - Lane C3 then made the A2A tool wrapper coerce through the pinned model, so a
      whitespace url is now REFUSED at ingest — correctably, naming
      ``push_notification_config.url`` — instead of being silently dropped. The
      buyer learns their registration did not take effect, which is the whole
      point of the epic.

    The C2 write guard is GONE, and its removal is part of the same movement: with
    ``_impl`` typed, ``PushNotificationConfig(url="   ")`` raises ``url_parsing``,
    so a blank-url config cannot be constructed and the guard became unreachable
    code. The protection did not disappear — it moved into the type, and this case
    grades it at the wrapper, which is why it asserts a REFUSAL as well as the
    absent row rather than only the absent row.
    """

    def test_whitespace_only_url_is_refused_and_writes_no_config_row(self, integration_db):
        with MediaBuyPushRegistrationEnv() as env:
            _, _principal, product, pricing_option = env.setup_media_buy_data()
            kwargs = env.minimal_create_kwargs(product, pricing_option)
            kwargs["push_notification_config"] = {
                "url": "   ",
                "authentication": _tool_auth_block(),
            }

            with pytest.raises(AdCPValidationError) as refusal:
                env.call_a2a(**kwargs)

            assert refusal.value.field == "push_notification_config.url", (
                f"a whitespace-only URL must be refused by name; got field={refusal.value.field!r}"
            )
            rows = env.persisted_config_rows()
            assert rows == [], (
                f"a whitespace-only URL was persisted as "
                f"{[(row.url, row.authentication_type) for row in rows]} — a refused registration "
                f"must leave nothing behind"
            )
