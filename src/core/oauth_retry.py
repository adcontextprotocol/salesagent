"""Retry logic for OAuth token refresh operations."""

import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from src.core.logging_config import oauth_structured_logger

T = TypeVar("T")


class OAuthRetryConfig:
    """Configuration for OAuth retry logic."""

    def __init__(
        self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0, backoff_multiplier: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier


def oauth_retry(config: OAuthRetryConfig = None):
    """Decorator for retrying OAuth operations with exponential backoff."""

    if config is None:
        config = OAuthRetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # Log successful operation
                    oauth_structured_logger.log_oauth_operation(
                        operation=f"{func.__name__}",
                        success=True,
                        details={"attempt": attempt + 1},
                        duration_ms=duration_ms,
                    )

                    return result

                except Exception as e:
                    last_exception = e
                    duration_ms = (time.time() - start_time) * 1000

                    # Log failed attempt
                    oauth_structured_logger.log_oauth_operation(
                        operation=f"{func.__name__}",
                        success=False,
                        details={"attempt": attempt + 1, "max_retries": config.max_retries},
                        error=str(e),
                        duration_ms=duration_ms,
                    )

                    # Don't retry on the last attempt
                    if attempt >= config.max_retries:
                        break

                    # Calculate delay with exponential backoff
                    delay = min(config.base_delay * (config.backoff_multiplier**attempt), config.max_delay)

                    time.sleep(delay)

            # If we get here, all retries failed
            if last_exception is not None:
                raise last_exception
            # This should never happen, but satisfy mypy
            raise RuntimeError("Unexpected: no result and no exception")

        return wrapper

    return decorator


def create_oauth_client_with_retry(client_id: str, client_secret: str, refresh_token: str):
    """Create OAuth client with retry logic."""

    @oauth_retry(OAuthRetryConfig(max_retries=2, base_delay=0.5))
    def _create_client():
        from googleads import oauth2

        # Create OAuth2 client
        oauth2_client = oauth2.GoogleRefreshTokenClient(
            client_id=client_id, client_secret=client_secret, refresh_token=refresh_token
        )

        # Test the token refresh immediately
        oauth2_client.Refresh()

        return oauth2_client

    return _create_client()
