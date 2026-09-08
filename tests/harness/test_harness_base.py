"""Meta-tests for BaseTestEnv / IntegrationEnv base contracts.

Guards the DRY-01 refactor: merging IntegrationEnv + ImplTestEnv into
a single BaseTestEnv. These tests verify that both integration and unit
modes share the same lifecycle contract.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestBaseClassContract:
    """BaseTestEnv must work in both integration (use_real_db=True) and unit modes."""

    def test_integration_env_has_mock_dict(self):
        """IntegrationEnv.__enter__ populates self.mock from EXTERNAL_PATCHES."""
        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {
                "some_dep": "os.getcwd",
            }

        env = _TestEnv()
        # Before enter, mock dict is empty
        assert env.mock == {}

        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            with patch("tests.factories.ALL_FACTORIES", []):
                with env:
                    assert "some_dep" in env.mock
                    assert isinstance(env.mock["some_dep"], MagicMock)

        # After exit, mock dict is cleared
        assert env.mock == {}

    def test_unit_env_has_mock_dict(self):
        """BaseTestEnv.__enter__ populates self.mock from EXTERNAL_PATCHES."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"some_dep": "os.getcwd"}

        env = _TestEnv()
        assert env.mock == {}

        with env:
            assert "some_dep" in env.mock
            assert isinstance(env.mock["some_dep"], MagicMock)

        assert env.mock == {}

    def test_integration_env_identity_is_lazy(self):
        """Identity is built on first access, not in __init__."""
        from tests.harness._base import IntegrationEnv

        env = IntegrationEnv(principal_id="p1", tenant_id="t1")
        assert env._identity_cache == {}
        identity = env.identity
        assert identity.principal_id == "p1"
        assert identity.tenant_id == "t1"

    def test_unit_env_identity_is_lazy(self):
        """Identity is built on first access, not in __init__."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(principal_id="p1", tenant_id="t1")
        assert env._identity_cache == {}
        identity = env.identity
        assert identity.principal_id == "p1"
        assert identity.tenant_id == "t1"

    def test_integration_env_patches_are_reversed_on_exit(self):
        """Patches are stopped in reverse order on exit."""
        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {
                "a": "os.getcwd",
                "b": "os.getpid",
            }

        env = _TestEnv()
        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            with patch("tests.factories.ALL_FACTORIES", []):
                with env:
                    # The registry holds the DB release too, so grade the PATCH
                    # entries by label — the property this test always meant,
                    # now stated precisely instead of by total count.
                    assert [label for label, _ in env._enter_cleanups if label.startswith("patch:")] == [
                        "patch:a",
                        "patch:b",
                    ]
                    # The DB registers THREE cleanups, one per acquisition, so a
                    # failure between them cannot strand the earlier resource.
                    assert [label for label, _ in env._enter_cleanups if label.startswith("db")] == [
                        "db_session",
                        "db_factories",
                    ]
                # After exit, the whole registry is cleared
                assert env._enter_cleanups == []

    def test_unit_env_patches_are_reversed_on_exit(self):
        """Patches are stopped in reverse order on exit."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd", "b": "os.getpid"}

        env = _TestEnv()
        with env:
            # A unit env binds no database, so the registry is the patches alone.
            assert [label for label, _ in env._enter_cleanups] == ["patch:a", "patch:b"]
        assert env._enter_cleanups == []

    def test_identity_respects_dry_run(self):
        """Both base classes pass dry_run to testing_context."""
        from tests.harness._base import BaseTestEnv, IntegrationEnv

        for cls in [IntegrationEnv, BaseTestEnv]:
            env = cls(dry_run=True)
            assert env.identity.testing_context.dry_run is True

    def test_configure_mocks_called_during_enter(self):
        """_configure_mocks is called after patches start."""
        from tests.harness._base import BaseTestEnv

        configure_called = []

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"dep": "os.getcwd"}

            def _configure_mocks(self):
                # Verify mocks are already available when configure is called
                configure_called.append(list(self.mock.keys()))

        with _TestEnv():
            pass

        assert configure_called == [["dep"]]

    def test_integration_env_has_use_real_db(self):
        """IntegrationEnv has use_real_db=True, BaseTestEnv has False."""
        from tests.harness._base import BaseTestEnv, IntegrationEnv

        assert BaseTestEnv.use_real_db is False
        assert IntegrationEnv.use_real_db is True

    def test_exit_cleans_up_even_when_patcher_raises(self):
        """__exit__ must stop all patchers even if one raises during stop."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {
                "a": "os.getcwd",
                "b": "os.getpid",
            }

        env = _TestEnv()
        env.__enter__()

        # Sabotage patcher "b" (last started, first stopped) so its stop() raises
        # -- but only AFTER it has really stopped. A MagicMock(side_effect=...)
        # here instead of a wrapper would mean the real stop() never runs, and
        # `os.getpid` would stay a MagicMock for the REST OF THE PROCESS. That is
        # not hypothetical: it is the leak that made `tests/unit/` unrunnable
        # under xdist. `logging.LogRecord.__init__` does
        # `self.process = os.getpid()`, so every later log record in this worker
        # carried a mock; pytest-json-report copies `dict(record.__dict__)` onto
        # the report, pytest's _report_to_json copies report.__dict__ raw onto the
        # execnet wire, and execnet cannot serialize a mock -- killing the worker
        # and truncating the session behind a summary that read "0 failed".
        # See tests/_xdist_report_safety.py for the measurement.
        #
        # The test's actual subject is unchanged: __exit__ still meets a patcher
        # whose stop() raises, and must still stop the others and clear its state.
        # The registry holds (label, cleanup) pairs, so sabotage the CLEANUP the
        # last acquisition registered rather than the patcher object itself. The
        # subject is unchanged: __exit__ still meets a cleanup that raises.
        _label, real_stop = env._enter_cleanups[-1]

        def _stop_then_raise() -> None:
            real_stop()
            raise RuntimeError("stop failed")

        env._enter_cleanups[-1] = (_label, _stop_then_raise)

        # __exit__ should still clean up patcher "a" and clear state
        # even though patcher "b" raises
        try:
            env.__exit__(None, None, None)
        except RuntimeError:
            pass  # Expected from the sabotaged patcher

        # Key assertion: mock dict and the cleanup registry must be cleared
        assert env._enter_cleanups == []
        assert env.mock == {}
        # And the patch must be genuinely unwound, not merely forgotten. Clearing
        # the bookkeeping while leaving `os.getpid` replaced is what broke the
        # unit suite under xdist -- see the comment above.
        assert isinstance(os.getpid(), int), (
            f"os.getpid is still patched ({type(os.getpid).__name__}) -- this leaks a mock into "
            f"every subsequent logging.LogRecord in this process"
        )

    def test_exception_in_test_body_still_cleans_up(self):
        """If test body raises, __exit__ still cleans up patches and mock dict."""
        from tests.harness._base import BaseTestEnv

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd", "b": "os.getpid"}

        env = _TestEnv()
        try:
            with env:
                assert len(env.mock) == 2
                raise ValueError("simulated test failure")
        except ValueError:
            pass

        # Cleanup must have happened despite the exception
        assert env.mock == {}
        assert env._enter_cleanups == []

    def test_identity_for_returns_correct_protocol(self):
        """identity_for(transport) sets the correct protocol on identity."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv(principal_id="p1", tenant_id="t1")

        impl_id = env.identity_for(Transport.IMPL)
        assert impl_id.protocol == "mcp"

        a2a_id = env.identity_for(Transport.A2A)
        assert a2a_id.protocol == "a2a"

        rest_id = env.identity_for(Transport.REST)
        assert rest_id.protocol == "rest"

        mcp_id = env.identity_for(Transport.MCP)
        assert mcp_id.protocol == "mcp"

        # All share same principal/tenant
        for ident in [impl_id, a2a_id, rest_id, mcp_id]:
            assert ident.principal_id == "p1"
            assert ident.tenant_id == "t1"

    def test_identity_for_is_cached_per_protocol(self):
        """Repeated calls with same transport return same identity object."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        id1 = env.identity_for(Transport.REST)
        id2 = env.identity_for(Transport.REST)
        assert id1 is id2

    def test_identity_backward_compat(self):
        """env.identity still works and returns IMPL protocol."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(principal_id="p1")
        assert env.identity.principal_id == "p1"
        assert env.identity.protocol == "mcp"

    def test_call_via_raises_for_unimplemented_transport(self):
        """call_via with Transport.A2A raises NotImplementedError if call_a2a not overridden."""

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        result = env.call_via(Transport.A2A)
        assert result.is_error
        assert isinstance(result.error, NotImplementedError)

    def test_call_via_mcp_raises_for_unimplemented(self):
        """call_via with Transport.MCP raises NotImplementedError if call_mcp not overridden."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        env = BaseTestEnv()
        result = env.call_via(Transport.MCP)
        assert result.is_error
        assert isinstance(result.error, NotImplementedError)

    def test_call_via_mcp_routes_through_call_mcp(self):
        """call_via(Transport.MCP) dispatches through McpDispatcher → deliver_mcp."""

        from pydantic import BaseModel

        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import DeliverResult, Transport

        class _Resp(BaseModel):
            ok: bool = True

        class _TestEnv(BaseTestEnv):
            # Test double: overrides the DELIVER point, which is what the
            # dispatchers call.
            def deliver_mcp(self, **kwargs):
                return DeliverResult(payload=_Resp(), wire_response=None)

        env = _TestEnv()
        result = env.call_via(Transport.MCP)
        assert result.is_success
        assert result.payload.ok is True
        assert result.envelope.get("transport") == "mcp"

    def test_call_via_impl_uses_call_impl(self):
        """call_via(Transport.IMPL) routes through call_impl."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import Transport

        class _TestEnv(BaseTestEnv):
            def call_impl(self, **kwargs):
                from pydantic import BaseModel

                class _Resp(BaseModel):
                    ok: bool = True

                return _Resp()

        env = _TestEnv()
        result = env.call_via(Transport.IMPL)
        assert result.is_success
        assert result.payload.ok is True

    def test_nested_integration_env_raises(self):
        """Nesting two IntegrationEnvs must raise to prevent session corruption."""
        import pytest

        from tests.harness._base import IntegrationEnv

        class _TestEnv(IntegrationEnv):
            EXTERNAL_PATCHES = {"dep": "os.getcwd"}

        with patch("src.core.database.database_session.get_engine") as mock_engine:
            mock_engine.return_value = MagicMock()
            # First env binds factories
            with patch("tests.factories.ALL_FACTORIES", [MagicMock(_meta=MagicMock(sqlalchemy_session=None))]):
                with _TestEnv():
                    # Second env should fail because factories are already bound
                    with pytest.raises(AssertionError, match="already bound"):
                        _TestEnv().__enter__()


