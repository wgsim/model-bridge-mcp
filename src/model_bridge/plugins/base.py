"""Base classes for provider plugins (P3-1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_bridge.core.provider_registry import ProviderCapabilities


@dataclass(frozen=True)
class PluginCapabilities:
    """Capabilities that a plugin supports."""

    supports_json: bool = True
    supports_stream: bool = False
    supports_force_model: bool = True


class ProviderPlugin(ABC):
    """Abstract base class for provider plugins.

    To create a custom provider plugin:

    ```python
    from model_bridge.plugins import ProviderPlugin, register_provider

    @register_provider
    class MyProvider(ProviderPlugin):
        @property
        def provider_id(self) -> str:
            return "my_provider"

        async def execute(self, prompt: str, model: str | None, options: dict, **kwargs) -> str:
            # Your implementation here
            return "response"
    ```
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'openai', 'anthropic', 'my_custom')."""
        pass

    @property
    def capabilities(self) -> PluginCapabilities:
        """Provider capabilities. Override to customize."""
        return PluginCapabilities()

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        """Execute a prompt and return the response.

        Args:
            prompt: The user prompt to send
            model: Optional model override
            options: Normalized options dict with keys:
                - timeout_seconds: float
                - max_output_tokens: int
                - response_format: 'text' | 'json'
                - verbosity: 'brief' | 'normal' | 'detailed'
                - stream: bool
            **kwargs: Additional provider-specific options

        Returns:
            Response string from the provider
        """
        pass

    def is_configured(self) -> bool:
        """Check if the provider is properly configured.

        Override to check for API keys, CLI availability, etc.

        Returns:
            True if provider is ready to use, False otherwise
        """
        return True

    def __repr__(self) -> str:
        return f"<ProviderPlugin {self.provider_id}>"
