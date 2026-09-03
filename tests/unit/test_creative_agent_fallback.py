"""Unit tests for the creative agent's raw-MCP fetch and MCP tool-result parser.

The fallback classes that used to live here (``TestStructuredContentFallbackTrigger``,
``TestSchemaValidationFailureTriggersFallback``) tested a mechanism that no
longer exists: the adcp SDK's own strict Pydantic parsing of
``list_creative_formats`` responses, which sometimes rejected a TextContent-only
reply and triggered a fallback to the raw-MCP path. The SDK client
(``ADCPMultiAgentClient``) has been removed from the OPERATOR agent path
entirely — it is routed through the guarded MCP seam instead — so there is no SDK-side
strict parser left to reject anything, and therefore nothing left to trigger a
fallback FROM. ``_parse_mcp_tool_result``'s own tolerant, per-format validation
(covered below) is now the ONLY ingestion path, for both the operator method
and the counterparty raw-MCP method.

The egress obligations that used to be graded here against a LOCAL
``check_url_ssrf`` pre-check are retargeted, not dropped. That pre-check was
deleted deliberately — the seam refuses or it sends, and re-deciding the
destination above it only bought a TOCTOU window and a second copy of a
decision ``asend`` already owns. So destination policy (blocked hostnames, IP
literals, resolve-then-check) is graded where it now lives, at the seam; what
this module still owes, and grades below, is that a seam refusal reaches the
caller UNCHANGED — not laundered into another code, not retried, and never
re-dialled through an HTTP client of this module's own.

Every test here drives the fetch by deciding what the SEAM answers. Nothing
programs ``httpx`` to answer for it: a test that did would grade a transport
this module no longer owns.
"""

import json

import httpx
import pytest

from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry
from src.core.exceptions import AdCPValidationError
from src.core.security.outbound_http import (
    CounterpartyUrl,
    OutboundDeliveryFailed,
    OutboundRequestBlocked,
    OutboundResult,
)


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


@pytest.fixture
def agent():
    """One agent config for every fetch test.

    The hostname is inert: ``asend`` is replaced in each test, so nothing here
    ever resolves or dials. What makes a URL the BUYER's on this path is the
    ``CounterpartyUrl`` provenance the caller passes, not the host it names —
    which is why one fixture serves both the transport tests and the
    buyer-refusal tests. The auth config is carried so the header-forwarding
    obligation has something to assert on.
    """
    return CreativeAgent(
        agent_url="https://creative.example.com",
        name="test-agent",
        auth={"type": "token", "credentials": "test-token"},
        auth_header="x-test-auth",
    )


SAMPLE_FORMATS_JSON = '{"formats": [{"format_id": {"agent_url": "https://creative.example.com", "id": "display_image"}, "name": "Display Image", "type": "display"}]}'

BUYER_FIELD = "creatives[0].format_id.agent_url"


def _seam_result(body: dict | str, *, content_type: str = "application/json") -> OutboundResult:
    """A real :class:`OutboundResult`, as the seam would hand one back.

    Deliberately the seam's own closed type rather than a mock. A ``MagicMock``
    stand-in answers ``result.headers.get(...)`` with another mock, whose ``in``
    test is False and whose ``.json()`` is a mock — so BOTH content-type
    branches fall through to the fetch's terminal "no parseable result" raise.
    Tests written that way go green while grading none of the branch they name,
    which is exactly what the SSE and parse-step threading tests below exist to
    catch.
    """
    raw = body if isinstance(body, str) else json.dumps(body)
    return OutboundResult(
        http_status=200,
        headers={"content-type": content_type},
        content=raw.encode(),
        attempts=1,
        duration_seconds=0.01,
    )


def _tool_result(content: list[dict]) -> dict:
    """A JSON-RPC envelope whose ``result`` is an MCP tools/call result."""
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": content}}


