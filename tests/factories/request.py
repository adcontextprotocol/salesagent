"""Request factories: one spec-conformant baseline payload per AdCP tool.

The request-side counterpart to the ORM and response factories already in this
package. A negative-path test wants ONE bad field, and until now the only way to
get there was to hand-type a whole ``create_media_buy`` payload around it — so
every scenario re-derived its own idea of "a valid request", and each copy was
graded only by "the Pydantic constructor accepted it".

That grade is the weaker of the two contracts in play. Our DTOs and the pinned
the DTOs are GENERATED FROM the pinned schemas, so a payload the constructor
accepts is a payload the schema accepts. Measured on this tree:
``CreateMediaBuyRequest`` and ``SyncAccountsRequest`` require exactly the sets
their pinned schemas require, and ``idempotency_key`` carries the schema's
``MinLen(16)``, ``MaxLen(255)`` and ``^[A-Za-z0-9_.:-]{16,255}$`` — a
hand-written ``"test-key-1"`` is REJECTED by the constructor.

This module's docstring used to claim the opposite, and a whole suite existed to
police the gap it described. The gap had closed and nobody re-measured. What is
left is a REFUSAL rather than a suite: ``_register_tool`` will not register a
tool whose DTO does not descend from ``AdcpVersionEnvelope``, because a DTO that
does not is one from a parallel hierarchy (salesagent-fdkub). Everything a
payload does on the wire is graded by BDD.

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

from src.core.tools.registry import TOOLS


def dto(tool: str) -> type:
    """The request model for *tool*, read from the registry rather than imported.

    A factory that names its model by import can bind a DIFFERENT class than the
    one the tool actually uses, and the names are close enough that nothing looks
    wrong: ``CompleteTaskRequest`` requires ``task_id``, ``resolution`` and
    ``resolved_by``; ``CompleteTaskRequestLocal``, which is what the registry
    binds to ``complete_task``, requires only ``task_id``. A factory written
    against the first produces a baseline the tool would reject, and the failure
    surfaces as a confusing ValidationError in the test's own setup.

    Reading the model off ``TOOLS`` makes that unrepresentable: there is one
    answer to 'which DTO does this tool use', and it is the same one MCP
    announces, the REST body validates against, and A2A dispatches with.
    """
    return TOOLS[tool].dto


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
    no ``date-time`` format checker, so every string satisfies BOTH arms and
    ``"asap"`` fails the ``oneOf`` as ambiguous. A baseline that cannot be
    validated is not a baseline; scenarios that specifically grade immediate
    start override it and accept that the schema assertion cannot grade them.
    """

    class Meta:
        model = dto("create_media_buy")

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
        model = dto("sync_creatives")

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

    The entry is in PROVISIONING mode, whose ``oneOf`` arm requires all three of
    ``brand`` + ``operator`` + ``billing`` — omitting ``billing`` (easy to do by
    hand, since our DTO tolerates it) makes the entry match neither arm. The
    settings-update mode is the other arm: override ``accounts`` with a single
    ``{"account": ...}`` key.
    """

    class Meta:
        model = dto("sync_accounts")

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
        model = dto("list_accounts")


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
        model = dto("list_creative_formats")


# --- the remaining nine tools -------------------------------------------------
#
# Every tool in ``src.core.tools.registry.TOOLS`` has a factory, so a scenario
# never hand-builds a payload. The tools below mostly declare NO required field:
# their baseline is the empty request, and what each factory supplies is the
# smallest set that makes the request MEAN something a seller can answer.
#
# Where the pin requires a field our DTO does not, the factory supplies it —
# same rule ``CreateMediaBuyRequestFactory`` states for ``account``. A baseline
# is only useful if it is one the spec would accept.


class GetProductsRequestFactory(_RequestFactory):
    """A get_products request conforming to ``media-buy/get-products-request.json``.

    ``buying_mode`` is supplied because the PIN REQUIRES IT — it is the sole
    entry in that schema's ``/required``, typed as the enum
    ``[brief, wholesale, refine]``, and its description says "v3 clients MUST
    include buying_mode". Our DTO widened it to ``str | None`` and therefore does
    not require it; that widening is a defect tracked as #2117. The
    baseline follows the pin rather than the widening, so it stays valid when the
    widening is deleted.

    ``brief`` pairs with ``buying_mode="brief"``: the pin's own description says
    'wholesale' means the buyer wants raw inventory and **brief must not be
    provided**, so brief and wholesale are mutually exclusive. A wholesale
    baseline is ``payload(buying_mode="wholesale", brief=OMIT)``.
    """

    class Meta:
        model = dto("get_products")

    buying_mode = "brief"
    brief = "display advertising for an outdoor apparel brand"
    brand = factory.LazyFunction(lambda: {"domain": "testbrand.com"})


class UpdateMediaBuyRequestFactory(_RequestFactory):
    """An update_media_buy request conforming to ``media-buy/update-media-buy-request.json``.

    All three of the pin's required fields are supplied, and our DTO requires the
    same three — the one tool where the two contracts already agree.

    ``media_buy_id`` is a placeholder: an update targets a buy that must already
    exist, so a scenario overrides it with the id its Given step created. The
    baseline exists to be perturbed, not to be sent as-is.
    """

    class Meta:
        model = dto("update_media_buy")

    idempotency_key = factory.LazyFunction(fresh_idempotency_key)
    account = factory.LazyFunction(lambda: dict(SAMPLE_ACCOUNT))
    media_buy_id = "mb-baseline"


class GetMediaBuysRequestFactory(_RequestFactory):
    """A get_media_buys request. The pin requires nothing.

    ``account`` is supplied because a query with no account asks for every buy
    the caller can see, which is a different question from the one most
    scenarios mean. Override with ``account=OMIT`` for the unscoped query.
    """

    class Meta:
        model = dto("get_media_buys")

    account = factory.LazyFunction(lambda: dict(SAMPLE_ACCOUNT))


class GetMediaBuyDeliveryRequestFactory(_RequestFactory):
    """A get_media_buy_delivery request. The pin requires nothing.

    Same reasoning as ``GetMediaBuysRequestFactory`` for ``account``.
    """

    class Meta:
        model = dto("get_media_buy_delivery")

    account = factory.LazyFunction(lambda: dict(SAMPLE_ACCOUNT))


class ListCreativesRequestFactory(_RequestFactory):
    """A list_creatives request. The pin requires nothing and so does the DTO.

    The baseline is deliberately EMPTY: an unfiltered list is the meaningful
    default, and every filter, sort and pagination scenario is an override on
    top of it. Supplying a filter here would make the unfiltered case the
    special one.
    """

    class Meta:
        model = dto("list_creatives")


class ListTasksRequestFactory(_RequestFactory):
    """A list_tasks request. Empty baseline, same reasoning as list_creatives."""

    class Meta:
        model = dto("list_tasks")


class GetAdcpCapabilitiesRequestFactory(_RequestFactory):
    """A get_adcp_capabilities request. Empty baseline.

    Capabilities is the discovery call: asking with no filters is the whole
    point, and ``protocols`` narrows it. Auth is optional on this tool, which is
    a property of the tool rather than of the payload, so nothing here carries it.
    """

    class Meta:
        model = dto("get_adcp_capabilities")


class GetTaskStatusRequestFactory(_RequestFactory):
    """A get_task_status request. ``task_id`` is required by the DTO.

    Named for the TOOL, which is named for its spec task: the pin calls the
    operation ``get-task-status`` and the SDK type is ``GetTaskStatusRequest``,
    so ``get_task`` was the odd name out and was renamed on main (f562b60df).

    This factory broke loudly on that rename -- ``dto("get_task")`` raised
    ``KeyError`` at import -- which is the intended failure mode. A factory that
    named its model by import would have kept building the old class silently.

    Placeholder id, same as ``UpdateMediaBuyRequestFactory.media_buy_id``: a
    scenario overrides it with the task its Given step created.
    """

    class Meta:
        model = dto("get_task_status")

    task_id = "task-baseline"


class CompleteTaskRequestFactory(_RequestFactory):
    """A complete_task request. ``task_id`` and ``status`` are both required.

    ``status`` used to be left unset here, on the reasoning that which terminal
    status a completion carries is what most scenarios grade, so picking one
    would make the other arm read as the override. That reasoning held while the
    DTO typed it ``str | None``. It no longer can: main narrowed it to a required
    ``Literal["completed", "failed"]`` (f562b60df), so a baseline that omits it
    does not build at all.

    ``completed`` is therefore the baseline and ``payload(status="failed")`` the
    other arm -- the ordinary case as the default, which is the same rule every
    other factory here follows.
    """

    class Meta:
        model = dto("complete_task")

    task_id = "task-baseline"
    status = "completed"
