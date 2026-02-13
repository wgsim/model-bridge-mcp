import asyncio
import json

import pytest

from model_bridge import main as main_module


async def _fake_codex(*args, **kwargs):
    return "codex-result"


async def _fake_gemini(*args, **kwargs):
    if kwargs.get("response_format") == "json":
        return json.dumps(
            {
                "provider": "gemini",
                "cached": False,
                "content": "gemini-result",
                "meta": {"verbosity": "normal", "max_output_tokens": 0, "stream": False},
            }
        )
    return "gemini-result"


async def _fake_ollama(*args, **kwargs):
    return "ollama-result"


async def _fake_claude_code(*args, **kwargs):
    return "claude-code-result"


@pytest.fixture(autouse=True)
def reset_provider_registry(monkeypatch):
    """Reset PROVIDER_REGISTRY before each test to ensure fresh handlers."""
    monkeypatch.setattr(main_module, "PROVIDER_REGISTRY", None)


def test_ask_unified_routes_to_codex(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="codex"))
    assert out == "codex-result"


def test_ask_unified_routes_to_ollama(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="ollama", model="default"))
    assert out == "ollama-result"


def test_ask_unified_routes_to_claude_code(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="claude_code"))
    assert out == "claude-code-result"


def test_ask_unified_forwards_model_to_codex_provider(monkeypatch):
    captured = {}

    async def _fake_codex_capture(*args, **kwargs):
        captured["model"] = kwargs.get("model")
        return "codex-result"

    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex_capture,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="codex", model="gpt-5"))
    assert out == "codex-result"
    assert captured["model"] == "gpt-5"


def test_ask_unified_forwards_output_mode_to_provider(monkeypatch):
    captured = {}

    async def _fake_codex_capture(*args, **kwargs):
        captured["output_mode"] = kwargs.get("output_mode")
        return "codex-result"

    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex_capture,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="codex", output_mode="raw"))
    assert out == "codex-result"
    assert captured["output_mode"] == "raw"


def test_ask_unified_uses_runtime_default_output_mode_when_omitted(monkeypatch):
    captured = {}

    async def _fake_codex_capture(*args, **kwargs):
        captured["output_mode"] = kwargs.get("output_mode")
        return "codex-result"

    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex_capture,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "runtime": {
                "ask_defaults": {
                    "timeout_seconds": 120,
                    "max_output_tokens": 0,
                    "response_format": "text",
                    "verbosity": "normal",
                    "stream": False,
                    "instruction_preset": "none",
                    "output_mode": "raw",
                }
            }
        },
    )

    out = asyncio.run(main_module.ask("hello", provider="codex"))
    assert out == "codex-result"
    assert captured["output_mode"] == "raw"


def test_ask_unified_json_response(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex,
            "gemini": _fake_gemini,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    out = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    payload = json.loads(out)
    assert payload["content"] == "gemini-result"


def test_ask_unified_json_cache_hit_marks_cached_without_double_wrap(monkeypatch):
    calls = {"count": 0}

    async def _fake_gemini_counted(*args, **kwargs):
        calls["count"] += 1
        return json.dumps(
            {
                "provider": "gemini",
                "cached": False,
                "content": "gemini-result",
                "meta": {"verbosity": "normal", "max_output_tokens": 0, "stream": False},
            }
        )

    cache = main_module.PromptCache(ttl_seconds=60, max_entries=8)
    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: {
            "codex": _fake_codex,
            "gemini": _fake_gemini_counted,
            "ollama": _fake_ollama,
            "claude_code": _fake_claude_code,
        },
    )
    monkeypatch.setattr(main_module, "_get_prompt_cache", lambda: cache)

    first = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    second = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))

    first_payload = json.loads(first)
    second_payload = json.loads(second)
    assert first_payload["content"] == "gemini-result"
    assert second_payload["content"] == "gemini-result"
    assert second_payload["cached"] is True
    assert not second_payload["content"].startswith("{")
    assert calls["count"] == 1


def test_ask_unified_json_cache_hit_with_malformed_json_falls_back_safely(monkeypatch):
    class _BadCache:
        def get(self, key):
            return "{not-json"

        def set(self, key, value):
            return None

    async def _should_not_be_called(*args, **kwargs):
        raise AssertionError("cache hit should bypass provider call")

    monkeypatch.setattr(main_module, "ask_gemini_cli", _should_not_be_called)
    monkeypatch.setattr(main_module, "_get_prompt_cache", lambda: _BadCache())

    out = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    payload = json.loads(out)
    assert payload["provider"] == "gemini"
    assert payload["cached"] is True
    assert payload["content"] == "{not-json"