def _patch_asend(monkeypatch, *, result: OutboundResult | None = None, error: Exception | None = None) -> list[dict]:
    """Replace the egress seam and record every call made through it.

    Returns the recorded call list, so a test can assert on what was HANDED to
    the seam (headers, provenance, and how many times it was asked) as well as
    on what came back.
    """
    calls: list[dict] = []

    async def fake_asend(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if error is not None:
            raise error
        assert result is not None, "_patch_asend needs either a result or an error"
        return result

    monkeypatch.setattr("src.core.creative_agent_registry.asend", fake_asend)
    return calls


def _forbid_own_http_client(monkeypatch) -> None:
    """Fail the test if anything builds an HTTP client outside the seam.

    The discriminator for "the refusal was honoured": a test that only asserted
    "an error was raised" would also pass against a fetch that caught the
    refusal and re-dialled on raw httpx, because that second dial would fail
    too. This makes the second dial itself observable.
    """

    def _refuse(*args, **kwargs):
        raise AssertionError("the fetch built an HTTP client of its own instead of going through the seam")

    monkeypatch.setattr(httpx, "AsyncClient", _refuse)


class TestFetchFormatsRawMcpThroughTheSeam:
    """``_fetch_formats_raw_mcp`` dials a counterparty agent through ``asend`` only."""

    async def test_json_response_parses_formats(self, registry, agent, monkeypatch):
        """A JSON tools/call result yields formats, on exactly one dial.

        The positive control for every refusal below: without it, a fetch that
        refused everything — or that never dialled at all — would satisfy them.
        """
        calls = _patch_asend(
            monkeypatch,
            result=_seam_result(_tool_result([{"type": "text", "text": SAMPLE_FORMATS_JSON}])),
        )

        formats = await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert len(formats) == 1
        assert formats[0].format_id.id == "display_image"
        assert len(calls) == 1, "the fetch dialled more than once — the seam owns attempts, not this method"

    async def test_sse_response_parses_formats(self, registry, agent, monkeypatch):
        """A ``text/event-stream`` body carrying ``data: {...}`` yields formats.

        The fetch has two content-type branches, each reaching the parse step at
        its own call site, so the JSON case above does not grade this one.
        """
        payload = json.dumps(_tool_result([{"type": "text", "text": SAMPLE_FORMATS_JSON}]))
        _patch_asend(monkeypatch, result=_seam_result(f"data: {payload}\n\n", content_type="text/event-stream"))

        formats = await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert len(formats) == 1
        assert formats[0].format_id.id == "display_image"

    async def test_auth_headers_forwarded(self, registry, agent, monkeypatch):
        """The agent's configured credential rides out under its configured header name."""
        calls = _patch_asend(
            monkeypatch,
            result=_seam_result(_tool_result([{"type": "text", "text": '{"formats": []}'}])),
        )

        await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert calls[0]["headers"]["x-test-auth"] == "test-token"

    async def test_the_seam_is_told_whose_url_it_is(self, registry, agent, monkeypatch):
        """``provenance`` is forwarded to the seam, not re-derived or dropped.

        It is the only thing that decides how a refusal is reported — a lost
        ``CounterpartyUrl`` turns the buyer's own correctable input into a seller
        misconfiguration — and nothing else in the fetch would notice.
        """
        calls = _patch_asend(
            monkeypatch,
            result=_seam_result(_tool_result([{"type": "text", "text": '{"formats": []}'}])),
        )

        await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert calls[0]["provenance"] == CounterpartyUrl(field=BUYER_FIELD)

    async def test_a_seam_refusal_is_not_laundered_or_re_dialled(self, registry, agent, monkeypatch):
        """A pre-connection refusal reaches the buyer unchanged, and nothing re-dials.

        Replaces the blocked-destination cases this module used to grade against
        a local ``check_url_ssrf`` pre-check. WHICH destinations are refused is
        the seam's decision now, and is graded there; what survives here is that
        the refusal is HONOURED — re-raised as the very object the seam raised,
        already VALIDATION_ERROR / correctable and already naming the buyer
        field, rather than rewrapped, retried, or swallowed.
        """
        blocked = OutboundRequestBlocked(field=BUYER_FIELD)
        calls = _patch_asend(monkeypatch, error=blocked)
        _forbid_own_http_client(monkeypatch)

        with pytest.raises(AdCPValidationError) as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert excinfo.value is blocked, "the seam's refusal was rewrapped — its classification was restated elsewhere"
        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.recovery == "correctable"
        assert excinfo.value.field == BUYER_FIELD
        # The refusal must not disclose our policy or the resolved address
        # (AdCP 3.1.1 building/by-layer/L1/security.mdx:104-119 step 6).
        message = str(excinfo.value)
        assert "10.0.0.0/8" not in message and "169.254.0.0/16" not in message, (
            f"Refusal leaks the blocked CIDR to the caller: {message}"
        )
        assert len(calls) == 1, "a refused dial was retried — a refusal is terminal"

    @pytest.mark.parametrize(
        "http_status",
        [
            None,  # transport failure — never reached the wire (timeout, connect error)
            429,  # rate-limited, retried to exhaustion by the seam
            503,  # origin up but failing
        ],
        ids=["transport-failure", "rate-limited", "server-error"],
    )
    async def test_a_delivery_failure_surfaces_unchanged_as_transient(self, registry, agent, monkeypatch, http_status):
        """A delivered-but-failed dial keeps the seam's own transient classification.

        Replaces the four httpx-exception cases this module used to grade
        (timeout, connect error, 5xx, 429). Turning a transport exception or a
        status into a typed AdCP error is the seam's job plus
        ``raise_mapped_outbound_error``'s, and both are graded where they live —
        including the choice, for a COUNTERPARTY url, to re-raise rather than
        re-classify. What remains this module's obligation is that it neither
        re-classifies the outcome nor runs a retry loop on top of the seam's.
        """
        failure = OutboundDeliveryFailed(attempts=3, http_status=http_status)
        calls = _patch_asend(monkeypatch, error=failure)

        with pytest.raises(Exception) as excinfo:  # noqa: PT011 - identity is the assertion, not the type
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert excinfo.value is failure
        assert excinfo.value.error_code == "SERVICE_UNAVAILABLE"
        assert excinfo.value.recovery == "transient"
        assert len(calls) == 1, "the fetch re-tried a dial the seam had already exhausted"

    async def test_a_response_with_no_result_is_a_correctable_buyer_error(self, registry, agent, monkeypatch):
        """A JSON body carrying no ``result`` refuses as VALIDATION_ERROR / correctable.

        This is the fetch's OWN raise, distinct from the parse step's: the agent
        answered, but with nothing that is a tools/call result at all. It is
        graded separately because mutating both raises together lets the parse
        step's grader mask this one.

        The agent_url is the BUYER's (this method is only reached on the
        counterparty branch), so the refusal is their correctable input, not a
        seller misconfiguration and not a transient outage.
        """
        _patch_asend(monkeypatch, result=_seam_result({"jsonrpc": "2.0", "id": 1}))  # no "result"

        with pytest.raises(AdCPValidationError, match="No parseable result") as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        exc = excinfo.value
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.recovery == "correctable"
        assert exc.field == BUYER_FIELD

    async def test_the_fetch_threads_field_down_to_the_refusal(self, registry, agent, monkeypatch):
        """``_fetch_formats_raw_mcp`` passes its ``field`` into the parse step.

        The helper-level test below proves the raise CARRIES a field it is given;
        this proves the caller actually GIVES it one. Both halves are needed: the
        threading lives at two call sites inside the fetch, and deleting it leaves
        every other test green because no other caller passes a field.

        The body carries a real ``result`` whose content has no text — the
        condition the PARSE step refuses on. A body with no ``result`` would stop
        at the fetch's own raise (above) and never exercise the threading, which
        is why the two are matched on distinct messages.
        """
        _patch_asend(monkeypatch, result=_seam_result(_tool_result([{"type": "image", "data": "..."}])))

        with pytest.raises(AdCPValidationError, match="No text content") as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=BUYER_FIELD))

        assert excinfo.value.field == BUYER_FIELD, (
            "the refusal reached the buyer without naming which input to fix — the fetch "
            "dropped the field on its way to the parse step"
        )

    async def test_the_sse_branch_threads_field_into_the_parse_step(self, registry, agent, monkeypatch):
        """The SSE path threads ``field`` at its OWN call site.

        The fetch has two content-type branches and each calls the parse step
        separately, so grading only the JSON one leaves the SSE threading free to
        rot.
        """
        sse_field = "creatives[3].format_id.agent_url"
        payload = json.dumps(_tool_result([{"type": "image"}]))
        _patch_asend(monkeypatch, result=_seam_result(f"data: {payload}\n", content_type="text/event-stream"))

        with pytest.raises(AdCPValidationError, match="No text content") as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=sse_field))

        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.field == sse_field, "the SSE branch dropped the buyer field on its way to the parse step"


