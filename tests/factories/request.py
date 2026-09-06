"""Request factories: one spec-conformant baseline payload per AdCP tool.

The request-side counterpart to the ORM and response factories already in this
package. A negative-path test wants ONE bad field, and until now the only way to
get there was to hand-type a whole ``create_media_buy`` payload around it — so
every scenario re-derived its own idea of "a valid request", and each copy was
graded only by "the Pydantic constructor accepted it".

That grade is the weaker of the two contracts in play. Our DTOs and the pinned
AdCP schemas do not agree field for field (``CreateMediaBuyRequest`` does not
require ``account``; ``SyncAccountsRequest`` does not require
``idempotency_key``; the pin requires both), so a payload our constructor accepts
can still be one the spec rejects. Every baseline here is therefore graded
against the PINNED SCHEMA by
``tests/unit/test_request_factory_schema_conformance.py``, with a divergence
allowlist whose rows each carry a spec citation. Adding a factory without a
conformant baseline fails that suite.

Usage — the perturbation this module exists for::

    from tests.factories import CreateMediaBuyRequestFactory

    # the conformant baseline, as the wire dict a transport carries
    payload = CreateMediaBuyRequestFactory.payload()

    # ONE field perturbed; everything else stays conformant
    payload = CreateMediaBuyRequestFactory.payload(start_time="not-a-timestamp")

    # a required field REMOVED rather than replaced
    payload = CreateMediaBuyRequestFactory.payload(idempotency_key=OMIT)

    # a typed request object, when the caller wants DTO validation to run
    req = CreateMediaBuyRequestFactory.build(po_number="PO-1")

``payload()`` applies overrides AFTER the model dump, on purpose: a negative-path
test usually needs a value the DTO itself would reject, and routing it through
the constructor would raise in the test's own setup instead of at the boundary
under test. ``build()`` is the opposite seam — overrides go through the model, so
the caller gets DTO validation. Both exist because both are wanted; neither is
the general case.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import factory

from src.core.schemas import (
    CreateMediaBuyRequest,
    ListAccountsRequest,
    ListCreativeFormatsRequest,
    SyncAccountsRequest,
    SyncCreativesRequest,
)
from tests.factories.creative_asset import build_assets, image_spec
from tests.factories.format import AGENT_URL
from tests.helpers.sample_account import SAMPLE_ACCOUNT


class _Omit:
    """Sentinel: ``payload(field=OMIT)`` deletes the key instead of setting it.

    A negative-path test that grades a MISSING required field cannot express
    itself with ``None`` — ``None`` is a value, and the baseline dump already
    drops null fields, so ``payload(account=None)`` would read as "leave the
    default in place" rather than "send a request without an account".
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "OMIT"


OMIT = _Omit()


def fresh_idempotency_key() -> str:
    """A fresh key matching the pin's ``^[A-Za-z0-9_.:-]{16,255}$``.

    Sixteen characters is a real floor: hand-written keys like ``"test-key-1"``
    are silently non-conformant, which is one of the things grading the baseline
    against the pin catches. Fresh per call rather than a stable sequence
    because a REUSED key replays the original response instead of performing the
    operation — a replay test wants one stable key for the whole scenario and
    should say so by overriding, which is a decision no default can make for it.
    """
    return f"idem-{uuid.uuid4().hex}"


@cache
def _campaign_window() -> tuple[datetime, datetime]:
    """One ``(start_time, end_time)`` for the whole process.

    Now-relative, because a hardcoded date goes stale and starts failing
    "start_time must be in the future"; but resolved ONCE, because two baselines
    built a few microseconds apart would otherwise differ in their campaign
    window, and "perturb one field" has to mean one. Contrast
    ``fresh_idempotency_key``, which is deliberately fresh per call — a reused key
    replays. Lazy rather than module-level so importing the factories does not
    read the clock.
    """
    anchor = datetime.now(UTC).replace(microsecond=0)
    return anchor + timedelta(days=1), anchor + timedelta(days=30)


class _RequestFactory(factory.Factory):
    """Base for request factories: adds the wire-dict seam ``payload()``."""

    class Meta:
        abstract = True

    @classmethod
    def payload(cls, **overrides: Any) -> dict[str, Any]:
        """The conformant baseline as a wire dict, with *overrides* applied verbatim.

        Overrides land AFTER ``model_dump``, so they may carry values the DTO
        would reject — that is the point of a negative-path perturbation. Pass
        ``OMIT`` to delete a key.
        """
        data: dict[str, Any] = cls.build().model_dump(mode="json", exclude_none=True)
        for key, value in overrides.items():
            if isinstance(value, _Omit):
                data.pop(key, None)
            else:
                data[key] = value
        return data


class CreateMediaBuyRequestFactory(_RequestFactory):
    """A create_media_buy request that conforms to ``media-buy/create-media-buy-request.json``.

    ``account`` is supplied even though our DTO does not require it: the pin
    lists it in ``/required``, and a baseline is only useful if it is one the
    spec would accept. It defaults to the natural-key form of
    ``tests.helpers.sample_account.SAMPLE_ACCOUNT`` so a payload from this
    factory resolves against an env seeded by ``seed_sample_account`` — one
    spelling for the account both halves agree on. Sellers with an
    ``account_id`` namespace override with ``account={"account_id": ...}``.

    ``start_time`` is an explicit timestamp rather than ``"asap"``, and that is
    NOT merely a taste: the pin models ``start_time`` as a ``oneOf`` over a
    ``date-time`` string and the constant ``"asap"``, and our validator asserts
    no ``date-time`` format checker, so every string satisfies BOTH branches and
    ``"asap"`` fails the ``oneOf`` as ambiguous. A baseline that cannot be
    validated is not a baseline; scenarios that specifically grade immediate
    start override it and accept that the schema assertion cannot grade them.
    """

    class Meta:
        model = CreateMediaBuyRequest

    idempotency_key = factory.LazyFunction(fresh_idempotency_key)
    account = factory.LazyFunction(lambda: dict(SAMPLE_ACCOUNT))
    brand = factory.LazyFunction(lambda: {"domain": "testbrand.com"})
    start_time = factory.LazyFunction(lambda: _campaign_window()[0])
    end_time = factory.LazyFunction(lambda: _campaign_window()[1])
    packages = factory.LazyFunction(
        lambda: [{"product_id": "prod-1", "budget": 5000.0, "pricing_option_id": "cpm_usd_fixed"}]
    )


