"""Provider registry and capabilities for unified ask routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_json: bool = True
    supports_stream: bool = False
    supports_force_model: bool = False


@dataclass(frozen=True)
class ProviderHealthPolicy:
    startup_check: bool = True
    lazy_probe: bool = False
    cooldown_seconds: int = 60


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    configured: bool
    capabilities: ProviderCapabilities
    handler: Callable[..., Any] | None = None
    health_policy: ProviderHealthPolicy | None = None
    required_env: list[str] | None = None


class ProviderRegistry:
    """Simple in-memory registry keyed by provider id."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> None:
        if spec.provider_id in self._providers:
            raise ValueError(f"provider already registered: {spec.provider_id}")
        self._providers[spec.provider_id] = spec

    def get(self, provider_id: str) -> ProviderSpec | None:
        return self._providers.get(provider_id)

    def list_provider_ids(self) -> list[str]:
        return sorted(self._providers.keys())

    def get_handler(self, provider_id: str) -> Callable[..., Any] | None:
        """Get the handler callable for a provider."""
        spec = self.get(provider_id)
        if spec is None:
            return None
        return spec.handler

    def supports_capability(self, provider_id: str, capability: str) -> bool:
        """Check if provider supports a specific capability."""
        spec = self.get(provider_id)
        if spec is None:
            return False
        caps = spec.capabilities
        match capability:
            case "json":
                return caps.supports_json
            case "stream":
                return caps.supports_stream
            case "force_model":
                return caps.supports_force_model
            case _:
                return False

    def validate_option(
        self, provider_id: str, option: str, value: Any
    ) -> tuple[bool, str | None]:
        """
        Validate if provider supports an option.
        Returns: (is_supported, error_message)
        """
        if option == "response_format" and value == "json":
            if not self.supports_capability(provider_id, "json"):
                return False, f"[CAPABILITY_ERROR] Provider '{provider_id}' does not support response_format='json'"
        if option == "stream" and value:
            if not self.supports_capability(provider_id, "stream"):
                return False, f"[CAPABILITY_WARNING] Provider '{provider_id}' does not support streaming, degrading to non-stream mode"
        if option == "force_model" and value:
            if not self.supports_capability(provider_id, "force_model"):
                return False, f"[CAPABILITY_ERROR] Provider '{provider_id}' does not support force_model option"
        return True, None

    def is_configured(self, provider_id: str) -> bool:
        """Check if provider is configured (has command config)."""
        spec = self.get(provider_id)
        if spec is None:
            return False
        return spec.configured


def build_default_provider_registry(
    config: dict,
    handlers: dict[str, Callable[..., Any]] | None = None,
) -> ProviderRegistry:
    commands_cfg = config.get("commands", {})
    registry = ProviderRegistry()
    defaults = {
        "codex": ProviderCapabilities(supports_json=True, supports_stream=False, supports_force_model=True),
        "gemini": ProviderCapabilities(supports_json=True, supports_stream=False, supports_force_model=True),
        "ollama": ProviderCapabilities(supports_json=True, supports_stream=False, supports_force_model=False),
        "claude_code": ProviderCapabilities(
            supports_json=True, supports_stream=False, supports_force_model=True
        ),
    }
    for provider_id, capabilities in defaults.items():
        handler = handlers.get(provider_id) if handlers else None
        registry.register(
            ProviderSpec(
                provider_id=provider_id,
                configured=provider_id in commands_cfg,
                capabilities=capabilities,
                handler=handler,
            )
        )
    return registry
