"""CreativeSyncEnv — integration test environment for _sync_creatives_impl.

Patches: creative agent registry, run_async_in_sync_context, notifications, audit, config.
Real: get_db_session, CreativeRepository, all validation/processing (all hit real DB).

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant, principal_id="p1")

            response = env.call_impl(creatives=[{
                "creative_id": "c1",
                "name": "Test Creative",
                "format_id": {"id": "display_300x250", "agent_url": "..."},
                "media_url": "https://example.com/img.png",
            }])
            assert len(response.results) == 1

Generative creative usage::

    with CreativeSyncEnv() as env:
        env.setup_default_data()
        fmt = env.setup_generative_build(
            format_id="gen_banner",
            build_result={"status": "draft", "context_id": "ctx-1", "creative_output": {}},
        )
        result = env.call_via(transport, creatives=[{
            "creative_id": "c1",
            "name": "Gen Creative",
            "format_id": fmt,
            "assets": build_assets(
                text_spec("message", content="Build me a banner")
            ),
        }])

Available mocks via env.mock:
    "registry"            -- get_creative_agent_registry (lazy import in _sync.py)
    "run_async"           -- run_async_in_sync_context (module-level import in _sync.py)
    "send_notifications"  -- _send_creative_notifications (from _workflow)
    "audit_log"           -- _audit_log_sync (from _workflow)
    "config"              -- get_config (lazy import in _processing.py)
    "ai_review_executor"  -- _ai_review_executor (lazy import in _processing.py, ai-powered arm)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from adcp.types import AccountReference

from src.core.schemas import SyncCreativesRequest, SyncCreativesResponse
from tests.harness._base import IntegrationEnv
from tests.harness._realize import e2e_unsupported, realize_e2e
from tests.harness.egress import EgressHatchMixin
from tests.harness.transport import DeliverResult
from tests.helpers.creative_test_helpers import creative_payload

# Kwargs ``IntegrationEnv._run_a2a_handler`` consumes itself (identity mock, protocol-level
# push config, request model) rather than forwarding as skill parameters — see
# tests/harness/_base.py. They must reach it untouched.
_A2A_RESERVED_KWARGS = frozenset({"identity", "a2a_push_notification_config", "req"})


@dataclass(frozen=True)
class CommittedSyncEffects:
    """What a SEPARATE database connection can see for one tenant right now.

    Every field is read over a connection the sync's transaction does not own,
    which is the only way to tell "written and committed" apart from "written
    and about to be rolled back" -- the question a dry_run preview asks, and the
    question an escaping effect (Slack) asks about the rows it names.
    """

    #: workflow_steps rows, tenant-scoped through their Context. Sorted.
    workflow_step_ids: list[str]
    #: object_workflow_mapping.object_id for those steps. Sorted.
    workflow_object_ids: list[str]
    #: contexts rows for the tenant. Sorted.
    context_ids: list[str]
    #: creative_assignments rows for the tenant.
    assignment_count: int
    #: creatives sitting at ``pending_review`` for the tenant+principal. Sorted.
    creatives_awaiting_approval: list[str]


@dataclass(frozen=True)
class CommittedAIReview:
    """The AI-review VERDICT a SEPARATE connection can see for one creative.

    The sibling oracle to :class:`CommittedSyncEffects`, for the one effect the
    sync itself never writes: the background reviewer opens its own unit of
    work, commits a decision onto the creative, and only then fires Slack and
    the push webhook. Grading that a verdict was SUBMITTED says nothing about
    whether one was ever REACHED, so this reads the row the reviewer is
    supposed to have written -- ``verdict is None`` means it never did.
    """

    #: ``creatives.status`` for the row, or None when there is no row at all.
    status: str | None
    #: ``creatives.data["ai_review"]``, or None when no verdict was committed.
    verdict: dict[str, Any] | None
    #: ``creatives.data["ai_review_error"]``, or None when the reviewer did not
    #: fail. Present here because the reviewer's own ``except Exception`` handler
    #: REVERTS a committed verdict's status to ``pending_review`` and writes this
    #: key, WITHOUT clearing ``ai_review``. A test that checks only ``verdict``
    #: therefore reads "approved" from a review that actually blew up
    #: -- so the absence of this key is part of the grade.
    error: dict[str, Any] | None = None


def creative_fingerprint(creative: Any) -> tuple[str, str]:
    """The per-row state comparison every creative-effect oracle uses.

    ONE definition, because two callers compare the same thing for two different
    reasons: the dry_run oracle compares the tenant's library before and after a
    preview, and the post-commit oracle compares what an escaping effect could
    SEE against what the sync actually committed. ``status`` alone is too weak
    for either -- the update arm re-writes ``data`` while leaving ``status`` at
    ``pending_review``, so a status-only fingerprint reads a stale row and a
    freshly-updated one as identical.
    """
    return (creative.status, repr(creative.data))


#: Distinguishes "the caller stated request_hash=None" (meaning: no transmission, so keep
#: the at-most-once machinery out) from "the caller said nothing", which derives the hash as
#: a transport wrapper would. A plain None default would collapse the two.
_UNSET = object()


class CreativeSyncEnv(EgressHatchMixin, IntegrationEnv):
    """Integration test environment for _sync_creatives_impl.

    Only mocks external services (creative agent registry, async runner,
    notifications, audit logging). Everything else is real:
    - Real get_db_session -> real DB queries
    - Real CreativeRepository -> real DB writes
    - Real validation/processing -> real business logic
    """

    EXTERNAL_PATCHES = {
        "registry": "src.core.creative_agent_registry.get_creative_agent_registry",
        "run_async": "src.core.tools.creatives._sync.run_async_in_sync_context",
        "send_notifications": "src.core.tools.creatives._sync._send_creative_notifications",
        "audit_log": "src.core.tools.creatives._sync._audit_log_sync",
        "config": "src.core.config.get_config",
        # The ai-powered arm of _processing.py hands a job to a real
        # ThreadPoolExecutor that opens its OWN AdminCreativeUoW, COMMITS a review
        # verdict, and then fires Slack + the push webhook
        # (src/admin/blueprints/creatives.py). That is an effect which escapes the
        # sync transaction entirely, so it belongs in this env's "only mocks
        # external services" set alongside send_notifications — and mocking it is
        # what makes "no AI-review side effect" an observable rather than a race
        # against a background thread. Per-test patches of the same target (e.g.
        # tests/integration/test_creative_sync_transport.py TestAIReviewTrigger)
        # nest inside this one and still win.
        "ai_review_executor": "src.admin.blueprints.creatives._ai_review_executor",
    }
    #: The EXTERNAL_PATCHES key above, bound to a name so the mock lookup and the base's
    #: ``patch:<key>`` cleanup label cannot drift from it: a rename that reached only one
    #: of them would turn "stop the executor patch" into a silent no-op.
    _AI_REVIEW_PATCH_NAME = "ai_review_executor"
    DEFAULT_AGENT_URL = "https://creative.test.example.com"
    REST_ENDPOINT = "/api/v1/creatives/sync"

    #: {creative_id: fingerprint-or-None} as seen by an INDEPENDENT connection at
    #: the instant the sync handed that creative to the AI-review executor. The
    #: job the sync submits opens its own session, so this is exactly what that
    #: job would read -- and ``None`` means it would find no row at all.
    ai_review_commit_observations: dict[str, tuple[str, str] | None]

    #: ``(step_ids, mapped object_ids)`` an INDEPENDENT connection can see at the
    #: instant the sync fired its Slack notification, or ``None`` while no
    #: observer is installed. Slack is an escaping effect: it names workflow
    #: steps a human is expected to open, so what a SEPARATE connection can see
    #: at that instant is exactly what the person following the link will find.
    workflow_rows_at_notification: tuple[list[str], list[str]] | None

    #: ``creative_assignments`` rows committed for the tenant at that same
    #: instant. Ordering between the notification and the assignment stage is
    #: only observable as a count taken AT the notification, never after it.
    assignment_count_at_notification: int | None

    def _configure_mocks(self) -> None:
        """Set up happy-path defaults for external mocks."""
        # Registry: return a mock that supports list_all_formats() + get_format()
        mock_registry = MagicMock()
        mock_registry.list_all_formats.return_value = []
        # get_format must return a coroutine (consumed by run_async_in_sync_context
        # in _validation.py). Return a truthy value to pass format existence check.
        mock_registry.get_format = AsyncMock(return_value={"id": "display_300x250", "name": "Display 300x250"})
        # build_creative and preview_creative must be AsyncMock because
        # _processing.py uses the REAL run_async_in_sync_context (not patched there).
        mock_registry.build_creative = AsyncMock(return_value={})
        mock_registry.preview_creative = AsyncMock(return_value={})
        self.mock["registry"].return_value = mock_registry

        # run_async: execute the coroutine synchronously (return empty list)
        self.mock["run_async"].side_effect = lambda coro: []

        # Notifications: no-op. The ordering observer is NOT installed here --
        # it is a side_effect, and installing it by default would make every
        # existing "was Slack called" scenario pay for two extra pooled-connection
        # reads. observe_effects_at_notification() opts a scenario in, and returns
        # None so those "was it called" assertions keep reading the same value.
        self.mock["send_notifications"].return_value = None
        self.workflow_rows_at_notification = None
        self.assignment_count_at_notification = None

        # Audit log: no-op
        self.mock["audit_log"].return_value = None

        # AI review executor: accept the submit, RECORD what a separate database
        # connection can see at that instant, and hand back an inert future.
        # _processing.py stores the returned future in _ai_review_tasks; nothing
        # in the sync path reads it back.
        self.ai_review_commit_observations = {}
        self.mock[self._AI_REVIEW_PATCH_NAME].submit.side_effect = self._observe_at_ai_review_submit

        # Config: default with no gemini key (safe for static creatives)
        mock_config = MagicMock()
        mock_config.gemini_api_key = None
        self.mock["config"].return_value = mock_config

    def _observe_at_ai_review_submit(self, *args: Any, **kwargs: Any) -> MagicMock:
        """Stand in for ``_ai_review_executor.submit`` and record DB visibility.

        The submitted job opens its OWN session (``AdminCreativeUoW`` in
        src/admin/blueprints/creatives.py), so the only state it can ever read is
        COMMITTED state. Reading that here, from a connection the sync's
        transaction does not own, is what turns "the effect was deferred until
        its transaction committed" into an observable rather than an inference:
        a flush leaves the row invisible to this read, a commit does not.
        """
        self.ai_review_commit_observations[kwargs["creative_id"]] = self._committed_creative_fingerprint(
            creative_id=kwargs["creative_id"],
            tenant_id=kwargs["tenant_id"],
            principal_id=kwargs["principal_name"],
        )
        return MagicMock()

    @staticmethod
    def _committed_creative_fingerprint(
        *, creative_id: str, tenant_id: str, principal_id: str
    ) -> tuple[str, str] | None:
        """The creative as a SEPARATE connection sees it, or None if not committed.

        Deliberately not ``get_db_session()``: that returns the thread's SCOPED
        session, which inside a request IS the transaction under test -- it would
        see the caller's own uncommitted writes and grade nothing. Binding a new
        Session to the engine takes a second pooled connection, which is the same
        isolation the background job gets.
        """
        from sqlalchemy.orm import Session as SQLAlchemySession

        from src.core.database.database_session import get_engine
        from src.core.database.repositories.creative import CreativeRepository

        with SQLAlchemySession(bind=get_engine()) as independent_session:
            row = CreativeRepository(independent_session, tenant_id).get_by_id(creative_id, principal_id)
            return None if row is None else creative_fingerprint(row)

    # --- the workflow-step / assignment oracle (GH #2002) ---
    #
    # Same independent-connection SHAPE as _committed_creative_fingerprint above,
    # over the rows _create_sync_workflow_steps writes. It exists because nothing
    # in this env could observe those rows: get_workflow_steps() reads the SCOPED
    # session, which inside a request IS the transaction under test -- it sees the
    # request's own un-committed writes, so it cannot tell "written and committed"
    # from "written and about to be rolled back", which is the entire question a
    # preview asks.

    @staticmethod
    def _independent_session() -> Any:
        """A Session on its OWN pooled connection -- never the scoped one."""
        from sqlalchemy.orm import Session as SQLAlchemySession

        from src.core.database.database_session import get_engine

        return SQLAlchemySession(bind=get_engine())

    @staticmethod
    def _committed_workflow_rows(*, tenant_id: str) -> tuple[list[str], list[str]]:
        """``(step_ids, mapped object_ids)`` COMMITTED for *tenant_id*, both sorted.

        WorkflowStep carries no tenant_id column, so tenant scoping goes through
        its Context relationship -- the same join BaseTestEnv.get_workflow_steps
        uses, moved onto an independent connection.
        """
        from sqlalchemy import select

        from src.core.database.models import Context, ObjectWorkflowMapping, WorkflowStep

        with CreativeSyncEnv._independent_session() as session:
            step_ids = sorted(
                session.scalars(
                    select(WorkflowStep.step_id).join(WorkflowStep.context).where(Context.tenant_id == tenant_id)
                ).all()
            )
            object_ids = (
                sorted(
                    session.scalars(
                        select(ObjectWorkflowMapping.object_id).where(ObjectWorkflowMapping.step_id.in_(step_ids))
                    ).all()
                )
                if step_ids
                else []
            )
            return step_ids, object_ids

    @staticmethod
    def _committed_context_ids(*, tenant_id: str) -> list[str]:
        """Context rows COMMITTED for *tenant_id*, sorted.

        The third row the write path creates. Graded separately from the steps
        because a rollback that reached the steps but left the context behind
        would still be a preview that persisted something.
        """
        from sqlalchemy import select

        from src.core.database.models import Context

        with CreativeSyncEnv._independent_session() as session:
            return sorted(session.scalars(select(Context.context_id).where(Context.tenant_id == tenant_id)).all())

    @staticmethod
    def _committed_assignment_count(*, tenant_id: str) -> int:
        """creative_assignments rows COMMITTED for *tenant_id*."""
        from sqlalchemy import func, select

        from src.core.database.models import CreativeAssignment

        with CreativeSyncEnv._independent_session() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(CreativeAssignment)
                    .where(CreativeAssignment.tenant_id == tenant_id)
                )
                or 0
            )

    @staticmethod
    def _committed_creatives_awaiting_approval(*, tenant_id: str, principal_id: str) -> list[str]:
        """creative_ids COMMITTED at ``pending_review`` for *tenant_id*, sorted."""
        from sqlalchemy import select

        from src.core.database.models import Creative

        with CreativeSyncEnv._independent_session() as session:
            return sorted(
                session.scalars(
                    select(Creative.creative_id).where(
                        Creative.tenant_id == tenant_id,
                        Creative.principal_id == principal_id,
                        Creative.status == "pending_review",
                    )
                ).all()
            )

    # --- the AI-review EFFECT oracle (GH #1972) ---
    #
    # Everything above observes what the SYNC committed. The three members below
    # observe what the background REVIEWER committed, which is a different
    # question and the one no scenario has ever asked: with the executor mocked
    # (EXTERNAL_PATCHES, above) the only observable is "submit() was called",
    # which is true whether or not the submitted job ever ran a line of its body.

    def run_ai_review_for_real(self) -> None:
        """Drop the ``_ai_review_executor`` mock so the submitted job really RUNS.

        The mock is what makes "no AI-review side effect" observable for every
        other scenario, and it is exactly what makes the review's own effects
        UNobservable: nothing behind ``submit`` executes. Stopping the patch puts
        the production executor back in the path, so the job is dispatched the way
        production dispatches it — the precondition for grading a verdict instead
        of a submit. Pair with :meth:`await_ai_review`, which is what makes the
        background completion a wait rather than a race.

        Stopping goes through ``BaseTestEnv``'s cleanup registry rather than a list
        of live patcher objects: since #1858 the base no longer keeps one — it
        registers ``patcher.stop`` under ``patch:<EXTERNAL_PATCHES key>`` and
        releases them LIFO. The entry is REMOVED as well as invoked, because a
        second ``stop()`` at teardown raises on an already-stopped patcher.
        """
        label = f"patch:{self._AI_REVIEW_PATCH_NAME}"
        for entry in list(self._enter_cleanups):
            if entry[0] == label:
                _label, stop = entry
                stop()
                self._enter_cleanups.remove(entry)
                self.mock.pop(self._AI_REVIEW_PATCH_NAME, None)
                return
        raise AssertionError(f"{label} is not registered — the executor is not patched, nothing to restore")

    @staticmethod
    def await_ai_review(creative_id: str, timeout: float = 30.0) -> None:
        """Block until every AI-review job submitted for *creative_id* finished.

        ``_defer_ai_review`` registers each job's Future in the module-level
        ``_ai_review_tasks``; joining on those Futures is what turns a background
        effect into something an assertion can read without sleeping on a timer.
        Returning does NOT imply the job did anything — a worker that finished
        without running the body finishes just as fast, which is the distinction
        :meth:`committed_ai_review` exists to make.
        """
        from concurrent.futures import wait

        from src.admin.blueprints.creatives import _ai_review_lock, _ai_review_tasks

        with _ai_review_lock:
            futures = [task["future"] for task in _ai_review_tasks.values() if task["creative_id"] == creative_id]
        assert futures, f"no AI review job was ever submitted for {creative_id}"
        done, pending = wait(futures, timeout=timeout)
        assert not pending, f"AI review job for {creative_id} did not finish within {timeout}s"
        for future in done:
            future.result()  # re-raise anything the worker thread swallowed

    def committed_ai_review(self, creative_id: str) -> CommittedAIReview:
        """The verdict an INDEPENDENT connection can see for *creative_id*.

        Same isolation as :meth:`_committed_creative_fingerprint` and for the same
        reason: the reviewer writes through its OWN unit of work, so only a
        connection this test's session does not own can tell a committed verdict
        from one that was never written.
        """
        from src.core.database.repositories.creative import CreativeRepository

        with self._independent_session() as session:
            row = CreativeRepository(session, self._tenant_id).get_by_id(creative_id, self._principal_id)
            if row is None:
                return CommittedAIReview(status=None, verdict=None)
            data = row.data if isinstance(row.data, dict) else {}
            return CommittedAIReview(
                status=row.status,
                verdict=data.get("ai_review"),
                error=data.get("ai_review_error"),
            )

    @realize_e2e(
        e2e_unsupported(
            "the notification observer is a side_effect installed on an in-process mock of "
            "_send_creative_notifications. Under e2e_rest the sync runs in the Docker server "
            "process, where that mock does not exist and the real notifier answers -- nothing "
            "would ever be recorded and the ordering assertions would read None. Observing it "
            "e2e needs effect capture at the server (a notification sink the test can poll), "
            "which is its own build"
        )
    )
    def observe_effects_at_notification(self) -> None:
        """Install the Slack-notification observer for this scenario.

        Ordering between an escaping effect and the writes it refers to is only
        observable AT the effect: after the request both are done and every
        ordering looks alike. The observer records what a separate connection
        could see the moment ``_send_creative_notifications`` was entered.
        """
        self.mock["send_notifications"].side_effect = self._observe_at_notification

    def _observe_at_notification(self, *args: Any, **kwargs: Any) -> None:
        """Stand in for ``_send_creative_notifications`` and record DB visibility.

        Falls off the end -> returns None, which is exactly what the plain
        ``return_value = None`` mock gave every existing caller, so scenarios
        that only assert the notification WAS sent read the same value.
        """
        self.workflow_rows_at_notification = self._committed_workflow_rows(tenant_id=self._tenant_id)
        self.assignment_count_at_notification = self._committed_assignment_count(tenant_id=self._tenant_id)

    @realize_e2e(
        e2e_unsupported(
            "every field of this snapshot is read over a second pooled connection to the engine "
            "THIS process is bound to. Under e2e_rest the request runs in the Docker server "
            "process against its own database, so the read answers about the wrong database -- it "
            "would report zero rows on every arm and grade nothing, which is strictly worse than "
            "not grading. Observing it e2e needs a server-side read-back surface (a tenant-scoped "
            "admin endpoint over workflow_steps / object_workflow_mapping / creative_assignments), "
            "which is its own build"
        )
    )
    def committed_sync_effects(self) -> CommittedSyncEffects:
        """Everything this tenant has COMMITTED right now, in ONE snapshot.

        One accessor rather than four: the scenarios compare these fields
        against each other (mappings against persisted creatives, the
        notification-time read against the final one), and four independently
        timed reads could not be compared -- besides multiplying the
        e2e-unrealizability declaration by four for one reason.
        """
        step_ids, object_ids = self._committed_workflow_rows(tenant_id=self._tenant_id)
        return CommittedSyncEffects(
            workflow_step_ids=step_ids,
            workflow_object_ids=object_ids,
            context_ids=self._committed_context_ids(tenant_id=self._tenant_id),
            assignment_count=self._committed_assignment_count(tenant_id=self._tenant_id),
            creatives_awaiting_approval=self._committed_creatives_awaiting_approval(
                tenant_id=self._tenant_id, principal_id=self._principal_id
            ),
        )

    @realize_e2e(
        e2e_unsupported(
            "the out-of-transaction effects this configures are observed as CALLS on in-process mocks "
            "(registry.build_creative / preview_creative, and the _ai_review_executor submit). Over real "
            "HTTP those objects live in the server process, so the assertions have nothing to read and the "
            "real creative agent answers for itself -- the scenario would grade the agent, not the gates. "
            "Observing them e2e needs effect capture at the server (a request sink + a review-verdict "
            "read-back), which is its own build"
        )
    )
    def configure_agent_served_creative(self, *, generative: bool, format_id: str) -> dict[str, str]:
        """Configure a format the creative agent actually serves, generative or not.

        ONE seam for both cells of the dry_run out-of-transaction outline, so the
        e2e-unrealizability is declared once, at the env method, rather than
        re-derived in a step body.
        """
        if generative:
            return self.setup_generative_build(format_id=format_id)

        from adcp.types import FormatId as LibraryFormatId

        mock_format = MagicMock()
        mock_format.format_id = LibraryFormatId(agent_url=self.DEFAULT_AGENT_URL, id=format_id)
        mock_format.agent_url = self.DEFAULT_AGENT_URL
        mock_format.output_format_ids = []  # non-generative -> preview_creative branch
        self.set_run_async_result([mock_format])
        registry = self.mock["registry"].return_value
        registry.preview_creative = AsyncMock(
            return_value={"previews": [{"url": "https://preview.example.com/p.html"}]}
        )
        registry.get_format = AsyncMock(return_value=mock_format)
        return {"agent_url": self.DEFAULT_AGENT_URL, "id": format_id}

    def setup_generative_build(
        self,
        format_id: str = "display_gen",
        agent_url: str | None = None,
        build_result: dict[str, Any] | None = None,
        gemini_api_key: str = "test-gemini-key",
    ) -> dict[str, str]:
        """Configure harness for generative creative testing.

        Sets up:
        - A format mock with output_format_ids (makes it generative)
        - build_creative AsyncMock with the given return value
        - gemini_api_key on the config mock
        - run_async to return the generative format list

        Returns a format_id dict for use in creative payloads::

            fmt = env.setup_generative_build(format_id="gen_banner")
            creative = {"creative_id": "c1", "name": "Test", "format_id": fmt, ...}
        """
        from adcp.types import FormatId as LibraryFormatId

        agent = agent_url or self.DEFAULT_AGENT_URL

        # Create format mock with matching FormatId
        mock_format = MagicMock()
        mock_format.format_id = LibraryFormatId(agent_url=agent, id=format_id)
        mock_format.agent_url = agent
        mock_format.output_format_ids = [format_id]  # Non-empty → generative

        # Configure run_async to return this format for list_all_formats
        self.set_run_async_result([mock_format])

        # Configure build_creative return value
        default_build = {
            "status": "draft",
            "context_id": "ctx-test-123",
            "creative_output": {
                "assets": {"headline": {"text": "Generated headline"}},
                "output_format": {"url": "https://generated.example.com/creative.html"},
            },
        }
        registry = self.mock["registry"].return_value
        registry.build_creative = AsyncMock(return_value=build_result or default_build)

        # Also configure get_format to return this format for validation
        registry.get_format = AsyncMock(return_value=mock_format)

        # Set gemini API key
        self.mock["config"].return_value.gemini_api_key = gemini_api_key

        return {"agent_url": agent, "id": format_id}

    def set_run_async_result(self, formats: list[Any]) -> None:
        """Configure run_async_in_sync_context to return *formats*.

        Unlike CreativeFormatsEnv.set_registry_formats (which patches
        registry.list_all_formats directly), this patches the sync bridge
        that wraps the async call in _sync.py.
        """
        self.mock["run_async"].side_effect = lambda coro: formats

    #: AdCP 3.1.1 makes idempotency_key REQUIRED on sync-creatives-request. Supplied here so
    #: every scenario gets a spec-conformant request without each of ~200 call sites naming a
    #: key it does not care about. A scenario that IS about the key overrides it, and its
    #: value wins because setdefault only fills an absent one.
    #: Shape-valid per the pin: ^[A-Za-z0-9_.:-]{16,255}$.
    #:
    #: FRESH PER CALL, because sync_creatives now HONOURS the key. A fixed default meant two
    #: successive calls in one scenario were the same request: the second replayed the
    #: first's response instead of executing, so a create-then-upsert test saw "created"
    #: twice, and a create-then-modify test hit IDEMPOTENCY_CONFLICT. The pin's own guidance
    #: is "use a fresh UUID v4 for each request", which is what a real buyer does per call.
    @property
    def DEFAULT_IDEMPOTENCY_KEY(self) -> str:  # noqa: N802 - kept as the documented name
        return f"harness-idem-{uuid4().hex}"

    def _with_required_request_fields(self, kwargs: dict, *, with_account: bool = True) -> dict:
        """Fill the spec-required fields a scenario has not set itself.

        `account` needs care: steps pass it EXPLICITLY as None for scenarios that are not
        about accounts (uc006_sync_creatives.py builds {"account": ctx.get("account_ref")}),
        and an explicit None fails validation now that the field is required -- setdefault
        would not see it. So a None is replaced, not merely defaulted.

        The value comes from the caller's own identity rather than a literal: the account a
        request names should be the account it is authenticated for, and a fabricated id
        would resolve to nothing. A scenario that IS about accounts sets account_ref and
        keeps it, because only a None is replaced.
        """
        # A MINIMAL VALID creative, not []. sync-creatives-request.json declares
        # ``creatives: {minItems: 1}``, so an empty array is a rejected request -- a test
        # that never mentions creatives (auth, isolation, notification) would fail on the
        # array rather than reaching what it grades. A test that explicitly passes [] still
        # gets [], because setdefault does not override an explicit value: that is how the
        # minItems rejection itself stays testable.
        kwargs.setdefault("creatives", [creative_payload()])
        kwargs.setdefault("idempotency_key", self.DEFAULT_IDEMPOTENCY_KEY)
        # ``with_account=False`` for the IMPL path. account is a field of the REQUEST, and
        # requests are built by transport wrappers -- _sync_creatives_impl does not take one.
        # Injecting it there makes every direct-impl test resolve an account before reaching
        # its subject, so a scenario about an unknown tenant answers AdCPAuthorizationError
        # from account resolution instead of the auth rejection it grades.
        if with_account and kwargs.get("account") is None:
            identity = kwargs.get("identity") or self.identity
            account_id = getattr(identity, "account_id", None)
            if not account_id:
                # No account on the identity: seed one and use it. Dropping the key was
                # viable only while the field was optional -- sync-creatives-request.json
                # lists account in /required, so an absent account is now a request the
                # schema rejects, and every scenario not ABOUT accounts would fail on a
                # missing field before reaching what it grades.
                if self._session is None:
                    # No DB bound (a contract test building a body outside ``with env:``).
                    # There is nothing to seed against and nothing that will resolve the
                    # reference, so a literal id gives the body its required SHAPE, which is
                    # all such a caller is asking for.
                    account_id = "acct_unbound"
                else:
                    account_id = self.setup_default_account(
                        principal_id=getattr(identity, "principal_id", None)
                    ).account_id
            # The TYPED reference, not a bare dict: the wrappers hand this straight to
            # enrich_identity_with_account, which reads AccountReference.root. A dict gets
            # as far as "'dict' object has no attribute 'root'". build_rest_body serialises
            # it for the wire itself.
            kwargs["account"] = AccountReference(root={"account_id": account_id})
        return kwargs

    def call_impl(self, **kwargs: Any) -> SyncCreativesResponse:
        """Call _sync_creatives_impl with real DB.

        Takes the same per-field kwargs a scenario always wrote and BUILDS the request from
        them, through ``SyncCreativesRequest`` — the one seam the three transports
        construct through. ``_sync_creatives_impl`` takes ``(req, identity, request_hash)``
        now, so a harness that forwarded loose fields would be the only caller in the tree
        still spreading a request across a call signature, and would grade a shape
        production no longer has.

        The 'identity' kwarg defaults to self.identity. If 'account' is present it is
        resolved via enrich_identity_with_account (same as the transport wrappers do); an
        absent one still reaches the REQUEST, because the schema requires the field, but is
        never resolved — so a scenario about an unknown tenant keeps reaching the auth
        rejection it grades rather than an account-resolution error.

        ``request_hash`` is derived by the wrappers' own rule unless the caller states one,
        so the direct-impl path exercises the same at-most-once behaviour as a transport.
        """
        from src.core.idempotency_canonical import canonical_request_hash
        from src.core.tools.creatives._sync import _sync_creatives_impl

        self._commit_factory_data()
        kwargs.setdefault("identity", self.identity)
        kwargs = self._with_required_request_fields(kwargs, with_account=False)

        identity = kwargs.pop("identity")
        stated_hash = kwargs.pop("request_hash", _UNSET)

        # Handle account kwarg — resolve at boundary, same as wrappers
        account = kwargs.pop("account", None)
        if account is not None:
            from src.core.transport_helpers import enrich_identity_with_account

            identity = enrich_identity_with_account(identity, account)

        req = SyncCreativesRequest(
            # The schema REQUIRES account, and this path deliberately does not resolve one
            # (see the docstring), so an unstated account gets a syntactically valid
            # reference that no lookup will ever consult. _sync_creatives_impl reads
            # identity, never req.account.
            account=account if account is not None else AccountReference(root={"account_id": "acct_unresolved"}),
            **kwargs,
        )
        request_hash = (
            (canonical_request_hash(req) if req.idempotency_key and not req.dry_run else None)
            if stated_hash is _UNSET
            else stated_hash
        )
        return _sync_creatives_impl(req=req, identity=identity, request_hash=request_hash)

    def deliver_a2a(self, **kwargs: Any) -> DeliverResult:
        """Dispatch sync_creatives through the REAL A2A ``on_message_send`` pipeline.

        This used to call ``sync_creatives_raw`` directly, routing AROUND
        ``on_message_send``. The consequence (per tests/CLAUDE.md's own table:
        A2A ``wire_response`` is populated ONLY when the env routes through
        ``_run_a2a_handler``) was that the A2A leg produced no wire at all — so
        every storyboard Then on this transport had nothing transport-observable
        to assert and fell back to reading an in-memory object. Delegating to the
        base ``_run_a2a_handler`` (message parse → skill routing →
        ``_handle_sync_creatives_skill`` → ``_serialize_for_a2a`` →
        Task/Artifact DataPart) makes the a2a seat grade the real handler,
        per-item failures included, instead of standing in for it.

        Outbound kwargs are JSON-normalized through :meth:`_wire_value` — the
        SAME normalizer the REST leg's ``build_rest_body`` uses, not a second
        hand-rolled one — because they now travel via
        ``create_a2a_message_with_skill`` -> ``_dict_to_value`` (protobuf),
        which cannot carry the Pydantic models the raw wrapper accepted as live
        Python objects (account, push_notification_config) and would otherwise
        turn them into repr strings instead of a document a buyer could send.
        Normalization is applied per-kwarg rather than by calling
        ``build_rest_body``, because that helper SELECTS the REST body's keys:
        routing through it would silently drop the three kwargs
        ``_run_a2a_handler`` consumes itself (see ``_A2A_RESERVED_KWARGS``),
        which must reach it untouched.

        The spec-required fields (creatives, idempotency_key, account) are filled by
        :meth:`_with_required_request_fields` BEFORE normalization, not by a local
        ``creatives=[]`` default: the pin makes all three required on
        sync-creatives-request, and the account it injects is a typed
        ``AccountReference`` that only survives the protobuf hop once ``_wire_value``
        has turned it into a dict.
        """
        kwargs = self._with_required_request_fields(kwargs)
        return self._run_a2a_handler(
            "sync_creatives",
            SyncCreativesResponse,
            **{k: v if k in _A2A_RESERVED_KWARGS else self._wire_value(v) for k, v in kwargs.items()},
        )

    def deliver_mcp(self, **kwargs: Any) -> DeliverResult:
        """Call sync_creatives via Client(mcp) — full pipeline dispatch.

        No enum coercion needed — FastMCP's TypeAdapter handles it automatically.
        """
        kwargs = self._with_required_request_fields(kwargs)
        return self._run_mcp_client("sync_creatives", SyncCreativesResponse, **kwargs)

    @classmethod
    def _wire_value(cls, value: Any) -> Any:
        """Convert a Pydantic model (or a list of them) to its wire dict form.

        Anything else passes through unchanged. Conversion only: no key
        filtering, no ``exclude_none`` — the REST seat's existing semantics.
        """
        if isinstance(value, list):
            return [cls._wire_value(item) for item in value]
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Convert kwargs to SyncCreativesBody shape for REST POST."""
        # The REST body expects 'creatives' as list[dict], matching SyncCreativesBody.
        # 'push_notification_config' and 'account' are declared by SyncCreativesBody and
        # forwarded by the route to sync_creatives_raw — dropping either here would make
        # any REST test of that behavior silently vacuous.
        #
        # 'idempotency_key' is schema-REQUIRED on sync_creatives (pinned_request_schema_fields
        # reports it in the required set). It is carried by the acceptance seam rather than
        # declared on SyncCreativesBody, so it must ride the REST body for the REST leg to
        # grade idempotency at all — omitting it here would make every REST idempotency
        # assertion vacuous. _with_required_request_fields is what SUPPLIES it (plus
        # creatives and account) when the caller did not, so the loop below finds a value
        # to carry rather than skipping the key.
        kwargs = self._with_required_request_fields(dict(kwargs))
        body: dict[str, Any] = {}
        if "creatives" in kwargs:
            body["creatives"] = self._wire_value(kwargs["creatives"])
        for key in ("assignments", "creative_ids", "push_notification_config", "account", "idempotency_key"):
            if kwargs.get(key) is not None:
                body[key] = self._wire_value(kwargs[key])
        for key in ("delete_missing", "dry_run", "validation_mode"):
            if key in kwargs:
                body[key] = self._wire_value(kwargs[key])
        return body

    def parse_rest_response(self, data: dict[str, Any]) -> SyncCreativesResponse:
        """Parse REST JSON into SyncCreativesResponse."""
        return SyncCreativesResponse(**data)