class SyncCreativesRequestFactory(_RequestFactory):
    """A sync_creatives request conforming to ``creative/sync-creatives-request.json``.

    The creative is built through ``image_spec``/``build_assets`` rather than as a
    literal dict, so the ``assets`` shape has the same single owner every other
    creative test uses. ``assets`` is on the pin's ``/required`` for a creative
    asset, which a hand-written ``{creative_id, name, format_id}`` triple misses.
    """

    class Meta:
        model = SyncCreativesRequest

    idempotency_key = factory.LazyFunction(fresh_idempotency_key)
    account = factory.LazyFunction(lambda: dict(SAMPLE_ACCOUNT))
    creatives = factory.LazyFunction(
        lambda: [
            {
                "creative_id": "c_0001",
                "name": "Test Creative",
                "format_id": {"id": "display_300x250_image", "agent_url": AGENT_URL},
                "assets": build_assets(image_spec("banner")),
            }
        ]
    )


class SyncAccountsRequestFactory(_RequestFactory):
    """A sync_accounts request conforming to ``account/sync-accounts-request.json``.

    The entry is in PROVISIONING mode, whose ``oneOf`` branch requires all three of
    ``brand`` + ``operator`` + ``billing`` — omitting ``billing`` (easy to do by
    hand, since our DTO tolerates it) makes the entry match neither branch. The
    settings-update mode is the other branch: override ``accounts`` with a single
    ``{"account": ...}`` key.
    """

    class Meta:
        model = SyncAccountsRequest

    idempotency_key = factory.LazyFunction(fresh_idempotency_key)
    accounts = factory.LazyFunction(
        lambda: [
            {
                "brand": dict(SAMPLE_ACCOUNT["brand"]),
                "operator": SAMPLE_ACCOUNT["operator"],
                "billing": "agent",
            }
        ]
    )


class ListAccountsRequestFactory(_RequestFactory):
    """A list_accounts request conforming to ``account/list-accounts-request.json``.

    The pin declares no required properties, so the conformant baseline is the
    empty request — which is exactly the point of having it here: a caller that
    wants to grade one filter overrides that one field and inherits a payload
    nothing else in it can be blamed for.
    """

    class Meta:
        model = ListAccountsRequest


class ListCreativeFormatsRequestFactory(_RequestFactory):
    """A list_creative_formats request conforming to ``media-buy/list-creative-formats-request.json``.

    Empty baseline for the same reason as ``ListAccountsRequestFactory``. The pinned
    tree ships the schema TWICE, under ``media-buy/`` and ``creative/``, and they
    differ; the ``media-buy/`` copy is the one graded here — not by anyone choosing it,
    but because ``ListCreativeFormatsRequest`` inherits
    ``adcp.types...media_buy.list_creative_formats_request``, and that is where
    ``tests.helpers.request_schemas`` reads the binding from.
    """

    class Meta:
        model = ListCreativeFormatsRequest


def declared_request_factories() -> dict[type, type[_RequestFactory]]:
    """``request DTO -> factory`` for every factory THIS MODULE declares.

    Read off each factory's own ``Meta.model``, which every ``factory.Factory``
    subclass must already declare — so the binding a five-row ``REQUEST_FACTORY_BY_TOOL``
    used to restate is taken from the declaration it was restating. Scoped to this
    module's namespace rather than ``__subclasses__()`` so a throwaway factory defined
    inside some other test cannot silently join the registry.
    """
    factories: dict[type, type[_RequestFactory]] = {}
    for obj in list(globals().values()):
        if not (isinstance(obj, type) and issubclass(obj, _RequestFactory) and obj is not _RequestFactory):
            continue
        model = obj._meta.model
        if model in factories:
            raise RuntimeError(
                f"{obj.__name__} and {factories[model].__name__} both build {model.__name__}. "
                f"A DTO has one baseline; two make 'the conformant payload' ambiguous."
            )
        factories[model] = obj
    return factories


def request_factories_by_tool() -> dict[str, type[_RequestFactory]]:
    """``tool -> its request factory``, DERIVED by joining the two live declarations.

    The tool -> DTO half comes from the MCP registry (the same lookup production
    announces the tool's shape with) and the DTO -> factory half from ``Meta.model``.
    Neither half is written here, so a factory cannot be bound to a DIFFERENT model than
    the tool actually builds, and the join is what the conformance suite grades over.

    A factory whose model no tool builds is absent from this map — and
    ``test_every_declared_factory_is_bound_to_a_registered_tool`` fails on it, so
    "absent" cannot mean "quietly ungraded".
    """
    from tests.helpers.registered_tools import registered_request_dtos

    factories = declared_request_factories()
    return {tool: factories[model] for tool, model in registered_request_dtos().items() if model in factories}
