"""PushNotificationConfig repository — tenant-scoped data access.

Core invariant: every query includes both ``tenant_id`` AND ``principal_id``
in the WHERE clause. PushNotificationConfig rows belong to a single
(tenant, principal) pair; cross-principal lookups are not exposed.

Write methods add objects to the session but never commit — the Unit of Work
(``PushNotificationConfigUoW``) handles commit/rollback at the boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from src.core.database.models import PushNotificationConfig
from src.core.webhooks.registration import ValidatedWebhookRegistration


class PushNotificationConfigRepository:
    """Tenant + principal scoped access for PushNotificationConfig.

    All queries filter by ``tenant_id`` automatically. Principal scope is
    required on every method — there is no cross-principal lookup.

    Args:
        session: SQLAlchemy session (caller manages lifecycle).
        tenant_id: Tenant scope for all queries.
    """

    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def _scoped(self, principal_id: str, *, active_only: bool) -> Select[tuple[PushNotificationConfig]]:
        """The (tenant, principal) scope every lookup here shares, in ONE place.

        This module's core invariant -- every query is scoped by tenant AND
        principal -- was previously enforced by prose repeated per method and by
        each method retyping the same two predicates. A third lookup would have
        made it a third copy, and the pair is exactly the thing that must not be
        forgotten once. Callers append their own single predicate.
        """
        stmt = select(PushNotificationConfig).where(
            PushNotificationConfig.tenant_id == self._tenant_id,
            PushNotificationConfig.principal_id == principal_id,
        )
        if active_only:
            stmt = stmt.where(PushNotificationConfig.is_active.is_(True))
        return stmt

    def get_by_id(
        self,
        config_id: str,
        principal_id: str,
        *,
        active_only: bool = True,
    ) -> PushNotificationConfig | None:
        """Get a single config by ID within the (tenant, principal) scope.

        Args:
            config_id: The config's primary-key id.
            principal_id: Principal scope filter.
            active_only: If True (default), only return configs where
                ``is_active`` is True. Pass False to include soft-deleted rows
                (e.g. for an upsert that needs to re-activate them).
        """
        stmt = self._scoped(principal_id, active_only=active_only).where(PushNotificationConfig.id == config_id)
        return self._session.scalars(stmt).first()

    def find_by_url(
        self,
        principal_id: str,
        url: str,
        *,
        active_only: bool = True,
    ) -> PushNotificationConfig | None:
        """Find a config by its URL within the (tenant, principal) scope.

        The duplicate check at registration used to hand-write this query in the
        admin route and omit ``is_active``, so a URL that had been deactivated
        still read as "already registered" -- the operator could not re-register
        it, and (before the same change) could not delete or re-enable it either.

        ``active_only=False`` is what the registration path passes: it needs to
        SEE the soft-deleted row so it can reuse that row's id and let
        :meth:`upsert` reactivate it, rather than inserting a second row for the
        same (principal, url) and leaving the first as debris.
        """
        stmt = self._scoped(principal_id, active_only=active_only).where(PushNotificationConfig.url == url)
        return self._session.scalars(stmt).first()

    def list_active_by_principal(self, principal_id: str) -> list[PushNotificationConfig]:
        """Return all active configs for a principal within this tenant."""
        return list(self._session.scalars(self._scoped(principal_id, active_only=True)).all())

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert(
        self,
        registration: ValidatedWebhookRegistration,
        *,
        config_id: str,
        principal_id: str,
        validation_token: str | None = None,
        session_id: str | None = None,
        protocol: str | None = None,
    ) -> tuple[PushNotificationConfig, bool]:
        """Insert or update a config within the (tenant, principal) scope.

        Takes the VALUE, not three loose strings. ``ValidatedWebhookRegistration``
        is the receipt that both ingest preconditions ran — the registration SSRF
        gate on the URL half and the pinned ``Authentication`` model built inside ``_accept`` on the
        credential half — so
        persisting a config that skipped a gate no longer type-checks.

        That is why this module no longer re-validates the URL. The former
        "defense-in-depth" check here existed because the receipt evaporated at
        this boundary: a caller that had never gated looked exactly like one that
        had. It also could not produce a good error — the repository cannot know
        the request path, so ``error.field`` was lost. SEND time is not this
        module's business either: every outbound request goes through the egress
        seam (``src.core.security.outbound_http``), which re-resolves and re-judges
        the URL when it is actually dialled.

        ``validation_token`` stays an explicit kwarg rather than a value field: it
        is sender-side ``X-Webhook-Token`` material, deliberately outside the auth
        resolver, and only the A2A ``setTaskPushNotificationConfig`` path stores one.

        Returns:
            (config, created): ``created`` is True if a new row was inserted,
            False if an existing row was updated (or reactivated).
        """
        columns = registration.to_columns()

        existing = self.get_by_id(config_id, principal_id, active_only=False)
        now = datetime.now(UTC)

        if existing is not None:
            existing.url = columns["url"]
            existing.authentication_type = columns["authentication_type"]
            existing.authentication_token = columns["authentication_token"]
            existing.validation_token = validation_token
            existing.session_id = session_id
            existing.protocol = protocol
            existing.updated_at = now
            existing.is_active = True
            self._session.flush()
            return existing, False

        config = PushNotificationConfig(
            id=config_id,
            tenant_id=self._tenant_id,
            principal_id=principal_id,
            session_id=session_id,
            url=columns["url"],
            authentication_type=columns["authentication_type"],
            authentication_token=columns["authentication_token"],
            validation_token=validation_token,
            protocol=protocol,
            is_active=True,
        )
        self._session.add(config)
        self._session.flush()
        return config, True

    def soft_delete(self, config_id: str, principal_id: str) -> bool:
        """Mark a config inactive within the (tenant, principal) scope.

        Finds the row regardless of its current ``is_active`` value and
        sets ``is_active=False``. Idempotent — calling on an already-inactive
        row still returns True.

        Returns:
            True if a matching row was found (and is now inactive),
            False if no row with that ``(tenant, principal, id)`` exists.
        """
        config = self.get_by_id(config_id, principal_id, active_only=False)
        if config is None:
            return False
        config.is_active = False
        config.updated_at = datetime.now(UTC)
        self._session.flush()
        return True