class TestParseMcpToolResult:
    """Test the MCP tool result parser."""

    def test_parses_text_content(self, registry):
        """Content with text type → parsed formats."""
        import logging

        result = {"content": [{"type": "text", "text": SAMPLE_FORMATS_JSON}]}
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].name == "Display Image"

    def test_no_text_content_raises(self, registry):
        """Content with no text items → raises AdCPValidationError.

        A silent ``return []`` used to mask failures as 'no formats'.
        """
        import logging

        result = {"content": [{"type": "image", "data": "..."}]}
        with pytest.raises(AdCPValidationError, match="No text content") as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger())
        # The agent_url came from the BUYER (this helper is only reached on the
        # counterparty branch), so an unusable answer is their correctable input —
        # not a seller misconfiguration, and not a transient outage.
        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.recovery == "correctable"

    def test_field_names_the_buyer_input_when_the_caller_has_one(self, registry):
        """A refusal carries the ``field`` that says WHICH buyer input to fix.

        The only production caller reaches here on the counterparty branch, where
        it holds the buyer's ``creatives[].format_id.agent_url`` path. A sync
        request carries up to 100 creatives, so without ``field`` the buyer is
        told their input is correctable but not which one — the same channel
        lanes 2 and 3 established as the only non-disclosing way to say it.

        Graded directly because every current caller happens to pass ``None``:
        dropping the threading would otherwise be invisible.
        """
        import logging

        result = {"content": [{"type": "image", "data": "..."}]}
        with pytest.raises(AdCPValidationError) as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger(), field="creatives[0].format_id.agent_url")

        assert excinfo.value.field == "creatives[0].format_id.agent_url"

    def test_empty_content_raises(self, registry):
        """Empty content list → raises AdCPValidationError.

        A silent ``return []`` used to mask failures as 'no formats'.
        """
        import logging

        result = {"content": []}
        with pytest.raises(AdCPValidationError, match="No text content") as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger())
        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.recovery == "correctable"


