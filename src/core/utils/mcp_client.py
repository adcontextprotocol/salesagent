"""Unified MCP client utility for consistent agent communication.

This module provides a single, standardized way to call MCP tools on
external agents (creative agents, signals agents, etc.).

Key features:
- Consistent URL handling (uses user's URL; if it fails after retries, does one
  final fallback attempt by appending "/mcp" when missing)
- Standardized auth header building
- Built-in retry logic with exponential backoff, driven by the shared
  egress Attempts machine — connect AND tool-call failures share ONE
  attempt sequence, so a transient tool-level failure is genuinely retried,
  not just classified after the fact
- Proper error handling and logging
- Testable in isolation

Usage:
    from src.core.utils.mcp_client import call_mcp_tool

    result = await call_mcp_tool(
        agent_url="https://example.com/mcp",
        tool="tool_name",
        arguments=params,
        auth={"type": "bearer", "credentials": "token123"},
        timeout=30,
    )
    payload = result.structured_content
"""

import logging
from typing import Any

# Both bound PRIVATELY: a plain import would publish `mcp_client.Client` and
# `mcp_client.StreamableHttpTransport`, and importing either from here resolves
# to the real symbol past the gate (GH #1802). The underscore makes that an
# ImportError, so the seam cannot re-export what it was sanctioned to import.
from fastmcp.client import (
    Client as _Client,
)
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import (
    StreamableHttpTransport as _StreamableHttpTransport,
)

