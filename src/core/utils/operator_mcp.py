"""The one place an operator-configured MCP tool is called.

Four registry methods used to spell the same ladder: dial through
:func:`~src.core.utils.mcp_client.call_mcp_tool`, extract the payload, and map
BOTH failure vocabularies onto AdCP errors -- each constructing the same
``OperatorEndpoint`` label twice, once per arm. Four copies is four chances to
forget an arm, and the copies had already drifted in what they passed
(``auth``/``auth_header`` on two of them, a literal ``30`` timeout on the other
two).

Lives in its own module rather than in ``mcp_client``: ``mcp_tool_payload``
already imports ``MCPCompatibilityError`` from ``mcp_client``, so siting this
function there and calling ``extract_tool_payload`` from it would close an
import cycle. This module imports both and nothing imports it back.

NOT for counterparty (buyer-supplied) URLs. Those dial through the egress seam's
``asend`` with a ``CounterpartyUrl`` provenance and have their own single-arm
mapping; :func:`raise_mapped_mcp_error` asserts operator provenance and would
fail on them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.core.exceptions import AdCPConfigurationError
from src.core.helpers.mcp_tool_payload import extract_tool_payload
from src.core.helpers.outbound_error_mapping import raise_mapped_mcp_error, raise_mapped_outbound_error
from src.core.security.outbound_http import OperatorEndpoint, OutboundError
from src.core.utils.mcp_client import (
    MCPCompatibilityError,
    MCPConnectionError,
    MCPSigningError,
    SignMcpAttempt,
    call_mcp_tool,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of an operator's "test connection" probe, for either registry.

    Replaces a ``dict[str, Any]`` whose keys each admin route read with
    ``.get(key, default)``. Two states were expressible through that dict and
    are not expressible here: a SUCCESS carrying no count (the route defaulted
    it to ``0``, indistinguishable from an agent that genuinely answered with
    zero), and a FAILURE whose sentence arrived under a different key than the
    one the route read -- the failure paths returned ``error`` while the success
    path returned ``message``, so an explanation reached the operator only
    because each route happened to read both.

    ``message`` is always present and always the operator-facing sentence,
    whichever way the probe went. ``count`` is ``None`` when the probe failed --
    an absence, not a zero. ``samples`` is empty unless the probe has examples
    to show.

    One type for both probes: each blueprint projects it onto the JSON key names
    its own template already contracts on (``signal_count`` / ``format_count``),
    so the wire shape is unchanged while the thing being projected is typed.
    """

    ok: bool
    message: str
    count: int | None = None
    samples: tuple[str, ...] = field(default_factory=tuple)


def probe_failure(exc: Exception, *, logger: logging.Logger) -> ProbeResult:
    """The operator-facing sentence for a probe that did not connect.

    Both registries' probes report failure the same way, and they must: the
    operator is reading one dialog with one set of levers to check, and a
    difference in wording between the creative button and the signals button
    would be a difference with no cause behind it. One home for the sentence is
    what keeps them from drifting apart the way the env readers and the refusal
    table already did elsewhere in this seam.

    ``AdCPConfigurationError`` covers everything the operator can fix by
    repointing or re-crediting the deployment: the guarded MCP seam rejecting us
    during the handshake, egress policy refusing the configured endpoint before
    the dial, and an endpoint answering with nothing parseable. The seam does
    not distinguish "bad auth" from "bad request", so the advice names every
    lever rather than presuming credentials -- an egress refusal has nothing to
    do with them, and ``exc.message`` already says which cause it was.

    A SIGNING failure is an ``AdCPConfigurationError`` too -- same wire code,
    same terminal recovery -- but NONE of those levers is its cause, so it gets
    its own sentence rather than the general one. It is told apart by its
    ``__cause__``, which :func:`call_operator_mcp_tool` chains from the one
    ``MCPSigningError`` arm a few lines below; the two functions are in one
    module precisely so that chaining discipline is checkable at a glance.
    The levers it names are the ones the posture gate actually reads
    (``signing_key_backed`` in ``src/core/signing/posture.py``, called by each
    registry's ``_request_signer``): an ACTIVE request-signing key whose private
    half this deployment can decrypt. The remaining posture gate --
    ``origin_is_publishable`` -- is deliberately NOT named: a non-publishable
    origin resolves to ``sign=None`` and dials unsigned, so it cannot be the
    cause of a request that failed WHILE signing.
    """
    if isinstance(exc, AdCPConfigurationError) and isinstance(exc.__cause__, MCPSigningError):
        logger.error("Connection test failed (signing): %s", exc.message)
        return ProbeResult(
            ok=False,
            message=(
                f"Connection failed: {exc.message.rstrip('.')}. This agent's tenant is configured to "
                f"sign its outbound calls, so check that its request-signing key is still ACTIVE and "
                f"that this deployment can decrypt the key's private half. The agent URL, its "
                f"credentials and the egress policy are not implicated -- nothing was sent."
            ),
        )
    if isinstance(exc, AdCPConfigurationError):
        logger.error("Connection test failed (configuration): %s", exc.message)
        return ProbeResult(
            ok=False,
            message=(
                f"Connection failed: {exc.message.rstrip('.')}. Check the agent URL, its credentials "
                f"and auth header, and whether this deployment's egress policy allows the address."
            ),
        )
    logger.error("Connection test failed: %s", exc, exc_info=True)
    return ProbeResult(ok=False, message=f"Connection failed: {exc}")