def _mcp_text_result(payload: dict) -> dict:
    """Wrap a list_creative_formats payload as an MCP tools/call TextContent result."""
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


# Two fully-known formats the pinned adcp library understands completely.
_KNOWN_FORMAT_A = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"},
    "name": "Medium Rectangle",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
_KNOWN_FORMAT_B = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
    "name": "Leaderboard",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
# AdCP-additive asset_type the canonical reference agent serves but the pinned
# (and latest) adcp closed Literal union does NOT model. This is the exact
# production defect class.
_ADDITIVE_FORMAT = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "tracking_pixel"},
    "name": "Tracking Pixel",
    "assets": [{"item_type": "individual", "asset_id": "pixel", "asset_type": "pixel_tracker", "required": True}],
}


class TestTolerantPerFormatIngestion:
    """Hermetic regression (Postel / asymmetric strictness).

    One unknown AdCP-additive asset_type must NOT nuke the whole
    list_creative_formats response. Fully-understood formats are returned;
    formats whose ONLY problem is an unrecognized additive asset_type are
    passed through (the unknown additive asset_type is tolerated) with ONE
    aggregated WARNING; genuinely malformed formats still fail LOUD.
    """

    def test_unknown_additive_asset_type_passes_through(self, registry, caplog):
        """Mixed batch: 2 known + 1 additive(pixel_tracker) → all 3 returned.

        SDK 5.7 accepts unknown asset_types as UnknownFormatAsset instead of
        rejecting them. This is better Postel's law behavior — unknown types
        are preserved, not dropped.
        """
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _ADDITIVE_FORMAT, _KNOWN_FORMAT_B]})

        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())

        ids = sorted(f.format_id.id for f in formats)
        assert ids == [
            "display_300x250_image",
            "display_728x90_image",
            "tracking_pixel",
        ], "All formats including additive-asset_type should pass through"

    def test_all_known_formats_pass_through_unchanged(self, registry):
        """No additive types → all formats returned, zero warnings (no behavior change)."""
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _KNOWN_FORMAT_B]})
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert sorted(f.format_id.id for f in formats) == ["display_300x250_image", "display_728x90_image"]

    def test_genuinely_malformed_format_still_fails_loud(self, registry):
        """A real schema bug (not an additive enum) must NOT be masked — fail loud."""
        import logging

        malformed = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken"},
            "name": 12345,  # wrong type — a genuine contract violation, not additive growth
            "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, malformed]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_additive_type_with_structurally_broken_asset_fails_loud(self, registry):
        """Unknown asset_type AND a structurally broken asset → not purely additive → fail loud."""
        import logging

        broken_additive = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken_pixel"},
            "name": "Broken Pixel",
            # asset_type unknown AND asset_id/required missing — substituting a known
            # asset_type would STILL fail, so this is not benign additive growth.
            "assets": [{"item_type": "individual", "asset_type": "pixel_tracker"}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, broken_additive]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_all_formats_additive_passes_through(self, registry, caplog):
        """SDK 5.7 accepts additive-only batch via UnknownFormatAsset — returns the format."""
        import logging

        result = _mcp_text_result({"formats": [_ADDITIVE_FORMAT]})
        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].format_id.id == "tracking_pixel"
