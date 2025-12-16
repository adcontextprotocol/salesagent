"""Helpers for handling external service availability in tests.

Tests that depend on external services (adcontextprotocol.org, creative.adcontextprotocol.org)
should skip gracefully when those services are unavailable, rather than failing CI.
"""

import asyncio
from typing import Any

import httpx


def is_external_service_exception(exc: Exception) -> bool:
    """Check if an exception is due to external service unavailability.

    Use this for tests that make direct HTTP calls to external services.

    Args:
        exc: The exception raised during the test.

    Returns:
        True if the exception indicates external service unavailability.
    """
    error_str = str(exc).lower()

    # Check for httpx-specific exceptions
    if isinstance(exc, (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)):
        return True

    # Task cancellation (often due to timeout/connection issues)
    if isinstance(exc, asyncio.CancelledError):
        return True

    # Check for HTTP error codes in error message
    if any(code in error_str for code in ["523", "502", "503", "504"]):
        return True

    # Connection errors
    if "connection" in error_str and ("refused" in error_str or "error" in error_str):
        return True

    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return True

    return False


def is_external_service_response_error(response: Any) -> bool:
    """Check if a response's errors are due to external service unavailability.

    Use this for tests that receive response objects with an `errors` field
    (e.g., CreateMediaBuyError) where the error may be caused by external
    services being unavailable.

    Args:
        response: A response object that may have an `errors` attribute.

    Returns:
        True if the response errors indicate external service unavailability.
    """
    if not hasattr(response, "errors") or not response.errors:
        return False

    for error in response.errors:
        error_msg = str(error.message).lower() if hasattr(error, "message") else str(error).lower()

        # Format lookup failures from creative agents
        if "format lookup failed" in error_msg and "creative.adcontextprotocol.org" in error_msg:
            return True

        # Connection errors
        if "connection" in error_msg and ("refused" in error_msg or "error" in error_msg):
            return True

        # HTTP error codes
        if any(code in error_msg for code in ["523", "502", "503", "504"]):
            return True

    return False
