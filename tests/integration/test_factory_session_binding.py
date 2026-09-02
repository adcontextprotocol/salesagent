"""One session-binding discipline for factories used outside the harness.

``tests/utils/database_helpers.bind_factories_to_session`` has the right shape — a
context manager that SAVES the previous binding and RESTORES it on exit. It was
private, so tests needing factories outside an ``IntegrationEnv`` hand-rolled a
bind-then-None loop instead; both sites now take the public ``bound_factory_session``
fixture (``test_media_buy_revision_confirmation.py`` and
``test_order_approval_background.py``).
Bind-then-None is not merely a duplicate: used outside any env it happens to be
equivalent (the previous binding IS None), but used inside one it clobbers the env's
session to None mid-env — a failure ``IntegrationEnv``'s entry assertion cannot catch,
because by then the env is already entered. Save/restore is the discipline for
anything not guaranteed to be outermost, which is why the helper becomes public and
gets a shared fixture.

The two mechanisms stay complementary, not redundant: ``_base.py:1129-1133`` asserts
factories are unbound on env ENTRY (the don't-nest tripwire) and ``:1191-1192``
hard-unbinds on exit; the helper governs the non-env case.

The fixture OWNS its session — it creates it, binds it, and closes it — because that
is what the hand-rolled version it replaces did (``SASession(bind=get_engine())`` …
``session.close()``). A fixture that only bound a session someone else owned would
leave every caller re-writing the create/close half.

GH #1941 (review finding F20)
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from src.core.database.database_session import get_engine
from tests.factories import ALL_FACTORIES

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def unbound_factories_after_test():
    """Leave the global factory bindings as this suite found them: unbound.

    These tests deliberately write ``_meta.sqlalchemy_session`` to prove save/restore
    semantics, and a leaked binding would trip the next ``IntegrationEnv.__enter__``
    assertion in an unrelated test.
    """
    yield
    for factory in ALL_FACTORIES:
        factory._meta.sqlalchemy_session = None


class TestBindFactoriesToSessionIsPublicAndRestores:
    """The helper is importable under a public name and restores what it found."""

    def test_previous_binding_is_restored_not_nulled(self, integration_db, unbound_factories_after_test):
        """RED before the lane: the public name does not exist yet.

        The assertion that matters is the last one — a bind-then-None implementation
        binds and unbinds just as well, and only differs when there WAS a previous
        binding to preserve. That is the case this pins.
        """
        from tests.utils.database_helpers import bind_factories_to_session

        previous = SASession(bind=get_engine())
        inner = SASession(bind=get_engine())
        try:
            for factory in ALL_FACTORIES:
                factory._meta.sqlalchemy_session = previous

            with bind_factories_to_session(inner):
                assert all(f._meta.sqlalchemy_session is inner for f in ALL_FACTORIES), (
                    "helper did not bind every factory to the given session"
                )

            assert all(f._meta.sqlalchemy_session is previous for f in ALL_FACTORIES), (
                "helper unbound the factories instead of restoring the previous session — "
                "bind-then-None clobbers an enclosing IntegrationEnv's binding mid-env"
            )
        finally:
            inner.close()
            previous.close()

    def test_binding_is_restored_even_when_the_body_raises(self, integration_db, unbound_factories_after_test):
        """A failing test body must not leak a binding into the next env."""
        from tests.utils.database_helpers import bind_factories_to_session

        session = SASession(bind=get_engine())
        try:
            with pytest.raises(RuntimeError), bind_factories_to_session(session):
                raise RuntimeError("boom")

            assert all(f._meta.sqlalchemy_session is None for f in ALL_FACTORIES)
        finally:
            session.close()


class TestSharedBoundFactorySessionFixture:
    """``bound_factory_session`` — the shared replacement for hand-rolled ``_factory_session``."""

    def test_fixture_binds_every_factory_to_the_session_it_yields(self, integration_db, bound_factory_session):
        """RED before the lane: no such fixture (pytest errors with "fixture not found").

        Also pins that the yielded session is a real, usable, engine-bound session —
        the fixture creates it rather than handing back one the caller must open.
        """
        assert isinstance(bound_factory_session, SASession)
        assert bound_factory_session.get_bind() is get_engine()
        assert all(f._meta.sqlalchemy_session is bound_factory_session for f in ALL_FACTORIES), (
            "some factories are not bound to the session the fixture yielded"
        )

        from tests.factories import MediaBuyFactory, TenantFactory

        # Explicit ids: the factory Sequences restart per process, so bare defaults
        # collide with rows an earlier test in the same database already inserted.
        # The assertion here is about the BINDING, not about id generation.
        tenant = TenantFactory(tenant_id="tenant_bound_fixture_probe")
        media_buy = MediaBuyFactory(tenant=tenant, media_buy_id="mb_bound_fixture_probe")
        assert bound_factory_session.get(type(media_buy), media_buy.media_buy_id) is media_buy

    def test_fixture_creates_binds_restores_and_closes(self, request, integration_db, unbound_factories_after_test):
        """The whole lifecycle, driven deterministically rather than across two tests.

        Requesting the fixture normally can only observe its setup half; teardown runs
        after the test body. Driving the generator directly is what lets the restore and
        the close be graded — and both halves are the point: the fixture replaces code
        that owned its session, so it must close what it opened, and it must restore the
        binding it found rather than nulling it.
        """
        from tests.integration import conftest as integration_conftest

        fixture_fn = integration_conftest.bound_factory_session.__wrapped__
        arguments = [request.getfixturevalue(name) for name in inspect.signature(fixture_fn).parameters]

        previous = SASession(bind=get_engine())
        try:
            for factory in ALL_FACTORIES:
                factory._meta.sqlalchemy_session = previous

            generator = fixture_fn(*arguments)
            session = next(generator)
            assert session is not previous, "fixture yielded the caller's session instead of creating its own"
            assert all(f._meta.sqlalchemy_session is session for f in ALL_FACTORIES)

            # Open a transaction so "closed" is observable: an untouched Session has no
            # transaction either, which would make the check below pass vacuously.
            session.execute(text("SELECT 1"))
            assert session.get_transaction() is not None

            with pytest.raises(StopIteration):
                next(generator)

            assert session.get_transaction() is None, "fixture did not close the session it created"
            assert all(f._meta.sqlalchemy_session is previous for f in ALL_FACTORIES), (
                "fixture unbound the factories instead of restoring the previous binding"
            )
        finally:
            previous.close()


class TestFixtureBindsToThePerTestEngine:
    """The fixture must resolve the engine AFTER integration_db has swapped it.

    ``integration_db`` creates a per-test database and rebinds the global engine.
    ``bound_factory_session`` calls ``get_engine()``, so if it does not depend on
    ``integration_db`` the ordering is decided by whichever fixture pytest happens to
    instantiate first — and pytest instantiates same-scope fixtures in ARGUMENT ORDER.

    The failure that buys is silent: factories bound to the pre-swap engine write to
    the shared database while the test reads the per-test one, and nothing raises.
    Declaring the dependency is what makes the order a fact rather than a convention,
    so this pins it.
    """

    def test_session_is_bound_to_the_engine_integration_db_installed(self, bound_factory_session, integration_db):
        """Argument order is deliberately the hazardous one.

        Listed this way round, a ``bound_factory_session`` that did not declare
        ``integration_db`` would be built first, against the engine in place BEFORE
        the per-test database was installed. Declaring the dependency reorders it
        regardless of how a caller writes the signature, which is the whole point —
        a grader that only passed in the safe order would grade nothing.
        """
        from src.core.database.database_session import get_engine

        current = get_engine()
        assert bound_factory_session.get_bind() is current, (
            "the fixture's session is bound to a different engine than the one integration_db "
            "installed — factories would write to the wrong database with nothing failing"
        )

        from tests.factories import ALL_FACTORIES

        assert all(f._meta.sqlalchemy_session is bound_factory_session for f in ALL_FACTORIES), (
            "factories are not bound to the session bound to the per-test engine"
        )