class TestEnvMethodNamingConsistency:
    """Env methods with the same name across subclasses must have consistent semantics."""

    def test_integration_env_has_setup_default_data(self):
        """IntegrationEnv.setup_default_data creates tenant + principal via factories."""
        from tests.harness._base import IntegrationEnv

        assert hasattr(IntegrationEnv, "setup_default_data"), (
            "IntegrationEnv should have setup_default_data() to reduce boilerplate"
        )

    def test_base_env_has_run_mcp_wrapper(self):
        """BaseTestEnv exposes _run_mcp_wrapper for DRY MCP dispatch."""
        from tests.harness._base import BaseTestEnv

        assert hasattr(BaseTestEnv, "_run_mcp_wrapper"), (
            "BaseTestEnv should have _run_mcp_wrapper to reduce call_mcp duplication"
        )

    def test_creative_sync_env_has_set_run_async_result(self):
        """CreativeSyncEnv uses set_run_async_result, not set_registry_formats.

        set_registry_formats patches registry.list_all_formats (CreativeFormatsEnv).
        CreativeSyncEnv patches run_async.side_effect, which is a different mechanic.
        Using the same name is a trap for new Env authors.
        """
        from tests.harness.creative_sync import CreativeSyncEnv

        assert hasattr(CreativeSyncEnv, "set_run_async_result"), (
            "CreativeSyncEnv should have set_run_async_result (not set_registry_formats)"
        )
        assert not hasattr(CreativeSyncEnv, "set_registry_formats"), (
            "CreativeSyncEnv should NOT have set_registry_formats — "
            "that name belongs to CreativeFormatsEnv (different mechanic)"
        )


