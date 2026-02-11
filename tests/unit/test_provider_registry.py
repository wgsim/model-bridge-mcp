from model_bridge.core.provider_registry import (
    ProviderCapabilities,
    ProviderRegistry,
    ProviderSpec,
    build_default_provider_registry,
)


def test_provider_registry_register_and_get():
    registry = ProviderRegistry()
    spec = ProviderSpec(
        provider_id="codex",
        configured=True,
        capabilities=ProviderCapabilities(supports_json=True),
    )
    registry.register(spec)

    loaded = registry.get("codex")
    assert loaded is not None
    assert loaded.provider_id == "codex"
    assert loaded.configured is True


def test_provider_registry_rejects_duplicate_registration():
    registry = ProviderRegistry()
    spec = ProviderSpec(
        provider_id="gemini",
        configured=True,
        capabilities=ProviderCapabilities(),
    )
    registry.register(spec)

    try:
        registry.register(spec)
        assert False, "expected ValueError for duplicate provider registration"
    except ValueError as exc:
        assert "provider already registered" in str(exc)


def test_build_default_provider_registry_marks_configured_from_commands():
    cfg = {
        "commands": {
            "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
            "gemini": {"exec": ["gemini"], "health": ["gemini", "--version"]},
            "ollama": {"exec": ["ollama", "run"], "health": ["ollama", "--version"]},
        }
    }
    registry = build_default_provider_registry(cfg)

    assert registry.get("codex").configured is True
    assert registry.get("claude_code").configured is False
    assert registry.list_provider_ids() == ["claude_code", "codex", "gemini", "ollama"]
