"""Shared builder for a valid create_media_buy request against the seeded product.

Both UC-002 (idempotency replay) and UC-019 (the post-create get_media_buys poll)
need "a create_media_buy request that succeeds against the product this env
seeded". That is one logical operation with one parameter — the buyer's PO number
— so it lives here rather than being copied per use case.

Reads ctx["default_product"] / ctx["default_pricing_option"], which
``MediaBuyCreateEnv.setup_media_buy_data()`` puts there via conftest.
"""

from __future__ import annotations

from typing import Any


def pricing_option_id(pricing_option: Any) -> str:
    """Synthetic pricing_option_id string from a PricingOption ORM row.

    Matches the production/`given_media_buy` convention
    ``{pricing_model}_{currency_lower}_{fixed|auction}``.
    """
    fixed_str = "fixed" if pricing_option.is_fixed else "auction"
    return f"{pricing_option.pricing_model}_{pricing_option.currency.lower()}_{fixed_str}"


def build_create_request_kwargs(
    ctx: dict,
    *,
    po_number: str | None = None,
    budget: float = 5000.0,
    product_id: str | None = None,
    pricing_option: str | None = None,
) -> dict[str, Any]:
    """Assemble a valid create_media_buy request dict against the seeded product.

    The single base-request literal. Stored on ctx["request_kwargs"] and returned.

    ``po_number`` is OMITTED when None rather than written as ``None``: the A2A
    wrapper no longer mints one when the caller omits it (it stays None for
    idempotency-hash + cross-transport parity), so a caller that hashes the
    canonical payload supplies its own exactly as a real buyer does — and a caller
    that does not want one should produce a dict without the key, not a dict with a
    null in it.

    ``product_id`` / ``pricing_option`` let a caller pass values it has already
    resolved. ``pricing_option`` is the ID STRING, not a ``PricingOption`` row — the
    natural name would shadow the ``pricing_option_id`` helper imported above, which
    is a small cost of there being exactly one such helper. Omitted, they are read from ctx, which is what the create-flow steps
    do. This is the seam that lets ``given_media_buy`` delegate its base dict here
    while keeping its own tolerance for a ctx that has no seeded product.

    Deliberately KEY-FREE: no idempotency_key. Minting one is the caller's decision
    and there are two different right answers — a fresh key per call (independent
    buys) and one stable key per scenario (replay). See ``given_media_buy``'s
    setdefault, and ``media_buy_create._ensure_idempotency_key``. A third minting
    site here would silently pick one of them for everybody.
    """
    from datetime import UTC, datetime, timedelta

    if product_id is None:
        product_id = ctx["default_product"].product_id
    if pricing_option is None:
        pricing_option = pricing_option_id(ctx["default_pricing_option"])
    now = datetime.now(UTC)
    kwargs: dict[str, Any] = {
        "brand": {"domain": "testbrand.com"},
        "start_time": (now + timedelta(days=1)).isoformat(),
        "end_time": (now + timedelta(days=30)).isoformat(),
        "packages": [
            {
                "product_id": product_id,
                "budget": budget,
                "pricing_option_id": pricing_option,
            }
        ],
    }
    if po_number is not None:
        kwargs["po_number"] = po_number
    ctx["request_kwargs"] = kwargs
    return ctx["request_kwargs"]
