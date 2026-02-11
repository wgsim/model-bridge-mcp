"""Provider registry and capabilities for unified ask routing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_json: bool = True
    supports_stream: bool = False
    supports_force_model: bool = False


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    configured: bool
    capabilities: ProviderCapabilities


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


def build_default_provider_registry(config: dict) -> ProviderRegistry:
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
        registry.register(
            ProviderSpec(
                provider_id=provider_id,
                configured=provider_id in commands_cfg,
                capabilities=capabilities,
            )
        )
    return registry
