import asyncio

from model_bridge import main as main_module


def test_ask_ollama_resolves_alias_before_adapter_call(monkeypatch):
    captured = {}

    async def _fake_run_async(service_name, args, input_text):
        captured["service_name"] = service_name
        captured["args"] = args
        captured["input_text"] = input_text
        return True, "ok"

    monkeypatch.setattr(main_module.ADAPTER, "run_async", _fake_run_async)
    result = asyncio.run(main_module.ask_ollama("hello", model="coder"))

    assert captured["service_name"] == "ollama"
    assert captured["args"] == ["qwen3-coder:30b-a3b-q8_0"]
    assert result.startswith("[Source: Ollama]")


def test_ask_ollama_returns_model_error_for_unknown_alias():
    result = asyncio.run(main_module.ask_ollama("hello", model="not_exists_alias"))
    assert result.startswith("[MODEL ERROR]")

