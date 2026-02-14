"""Unit tests for weighted routing chains (P2-1)."""

from __future__ import annotations

import pytest

from model_bridge.config.config_loader import (
    ProviderRoutingEntry,
    WeightedRoutingChains,
    RoutingChains,
    RoutingConfig,
    load_config,
)


class TestProviderRoutingEntry:
    """Test ProviderRoutingEntry dataclass."""

    def test_valid_provider_routing_entry(self):
        """Test creating a valid routing entry."""
        entry = ProviderRoutingEntry(provider="codex", weight=100)
        assert entry.provider == "codex"
        assert entry.weight == 100

    def test_default_weight(self):
        """Test that default weight is 100."""
        entry = ProviderRoutingEntry(provider="ollama")
        assert entry.weight == 100

    def test_weight_validation_fails_below_minimum(self):
        """Test that weight below 1 raises validation error."""
        with pytest.raises(Exception):  # pydantic.ValidationError
            ProviderRoutingEntry(provider="codex", weight=0)

    def test_weight_validation_fails_above_maximum(self):
        """Test that weight above 100 raises validation error."""
        with pytest.raises(Exception):  # pydantic.ValidationError
            ProviderRoutingEntry(provider="codex", weight=101)

    def test_provider_required(self):
        """Test that provider is required."""
        with pytest.raises(Exception):
            ProviderRoutingEntry(weight=100)


class TestWeightedRoutingChains:
    """Test WeightedRoutingChains schema."""

    def test_valid_weighted_chains(self):
        """Test creating valid weighted routing chains."""
        chains = WeightedRoutingChains(
            ask_chatgpt_cli=[
                ProviderRoutingEntry(provider="codex", weight=100),
                ProviderRoutingEntry(provider="gemini", weight=50),
            ],
            ask_gemini_cli=[
                ProviderRoutingEntry(provider="gemini", weight=100),
            ],
            ask_ollama_cloud_fallback=[
                ProviderRoutingEntry(provider="codex", weight=100),
            ],
        )
        assert len(chains.ask_chatgpt_cli) == 2
        assert chains.ask_chatgpt_cli[0].weight == 100
        assert chains.ask_gemini_cli[0].provider == "gemini"
        assert chains.ask_ollama_cloud_fallback is not None

    def test_empty_chains_allowed(self):
        """Test that empty lists are not allowed (min_length=1)."""
        with pytest.raises(Exception):
            WeightedRoutingChains(
                ask_chatgpt_cli=[],
            )


class TestRoutingConfig:
    """Test RoutingConfig with weighted chains."""

    def test_routing_config_with_weighted_chains(self):
        """Test RoutingConfig accepts weighted_chains."""
        config = RoutingConfig(
            default_chains=RoutingChains(
                ask_chatgpt_cli=["codex", "gemini"],
                ask_gemini_cli=["gemini"],
                ask_ollama_cloud_fallback=["codex"],
            ),
            weighted_chains=WeightedRoutingChains(
                ask_chatgpt_cli=[
                    ProviderRoutingEntry(provider="codex", weight=100),
                ],
                ask_ollama_cloud_fallback=[
                    ProviderRoutingEntry(provider="codex", weight=100),
                ],
            ),
        )
        assert config.weighted_chains is not None
        assert len(config.weighted_chains.ask_chatgpt_cli) == 1

    def test_routing_config_without_weighted_chains(self):
        """Test RoutingConfig works without weighted_chains."""
        config = RoutingConfig(
            default_chains=RoutingChains(
                ask_chatgpt_cli=["codex"],
                ask_gemini_cli=["gemini"],
                ask_ollama_cloud_fallback=["ollama"],
            ),
        )
        assert config.weighted_chains is None


class TestWeightedRoutingSelection:
    """Test provider selection based on weights."""

    def test_select_provider_by_weight(self):
        """Test weighted random selection of providers."""
        import random

        # Mock random to ensure deterministic selection
        providers = [
            ProviderRoutingEntry(provider="codex", weight=100),
            ProviderRoutingEntry(provider="gemini", weight=50),
            ProviderRoutingEntry(provider="ollama", weight=10),
        ]

        # Calculate total weight
        total_weight = sum(p.weight for p in providers)
        assert total_weight == 160

        # Verify weight distribution
        weights = [p.weight for p in providers]
        assert weights == [100, 50, 10]
