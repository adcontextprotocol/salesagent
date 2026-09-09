"""E2E tests: tenant-scoped admin routes (#2203) against the Docker stack.

The e2e transport of BR-ADMIN-TENANT-SCOPING.feature: the same harness the BDD
integration suite drives through Flask ``test_client`` is driven here through
``requests.Session`` against nginx -> FastAPI -> admin blueprints, as
tests/e2e/test_admin_bdd_e2e.py does for BR-ADMIN-ACCOUNTS.

Requires: ADCP_SALES_PORT set (Docker stack running). The stack runs with
ADCP_AUTH_TEST_MODE=true, so sessions come from ``/test/auth`` as the non-admin
``test_tenant_user`` identity, logged in against a tenant that is never the
target — which keeps the test-mode bypass out of every membership decision.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import admin_stack_env
from tests.harness.admin_tenant_scoping import (
    ACTIVE_BUY_BUDGET,
    ROUTES,
    AdminTenantScopingEnv,
    assert_anonymous_rejected,
    assert_membership_rejected,
    expected_suggestions_body,
    redirect_path,
)

# (case id, method, route name, api_mode): one row per route and method the feature grades.
_CASES = [
    (f"{name}-{method}", method, name, route.api_mode) for name, route in ROUTES.items() for method in route.methods
]
_CASE_PARAMS = "method,route,api_mode"
_CASE_ROWS = [case[1:] for case in _CASES]
_CASE_IDS = [case[0] for case in _CASES]


@pytest.fixture()
def scoping_env(docker_services_e2e):
    """AdminTenantScopingEnv in e2e mode, with the target tenant already seeded."""
    with admin_stack_env(docker_services_e2e, lambda: AdminTenantScopingEnv(mode="e2e")) as env:
        env.seed_target_tenant()
        yield env


class TestAnonymousDenied:
    """T-ADMIN-SCOPE-001/002: no session -> the tenant check answers, and nothing changes."""

    @pytest.mark.parametrize(_CASE_PARAMS, _CASE_ROWS, ids=_CASE_IDS)
    def test_anonymous_is_rejected(self, scoping_env: AdminTenantScopingEnv, method, route, api_mode) -> None:
        scoping_env.clear_auth()

        response = scoping_env.send(method, route)

        assert_anonymous_rejected(response, api_mode, scoping_env.target.tenant_id)
        assert scoping_env.target_state() == scoping_env.seeded_state


class TestNonMemberDenied:
    """T-ADMIN-SCOPE-003..006: a session without an active membership in the target -> 403."""

    @pytest.mark.parametrize(_CASE_PARAMS, _CASE_ROWS, ids=_CASE_IDS)
    def test_member_of_other_tenant_receives_403(
        self, scoping_env: AdminTenantScopingEnv, method, route, api_mode
    ) -> None:
        scoping_env.login_as_member_of_other_tenant()

        response = scoping_env.send(method, route)

        assert_membership_rejected(response, api_mode)
        assert scoping_env.target_state() == scoping_env.seeded_state

    @pytest.mark.parametrize(_CASE_PARAMS, _CASE_ROWS, ids=_CASE_IDS)
    def test_inactive_member_receives_403(self, scoping_env: AdminTenantScopingEnv, method, route, api_mode) -> None:
        scoping_env.login_with_target_membership(is_active=False)

        response = scoping_env.send(method, route)

        assert_membership_rejected(response, api_mode)
        assert scoping_env.target_state() == scoping_env.seeded_state


class TestActiveMemberUnchanged:
    """T-ADMIN-SCOPE-007..010: an active membership keeps today's status and body."""

    def test_revenue_chart_lists_the_tenant_buy(self, scoping_env: AdminTenantScopingEnv) -> None:
        scoping_env.login_with_target_membership(is_active=True)

        response = scoping_env.send("GET", "revenue chart API")

        assert response.status_code == 200
        assert response.get_json() == {
            "labels": [scoping_env.target.principal_name],
            "values": [float(ACTIVE_BUY_BUDGET)],
        }

    def test_products_lists_the_tenant_catalogue(self, scoping_env: AdminTenantScopingEnv) -> None:
        scoping_env.login_with_target_membership(is_active=True)

        response = scoping_env.send("GET", "products API")

        assert response.status_code == 200
        assert response.get_json() == {"products": scoping_env.target.products_payload}

    def test_product_suggestions_list_the_default_catalogue(self, scoping_env: AdminTenantScopingEnv) -> None:
        scoping_env.login_with_target_membership(is_active=True)

        response = scoping_env.send("GET", "product suggestions API")

        assert response.status_code == 200
        assert response.get_json() == expected_suggestions_body()

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_policy_rules_redirects_to_policy_index(self, scoping_env: AdminTenantScopingEnv, method: str) -> None:
        scoping_env.login_with_target_membership(is_active=True)

        response = scoping_env.send(method, "policy rules page")

        assert response.status_code == 302
        assert redirect_path(response) == f"/tenant/{scoping_env.target.tenant_id}/policy/"
