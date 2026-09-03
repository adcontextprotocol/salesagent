"""Regression tests for salesagent-9eu: a signals agent answering nothing usable must raise.

History, because this file no longer tests what it was written for. It was written
against ``SignalsAgentRegistry._get_signals_from_agent``, which interpreted an
``adcp.ADCPMultiAgentClient`` task result: three anomalous states — ``status=completed``
with ``data=None``, ``status=submitted`` with ``submitted=None``, and any unexpected
status such as ``working`` — each returned ``[]`` silently, so ``get_signals()`` recorded
no error and callers could not tell "agent down" from "genuinely 0 signals"
(prebid/salesagent#1136; same class as ``creative_agent_registry.py``, fixed in PR #1167).

PR #1802 deleted that method, the ``ADCPMultiAgentClient`` dial and the whole status
machine, routing the operator dial through the guarded MCP seam
(``call_operator_mcp_tool``) instead — that path answers COMPLETED or FAILED only, so
there is no status to misread and no async/webhook branch to preserve. Those three inputs
are no longer expressible against production, and nothing here resurrects them.

What survived the rewrite is the invariant and its one live silent-``[]`` site:
``_fetch_signals_operator``'s payload gate. An agent that answers with nothing parseable
would otherwise reach ``GetSignalsResponse.model_validate({})``, which validates CLEANLY
with ``signals=None`` — every field is optional in the pinned schema — and produce ``[]``
a second time. Production raises there, and no other test in the tree drives that raise
(the sibling ``tests/integration/test_operator_agent_mcp_seam_egress.py`` grades a JSON
ARRAY payload and an unparseable ``TextContent`` block, both of which fail validation
loudly; the empty answer is the one that fails silently). So it is pinned here.

The pair is the whole obligation: an unusable answer raises, and a genuinely empty
signals list still returns ``[]``. Either test alone would pass under a wrong fix — a
production path that raised on every empty result would satisfy the first, and the
silent-``[]`` regression itself would satisfy the second.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import (
    RECOVERY_BY_WIRE_CODE,
    AdCPConfigurationError,
    build_two_layer_error_envelope,
)
from src.core.signals_agent_registry import SignalsAgent, SignalsAgentRegistry
from tests.helpers import assert_envelope_shape

# Stub the DIAL, not ``call_operator_mcp_tool`` itself: ``extract_tool_payload`` runs
# inside that function and is what turns an unusable answer into the empty payload the
# gate under test refuses. Same patch point as the sibling integration suite.
_SEAM_DIAL = "src.core.utils.operator_mcp.call_mcp_tool"


@pytest.fixture
def agent() -> SignalsAgent:
    return SignalsAgent(
        agent_url="https://signals.example.com",
        name="test-signals-agent",
        auth={"type": "token", "credentials": "test-token"},
        auth_header="x-test-auth",
    )


def _seam_answers(monkeypatch: pytest.MonkeyPatch, *, structured_content: Any, text: str | None = None) -> None:
    """Make the guarded seam hand the registry a successful tool result it must interpret."""
    content = [MagicMock(text=text)] if text is not None else []
    result = MagicMock(structured_content=structured_content, content=content)
    monkeypatch.setattr(_SEAM_DIAL, AsyncMock(return_value=result))


class TestAnUnusableAnswerRaisesInsteadOfReturningEmpty:
    """``_fetch_signals_operator`` distinguishes "nothing usable" from "zero signals"."""

    @pytest.mark.asyncio
    async def test_an_answer_with_nothing_parseable_raises(self, agent, monkeypatch):
        """No ``structured_content`` and no text block: raise, do not return ``[]``.

        Asserts the buyer-visible wire envelope rather than the exception's attributes,
        and reads the recovery from the pin instead of writing a literal, so a spec bump
        moves this assertion instead of leaving it asserting yesterday's answer.
        """
        _seam_answers(monkeypatch, structured_content=None)

        with pytest.raises(AdCPConfigurationError) as excinfo:
            await SignalsAgentRegistry()._fetch_signals_operator(agent, brief="test")

        expected_recovery = RECOVERY_BY_WIRE_CODE["CONFIGURATION_ERROR"]
        assert expected_recovery == "terminal", (
            f"the pinned enumMetadata classifies CONFIGURATION_ERROR as {expected_recovery!r}, "
            "not 'terminal' — the premise this assertion is built on no longer holds"
        )
        assert_envelope_shape(
            build_two_layer_error_envelope(excinfo.value),
            "CONFIGURATION_ERROR",
            recovery=expected_recovery,
        )

    @pytest.mark.asyncio
    async def test_a_genuinely_empty_signals_list_is_returned_not_raised(self, agent, monkeypatch):
        """An agent that answered properly with zero signals is NOT a failure."""
        _seam_answers(monkeypatch, structured_content={"signals": []})

        result = await SignalsAgentRegistry()._fetch_signals_operator(agent, brief="test")

        assert result == [], f"a well-formed zero-signal answer must pass through as [], got {result!r}"
