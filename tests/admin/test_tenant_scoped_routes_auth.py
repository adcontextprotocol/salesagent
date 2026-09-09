"""Authorization regression tests for the four tenant-scoped admin routes of #2203.

``GET /api/tenant/<tenant_id>/revenue-chart``, ``GET /api/tenant/<tenant_id>/products``,
``GET /api/tenant/<tenant_id>/products/suggestions`` and ``GET,POST
/tenant/<tenant_id>/policy/rules`` take the tenant from the URL. Before #2203 they carried
only ``require_auth()``, which checks that *somebody* is logged in. A tenant-scoped route must
prove the caller is an active member of that tenant, and exactly one component does that:
``require_tenant_access`` (``src/admin/utils/helpers.py``). Every expectation below is that
decorator's observable contract:

* anonymous        -> JSON 401 ``{"error": "Authentication required"}`` on the three
                      ``api_mode`` routes; redirect to the tenant login page on the HTML route
* other tenant     -> 403 (JSON ``{"error": "Access denied"}`` on the API routes)
* inactive member  -> 403, same shape (``is_active=False`` row in the requested tenant)
* active member    -> today's behaviour, same status and body
* any rejection    -> no state change

Sessions are real ``User`` memberships, never the super-admin or ``ADCP_AUTH_TEST_MODE``
bypass, so each rejection test here fails if the decorator is removed. Test data comes
from factory-boy factories (``tests/CLAUDE.md``); no ``session.add()`` in test bodies.
The route table, seeding, state snapshot and assertion helpers are shared with the BDD
harness (``tests/harness/admin_tenant_scoping.py``) so all three layers grade one contract.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

from src.admin.app import create_app
from src.core.database.models import Tenant
from tests.factories import UserFactory
from tests.harness.admin_tenant_scoping import (
    ACTIVE_BUY_BUDGET,
    ROUTES,
    TargetTenant,
    assert_anonymous_rejected,
    assert_membership_rejected,
    expected_suggestions_body,
    member_session,
    redirect_path,
    seed_target_tenant,
    tenant_state,
)

app = create_app()

pytestmark = [pytest.mark.admin, pytest.mark.requires_db]

# (case id, method, path template, api_mode): one row per route and method.
_CASES = [
    (f"{name}-{method}", method, route.path, route.api_mode)
    for name, route in ROUTES.items()
    for method in route.methods
]
_CASE_PARAMS = "method,path,api_mode"
_CASE_ROWS = [case[1:] for case in _CASES]
_CASE_IDS = [case[0] for case in _CASES]

# Two ways a logged-in user can fail membership in the requested tenant. Each builds the
# User row whose email the session will carry.
_REJECTED_MEMBERSHIPS = {
    "other_tenant": lambda target: UserFactory(),  # active member of a different tenant
    "inactive_member": lambda target: UserFactory(tenant=target, is_active=False),
}


@pytest.fixture
def client() -> Iterator[FlaskClient]:
    """Flask test client with CSRF disabled."""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SESSION_COOKIE_PATH"] = "/"
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_ambient_super_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory users live at ``@example.com``.

    An inherited ``SUPER_ADMIN_DOMAINS=example.com`` would turn every rejection case below
    into a super-admin pass and prove nothing about tenant membership.
    """
    monkeypatch.delenv("SUPER_ADMIN_DOMAINS", raising=False)


def _member_session(client: FlaskClient, tenant_id: str, email: str) -> None:
    """Authenticated session for a normal tenant member (never the test-mode bypass keys)."""
    with client.session_transaction() as sess:
        sess.update(member_session(email, tenant_id))


def _seed(session: Session) -> tuple[TargetTenant, Tenant, tuple]:
    """The target tenant, its ORM row (for membership factories) and its state snapshot."""
    target = seed_target_tenant(session)
    tenant = session.get(Tenant, target.tenant_id)
    assert tenant is not None
    return target, tenant, tenant_state(session, target.tenant_id)


