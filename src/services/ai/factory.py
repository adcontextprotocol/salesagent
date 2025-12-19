"""Factory for creating Pydantic AI models with tenant-aware configuration."""

import logging
import os
from functools import lru_cache

from src.services.ai.config import (
    TenantAIConfig,
    build_model_string,
    get_platform_defaults,
)

logger = logging.getLogger(__name__)

# Track if logfire has been configured
_logfire_configured = False


def configure_logfire(token: str | None = None) -> bool:
    """Configure Logfire for AI observability.

    Args:
        token: Optional Logfire token. If not provided, uses LOGFIRE_TOKEN env var
               or attempts to use default credentials from ~/.logfire/

    Returns:
        True if Logfire was successfully configured, False otherwise
    """
    global _logfire_configured

    if _logfire_configured:
        return True

    try:
        import logfire

        # Logfire will automatically use:
        # 1. Explicit token if provided
        # 2. LOGFIRE_TOKEN env var
        # 3. Default credentials from ~/.logfire/default.toml
        if token:
            logfire.configure(token=token)
        else:
            # Let logfire find credentials automatically
            logfire.configure()

        # Instrument Pydantic AI for automatic tracing
        logfire.instrument_pydantic_ai()

        _logfire_configured = True
        logger.info("Logfire configured for AI observability")
        return True

    except Exception as e:
        logger.debug(f"Logfire not configured: {e}")
        return False


class AIServiceFactory:
    """Factory for creating Pydantic AI models with tenant-aware configuration.

    Usage:
        factory = AIServiceFactory()

        # Using platform defaults
        model = factory.create_model()

        # Using tenant configuration
        model = factory.create_model(tenant_ai_config=tenant.ai_config)
    """

    def __init__(self):
        """Initialize the factory with platform defaults."""
        self._platform_defaults = get_platform_defaults()

        # Try to configure logfire on factory creation
        configure_logfire(self._platform_defaults.get("logfire_token"))

    def create_model(
        self,
        tenant_ai_config: dict | TenantAIConfig | None = None,
        provider_override: str | None = None,
        model_override: str | None = None,
    ) -> str:
        """Create a Pydantic AI model string with the appropriate configuration.

        Configuration priority:
        1. Explicit overrides (provider_override, model_override)
        2. Tenant-specific config (tenant_ai_config)
        3. Platform defaults (environment variables)

        Args:
            tenant_ai_config: Tenant's AI configuration (from database or dict)
            provider_override: Override the provider (for testing)
            model_override: Override the model (for testing)

        Returns:
            Pydantic AI model string (e.g., "anthropic:claude-sonnet-4-20250514")

        Raises:
            ValueError: If no API key is available for the configured provider
        """
        # Parse tenant config if provided as dict
        if isinstance(tenant_ai_config, dict):
            config = TenantAIConfig.model_validate(tenant_ai_config)
        elif tenant_ai_config:
            config = tenant_ai_config
        else:
            config = TenantAIConfig()

        # Resolve configuration with priority
        provider = provider_override or config.provider or self._platform_defaults["provider"]
        model_name = model_override or config.model or self._platform_defaults["model"]
        api_key = config.api_key or self._platform_defaults.get("api_key")

        # Configure logfire with tenant token if provided
        if config.logfire_token:
            configure_logfire(config.logfire_token)

        # Build model string for Pydantic AI
        model_string = build_model_string(provider, model_name)

        # Set the API key in environment for the provider
        # Pydantic AI reads from standard env vars
        self._set_provider_api_key(provider, api_key)

        logger.debug(f"Creating Pydantic AI model: {model_string}")

        # Return the model string - Pydantic AI Agent will resolve it
        return model_string

    def _set_provider_api_key(self, provider: str, api_key: str | None) -> None:
        """Set the API key environment variable for a provider.

        Pydantic AI reads API keys from standard environment variables.

        Args:
            provider: Provider name
            api_key: API key to set
        """
        if not api_key:
            return

        env_vars = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
        }

        env_var = env_vars.get(provider)
        if env_var:
            os.environ[env_var] = api_key

    def is_ai_enabled(
        self,
        tenant_ai_config: dict | TenantAIConfig | None = None,
    ) -> bool:
        """Check if AI is enabled for the given configuration.

        AI is enabled if there's an API key available (from tenant or platform).

        Args:
            tenant_ai_config: Tenant's AI configuration

        Returns:
            True if AI calls can be made, False otherwise
        """
        if isinstance(tenant_ai_config, dict):
            config = TenantAIConfig.model_validate(tenant_ai_config)
        elif tenant_ai_config:
            config = tenant_ai_config
        else:
            config = TenantAIConfig()

        # AI is enabled if we have an API key from either source
        return bool(config.api_key or self._platform_defaults.get("api_key"))

    def get_effective_config(
        self,
        tenant_ai_config: dict | TenantAIConfig | None = None,
    ) -> dict:
        """Get the effective configuration that would be used.

        Useful for debugging and displaying configuration in admin UI.

        Args:
            tenant_ai_config: Tenant's AI configuration

        Returns:
            dict with effective provider, model, and whether API key is set
        """
        if isinstance(tenant_ai_config, dict):
            config = TenantAIConfig.model_validate(tenant_ai_config)
        elif tenant_ai_config:
            config = tenant_ai_config
        else:
            config = TenantAIConfig()

        provider = config.provider or self._platform_defaults["provider"]
        model = config.model or self._platform_defaults["model"]
        has_api_key = bool(config.api_key or self._platform_defaults.get("api_key"))
        has_logfire = bool(config.logfire_token or self._platform_defaults.get("logfire_token"))

        return {
            "provider": provider,
            "model": model,
            "has_api_key": has_api_key,
            "has_logfire": has_logfire,
            "settings": config.settings.model_dump(),
            "source": "tenant" if config.provider else "platform",
        }


@lru_cache(maxsize=1)
def get_factory() -> AIServiceFactory:
    """Get the singleton factory instance.

    Returns:
        AIServiceFactory instance
    """
    return AIServiceFactory()
