"""Unit tests for ProviderRegistry capability negotiation."""

from __future__ import annotations

import pytest

from model_bridge.core.provider_registry import (
    ProviderCapabilities,
    ProviderHealthPolicy,
    ProviderRegistry,
    ProviderSpec,
    build_default_provider_registry,
)


@pytest.fixture
def sample_registry():
    """Create a registry with sample providers."""
    registry = ProviderRegistry()

    registry.register(
        ProviderSpec(
            provider_id="codex",
            configured=True,
            capabilities=ProviderCapabilities(
                supports_json=True,
                supports_stream=False,
                supports_force_model=True,
            ),
            handler=lambda prompt, **kwargs: f"codex: {prompt}",
            health_policy=ProviderHealthPolicy(startup_check=True, lazy_probe=False),
            required_env=["OPENAI_API_KEY"],
        )
    )

    registry.register(
        ProviderSpec(
            provider_id="ollama",
            configured=True,
            capabilities=ProviderCapabilities(
                supports_json=True,
                supports_stream=False,
                supports_force_model=False,
            ),
            handler=lambda prompt, **kwargs: f"ollama: {prompt}",
        )
    )

    return registry


class TestProviderRegistry:
    """Test ProviderRegistry core functionality."""

    def test_register_and_get_provider(self, sample_registry):
        """Test registering and retrieving a provider."""
        spec = sample_registry.get("codex")
        assert spec is not None
        assert spec.provider_id == "codex"
        assert spec.configured is True
        assert spec.capabilities.supports_json is True
        assert spec.capabilities.supports_stream is False

    def test_get_nonexistent_provider(self, sample_registry):
        """Test getting a provider that doesn't exist."""
        spec = sample_registry.get("nonexistent")
        assert spec is None

    def test_list_provider_ids(self, sample_registry):
        """Test listing all provider IDs."""
        ids = sample_registry.list_provider_ids()
        assert ids == ["codex", "ollama"]

    def test_register_duplicate_provider_raises_error(self, sample_registry):
        """Test that registering a duplicate provider raises ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            sample_registry.register(
                ProviderSpec(
                    provider_id="codex",
                    configured=True,
                    capabilities=ProviderCapabilities(),
                )
            )

    def test_get_handler(self, sample_registry):
        """Test getting handler callable."""
        handler = sample_registry.get_handler("codex")
        assert handler is not None
        assert callable(handler)
        result = handler("test prompt")
        assert "codex" in result

    def test_get_handler_nonexistent(self, sample_registry):
        """Test getting handler for nonexistent provider."""
        handler = sample_registry.get_handler("nonexistent")
        assert handler is None


class TestCapabilityNegotiation:
    """Test capability negotiation methods."""

    def test_supports_json_capability(self, sample_registry):
        """Test JSON capability check."""
        assert sample_registry.supports_capability("codex", "json") is True

    def test_supports_stream_capability(self, sample_registry):
        """Test stream capability check."""
        assert sample_registry.supports_capability("codex", "stream") is False

    def test_supports_force_model_capability(self, sample_registry):
        """Test force_model capability check."""
        assert sample_registry.supports_capability("codex", "force_model") is True
        assert sample_registry.supports_capability("ollama", "force_model") is False

    def test_supports_unknown_capability(self, sample_registry):
        """Test unknown capability returns False."""
        assert sample_registry.supports_capability("codex", "unknown") is False

    def test_validate_json_option_supported(self, sample_registry):
        """Test validating JSON option when supported."""
        is_supported, error = sample_registry.validate_option("codex", "response_format", "json")
        assert is_supported is True
        assert error is None

    def test_validate_json_option_unsupported(self, sample_registry):
        """Test validating JSON option when not supported."""
        # Register a provider without JSON support
        sample_registry.register(
            ProviderSpec(
                provider_id="no_json_provider",
                configured=True,
                capabilities=ProviderCapabilities(supports_json=False),
            )
        )
        is_supported, error = sample_registry.validate_option(
            "no_json_provider", "response_format", "json"
        )
        assert is_supported is False
        assert "does not support" in error
        assert "json" in error

    def test_validate_stream_option_unsupported(self, sample_registry):
        """Test validating stream option when not supported."""
        is_supported, error = sample_registry.validate_option("codex", "stream", True)
        assert is_supported is False
        assert "does not support streaming" in error

    def test_validate_force_model_option_unsupported(self, sample_registry):
        """Test validating force_model option when not supported."""
        is_supported, error = sample_registry.validate_option("ollama", "force_model", True)
        assert is_supported is False
        assert "does not support force_model" in error

    def test_is_configured(self, sample_registry):
        """Test checking if provider is configured."""
        assert sample_registry.is_configured("codex") is True
        assert sample_registry.is_configured("nonexistent") is False


class TestBuildDefaultProviderRegistry:
    """Test build_default_provider_registry function."""

    def test_builds_registry_from_config(self):
        """Test building registry from config dict."""
        config = {
            "commands": {
                "codex": {"exec": ["echo"], "health": ["echo"]},
                "gemini": {"exec": ["echo"], "health": ["echo"]},
                "ollama": {"exec": ["echo"], "health": ["echo"]},
            },
            "models": {
                "ollama_default_model": "llama3.2",
                "ollama_final_backup_model": "llama3.2",
                "ollama_catalog": ["llama3.2"],
                "ollama_aliases": {},
                "ollama_local_fallback_chain": [],
                "codex_model_catalog": [],
                "gemini_model_catalog": [],
                "claude_code_model_catalog": [],
            },
            "security": {
                "block_patterns": [r"rm\s+"],
                "sensitive_paths": [r"/etc/"],
            },
            "runtime": {
                "system_suffix": "",
                "apply_system_suffix": {
                    "codex": True,
                    "gemini": True,
                    "ollama": True,
                },
                "subprocess_timeout_seconds": 120.0,
                "ollama_timeout_seconds": 300.0,
            },
            "routing": {
                "default_chains": {
                    "ask_chatgpt_cli": ["codex"],
                    "ask_gemini_cli": ["gemini"],
                    "ask_ollama_cloud_fallback": ["codex"],
                },
            },
        }

        handlers = {
            "codex": lambda prompt, **kwargs: "codex response",
            "gemini": lambda prompt, **kwargs: "gemini response",
        }

        registry = build_default_provider_registry(config, handlers=handlers)

        # Check that configured providers are registered
        assert "codex" in registry.list_provider_ids()
        assert "gemini" in registry.list_provider_ids()
        assert "ollama" in registry.list_provider_ids()

        # Check configured status
        assert registry.is_configured("codex") is True
        assert registry.is_configured("gemini") is True
        assert registry.is_configured("ollama") is True
        assert registry.is_configured("claude_code") is False

    def test_builds_registry_without_handlers(self):
        """Test building registry without handlers (handlers default to None)."""
        config = {
            "commands": {
                "codex": {"exec": ["echo"], "health": ["echo"]},
            },
            "models": {
                "ollama_default_model": "llama3.2",
                "ollama_final_backup_model": "llama3.2",
                "ollama_catalog": ["llama3.2"],
                "ollama_aliases": {},
                "ollama_local_fallback_chain": [],
                "codex_model_catalog": [],
                "gemini_model_catalog": [],
                "claude_code_model_catalog": [],
            },
            "security": {
                "block_patterns": [r"rm\s+"],
                "sensitive_paths": [r"/etc/"],
            },
            "runtime": {
                "system_suffix": "",
                "apply_system_suffix": {
                    "codex": True,
                    "gemini": True,
                    "ollama": True,
                },
                "subprocess_timeout_seconds": 120.0,
                "ollama_timeout_seconds": 300.0,
            },
            "routing": {
                "default_chains": {
                    "ask_chatgpt_cli": ["codex"],
                },
            },
        }

        registry = build_default_provider_registry(config)

        # Providers should still be registered, but with None handlers
        codex_spec = registry.get("codex")
        assert codex_spec is not None
        assert codex_spec.handler is None
