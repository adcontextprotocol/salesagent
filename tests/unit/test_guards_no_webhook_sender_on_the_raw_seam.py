"""Guard: no webhook sender dials the egress seam directly with ``json=``.

Part of #1802's "one webhook value from registration to delivery".

Outbound HTTP has one seam (``src/core/security/outbound_http``), and webhooks
have one module on top of it (``deliver_webhook`` / ``deliver_webhook_with_retry``)
that owns signing, retry policy and the delivery record. A sender that calls
``send(url, json=...)`` skips that module entirely: it leaves unsigned, unrecorded,
with retry re-decided at the call site — and three did, in a dev adapter and two
operator-notification paths, i.e. exactly where nobody looks.

The seam's ``json=`` parameter is NOT banned outright. It is the right call for a
non-webhook request (a vendor API, a health probe). What is banned is a WEBHOOK
sender reaching it: a module that posts to a URL some tenant or buyer registered.
This guard encodes that as "these three modules do not import ``send``", which is
the property the change made true — they now import nothing from the raw seam
because ``deliver_webhook`` / ``SlackNotifier`` do their dialing.

Deliberately narrow. A whole-tree "does this look like a webhook?" heuristic would
misfire on every legitimate ``send`` in the tree; naming the modules that were
converted keeps the guard exact, and the list may only GROW as more senders are
converted — never shrink, which would mean a sender went back to the raw seam.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import parse_module, repo_root

# Modules that post to a registered webhook URL and must go through the webhook
# module. May only grow: a removal means a sender returned to the raw seam.
_WEBHOOK_SENDER_MODULES = (
    "src/adapters/mock_ad_server.py",
    "src/adapters/base_workflow.py",
    "src/admin/blueprints/tenants.py",
)

_RAW_SEAM = "src.core.security.outbound_http"
# The dialing entry points. OutboundError and friends are types, not dials.
_DIALS = frozenset({"send", "asend"})


def find_raw_seam_dial_imports(tree: ast.Module) -> list[int]:
    """Line numbers importing a dialing function from the raw egress seam."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == _RAW_SEAM
        and any(alias.name in _DIALS for alias in node.names)
    ]


class TestNoWebhookSenderOnTheRawSeam:
    @pytest.mark.arch_guard
    @pytest.mark.parametrize("module", _WEBHOOK_SENDER_MODULES)
    def test_sender_does_not_import_a_raw_dial(self, module):
        path = repo_root() / module
        lines = find_raw_seam_dial_imports(parse_module(path))
        assert not lines, (
            f"{module}:{lines} imports a dialing function from {_RAW_SEAM}.\n"
            "    A webhook sender must go through the webhook module, which owns\n"
            "    signing, retry and the delivery record:\n"
            "        deliver_webhook(url, payload, auth=...)        # one shot\n"
            "        SlackNotifier(...).send_message(text=, blocks=) # operator notifications\n"
            "    Dialing the seam directly sends unsigned and unrecorded, and\n"
            "    re-decides retry policy per call site."
        )


class TestDetector:
    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("import send", "from src.core.security.outbound_http import send\n"),
            ("import asend", "from src.core.security.outbound_http import asend\n"),
            ("send among others", "from src.core.security.outbound_http import OutboundError, send\n"),
        ],
    )
    def test_detector_catches_known_bad(self, label, source):
        assert find_raw_seam_dial_imports(ast.parse(source)), f"detector missed: {label}"

    @pytest.mark.arch_guard
    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("types only", "from src.core.security.outbound_http import OutboundError\n"),
            ("the webhook module", "from src.core.security.webhook_egress import deliver_webhook\n"),
            ("a different module's send", "from some.other.module import send\n"),
        ],
    )
    def test_detector_does_not_flag_legitimate_imports(self, label, source):
        assert not find_raw_seam_dial_imports(ast.parse(source)), f"detector wrongly flagged: {label}"
