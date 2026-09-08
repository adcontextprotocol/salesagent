"""Guard: a PushNotificationConfig row is built by the repository and nowhere else.

Part of #1802's "one webhook value from registration to delivery".

The disease, stated once: *a caller builds a config-shaped object to satisfy a
type.* ``ProtocolWebhookService.send_notification`` takes ``DeliverableWebhookTarget``,
a structural Protocol over three fields, and an ORM instance satisfies it — so for a
long time the cheapest way to call the sender was to fabricate a detached
``PushNotificationConfig``. Three sites did it, and each one handed a sender a config
that no gate ever receipted:

* ``adcp_a2a_server.py`` — a row with ``tenant_id=""``/``principal_id=""`` built purely
  to type-check (deleted when the repository began taking the value)
* ``delivery_webhook_scheduler.py`` — a ``temp_`` row on the scheduled-delivery path
* ``admin/blueprints/creatives.py`` — a ``pnc_`` row on the creative-sync path

Both survivors also destructured ``authentication`` by hand to fill that row, which is
how ``schemes[0]`` — accepting a two-scheme document the pinned schema forbids, then
delivering under whichever was listed first — outlived the change that removed the
same read from the tool path, whose inventory never listed these two sites.

**Why a guard here, when a type is normally preferable.** The type already exists and
is already correct: ``ValidatedWebhookRegistration`` satisfies the Protocol, so the
right call needs no adapter. What no type can express is the NEGATIVE — Python cannot
stop a caller from instantiating a public ORM class. That gap is exactly what a
structural guard is the fallback for.

The allowlist is EMPTY and must stay empty. An entry here would mean a caller is
building a webhook config outside the repository again, which is the defect itself.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_violations_match_allowlist,
    parse_module,
    rel,
    repo_root,
    src_python_files,
)

# The ORM class, plus the alias every non-repository module imports it under.
_CONFIG_NAMES = frozenset({"PushNotificationConfig", "DBPushNotificationConfig"})

# The one module allowed to construct it: the repository is where a
# ValidatedWebhookRegistration becomes a row.
_REPOSITORY = "src/core/database/repositories/push_notification_config.py"

# EMPTY, and shrink-only in the sense that it can never grow: a new entry would be a
# caller fabricating a config again. Fix the caller instead — hand it the gate's value.
_ALLOWLIST: set[tuple[str, ...]] = set()


def find_config_construction_violations(tree: ast.Module) -> list[int]:
    """Line numbers where a PushNotificationConfig is constructed."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONFIG_NAMES
    ]


class TestWebhookConfigBuiltOnlyByTheRepository:
    @pytest.mark.arch_guard
    def test_no_module_outside_the_repository_constructs_one(self):
        repo = repo_root()
        found: set[tuple[str, ...]] = set()
        detail: list[str] = []
        for path in src_python_files(repo):
            relative = rel(path)
            if relative == _REPOSITORY:
                continue
            lines = find_config_construction_violations(parse_module(path))
            if lines:
                found.add((relative,))
                detail.extend(f"  {relative}:{line}" for line in sorted(lines))

        assert_violations_match_allowlist(
            found,
            _ALLOWLIST,
            fix_hint=(
                "Do not build a PushNotificationConfig to hand to a sender.\n"
                "    send_notification takes DeliverableWebhookTarget, which\n"
                "    ValidatedWebhookRegistration already satisfies:\n"
                "        target = accept_push_notification_config(cfg, field_prefix=...)\n"
                "    A hand-built config carries no receipt that the registration was ever\n"
                "    valid, and filling one by hand is what kept schemes[0] alive.\n"
                "    To PERSIST a registration, use PushNotificationConfigRepository.upsert().\n"
                "Sites found:\n" + "\n".join(sorted(detail))
            ),
        )


class TestDetector:
    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("bare name", 'c = PushNotificationConfig(id="x", url="https://e.test")\n'),
            ("import alias", 'c = DBPushNotificationConfig(id="x", url="https://e.test")\n'),
            ("nested in a call", "send(config=PushNotificationConfig(url=u))\n"),
            ("inside a branch", "if not row:\n    row = DBPushNotificationConfig(url=u)\n"),
        ],
    )
    def test_detector_catches_known_bad(self, label, source):
        """A drained detector passes silently — prove it still fires."""
        assert_detector_catches_ast_snippets(find_config_construction_violations, snippets={label: source})

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("the gate's value", 'target = accept_push_notification_config(cfg, field_prefix="w")\n'),
            ("a query, not a construction", "row = session.scalars(select(PushNotificationConfig)).first()\n"),
            ("an annotation only", "def f(c: PushNotificationConfig) -> None: ...\n"),
            ("attribute access", "url = push_notification_config.url\n"),
        ],
    )
    def test_detector_does_not_flag_legitimate_use(self, label, source):
        """Reading, querying and annotating the model are all fine — only building is not."""
        assert not find_config_construction_violations(ast.parse(source)), (
            f"detector wrongly flagged legitimate use: {label}"
        )
