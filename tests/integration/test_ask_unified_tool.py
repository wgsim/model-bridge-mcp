import asyncio
import json

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


def test_ask_unified_routes_to_codex(monkeypatch):
    monkeypatch.setattr(main_module, "ask_chatgpt_cli", _fake_codex)
    out = asyncio.run(main_module.ask("hello", provider="codex"))
    assert out == "codex-result"


def test_ask_unified_routes_to_ollama(monkeypatch):
    monkeypatch.setattr(main_module, "ask_ollama", _fake_ollama)
    out = asyncio.run(main_module.ask("hello", provider="ollama", model="default"))
    assert out == "ollama-result"


def test_ask_unified_json_response(monkeypatch):
    monkeypatch.setattr(main_module, "ask_gemini_cli", _fake_gemini)
    out = asyncio.run(main_module.ask("hello", provider="gemini", response_format="json"))
    payload = json.loads(out)
    assert payload["content"] == "gemini-result"
