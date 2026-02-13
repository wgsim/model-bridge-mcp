import asyncio
import json
import pytest

from model_bridge import main as main_module


class FakeDispatcher:
    """Fake dispatcher that returns canned responses for testing."""

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.default_response = "default-result"

    def set_response(self, provider: str, response: str):
        self.responses[provider] = response

    async def dispatch(self, provider_id: str, prompt: str, **kwargs):
        self.calls.append({"provider": provider_id, "prompt": prompt, "kwargs": kwargs})
        return self.responses.get(provider_id, self.default_response)


@pytest.fixture
def fake_dispatcher(monkeypatch):
    """Fixture that mocks _dispatch_ask_provider with a FakeDispatcher."""
    dispatcher = FakeDispatcher()

    async def _fake_dispatch(provider_id: str, prompt: str, **kwargs):
        return await dispatcher.dispatch(provider_id, prompt, **kwargs)

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _fake_dispatch)
    return dispatcher


def test_ask_unified_routes_to_codex(fake_dispatcher):
    fake_dispatcher.set_response("codex", "codex-result")
    out = asyncio.run(main_module.ask("hello", provider="codex"))
    assert out == "codex-result"


def test_ask_unified_routes_to_ollama(fake_dispatcher):
    fake_dispatcher.set_response("ollama", "ollama-result")
    out = asyncio.run(main_module.ask("hello", provider="ollama", model="default"))
    assert out == "ollama-result"


def test_ask_unified_routes_to_claude_code(fake_dispatcher):
    fake_dispatcher.set_response("claude_code", "claude-code-result")
    out = asyncio.run(main_module.ask("hello", provider="claude_code"))
    assert out == "claude-code-result"


def test_ask_unified_forwards_model_to_codex_provider(fake_dispatcher):
    fake_dispatcher.set_response("codex", "codex-result")
    out = asyncio.run(main_module.ask("hello", provider="codex", model="gpt-5"))
    assert out == "codex-result"
    # Check that model was captured in the dispatch call
    assert len(fake_dispatcher.calls) == 1
    assert fake_dispatcher.calls[0]["kwargs"].get("model") == "gpt-5"


def test_ask_unified_forwards_output_mode_to_provider(fake_dispatcher):
    fake_dispatcher.set_response("codex", "codex-result")
    out = asyncio.run(main_module.ask("hello", provider="codex", output_mode="raw"))
    assert out == "codex-result"
    assert len(fake_dispatcher.calls) == 1
    assert fake_dispatcher.calls[0]["kwargs"].get("output_mode") == "raw"


def test_ask_unified_uses_runtime_default_output_mode_when_omitted(fake_dispatcher, monkeypatch):
    fake_dispatcher.set_response("codex", "codex-result")
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
    assert len(fake_dispatcher.calls) == 1
    assert fake_dispatcher.calls[0]["kwargs"].get("output_mode") == "raw"


def test_ask_unified_json_response(fake_dispatcher):
    fake_dispatcher.set_response(
        "gemini",
        json.dumps(
            {
                "provider": "gemini",
                "cached": False,
                "content": "gemini-result",
                "meta": {"verbosity": "normal", "max_output_tokens": 0, "stream": False},
            }
        ),
    )
    out = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    payload = json.loads(out)
    assert payload["content"] == "gemini-result"


def test_ask_unified_json_cache_hit_marks_cached_without_double_wrap(fake_dispatcher, monkeypatch):
    calls = {"count": 0}

    class CountingDispatcher:
        def __init__(self):
            self.dispatcher = FakeDispatcher()

        async def dispatch(self, provider_id: str, prompt: str, **kwargs):
            calls["count"] += 1
            return json.dumps(
                {
                    "provider": "gemini",
                    "cached": False,
                    "content": "gemini-result",
                    "meta": {"verbosity": "normal", "max_output_tokens": 0, "stream": False},
                }
            )

    counting = CountingDispatcher()
    cache = main_module.PromptCache(ttl_seconds=60, max_entries=8)

    async def _fake_dispatch(provider_id: str, prompt: str, **kwargs):
        return await counting.dispatch(provider_id, prompt, **kwargs)

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _fake_dispatch)
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

    async def _should_not_be_called(provider_id: str, prompt: str, **kwargs):
        raise AssertionError("cache hit should bypass provider call")

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _should_not_be_called)
    monkeypatch.setattr(main_module, "_get_prompt_cache", lambda: _BadCache())

    out = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    payload = json.loads(out)
    assert payload["provider"] == "gemini"
    assert payload["cached"] is True
    assert payload["content"] == "{not-json"