class TestIsE2EProperty:
    """BaseTestEnv.is_e2e keys on e2e_config, not database_url."""

    def test_is_e2e_true_when_e2e_config_set(self):
        """e2e_config set -> is_e2e True."""
        from tests.harness._base import BaseTestEnv
        from tests.harness.transport import E2EConfig

        env = BaseTestEnv(e2e_config=E2EConfig(base_url="http://unused", postgres_url="postgresql://x/y"))
        assert env.is_e2e is True

    def test_is_e2e_false_with_database_url_only(self):
        """database_url alone rebinds the DB but is NOT e2e mode."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv(database_url="postgresql://x/y")
        assert env.is_e2e is False

    def test_is_e2e_false_when_neither_set(self):
        """No e2e_config, no database_url -> in-process mode."""
        from tests.harness._base import BaseTestEnv

        env = BaseTestEnv()
        assert env.is_e2e is False


class TestPartialEnterUnwind:
    """A failed ``__enter__`` must leave the process exactly as it found it.

    Python does NOT call ``__exit__`` when ``__enter__`` raises, so every
    resource an env acquires before the failure point survives for the rest of
    the xdist worker unless the env releases it itself. Today's unwind guard
    protects a LEXICAL REGION -- the body of ``BaseTestEnv.__enter__`` -- rather
    than the env's acquisition SET, so a cooperative ``super().__enter__()``
    chain places every subclass's setup outside the guard by construction.

    These tests grade the acquisition set: whatever an env acquired is released,
    wherever it was acquired from. Two of them (``local_origin_mixin`` and
    ``fast_backoff_mixin``) are security oracles -- the resource they pin is an
    ENVIRONMENT VARIABLE that relaxes the outbound egress posture, and a leaked
    ``ADCP_OUTBOUND_ALLOW_PRIVATE=true`` silently disarms every later refusal
    scenario on the same worker.
    """

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _origin_is_listening(origin) -> bool:
        """Whether the local origin's socket still accepts connections.

        The honest observation of "the origin context exited": ``serve_in_thread``
        shuts the server down and closes the socket in its ``finally``, so a
        refused connect is the only proof the context really unwound. Reading a
        bookkeeping attribute would pass on an env that forgot the socket.
        """
        import socket

        try:
            with socket.create_connection((origin.host, origin.port), timeout=1.0):
                return True
        except OSError:
            return False

    @staticmethod
    def _force_release(env) -> None:
        """Best-effort hermeticity net -- a NO-OP once the unwind works.

        Runs only in a ``finally``, after every observation has been captured
        into locals, so it can never mask the leak it exists to clean up. It is
        here because a RED run of these tests genuinely leaks a live TLS server
        thread and two environment variables into the rest of the session.
        """
        from contextlib import suppress

        for name in ("_fast_backoff", "_egress_hatches", "_origin_ctx", "_ssl_cert_file"):
            resource = getattr(env, name, None)
            if resource is None:
                continue
            with suppress(Exception):
                if name == "_origin_ctx":
                    resource.__exit__(None, None, None)
                else:
                    resource.stop()
        with suppress(Exception):
            env.__exit__(None, None, None)

    # -- the base's own hooks --------------------------------------------

    def test_enter_post_failure_unwinds_everything(self):
        """A raising ``_enter_post`` releases the patches AND the pre-hook's resources.

        ``_enter_post`` is the last thing ``__enter__`` runs, so a failure there
        is the worst case: the env is fully acquired and nothing has been
        released. Everything registered -- by the base's patch loop and by a
        subclass's ``_enter_pre`` -- must come back.
        """
        import pytest

        from tests.harness._base import BaseTestEnv

        released: list[str] = []

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd", "b": "os.getpid"}

            def _enter_pre(self) -> None:
                self._guard("pre_resource", lambda: released.append("pre_resource"))

            def _enter_post(self) -> None:
                raise RuntimeError("post failed")

        env = _TestEnv()
        try:
            with pytest.raises(RuntimeError, match="post failed"):
                env.__enter__()

            assert released == ["pre_resource"], f"the pre-hook's registered cleanup was not released: {released}"
            assert env.mock == {}
            assert env._enter_cleanups == []
            # Genuinely unwound, not merely forgotten: a MagicMock left on
            # os.getpid rides into every later logging.LogRecord in this worker.
            assert isinstance(os.getpid(), int)
            assert isinstance(os.getcwd(), str)
        finally:
            self._force_release(env)

    def test_enter_pre_partial_failure_releases_earlier_resources(self):
        """A hook that fails half way through releases what it already acquired, LIFO.

        This is the shape every hand-rolled ``__enter__`` gets wrong: two
        resources acquired, the second acquisition fails, and the first is
        stranded. Registering each acquisition as it happens is what makes a
        partial failure recoverable, and reverse order is what makes the
        release valid (a later resource may depend on an earlier one).
        """
        import pytest

        from tests.harness._base import BaseTestEnv

        released: list[str] = []

        class _TestEnv(BaseTestEnv):
            EXTERNAL_PATCHES = {"a": "os.getcwd"}

            def _enter_pre(self) -> None:
                self._guard("first", lambda: released.append("first"))
                self._guard("second", lambda: released.append("second"))
                raise RuntimeError("pre failed")

        env = _TestEnv()
        try:
            with pytest.raises(RuntimeError, match="pre failed"):
                env.__enter__()

            assert released == ["second", "first"], f"expected LIFO release of both pre-hook resources, got {released}"
            assert env._enter_cleanups == []
            # The failure was in the PRE hook, so the patch loop never ran and
            # os.getcwd was never replaced -- prove it stayed real.
            assert isinstance(os.getcwd(), str)
        finally:
            self._force_release(env)

    # -- the security oracles ---------------------------------------------

    def test_local_origin_mixin_unwinds_on_base_failure(self):
        """A base failure must not leave the egress hatch open for the whole worker.

        ``LocalOriginMixin`` acquires three resources -- the ``SSL_CERT_FILE``
        patch, the running TLS origin, and ``ADCP_OUTBOUND_ALLOW_PRIVATE=true``
        -- and only then enters the base. When the base fails, Python skips
        ``__exit__`` and all three survive. The env var is the one that matters:
        every later scenario on this worker that grades a private-address
        refusal is then graded with the hatch WIDE OPEN, and passes for the
        wrong reason.
        """
        import pytest

        from tests.harness._base import IntegrationEnv
        from tests.harness._mixins import LocalOriginMixin
        from tests.helpers.egress_hatches import ALLOW_PRIVATE_ENV

        class _OriginEnv(LocalOriginMixin, IntegrationEnv):
            EXTERNAL_PATCHES: dict[str, str] = {}

        env = _OriginEnv()
        # patch.dict with no changes snapshots os.environ and restores it
        # wholesale on exit -- including deletions -- so a RED run of this test
        # cannot leak the hatch into the rest of the session.
        with patch.dict(os.environ, {}):
            os.environ.pop("SSL_CERT_FILE", None)
            os.environ.pop(ALLOW_PRIVATE_ENV, None)
            try:
                with (
                    patch(
                        "src.core.database.database_session.get_engine",
                        side_effect=RuntimeError("engine boom"),
                    ),
                    patch("tests.factories.ALL_FACTORIES", []),
                    pytest.raises(RuntimeError, match="engine boom"),
                ):
                    env.__enter__()

                leaked_ssl_cert_file = os.environ.get("SSL_CERT_FILE")
                leaked_allow_private = os.environ.get(ALLOW_PRIVATE_ENV)
                origin = getattr(env, "_origin", None)
                origin_still_listening = origin is not None and self._origin_is_listening(origin)
            finally:
                self._force_release(env)

            assert leaked_allow_private is None, (
                f"{ALLOW_PRIVATE_ENV}={leaked_allow_private!r} survived a failed __enter__ -- "
                f"the private-egress hatch is now open for the rest of this worker, and every "
                f"later scenario grading a private-address refusal is disarmed"
            )
            assert leaked_ssl_cert_file is None, (
                f"SSL_CERT_FILE={leaked_ssl_cert_file!r} survived a failed __enter__ -- "
                f"later outbound work in this worker trusts the test CA"
            )
            assert origin_still_listening is False, (
                "the local TLS origin was still accepting connections after a failed "
                "__enter__ -- its context was never exited"
            )

    def test_fast_backoff_mixin_unwinds_on_failed_enter(self):
        """A failed enter must not leave production's retry backoff shortened.

        ``OrderApprovalWebhookEnv`` shortens the egress seam's retry base to
        10ms so its retry cases do not cost wall time. That override is read by
        the seam at CALL time from the environment, so a copy stranded by a
        failed enter silently rescales BR-RULE-029's 1s/2s/4s schedule for every
        later test in this worker -- including the ones that grade the schedule.
        """
        import pytest

        from src.core.security.egress.attempts import _BACKOFF_BASE_ENV
        from tests.harness.order_approval_webhook import OrderApprovalWebhookEnv

        env = OrderApprovalWebhookEnv()
        with patch.dict(os.environ, {}):
            os.environ.pop(_BACKOFF_BASE_ENV, None)
            try:
                with (
                    patch(
                        "src.core.database.database_session.get_engine",
                        side_effect=RuntimeError("engine boom"),
                    ),
                    patch("tests.factories.ALL_FACTORIES", []),
                    pytest.raises(RuntimeError, match="engine boom"),
                ):
                    env.__enter__()

                leaked_backoff = os.environ.get(_BACKOFF_BASE_ENV)
            finally:
                self._force_release(env)

            assert leaked_backoff is None, (
                f"{_BACKOFF_BASE_ENV}={leaked_backoff!r} survived a failed __enter__ -- "
                f"the egress seam's retry schedule stays shortened for the rest of this worker"
            )

        # The override belongs to one owner, composed into this env -- not to a
        # hand-rolled __enter__/__exit__ pair that test_harness_envs_define_no_enter_exit
        # forbids.
        from tests.harness.egress import FastOutboundBackoffMixin

        assert FastOutboundBackoffMixin in type(env).__mro__, (
            "OrderApprovalWebhookEnv must get its fast backoff from FastOutboundBackoffMixin"
        )

    def test_admin_env_failed_enter_releases_client(self):
        """``AdminAccountEnv`` acquires a Flask client, then does DB work that can fail.

        It is not a ``BaseTestEnv`` and keeps its own ``__enter__``; that makes
        it the one place the guarantee is hand-rolled rather than structural, so
        it needs its own oracle. ``_setup_integration`` opens the test client
        (an entered context manager) and ``_ensure_tenant`` then hits the
        database -- a failure there strands the client.
        """
        import pytest

        from tests.harness.admin_accounts import AdminAccountEnv

        env = AdminAccountEnv(mode="integration")
        try:
            with (
                patch.object(AdminAccountEnv, "_ensure_tenant", side_effect=RuntimeError("tenant boom")),
                pytest.raises(RuntimeError, match="tenant boom"),
            ):
                env.__enter__()

            assert env._flask_client is None, (
                "the Flask test client survived a failed __enter__ -- its context was never exited"
            )
        finally:
            from contextlib import suppress

            with suppress(Exception):
                env.__exit__(None, None, None)

    def test_fast_backoff_is_observed_at_the_seam(self):
        """The mixin's override reaches production's schedule, end to end.

        Grades mixin -> environment -> ``attempts._backoff_seconds`` rather than
        the env var alone: an override the seam does not actually read is an
        override that buys nothing. No wall clock is involved -- the jitter draw
        is pinned to 0 and the schedule is read as a NUMBER.
        """
        from src.core.security.egress import attempts
        from tests.harness.egress import FastOutboundBackoffMixin
        from tests.harness.order_approval_webhook import OrderApprovalWebhookEnv

        assert FastOutboundBackoffMixin in OrderApprovalWebhookEnv.__mro__, (
            "OrderApprovalWebhookEnv must compose FastOutboundBackoffMixin"
        )

        with (
            patch("src.core.database.database_session.get_engine") as mock_engine,
            patch("tests.factories.ALL_FACTORIES", []),
        ):
            mock_engine.return_value = MagicMock()
            with OrderApprovalWebhookEnv() as env:
                assert env is not None
                with patch("src.core.security.egress.attempts.random.uniform", return_value=0.0):
                    assert attempts._backoff_seconds(1) == 0.01
                    # The shape is NOT overridden -- only the base. Doubling
                    # still holds, which is what makes the override safe.
                    assert attempts._backoff_seconds(2) == 0.02


class TestHarnessLifecycleRoleDeclaration:
    """``__enter__``/``__exit__`` have exactly two declared homes in the harness.

    A frozen ROLE DECLARATION, not a violations allowlist: the set below names
    where the context-manager protocol is IMPLEMENTED, and it can only shrink.
    Any other env that grows one is acquiring resources outside
    ``BaseTestEnv``'s unwind guard by construction -- which is the defect the
    ``_enter_pre``/``_enter_post`` hooks exist to make unnecessary.
    """

    LIFECYCLE_METHODS = frozenset({"__enter__", "__exit__", "__aenter__", "__aexit__"})

    # (file name, class name) -- the only two homes.
    #   _base.py / BaseTestEnv       -- owns the ONE enter/exit for every env
    #   admin_accounts.py / AdminAccountEnv -- not a BaseTestEnv (own Flask /
    #       requests transports); a named, tested exception whose interior is
    #       still hand-guarded (see test_admin_env_failed_enter_releases_client)
    DECLARED_HOMES = frozenset(
        {
            ("_base.py", "BaseTestEnv"),
            ("admin_accounts.py", "AdminAccountEnv"),
        }
    )

    def test_harness_envs_define_no_enter_exit(self):
        """No harness module outside the two declared homes implements the protocol."""
        import ast
        import pathlib

        harness_root = pathlib.Path(__file__).parent
        # rglob, not glob: a future env in a subpackage must not escape by
        # sitting one directory down.
        sources = [p for p in sorted(harness_root.rglob("*.py")) if not p.name.startswith("test_")]
        assert sources, f"no harness modules found under {harness_root}"

        found: set[tuple[str, str, str]] = set()
        for path in sources:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name in self.LIFECYCLE_METHODS:
                        found.add((path.name, node.name, item.name))

        # The async pair is covered too: freezing only the sync pair leaves a
        # silent hole on the day someone writes an async env.
        async_defs = sorted(f for f in found if f[2] in {"__aenter__", "__aexit__"})
        assert async_defs == [], (
            f"async context-manager methods in tests/harness/: {async_defs}. "
            f"Acquire through _enter_pre / _enter_post instead."
        )

        homes = {(file_name, class_name) for file_name, class_name, _ in found}
        undeclared = sorted(homes - self.DECLARED_HOMES)
        assert undeclared == [], (
            f"these harness classes implement __enter__/__exit__ outside the two declared homes: "
            f"{undeclared}. Subclass setup belongs in _enter_pre / _enter_post, whose bodies run "
            f"inside BaseTestEnv.__enter__'s unwind guard; a hand-rolled __enter__ acquires "
            f"resources the guard cannot release."
        )
        missing = sorted(self.DECLARED_HOMES - homes)
        assert missing == [], (
            f"declared lifecycle homes no longer implement the protocol: {missing}. "
            f"The set may shrink -- but shrink it here, deliberately."
        )