from src.core.security.egress.attempts import Attempts
from src.core.security.outbound_http import (
    OutboundError,
    find_wrapped,
    guarded_client_factory,
    sleep_backoff,
    validate_url,
)

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Raised when MCP client connection fails after all retries."""

    pass


class MCPCompatibilityError(Exception):
    """Raised when MCP SDK version compatibility issue detected."""

    pass


def _build_auth_headers(auth: dict[str, Any] | None, auth_header: str | None = None) -> dict[str, str]:
    """Build authentication headers from auth config.

    Args:
        auth: Auth configuration dict with 'type' and 'credentials' keys
        auth_header: Optional custom header name (defaults based on auth type)

    Returns:
        Dictionary of headers to include in request

    Examples:
        >>> _build_auth_headers({"type": "bearer", "credentials": "token123"})
        {"Authorization": "Bearer token123"}

        >>> _build_auth_headers({"type": "api_key", "credentials": "key123"})
        {"x-api-key": "key123"}

        >>> _build_auth_headers({"type": "bearer", "credentials": "token"}, "X-Custom-Auth")
        {"X-Custom-Auth": "Bearer token"}
    """
    headers: dict[str, str] = {}

    if not auth:
        return headers

    auth_type = auth.get("type")
    credentials = auth.get("credentials")

    if not auth_type or not credentials:
        return headers

    # Determine header name
    if auth_header:
        header_name = auth_header
    elif auth_type == "bearer":
        header_name = "Authorization"
    elif auth_type == "api_key":
        header_name = "x-api-key"
    else:
        # Generic auth type - use x-api-key as default
        header_name = "x-api-key"

    # Format header value
    if auth_type == "bearer":
        headers[header_name] = f"Bearer {credentials}"
    else:
        # For api_key and other types, use credentials as-is
        headers[header_name] = credentials

    return headers


async def call_mcp_tool(
    agent_url: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    auth: dict[str, Any] | None = None,
    auth_header: str | None = None,
    timeout: int = 30,
    max_attempts: int = 3,
) -> CallToolResult:
    """Call an MCP tool with standardized connection handling and retry.

    This is the ONLY place where MCP clients should be created. This ensures
    consistent URL handling, auth, retry logic, and error handling across
    all agent communications.

    The connect AND the tool call live inside the SAME per-attempt ``try`` and
    drive the SAME :class:`~src.core.security.egress.attempts.Attempts`
    sequence, so a tool-level failure is retried exactly like a connect
    failure — the tool is re-invoked on the next attempt, not just reported
    once a connection later happens to succeed. The predecessor
    (``create_mcp_client``, an ``@asynccontextmanager``) could not offer this:
    its ``yield`` sat inside the retry ``try``, but the caller's
    ``client.call_tool(...)`` ran in the CALLER's own ``async with`` body,
    outside that ``try`` — a tool failure was thrown back into the generator
    at the yield and contextlib refused to resume it.

    Args:
        agent_url: URL of the MCP agent endpoint
                  Examples: "https://creative.adcontextprotocol.org/mcp"
                           "https://audience-agent.fly.dev/FastMCP/"
                  NOTE: Use the exact URL the user provided - no modifications!
        tool: Name of the MCP tool to call
        arguments: Arguments to pass to the tool
        auth: Optional auth configuration dict
              Format: {"type": "bearer"|"api_key", "credentials": "token_value"}
        auth_header: Optional custom auth header name
                    (defaults: "Authorization" for bearer, "x-api-key" for api_key)
        timeout: Request timeout in seconds (default: 30)
        max_attempts: Maximum attempts against the primary URL (default: 3)

    Returns:
        The tool call's result

    Raises:
        OutboundError: If egress policy refuses the destination — either at the
            pre-check below or during the dial itself. Propagates UNRETRIED and
            with its own classification; the attempt budget does not apply to a
            destination the policy already refused.
        MCPConnectionError: If connection or the tool call fails after all retries
        MCPCompatibilityError: If MCP SDK version incompatibility detected

    Example:
        result = await call_mcp_tool(
            agent_url="https://creative.adcontextprotocol.org/mcp",
            tool="list_creative_formats",
            arguments={},
            auth={"type": "bearer", "credentials": "token123"},
            timeout=30,
        )
        formats = result.structured_content
    """
    # Strip trailing slashes only - preserve the actual path (no mutation besides trimming)
    agent_url = agent_url.rstrip("/")

    # Egress policy, once, BEFORE the candidate loop and outside every try.
    #
    # Position is what makes the refusal CHEAP: refused here, nothing is built and
    # no candidate is tried. It is no longer what makes it CORRECT — the in-loop
    # handler below recovers a refusal raised during the dial itself and re-raises
    # it unretried, because this pre-check and the pinned transport's own
    # resolution are two separate resolutions that can disagree.
    #
    # Validating the primary also covers the ``/mcp`` fallback below: it differs
    # only by path, and the seam's policy is about scheme and address.
    validate_url(agent_url)

    # Build auth headers
    headers = _build_auth_headers(auth, auth_header)

    # Prepare connection candidates: primary URL first, then a single '/mcp' fallback (if missing)
    primary_url = agent_url
    fallback_url = None
    if not primary_url.endswith("/mcp"):
        fallback_url = f"{primary_url}/mcp"

    candidates: list[tuple[str, int]] = [(primary_url, max_attempts)]
    if fallback_url:
        # Per requirement: try once again with '/mcp' after primary retries fail
        candidates.append((fallback_url, 1))

    last_exception: BaseException | None = None

    for current_url, candidate_attempts in candidates:
        attempts = Attempts(candidate_attempts)

        for attempt in attempts.next_attempt():
            try:
                # Create transport and client. The httpx_client_factory pins the
                # connection to current_url's validated IP and refuses redirects:
                # without it fastmcp falls back to mcp.shared._httpx_utils's
                # create_mcp_http_client, which follows redirects with no pin, so a
                # counterparty answering `302 -> http://169.254.169.254/` reaches an
                # address validate_url's pre-check never saw. Pinning current_url — the URL
                # actually dialed — also means validate-and-dial cannot diverge.
                transport = _StreamableHttpTransport(
                    url=current_url,
                    headers=headers,
                    httpx_client_factory=guarded_client_factory(current_url),
                )
                client = _Client(transport=transport)

                # Connect and call the tool inside the SAME try — a tool-level
                # failure is caught by the except below and retried on this
                # attempt sequence, exactly like a connect failure.
                async with client:
                    result = await client.call_tool(tool, arguments)

                logger.debug(f"MCP tool {tool!r} on {current_url} succeeded on attempt {attempt}")
                return result

            except Exception as e:
                # A dial-time egress refusal is TERMINAL: the attempt budget does
                # not apply to a destination the policy already refused. Let it
                # out with its own type, before any retry bookkeeping.
                #
                # It has to be recovered from the chain rather than caught by
                # type, because fastmcp re-raises it as a bare RuntimeError
                # ("Client failed to connect: ..."). An `except OutboundError`
                # arm here reads like it closes the case and catches nothing --
                # the shape this epic exists to delete -- so the unwrap is the
                # one mechanism, not a decoration in front of one.
                #
                # validate_url above the loop does NOT make this unreachable: it
                # resolves separately from guarded_client_factory's resolution
                # inside `async with client`, and the two can disagree under DNS
                # rebind, which is precisely when retrying a refusal is worst.
                refusal = find_wrapped(e, OutboundError)
                if refusal is not None:
                    raise refusal from e

                last_exception = e
                error_msg = str(e)

                # Check for known compatibility issues
                if "notifications/initialized" in error_msg:
                    logger.warning(
                        f"MCP SDK compatibility issue with {current_url}: "
                        f"Server doesn't support 'notifications/initialized' notification. "
                        f"This is a known issue between FastMCP SDK versions."
                    )
                    raise MCPCompatibilityError(
                        f"MCP SDK compatibility issue with {current_url}: "
                        f"Server doesn't support notifications/initialized notification. "
                        f"The agent may need to upgrade their FastMCP version to match the client."
                    ) from e

                attempts.record_transport_failure()

                # Log and retry for this candidate
                logger.warning(
                    f"MCP connection attempt {attempt}/{candidate_attempts} failed for {current_url}: {type(e).__name__}: {e}"
                )

                if attempt < candidate_attempts:
                    # Backoff for the primary candidate only (candidate_attempts > 1).
                    # This client owns its transport for protocol reasons — a
                    # stateful MCP session over StreamableHttpTransport, which the
                    # egress seam's one-shot asend cannot carry — so it defers to
                    # the seam's BR-RULE-029 schedule (via the shared Attempts
                    # instance) instead of recomputing one.
                    await sleep_backoff(attempts)
                else:
                    # Exhausted attempts for this candidate; move to next (if any)
                    logger.error(
                        f"All {candidate_attempts} connection attempt(s) failed for {current_url}. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    break

    # If we reach here, all candidates failed — preserve legacy error format regardless of fallback
    raise MCPConnectionError(
        f"Failed to connect to MCP agent at {agent_url} after {max_attempts} attempts: "
        f"{type(last_exception).__name__ if last_exception else 'UnknownError'}: {last_exception}"
    ) from last_exception
