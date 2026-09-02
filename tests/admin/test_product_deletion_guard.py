"""Which media-buy statuses stop a product being deleted underneath them.

The guard in ``products.delete_product`` protects a product that a buy could still
deliver against. Its membership rule is "could still deliver", which is NOT the same
as "the seller committed": a COMPLETED or CANCELED buy is committed and has no future
delivery to protect, so treating commitment as the rule would make products
undeletable forever.

``scheduled`` is the member this grades. A buy whose flight window has not opened is
a live commitment the seller has agreed to run, and it became reachable here when the
admin approval routes started writing the resolved flight-window status: a pre-window
buy used to land ``active`` — and so was protected by that member — and now lands
``scheduled``. Nothing observed the difference, so the product went from protected to
deletable with no test failing.
"""

from __future__ import annotations

import pytest

from src.admin.app import create_app
from tests.helpers.media_buy_approval import login_as, seed_pending_buy

app = create_app()

pytestmark = [pytest.mark.admin, pytest.mark.requires_db]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _seed_live_buy_on_a_product(session, *, status: str, starts_in_days: int):
    """Seed a buy in *status* and return the product id it references.

    ``seed_pending_buy`` builds a ``raw_request`` for the approval path, which
    revalidates it as a ``CreateMediaBuyRequest`` — so it carries ``packages[].product_id``
    and no top-level ``product_ids``. Production writes BOTH: ``media_buy_create``
    persists ``"product_ids": req.get_product_ids()`` alongside the packages at four
    sites, and the deletion guard reads that flat list.

    So the flat key is added here rather than left out. Omitting it would make every
    case below pass for the wrong reason — the guard would find no product to protect
    and allow the delete, and a test asserting refusal would fail while a test asserting
    permission would go green against a guard that never ran.
    """
    seeded = seed_pending_buy(starts_in_days=starts_in_days, status=status)
    product_id = seeded.media_buy.raw_request["packages"][0]["product_id"]
    seeded.media_buy.raw_request = {**seeded.media_buy.raw_request, "product_ids": [product_id]}
    session.commit()
    return seeded, product_id


@pytest.mark.parametrize(
    ("status", "starts_in_days"),
    [
        ("scheduled", 7),  # pre-window: agreed to run, has not started
        ("active", -1),  # in-window: currently delivering
        ("paused", -1),  # in-window, halted, resumable
    ],
)
def test_product_used_by_a_live_buy_cannot_be_deleted(client, factory_session, status, starts_in_days):
    """Every status that could still deliver must refuse the delete."""
    seeded, product_id = _seed_live_buy_on_a_product(factory_session, status=status, starts_in_days=starts_in_days)
    login_as(client, tenant_id=seeded.tenant_id)

    response = client.delete(f"/tenant/{seeded.tenant_id}/products/{product_id}/delete")

    assert response.status_code == 400, (
        f"a {status!r} buy could still deliver, so deleting its product must be refused; "
        f"got {response.status_code} — the product is now deletable underneath a live buy"
    )
    assert seeded.media_buy_id in response.get_json()["error"], (
        "the refusal must name the buy that blocks it — an operator cannot act on 'some media buy is using this'"
    )


@pytest.mark.parametrize("status", ["completed", "canceled"])
def test_product_used_only_by_a_finished_buy_can_be_deleted(client, factory_session, status):
    """A finished buy is committed but has no future delivery, so it must NOT block.

    This is the half that makes the guard's list right rather than merely longer, and
    the reason it is written out instead of reusing ``_SELLER_COMMITTED_STATUSES``:
    that set contains both of these.
    """
    seeded, product_id = _seed_live_buy_on_a_product(factory_session, status=status, starts_in_days=-60)
    login_as(client, tenant_id=seeded.tenant_id)

    response = client.delete(f"/tenant/{seeded.tenant_id}/products/{product_id}/delete")

    assert response.status_code == 200, (
        f"a {status!r} buy has no delivery left to protect, so its product must remain "
        f"deletable; got {response.status_code} — adopting the committed-statuses set "
        f"here would strand every product behind a finished campaign"
    )
