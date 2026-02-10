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
    monkeypatch.setattr(
        main_module,
        "_get_installed_ollama_models",
        lambda: (["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"], ""),
    )
    result = asyncio.run(main_module.ask_ollama("hello", model="coder"))

    assert captured["service_name"] == "ollama"
    assert captured["args"] == ["qwen3-coder-next:Q4_K_M"]
    assert result.startswith("[Source: Ollama]")


def test_ask_ollama_returns_model_error_for_unknown_alias():
    result = asyncio.run(main_module.ask_ollama("hello", model="not_exists_alias"))
    assert result.startswith("[MODEL ERROR]")


def test_ask_ollama_uses_default_alias_when_model_not_provided(monkeypatch):
    captured = {}

    async def _fake_run_async(service_name, args, input_text):
        captured["args"] = args
        return True, "ok"

    monkeypatch.setattr(main_module.ADAPTER, "run_async", _fake_run_async)
    monkeypatch.setattr(main_module, "_get_installed_ollama_models", lambda: (["gpt-oss:20b"], ""))

    result = asyncio.run(main_module.ask_ollama("hello"))
    assert result.startswith("[Source: Ollama]")
    assert captured["args"] == ["gpt-oss:20b"]


def test_ask_ollama_returns_install_error_when_requested_model_not_installed(monkeypatch):
    monkeypatch.setattr(main_module, "_get_installed_ollama_models", lambda: (["gpt-oss:20b"], ""))
    result = asyncio.run(main_module.ask_ollama("hello", model="coder"))
    assert result.startswith("[MODEL ERROR] Requested model 'qwen3-coder-next:Q4_K_M' is not installed")


def test_ask_ollama_tries_local_fallback_chain_before_cloud(monkeypatch):
    calls = []

    async def _fake_run_async(service_name, args, input_text):
        calls.append((service_name, args, input_text))
        if args == ["gpt-oss:20b"]:
            return False, "first model failed"
        if args == ["qwen3-coder-next:Q4_K_M"]:
            return True, "fallback ok"
        return False, "unknown"

    async def _fake_cloud(*args, **kwargs):
        raise AssertionError("cloud fallback should not be used when local fallback succeeds")

    monkeypatch.setattr(main_module.ADAPTER, "run_async", _fake_run_async)
    monkeypatch.setattr(
        main_module,
        "_get_installed_ollama_models",
        lambda: (["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"], ""),
    )
    monkeypatch.setattr(main_module.FAILOVER, "execute_async", _fake_cloud)

    result = asyncio.run(main_module.ask_ollama("hello", model="default"))
    assert result.startswith("[Source: Ollama]")
    assert calls[0][1] == ["gpt-oss:20b"]
    assert calls[1][1] == ["qwen3-coder-next:Q4_K_M"]
