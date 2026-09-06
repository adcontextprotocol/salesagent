"""The nested in-process creative sync borrows the outer media buy's client key.

``create_media_buy`` and ``update_media_buy`` upload their packages' inline creatives by
building a real ``SyncCreativesRequest`` and calling ``_sync_creatives_impl``. The key on
that nested request is the OUTER request's ``idempotency_key`` — the buyer's own
client-generated key, not an invented one, because the nested upload is part of that one
operation.

Borrowing collides with the verbatim success cache if the implementation probes it. The
cache's lookup scope is the spec's (agent, account, key) tuple with NO tool dimension
(``IdempotencyAttemptRepository.find_by_key`` says so explicitly: "a key reused by a
different tool must hit this same row"), so a nested sync probing with the borrowed key would
find the MEDIA BUY's own row and be refused with IDEMPOTENCY_CONFLICT.

It cannot, because the probe lives at the transport boundary
(``src/core/tools/_boundary.py``) and a nested upload never crosses one — it enters the
implementation directly. That used to be arranged by threading a ``request_hash`` down and
having the in-process caller pass ``None``; the exemption is now structural, and these tests
pin both halves of it: the in-process caller is exempt, and the transports are not.
"""

import asyncio

import pytest

from src.core.exceptions import AdCPIdempotencyConflictError
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness import CreativeSyncEnv
from tests.helpers.creative_test_helpers import creative_payload
from tests.helpers.idempotency_seeds import make_active_cached_success, seed_cached_success

#: The buyer's key on the OUTER create_media_buy / update_media_buy.
_OUTER_KEY = "outer-media-buy-key-0001"

#: The canonical hash of that outer request, as production stored it beside the key.
_OUTER_HASH = "0" * 64


class TestNestedSyncBorrowsTheOuterKey:
    """A borrowed key reaches the cache from a transport and never from in-process."""

    def _seed(self, env: CreativeSyncEnv) -> None:
        tenant = TenantFactory(tenant_id="test_tenant")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        env._commit_factory_data()
        seed_cached_success(
            "test_tenant",
            "test_principal",
            _OUTER_KEY,
            response_model=make_active_cached_success(),
            payload_hash=_OUTER_HASH,
        )

    @pytest.mark.requires_db
    def test_in_process_sync_with_the_borrowed_key_executes(self, integration_db):
        """No boundary crossed, so no probe: the nested sync runs instead of conflicting.

        ``call_impl`` is the path ``create_media_buy``'s inline-creative upload takes. If the
        probe ever moved back into the implementation, this raises IDEMPOTENCY_CONFLICT: the
        probe would hit the seeded create_media_buy row, whose stored hash cannot match a
        sync_creatives payload.
        """
        with CreativeSyncEnv() as env:
            self._seed(env)

            response = env.call_impl(
                creatives=[creative_payload(creative_id="c_nested")],
                idempotency_key=_OUTER_KEY,
            )

        assert [r.creative_id for r in response.creatives] == ["c_nested"]
        assert response.creatives[0].action == "created"

    @pytest.mark.requires_db
    def test_a_transport_reusing_the_same_key_still_conflicts(self, integration_db):
        """The in-process exemption is not a way to opt out of at-most-once.

        A buyer's sync_creatives carrying the media buy's key crosses the boundary, which
        canonicalises the request and compares it to the stored hash. A different payload
        under the same key is the definition of the conflict, and it is refused.
        """
        from src.core.schemas.creative import SyncCreativesRequest
        from src.core.tools._boundary import invoke_tool

        with CreativeSyncEnv() as env:
            self._seed(env)
            req = SyncCreativesRequest(
                creatives=[creative_payload(creative_id="c_nested")],
                idempotency_key=_OUTER_KEY,
                account=env.default_account_reference(),
            )

            with pytest.raises(AdCPIdempotencyConflictError):
                asyncio.run(invoke_tool("sync_creatives", req, env.identity))

    @pytest.mark.requires_db
    def test_both_in_process_callers_borrow_a_required_outer_key(self):
        """Both converted call sites borrow, so the exemption protects both — not just one.

        Both fields the nested request needs -- ``account`` and ``idempotency_key`` -- are
        spec-REQUIRED on BOTH outer requests, so neither nested upload can avoid carrying a
        real outer key, and neither can fail to supply an account. Read off the models rather
        than asserted in prose, so a requiredness change fails this test instead of silently
        invalidating the reasoning this exemption rests on.

        create_media_buy's ``account`` was the one exception when this test was written --
        the last surviving instance of salesagent-prkv.28 -- and it is required now, so the
        four assertions below are symmetric. That symmetry IS the finding: an asymmetry here
        is what made the nested request unformable for one caller and not the other.
        """
        from src.core.schemas import CreateMediaBuyRequest, UpdateMediaBuyRequest

        for model in (CreateMediaBuyRequest, UpdateMediaBuyRequest):
            assert model.model_fields["idempotency_key"].is_required(), model.__name__
            assert model.model_fields["account"].is_required(), model.__name__
