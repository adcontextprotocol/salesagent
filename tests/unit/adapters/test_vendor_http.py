"""The two rules ``VendorHttpClient`` enforces that no other test can see.

Both are invisible to the adapter suites by construction. The per-client
``timeout`` defaults to the same 30 seconds every existing caller already used,
so a test that asserts ``timeout=30.0`` passes whether the field is wired up or
deleted outright. The overlap rule fires on a key clash, and no production call
site has one — which is the reason to test it here, not a reason to skip it.
"""

from types import MappingProxyType
from unittest.mock import patch

import pytest

from src.adapters.vendor_http import VendorHttpClient
from src.core.exceptions import AdCPConfigurationError


def _client(**overrides):
    kwargs = {"base_url": "https://vendor.example", "headers": {}}
    return VendorHttpClient(**{**kwargs, **overrides})


class TestPerClientTimeout:
    def test_a_clients_own_timeout_reaches_the_seam(self):
        """A non-default timeout is what the seam is called with.

        Asserted with a value that is not 30: the default and the wired-up field
        are indistinguishable at 30, so a test written there grades nothing.
        """
        with patch("src.adapters.vendor_http.send") as mock_send:
            _client(timeout=7.5).call("GET", "/ping")

        assert mock_send.call_args.kwargs["timeout"] == 7.5

    def test_a_client_that_names_no_timeout_still_sends_the_default(self):
        with patch("src.adapters.vendor_http.send") as mock_send:
            _client().call("GET", "/ping")

        assert mock_send.call_args.kwargs["timeout"] == 30.0


class TestParamsMerge:
    def test_client_params_and_per_call_params_arrive_together(self):
        client = _client(params=MappingProxyType({"access_token": "T"}))

        with patch("src.adapters.vendor_http.send") as mock_send:
            client.call("GET", "/records", params={"start_date": "2026-01-01"})

        assert mock_send.call_args.kwargs["params"] == {
            "access_token": "T",
            "start_date": "2026-01-01",
        }

    def test_a_client_param_survives_a_call_that_passes_none(self):
        client = _client(params=MappingProxyType({"access_token": "T"}))

        with patch("src.adapters.vendor_http.send") as mock_send:
            client.call("GET", "/records")

        assert mock_send.call_args.kwargs["params"] == {"access_token": "T"}

    def test_a_caller_cannot_shadow_a_client_level_parameter(self):
        """A key the client already fixed is a defect, not a value to resolve.

        The client-level mapping is where a query-string credential lives, so a
        caller supplying the same key is forging it or shadowing a dial
        coordinate. Picking a winner silently would let either bug ship.
        """
        client = _client(params=MappingProxyType({"access_token": "T"}))

        with patch("src.adapters.vendor_http.send") as mock_send:
            with pytest.raises(AdCPConfigurationError, match="access_token"):
                client.call("GET", "/records", params={"access_token": "forged"})

        assert not mock_send.called, "the clash must be caught before any request is sent"

    def test_the_clash_error_names_every_offending_key(self):
        client = _client(params=MappingProxyType({"access_token": "T", "network": "1"}))

        with patch("src.adapters.vendor_http.send"):
            with pytest.raises(AdCPConfigurationError) as exc_info:
                client.call("GET", "/r", params={"access_token": "x", "network": "2", "ok": "y"})

        # Quoted forms: a bare "ok" would match inside "access_token".
        message = str(exc_info.value)
        assert "'access_token'" in message
        assert "'network'" in message
        assert "'ok'" not in message, "a key that does not clash must not be blamed"


class TestImmutability:
    def test_a_caller_cannot_mutate_the_clients_params_through_the_sent_mapping(self):
        """The mapping handed to the seam is a copy, not the client's own."""
        client = _client(params=MappingProxyType({"access_token": "T"}))

        with patch("src.adapters.vendor_http.send") as mock_send:
            client.call("GET", "/r", params={"a": "1"})

        mock_send.call_args.kwargs["params"]["access_token"] = "mutated"
        assert client.params["access_token"] == "T"