def _login_active_member(client: FlaskClient, tenant: Tenant) -> None:
    user = UserFactory(tenant=tenant)
    _member_session(client, tenant.tenant_id, user.email)


def _dispatch(client: FlaskClient, method: str, path: str, tenant_id: str) -> TestResponse:
    url = path.format(tenant_id=tenant_id)
    if method == "GET":
        return client.get(url)
    if method == "POST":
        return client.post(url, data={})
    raise AssertionError(f"unexpected method {method}")


class TestAnonymousDenied:
    """Unauthenticated callers are rejected before the handler runs, with no state change."""

    @pytest.mark.parametrize(_CASE_PARAMS, _CASE_ROWS, ids=_CASE_IDS)
    def test_anonymous_is_rejected(
        self, client: FlaskClient, factory_session: Session, method: str, path: str, api_mode: bool
    ) -> None:
        target, _tenant, before = _seed(factory_session)

        response = _dispatch(client, method, path, target.tenant_id)

        assert_anonymous_rejected(response, api_mode, target.tenant_id)
        assert tenant_state(factory_session, target.tenant_id) == before


class TestNonMemberDenied:
    """A logged-in user without an active membership in the requested tenant receives 403.

    ``other_tenant`` is an active member somewhere else; ``inactive_member`` has a row in the
    requested tenant with ``is_active=False``. Both must be refused identically.
    """

    @pytest.mark.parametrize("membership", sorted(_REJECTED_MEMBERSHIPS))
    @pytest.mark.parametrize(_CASE_PARAMS, _CASE_ROWS, ids=_CASE_IDS)
    def test_non_member_receives_403(
        self,
        client: FlaskClient,
        factory_session: Session,
        membership: str,
        method: str,
        path: str,
        api_mode: bool,
    ) -> None:
        target, tenant, before = _seed(factory_session)
        user = _REJECTED_MEMBERSHIPS[membership](tenant)
        _member_session(client, user.tenant_id, user.email)

        response = _dispatch(client, method, path, target.tenant_id)

        assert_membership_rejected(response, api_mode)
        assert tenant_state(factory_session, target.tenant_id) == before


class TestActiveMemberUnchanged:
    """An active same-tenant ``User`` row is enough; status and body stay exactly as today."""

    def test_revenue_chart_lists_the_tenant_buys(self, client: FlaskClient, factory_session: Session) -> None:
        target, tenant, _before = _seed(factory_session)
        _login_active_member(client, tenant)

        response = client.get(f"/api/tenant/{target.tenant_id}/revenue-chart")

        assert response.status_code == 200
        assert response.get_json() == {"labels": [target.principal_name], "values": [float(ACTIVE_BUY_BUDGET)]}

    def test_products_lists_the_tenant_catalogue(self, client: FlaskClient, factory_session: Session) -> None:
        target, tenant, _before = _seed(factory_session)
        _login_active_member(client, tenant)

        response = client.get(f"/api/tenant/{target.tenant_id}/products")

        assert response.status_code == 200
        assert response.get_json() == {"products": target.products_payload}

    def test_product_suggestions_list_the_default_catalogue(
        self, client: FlaskClient, factory_session: Session
    ) -> None:
        target, tenant, _before = _seed(factory_session)
        _login_active_member(client, tenant)

        response = client.get(f"/api/tenant/{target.tenant_id}/products/suggestions")

        assert response.status_code == 200
        assert response.get_json() == expected_suggestions_body()

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_policy_rules_redirects_to_policy_index(
        self, client: FlaskClient, factory_session: Session, method: str
    ) -> None:
        target, tenant, _before = _seed(factory_session)
        _login_active_member(client, tenant)

        response = _dispatch(client, method, "/tenant/{tenant_id}/policy/rules", target.tenant_id)

        assert response.status_code == 302
        assert redirect_path(response) == f"/tenant/{target.tenant_id}/policy/"
