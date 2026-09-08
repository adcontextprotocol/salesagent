"""Factories for the webhook models: the stored config, and a delivery's task identity."""

from __future__ import annotations

import factory
from factory import LazyAttribute, Sequence, SubFactory

from src.core.database.models import PushNotificationConfig
from src.core.webhooks.delivery import WebhookTaskContext
from tests.factories.core import TenantFactory
from tests.factories.principal import PrincipalFactory


class PushNotificationConfigFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PushNotificationConfig
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

    tenant = SubFactory(TenantFactory)
    principal = SubFactory(PrincipalFactory, tenant=factory.SelfAttribute("..tenant"))

    id = Sequence(lambda n: f"webhook_{n:04d}")
    tenant_id = LazyAttribute(lambda o: o.tenant.tenant_id)
    principal_id = LazyAttribute(lambda o: o.principal.principal_id)
    url = factory.LazyFunction(lambda: "https://example.com/webhook")
    is_active = True


class WebhookTaskContextFactory(factory.Factory):
    """A delivery's task identity — the value the sender carries to the delivery row.

    Seven fields, all required on the frozen dataclass, so every test that drives
    a sender had to spell all seven. Three files had spelled the identical
    literal, which is the copy-paste-with-variable-substitution shape the
    duplication ratchet exists to refuse (it went 72 -> 73 and failed the Quality
    Gate).

    ``sequence_number`` and ``notification_type`` default to the values a first,
    unmarked delivery carries. Both are worth overriding explicitly in any test
    that grades what reaches ``webhook_delivery_log``: they were re-derived from
    the payload downstream until the typed context travelled whole, so a test
    that leaves them at their defaults is not grading them.
    """

    class Meta:
        model = WebhookTaskContext

    task_id = "task-1"
    task_type = "create_media_buy"
    tenant_id = None
    principal_id = None
    media_buy_id = None
    sequence_number = 1
    notification_type = None
