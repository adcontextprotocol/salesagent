"""Regression tests for : silent return [] masks agent failures.

A creative-agent fetch failure must surface as an error in
``FormatFetchResult.errors``, never as a silently empty format list — that
distinction is what lets ``products.py`` tell "agent up, genuinely 0 formats"
apart from "agent unreachable" and trigger graceful degradation accordingly.

Two of this file's original classes were retired, each for its own reason, and
neither because the invariant relaxed:

``TestFetchFormatsAnomalousStatusesMustRaise`` (anomalous ``status`` values on
a mocked adcp SDK response) was retired by salesagent-4n88: the OPERATOR agent
path no longer goes through ``adcp.ADCPMultiAgentClient`` at all — neither
``_fetch_formats_from_agent`` nor ``_build_adcp_client`` exists, so there is no
SDK-shaped ``status`` field left to be anomalous.

``TestRawMcpFallbackMustRaise`` was retired because its coverage MOVED, not
because its subject died: ``_fetch_formats_raw_mcp`` is still live, but it now
dials the egress seam (``asend``) rather than ``httpx.AsyncClient``, requires a
keyword-only ``provenance``, and raises ``AdCPValidationError`` (a sibling of
``AdCPAdapterError``, not a subclass). Both of its cases are graded — through
the seam, with the provenance and the exact refusal field — by
``test_creative_agent_fallback.py``:
``TestParseMcpToolResult::test_a_response_with_no_result_is_a_correctable_buyer_error``
and ``::test_empty_content_raises``.

What this file grades now is the invariant on the path that REPLACED them: the
operator dial ``_fetch_formats_operator``, which reads its answer out of the
guarded, RFC 9421-signed MCP seam (``call_operator_mcp_tool``). That dial's
``"formats" not in payload`` raise is the merged successor of every retired
"must raise, not return []" test above, and ``creative_agent_registry.py`` names
this file as its guard.

Bug: prebid/salesagent#1136
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry
from src.core.exceptions import AdCPConfigurationError


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


@pytest.fixture
def agent():
    return CreativeAgent(agent_url="https://creative.example.com", name="test-agent")


def _seam_answers(payload: dict):
    """Patch the guarded MCP seam, as ``_fetch_formats_operator`` imports it, to answer *payload*."""
    return patch(
        "src.core.creative_agent_registry.call_operator_mcp_tool",
        AsyncMock(return_value=payload),
    )


class TestOperatorDialMustRaiseOnUnparseablePayload:
    """``_fetch_formats_operator`` must raise when the payload carries no ``formats``.

    This is the live #1136 surface. ``call_operator_mcp_tool`` answers ``{}``
    when neither structuredContent nor a TextContent block carried a JSON
    object — a dead or wrong-answering agent — and an object that simply lacks
    ``formats`` did not answer ``list_creative_formats``. Reading
    ``.get("formats", [])`` over either would turn both into "agent up, 0
    formats", which ``products.py`` acts on by rejecting every submitted format
    ID. The gate must therefore be key PRESENCE, not truthiness.

    Nothing here mocks the signing gate: ``tenant_id=None`` is production's own
    "no tenant in scope, dial unsigned" answer, so the real
    ``request_signer_for_tenant`` runs.
    """

    @pytest.mark.asyncio
    async def test_empty_payload_raises(self, registry, agent):
        """Nothing parseable came back — must raise, not return []."""
        with _seam_answers({}):
            with pytest.raises(AdCPConfigurationError, match="No parseable content"):
                await registry._fetch_formats_operator(agent, tenant_id=None)

    @pytest.mark.asyncio
    async def test_payload_without_formats_key_raises(self, registry, agent):
        """A non-empty object that answered something else — must raise, not return [].

        The case a truthiness gate (``if not payload``) would wave through: the
        payload is truthy, so only checking key presence catches it.
        """
        with _seam_answers({"some_other_tool_response": {"ok": True}}):
            with pytest.raises(AdCPConfigurationError, match="No parseable content"):
                await registry._fetch_formats_operator(agent, tenant_id=None)

    @pytest.mark.asyncio
    async def test_genuinely_empty_format_list_is_not_an_error(self, registry, agent):
        """``{"formats": []}`` IS "agent up, genuinely 0 formats" — the one honest [].

        The counterpart assertion: the raise above must not be so broad that a
        healthy agent with no formats is reported as a failure. Without this,
        the gate could be tightened to ``if not payload.get("formats")`` and
        every test above would still pass.
        """
        with _seam_answers({"formats": []}):
            assert await registry._fetch_formats_operator(agent, tenant_id=None) == []


class TestListAllFormatsErrorPropagation:
    """End-to-end: a failed agent fetch must produce an error in FormatFetchResult.

    This is the critical integration point — when the operator fetch raises,
    list_all_formats_with_errors must record it as an error so that
    products.py can trigger graceful degradation.
    """

    @pytest.mark.asyncio
    async def test_operator_fetch_failure_produces_error(self, registry, agent, monkeypatch):
        """When the guarded MCP seam fails, the failure lands in FormatFetchResult.errors.

        Not the seam's business (asend/call_mcp_tool's own retry/backoff is
        graded elsewhere): what's graded here is that list_all_formats_with_errors
        turns a raised exception into a recorded error rather than an empty
        format list — a failed fetch must never look like "agent up, no formats".

        The failure is injected at the dial as ``call_operator_mcp_tool``
        imports it, so it travels the full production path — through that
        function's except arms (which do NOT catch a bare ``RuntimeError``) and
        out of ``_fetch_formats_operator`` — before the recording under test.
        """
        monkeypatch.delenv("ADCP_TESTING", raising=False)

        monkeypatch.setattr(registry, "_get_tenant_agents", lambda tenant_id=None: [agent])

        with patch("src.core.utils.operator_mcp.call_mcp_tool", AsyncMock(side_effect=RuntimeError("boom"))):
            result = await registry.list_all_formats_with_errors(tenant_id="test")

        assert len(result.errors) > 0, (
            "FormatFetchResult.errors must be non-empty when the operator fetch fails. "
            "Silent return [] masks the failure as 'agent up, no formats'."
        )
        assert len(result.formats) == 0

    @pytest.mark.asyncio
    async def test_unparseable_payload_is_recorded_as_an_error_not_zero_formats(self, registry, agent, monkeypatch):
        """The #1136 shape end to end: an unparseable payload must reach ``.errors``.

        Closes the loop the two layers above only half-grade — the dial raises
        (``TestOperatorDialMustRaiseOnUnparseablePayload``) and a raise is
        recorded (test above) — by driving the ACTUAL payload a dead agent
        returns all the way to the FormatFetchResult products.py reads.
        """
        monkeypatch.delenv("ADCP_TESTING", raising=False)
        monkeypatch.setattr(registry, "_get_tenant_agents", lambda tenant_id=None: [agent])

        with patch("src.core.creative_agent_registry.call_operator_mcp_tool", AsyncMock(return_value={})):
            result = await registry.list_all_formats_with_errors(tenant_id="test")

        assert len(result.formats) == 0
        assert len(result.errors) > 0, (
            "An unparseable list_creative_formats payload must be recorded as an error. "
            "FormatFetchResult(formats=[], errors=[]) is read by products.py as "
            "'agent up, genuinely 0 formats' and rejects every submitted format ID."
        )
