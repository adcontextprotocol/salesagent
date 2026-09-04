"""Regression tests for issue #1237: sync_creatives account raw-dict crash.

_handle_sync_creatives_skill passed `account` as a raw dict to core, but
resolve_account calls .root on it expecting an AccountReference RootModel.
Verifies the A2A handler wraps the dict in AccountReference before forwarding.
"""

from unittest.mock import MagicMock, patch

import pytest
from adcp.types import AccountReference as LibraryAccountReference

from src.core.exceptions import AdCPValidationError
from src.core.resolved_identity import ResolvedIdentity
from src.core.schema_helpers import to_account_reference
from src.core.schemas import SyncCreativesRequest

_MOCK_IDENTITY = ResolvedIdentity(
    principal_id="principal_123",
    tenant_id="tenant_123",
    tenant={"tenant_id": "tenant_123"},
    protocol="a2a",
)


def test_to_account_reference_handles_supported_inputs():
    """The shared helper validates dicts and preserves typed/empty values."""
    account_dict = {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
    result = to_account_reference(account_dict)
    assert isinstance(result, LibraryAccountReference)
    assert result.root.brand.domain == "example.com"
    assert result.root.operator == "op-1"
    assert result.root.sandbox is False
    assert to_account_reference(result) is result
    assert to_account_reference(None) is None


def test_to_account_reference_rejects_invalid_account_payload():
    """Malformed oneOf account payloads fail as a TYPED error at the shared helper.

    Updated for #1417: the to_* coercions carry an internal
    ``adcp_validation_boundary`` (the coerce_creative_filters pattern), so the
    rejection is an ``AdCPValidationError`` with a top-level suggestion — the
    previous raw ``pydantic.ValidationError`` leak WAS the disease this test
    now guards against.
    """
    with pytest.raises(AdCPValidationError) as excinfo:
        to_account_reference({})


#: A minimal creative the pinned schema accepts. sync-creatives-request.json requires
#: creatives with minItems 1, so every payload in this module needs at least one.
_WIRE_CREATIVE = {
    "creative_id": "c1",
    "name": "Wire Creative",
    "format_id": {"agent_url": "https://creative.example.com", "id": "display_300x250"},
    "assets": {},
}


class TestSyncCreativesAccountCoercion:
    """A2A handler must coerce raw account dict to AccountReference before calling core."""

    def _call_handler_with_account(self, account_param):
        """Invoke _handle_sync_creatives_skill with a given account parameter value."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler.__new__(AdCPRequestHandler)

        captured = {}

        def _fake_core(**kwargs):
            # account rides ON the request now, so it is read from there.
            captured["account"] = kwargs["req"].account
            result = MagicMock()
            result.model_dump.return_value = {}
            return result

        with patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool", side_effect=_fake_core):
            import asyncio

            asyncio.run(
                handler._handle_sync_creatives_skill(
                    # A BUILDABLE payload. This used to pass `creatives: []`, which
                    # sync-creatives-request.json forbids (minItems 1) -- and it passed,
                    # because patching the wrapper also patched away the builder inside it,
                    # so nothing ever validated the request. The handler builds now, so the
                    # payload has to be one a buyer could actually send.
                    parameters={
                        "creatives": [_WIRE_CREATIVE],
                        "account": account_param,
                        # Also /required on sync-creatives-request.json.
                        "idempotency_key": "idem-a2a-account-0001",
                    },
                    identity=_MOCK_IDENTITY,
                )
            )

        return captured.get("account")

    def test_dict_account_is_wrapped_in_account_reference(self):
        """A raw dict account is coerced to AccountReference with field values preserved."""
        account_dict = {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        result = self._call_handler_with_account(account_dict)
        assert isinstance(result, LibraryAccountReference)
        assert result.root.brand.domain == "example.com"
        assert result.root.operator == "op-1"
        assert result.root.sandbox is False

    def test_already_typed_account_passes_through(self):
        """An already-validated AccountReference is forwarded by identity, not re-validated."""
        typed = LibraryAccountReference.model_validate(
            {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        )
        result = self._call_handler_with_account(typed)
        assert result is typed


class TestSyncCreativesFormatIdStaysWire:
    """The A2A handler must forward format_id as a WIRE DICT, never as a model.

    salesagent-kyc89: the handler upgraded each creative's format_id with
    ``upgrade_legacy_format_id``, which returns OUR ``FormatId`` subclass. Pydantic
    does not re-validate a model instance that already satisfies an annotation, so
    that subclass survived into ``CreativeAsset.format_id`` -- making A2A the only
    transport whose request carried a different CLASS. Pydantic v2 equality is
    class-sensitive, so the registry match in ``_processing`` found nothing and
    every generative creative was silently written as a plain static asset.

    The upgrade itself must stay (the library CreativeAsset rejects both a bare
    string and a dict with no agent_url), so what is graded here is its SHAPE: a
    JSON-native dict, identical to the request MCP and REST build.
    """

    @staticmethod
    def _forwarded_creatives(creatives: list[dict]) -> list:
        """The ``creatives`` argument the handler hands to the core tool."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler.__new__(AdCPRequestHandler)
        captured = {}

        def _fake_core(**kwargs):
            # creatives ride ON the request now.
            captured["creatives"] = kwargs["req"].creatives
            result = MagicMock()
            result.model_dump.return_value = {}
            return result

        with patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool", side_effect=_fake_core):
            import asyncio

            asyncio.run(
                handler._handle_sync_creatives_skill(
                    # account and idempotency_key are /required on
                    # sync-creatives-request.json; the payload has to carry them for the
                    # request to be constructible at all.
                    parameters={
                        "creatives": creatives,
                        "account": {"account_id": "acct-wire"},
                        "idempotency_key": "idem-a2a-formatid-0001",
                    },
                    identity=_MOCK_IDENTITY,
                )
            )

        return captured["creatives"]

    def test_structured_format_id_is_forwarded_as_a_dict(self):
        """A structured format_id reaches core as a dict, not a FormatId instance."""
        forwarded = self._forwarded_creatives(
            [
                {
                    "creative_id": "c1",
                    "name": "Structured",
                    "format_id": {"agent_url": "https://creative.example.com", "id": "display_300x250"},
                    "assets": {},
                }
            ]
        )
        # The handler builds now, so what it forwards is the TYPED field -- the divergence
        # this class guards (A2A alone constructing our FormatId subclass) is closed by
        # construction rather than by keeping the payload a dict. The value is what matters.
        format_id = forwarded[0].format_id
        assert str(format_id.agent_url).rstrip("/") == "https://creative.example.com"
        assert format_id.id == "display_300x250"

    def test_legacy_string_format_id_is_upgraded_with_the_default_agent_url(self):
        """A legacy string still gains its agent_url on the way to the request."""
        forwarded = self._forwarded_creatives(
            [{"creative_id": "c1", "name": "Legacy", "format_id": "display_300x250", "assets": {}}]
        )
        format_id = forwarded[0].format_id
        assert str(format_id.agent_url).rstrip("/") == "https://creative.adcontextprotocol.org"
        assert format_id.id == "display_300x250"

    def test_parameterized_format_id_keeps_its_parameters(self):
        """AdCP 2.5 width/height survive the dump rather than being dropped."""
        forwarded = self._forwarded_creatives(
            [
                {
                    "creative_id": "c1",
                    "name": "Parameterized",
                    "format_id": {
                        "agent_url": "https://creative.example.com",
                        "id": "display",
                        "width": 300,
                        "height": 250,
                    },
                    "assets": {},
                }
            ]
        )
        format_id = forwarded[0].format_id
        assert str(format_id.agent_url).rstrip("/") == "https://creative.example.com"
        assert format_id.id == "display"
        assert (format_id.width, format_id.height) == (300, 250)

    def test_forwarded_creative_builds_the_same_class_every_transport_builds(self):
        """The end the divergence actually had: CreativeAsset.format_id's CLASS.

        What A2A forwards must carry the same concrete format_id type as what the SHARED
        builder produces from the untouched wire dict -- which is now literally what every
        other transport calls. The divergence (A2A alone constructing our FormatId
        subclass) is closed by construction: both sides here go through one builder.
        """

        wire = {
            "creative_id": "c1",
            "name": "Same class",
            "format_id": {"agent_url": "https://creative.example.com", "id": "display_300x250"},
            "assets": {},
        }
        # A2A: through the handler, which upgrades legacy format_ids and then builds.
        from_a2a = self._forwarded_creatives([dict(wire)])[0]
        # Every other transport: the SAME builder, straight from the untouched wire dict.
        from_other_transports = SyncCreativesRequest(
            creatives=[dict(wire)],
            account=LibraryAccountReference.model_validate({"account_id": "acct-wire"}),
            idempotency_key="idem-a2a-formatid-0001",
        ).creatives[0]

        assert type(from_a2a.format_id) is type(from_other_transports.format_id)
        assert from_a2a.format_id == from_other_transports.format_id