async def call_operator_mcp_tool(
    agent_url: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    label: str,
    auth: dict[str, Any] | None = None,
    auth_header: str | None = None,
    timeout: int = 30,
    sign: SignMcpAttempt | None = None,
) -> dict[str, Any]:
    """Call *tool* on an operator-configured MCP agent and return its payload.

    Owns the dial, the payload extraction and BOTH error mappings, so a caller
    has one call to make and no arms to remember. ``label`` is the operator-facing
    name that rides out in a refusal message; it is built into an
    ``OperatorEndpoint`` ONCE here rather than once per except arm.

    ``agent_url`` is passed EXACTLY as the caller supplies it. The creative
    registry resolves a connection alias before calling; the signals registry
    does not. Resolving it here would silently give the signals path aliasing it
    does not have today.

    ``sign`` is forwarded VERBATIM, ``None`` included. WHETHER a dial may carry
    an RFC 9421 signature is the caller's decision -- it depends on the tenant's
    signing posture and on the operation name a conformant verifier will check
    the signature against -- so this function neither resolves a signer nor
    supplies a default. It is a passthrough with an error arm, not a policy.
    """
    provenance = OperatorEndpoint(label)
    try:
        result = await call_mcp_tool(
            agent_url=agent_url,
            tool=tool,
            arguments=arguments,
            auth=auth,
            auth_header=auth_header,
            timeout=timeout,
            sign=sign,
        )
        return extract_tool_payload(result)
    except OutboundError as exc:
        raise_mapped_outbound_error(exc, provenance=provenance, logger=logger)
    except MCPSigningError as exc:
        # A THIRD arm, not a fold into the one below, because a signing failure is
        # not a delivery failure: the seam raised inside its own httpx request hook,
        # before any socket was written, precisely so the request would NOT go out in
        # the clear. Routing it through ``raise_mapped_mcp_error`` would classify it
        # by an HTTP status it does not have and report "unreachable" for an endpoint
        # that was never dialled -- telling the operator to check the URL, the
        # credentials and the egress policy while the actual cause sat in their key
        # material. ``MCPSigningError`` subclasses plain ``Exception``, so without
        # this arm it escapes both of its neighbours and surfaces raw.
        #
        # CONFIGURATION_ERROR / terminal is the right class for the same reason a
        # refused operator endpoint is: the address AND the key are this
        # deployment's, the buyer has no lever, and per the pinned enum they "MUST
        # NOT auto-retry" -- which also matches the seam, whose retry loop
        # deliberately does not retry an unsignable request. Naming ``label`` (a
        # role) and never the address or the signer's own text keeps this consistent
        # with the sibling mappers; the detail goes to the log.
        logger.error("Could not sign the dial to %s, so nothing was sent: %s", provenance.name, exc)
        raise AdCPConfigurationError(
            f"The dial to {provenance.name} could not be signed, so nothing was sent."
        ) from exc
    except (MCPConnectionError, MCPCompatibilityError) as exc:
        raise_mapped_mcp_error(exc, provenance=provenance, logger=logger)