class RealRegistryCreativeSyncEnv(CreativeSyncEnv):
    """``CreativeSyncEnv`` with the creative-agent registry left UNPATCHED.

    ``CreativeSyncEnv`` mocks ``get_creative_agent_registry`` so ordinary sync
    tests never reach the network. This variant drops exactly that one patch and
    changes nothing else, so a buyer-supplied ``format_id.agent_url`` travels the
    real registry and is judged by the real egress seam — which is the point: a
    refusal produced by a mock proves nothing about production.

    Hermetic for the causes worth grading. A refused destination (cloud metadata,
    a reserved literal, a non-https scheme) is refused BEFORE a connection is
    opened, so no packet leaves and no DNS answer is needed. A scenario that
    wants a SUCCESSFUL fetch wants plain ``CreativeSyncEnv`` — here the reference
    agent would be dialled for real.

    TRAP inherited from the same pattern in ``RealResolverProductEnv``:
    ``self.mock["registry"]`` does not exist after ``__enter__``, so any helper
    that programs the registry mock (``setup_generative_build``,
    ``set_run_async_result``) will ``KeyError`` on this env.
    """

    EXTERNAL_PATCHES = {name: target for name, target in CreativeSyncEnv.EXTERNAL_PATCHES.items() if name != "registry"}

    def _configure_mocks(self) -> None:
        """Configure everything except the registry, which is real here.

        Same shape as ``RealResolverProductEnv`` (tests/harness/product.py): a throwaway
        stand-in absorbs the parent's registry wiring and is deleted afterwards, so the
        REST of the parent's wiring still runs. Forking the body instead — which is what
        this method used to do — silently dropped whatever the parent gained later, and it
        HAS gained: the ai_review_executor stand-in and the
        ``ai_review_commit_observations`` / ``*_at_notification`` attributes the effect
        oracles read. A fork would leave those unset and every oracle would AttributeError.
        """
        self.mock["registry"] = MagicMock()
        try:
            super()._configure_mocks()
        finally:
            del self.mock["registry"]
