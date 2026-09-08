"""MCP must not offer a rebuilt copy of an envelope it already captures.

``synthesized_error_envelope`` is what production WOULD emit for an exception,
recomputed by the harness from the same builder production uses. On IMPL that is
honest: there is no wire by definition, so the synthesized value is the only view
that exists and its name says so. On MCP there IS a wire, so the field is either
redundant (the wire is present) or a mask (the wire was lost) -- and a mask is
what let ``MediaBuyListEnv`` declare a wire it never captured, right up until
the fix in #1802.

``McpDispatcher``'s own comment already said "NEVER the synthesized fallback --
a dead MCP wire path must yield None here". The construction two lines below it
passed one anyway. These tests pin the comment.
"""

import json

import pytest
from fastmcp.exceptions import ToolError

from src.core.exceptions import AdCPValidationError, build_two_layer_error_envelope
from tests.harness.dispatchers import A2ADispatcher, ImplDispatcher, McpDispatcher, RestDispatcher


def _raising_env(exc: Exception):
    """A stand-in env whose every transport entry point raises *exc*."""

    class _Env:
        # The entry points the dispatchers ACTUALLY call. Stubbing anything
        # else lets the dispatcher die on an AttributeError BEFORE it reaches
        # the error arm under test, and the assertions below then hold for a
        # reason unrelated to what they claim to test -- both of the "no
        # envelope" ones pass by construction on a dispatch that never ran.
        #
        # #1858 renamed the env dispatch contract call_mcp/call_a2a ->
        # deliver_mcp/deliver_a2a: the deliver_* pair is now THE override point
        # (it returns a DeliverResult carrying payload AND wire), while
        # call_mcp/call_a2a are defined once on BaseTestEnv as
        # ``deliver_*(...).payload`` and are explicitly never overridden. This
        # stub predates that rename. There is no deliver_rest -- RestDispatcher
        # reads ``REST_ENDPOINT`` and then calls ``_run_rest_request`` -- and
        # the IMPL leg still calls ``call_impl``.
        REST_ENDPOINT = "/stub"

        def call_impl(self, **kwargs):
            raise exc

        def deliver_mcp(self, **kwargs):
            raise exc

        def deliver_a2a(self, **kwargs):
            raise exc

        def _run_rest_request(self, endpoint, **kwargs):
            raise exc

        def build_rest_body(self, **kwargs):
            return {}

        def parse_rest_response(self, data):
            return data

    return _Env()


def _an_error() -> AdCPValidationError:
    return AdCPValidationError("boom", field="push_notification_config.authentication.credentials")


class TestMcpDoesNotSynthesize:
    def test_a_typed_error_with_no_captured_wire_yields_no_envelope_at_all(self):
        """A dead MCP wire path must produce nothing to read, not a rebuilt copy.

        This is the whole point: a test downstream that falls back to the
        synthesized value would go green off a value regenerated from the
        exception, which cannot witness a regression in the production
        translator -- both sides compute it from the same in-memory object.
        """
        result = McpDispatcher().dispatch(_raising_env(_an_error()))

        assert result._synthesized_error_envelope is None
        assert result.wire_error_envelope is None

    def test_a_tool_error_carrying_wire_json_is_read_as_the_wire(self):
        """The real capture path still works -- asserted with a REAL envelope.

        Without this case the sibling above is vacuous: a bare exception is
        neither a ToolError carrying JSON nor stash-carrying, so both capture
        paths return None by construction and the file would stay green with
        MCP's wire capture entirely dead. That is the exact defect pldmk.24
        fixed one commit ago, so it is the one this file must be able to see.
        """
        envelope = build_two_layer_error_envelope(_an_error())
        result = McpDispatcher().dispatch(_raising_env(ToolError(json.dumps(envelope))))

        assert result.wire_error_envelope == envelope
        assert result._synthesized_error_envelope is None

    def test_a_stashed_wire_envelope_is_read_as_the_wire(self):
        """The second capture path: an AdCPError carrying the harness stash."""
        exc = _an_error()
        envelope = build_two_layer_error_envelope(exc)
        exc._wire_error_envelope = envelope

        result = McpDispatcher().dispatch(_raising_env(exc))

        assert result.wire_error_envelope == envelope
        assert result._synthesized_error_envelope is None


class TestOnlyTheTransportWithNoWireMaySynthesize:
    """The contract ``TransportResult`` already documents, pinned as a whole.

    Pinning only the deleted construction would grade "line 229 stayed deleted".
    Pinning every dispatcher grades the rule that line violated, which is what
    stops the field quietly becoming a fallback again on some other transport.

    A2A passing here does NOT mean A2A is clean. It leaves this field ``None``
    while putting a builder-regenerated envelope into ``wire_error_envelope``
    instead -- the same substitution under the name of the real thing, which is
    strictly worse and is why it needs its own change (#1417).
    """

    def test_impl_still_synthesizes_because_it_has_no_wire_to_lose(self):
        """IMPL's value is load-bearing and must survive this change.

        Five integration tests read it. It is not a mask there: ``has_wire=False``
        is a definition for an in-process call, not a lost capture.
        """
        result = ImplDispatcher().dispatch(_raising_env(_an_error()))

        assert result._synthesized_error_envelope is not None
        assert result.wire_error_envelope is None

    @pytest.mark.parametrize("dispatcher", [A2ADispatcher, McpDispatcher, RestDispatcher])
    def test_a_transport_that_has_a_wire_never_synthesizes(self, dispatcher):
        """BOTH fields, not just the private one (Chris SF3, #1802 review).

        Asserting only ``_synthesized_error_envelope is None`` grades the
        channel that was already closed and leaves the one that matters open.
        The deleted fallback at ``tests/harness/dispatchers.py:78`` did not put
        a rebuilt envelope in the private field -- it handed it back under
        ``wire_error_envelope``, the name of the thing it was impersonating. So
        re-introducing that line left this case green: the private field stayed
        None either way. Probed on the pre-fix tree, exactly as the review
        describes.

        ``wire_error_envelope is None`` is the assertion that reddens. It is the
        A2A twin of what ``TestMcpNoCapture`` one class up already asserts for
        MCP, and its absence is what that file's own docstring named as the gap.
        """
        result = dispatcher().dispatch(_raising_env(_an_error()))

        assert result._synthesized_error_envelope is None
        assert result.wire_error_envelope is None
