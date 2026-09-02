"""Factory_boy factories for MediaBuy and MediaPackage models.

Also holds the Pydantic factory for the ``get_media_buys`` RESPONSE item
(``GetMediaBuysMediaBuyFactory``) — the wire-shaped sibling of the ORM
``MediaBuyFactory`` above it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import factory
from adcp.types import MediaBuyStatus
from factory import LazyAttribute, Sequence, SubFactory

from src.core.database.models import MediaBuy, MediaPackage, is_media_buy_seller_confirmed
from src.core.schemas import GetMediaBuysMediaBuy
from tests.factories.core import TenantFactory
from tests.factories.principal import PrincipalFactory


class MediaBuyFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = MediaBuy
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    # ``MediaBuy.__init__`` refuses ``confirmed_at``/``revision`` outright, so a row
    # cannot be born already committed without passing the repository's stamp. The
    # factory still needs to seed those columns — a test grading listing or concurrency
    # has to start from a row in a state production reaches — so it takes the route the
    # repository takes: construct without them, then assign. Both doors are covered,
    # because ``.build()`` and ``.create()`` reach the model through different hooks.
    #
    # This deliberately adds NO escape hatch to the model. An exemption keyed on "the
    # caller is a factory" would have to enumerate its callers, and the guard this
    # replaces failed precisely because enumeration always misses a spelling.
    @staticmethod
    def _seed_seam_fields(instance, seam):
        """Apply repository-managed columns by assignment, the way the repository does."""
        for field, value in seam.items():
            setattr(instance, field, value)
        return instance

    @classmethod
    def _split_seam_kwargs(cls, kwargs):
        return {field: kwargs.pop(field) for field in MediaBuy._SEAM_MANAGED_FIELDS if field in kwargs}

    @classmethod
    def _build(cls, model_class, *args, **kwargs):
        seam = cls._split_seam_kwargs(kwargs)
        return cls._seed_seam_fields(super()._build(model_class, *args, **kwargs), seam)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        seam = cls._split_seam_kwargs(kwargs)
        instance = cls._seed_seam_fields(super()._create(model_class, *args, **kwargs), seam)
        if seam and cls._meta.sqlalchemy_session is not None:
            cls._meta.sqlalchemy_session.flush()
        return instance

    tenant = SubFactory(TenantFactory)
    principal = SubFactory(PrincipalFactory, tenant=factory.SelfAttribute("..tenant"))

    media_buy_id = Sequence(lambda n: f"mb_{n:04d}")
    tenant_id = LazyAttribute(lambda o: o.tenant.tenant_id)
    principal_id = LazyAttribute(lambda o: o.principal.principal_id)
    order_name = LazyAttribute(lambda o: f"Order {o.media_buy_id}")
    advertiser_name = LazyAttribute(lambda o: o.principal.name)
    budget = Decimal("10000.00")
    currency = "USD"
    start_date = date(2025, 1, 1)
    end_date = date(2027, 12, 31)
    status = "pending_approval"
    # This factory persists STRAIGHT to the session (sqlalchemy_session_persistence
    # = "commit"), bypassing MediaBuyRepository — so it must reproduce the writer's
    # confirmation stamp itself. The repository writes confirmed_at the instant a buy
    # reaches a seller-committed status (_stamp_confirmation_if_needed), and the
    # pinned get-media-buys-response item schema forbids status "active" with a null
    # confirmed_at. Without this, every factory-seeded confirmed buy is a row
    # production cannot produce, and the wire documents built from it validate only
    # while a read-time fallback fabricates the missing value.
    #
    # The writer NO LONGER shares this predicate. It takes an explicit
    # ``seller_committed`` flag from the caller and does not consult status at all,
    # because ``pending_creatives`` names two states — an auto-approved buy with
    # nothing supplied yet (committed) and a buy held on creative review (not) — and
    # no status-keyed rule can be right about both. This factory keeps a
    # status-derived DEFAULT because a fixture needs one, and the predicate is still
    # the best available approximation for every status except that one; it is a
    # convenience default, not a mirror of the writer.
    #
    # For the ambiguous member, pass ``confirmed_at`` explicitly: a held
    # ``pending_creatives`` row is the default (None), and the auto-approved variant
    # is seeded with an explicit timestamp.
    #
    # Two properties are deliberate and must survive edits:
    #   - CONDITIONAL rather than re-listing statuses — a second listing drifts, and
    #     an unconditional stamp would manufacture committed instants on
    #     draft/rejected/failed rows that no production path can produce.
    #   - a FRESH clock reading, like the writer's, never derived from another column
    #     (approved_at/created_at) — that derivation is the read-time fabricator, and
    #     reproducing it here would re-import it into every fixture.
    # Opt out with an explicit ``confirmed_at=None`` (an explicit kwarg beats a
    # LazyAttribute in factory_boy) when the test grades the repository's own stamp.
    confirmed_at = LazyAttribute(lambda o: datetime.now(UTC) if is_media_buy_seller_confirmed(o.status) else None)
    raw_request = LazyAttribute(
        lambda o: {
            "packages": [{"package_id": "pkg_001", "product_id": "prod_001"}],
        }
    )


class MediaPackageFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = MediaPackage
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    media_buy = SubFactory(MediaBuyFactory)
    media_buy_id = LazyAttribute(lambda o: o.media_buy.media_buy_id)
    package_id = Sequence(lambda n: f"pkg_{n:04d}")
    budget = Decimal("5000.00")
    pacing = "even"
    package_config = LazyAttribute(
        lambda o: {
            "package_id": o.package_id,
            "product_id": "prod_001",
            "budget": float(o.budget),
        }
    )


class GetMediaBuysMediaBuyFactory(factory.Factory):
    """Pydantic factory for a ``get_media_buys`` response item.

    Not an ORM factory — this builds the wire-shaped item that
    ``GetMediaBuysResponse.media_buys`` carries, so tests that grade the
    response (serialization, the protocol ``message``) don't hand-roll it.

    ``confirmed_at`` and ``revision`` are spec-REQUIRED on ``media_buys[]`` at
    AdCP 3.1.1 and the model is grounded on the library item type, so both carry
    concrete defaults here rather than being left to the caller.
    """

    class Meta:
        model = GetMediaBuysMediaBuy

    media_buy_id = Sequence(lambda n: f"mb_{n:04d}")
    status = MediaBuyStatus.active
    currency = "USD"
    total_budget = 10000.0
    confirmed_at = datetime(2025, 1, 1, tzinfo=UTC)
    revision = 1
    # LazyFunction, not a bare ``[]``: a mutable class attribute would be the SAME
    # list object on every built item.
    packages = factory.LazyFunction(list)
