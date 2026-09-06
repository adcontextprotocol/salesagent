"""Integration tests for account REST routes (list_accounts + sync_accounts).

Verifies REST transport parity with IMPL/A2A/MCP transports.

"""

from __future__ import annotations

import pytest

from tests.factories.account import AccountFactory, AgentAccountAccessFactory


@pytest.mark.requires_db
class TestListAccountsRestRoute:
    """REST /api/v1/accounts reaches the same implementation IMPL does."""

    def test_list_accounts_returns_accounts(self, integration_db):
        """GET accounts via REST returns same data as IMPL."""
        from tests.harness.account_list import AccountListEnv

        with AccountListEnv() as env:
            tenant, principal = env.setup_default_data()
            AccountFactory(tenant=tenant, status="active")
            AgentAccountAccessFactory(
                tenant_id=tenant.tenant_id,
                principal=principal,
                account=AccountFactory._meta.sqlalchemy_session.query(AccountFactory._meta.model).first(),
            )

            # IMPL baseline
            impl_response = env.call_impl()
            assert len(impl_response.accounts) >= 1

            # REST should return the same
            client = env.get_rest_client()
            rest_response = client.post("/api/v1/accounts", json={})
            assert rest_response.status_code == 200, (
                f"Expected 200, got {rest_response.status_code}: {rest_response.text}"
            )
            data = rest_response.json()
            assert "accounts" in data
            assert len(data["accounts"]) == len(impl_response.accounts)


@pytest.mark.requires_db
class TestSyncAccountsRestRoute:
    """REST /api/v1/accounts/sync reaches the same implementation IMPL does."""

    def test_sync_accounts_creates_account(self, integration_db):
        """POST sync via REST creates account same as IMPL."""
        from tests.factories.request import fresh_idempotency_key
        from tests.harness.account_sync import AccountSyncEnv

        with AccountSyncEnv() as env:
            env.setup_default_data()

            client = env.get_rest_client()
            rest_response = client.post(
                "/api/v1/accounts/sync",
                json={
                    "accounts": [
                        {
                            "brand": {"domain": "rest-test.com"},
                            "operator": "rest-test.com",
                            "billing": "operator",
                        }
                    ],
                    # Required by sync-accounts-request.json 3.1.1 (prkv.86). This asserts a
                    # 200 that CREATES the account, so the body must be one REST accepts;
                    # without the key the route correctly answers 400 INVALID_REQUEST and the
                    # creation this test exists to grade never happens.
                    "idempotency_key": fresh_idempotency_key(),
                },
            )
            assert rest_response.status_code == 200, (
                f"Expected 200, got {rest_response.status_code}: {rest_response.text}"
            )
            data = rest_response.json()
            assert "accounts" in data
            assert len(data["accounts"]) == 1
            assert data["accounts"][0]["brand"]["domain"] == "rest-test.com"
