import asyncio
import json

from model_bridge import main as main_module


class _FakeFailover:
    async def execute_async(
        self,
        primary,
        secondary,
        prompt,
        mode,
        force_primary=False,
        allow_tertiary=True,
    ):
        return (
            f"{primary}-{secondary}-ok:{prompt}:{mode}:{force_primary}:{allow_tertiary}\n\n"
            "--- [Routing Log] ---\n"
            f"[1] Primary ({primary}): Trying...\n    [SUCCESS]"
        )


class _FakeAdapter:
    async def run_async(self, service_name, args, input_text, timeout_seconds=None, strip_noise=True):
        return True, f"{service_name}:{args[0]}:{input_text}"


def _fake_config():
    return {
        "models": {
            "ollama_default_model": "gpt-oss:20b",
            "ollama_final_backup_model": "qwen3-coder-next:Q4_K_M",
            "ollama_catalog": ["gpt-oss:20b", "glm-4.7-flash:Q8_0", "qwen3-coder-next:Q4_K_M"],
            "ollama_aliases": {
                "default": "gpt-oss:20b",
                "fast": "glm-4.7-flash:Q8_0",
                "coder": "qwen3-coder-next:Q4_K_M",
            },
            "ollama_local_fallback_chain": ["default", "coder"],
        }
    }


def test_ask_chatgpt_cli_smoke(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)
    result = asyncio.run(main_module.ask_chatgpt_cli("hello"))

    assert "codex-gemini-ok:hello:execution:False:True" in result
    assert "--- [Routing Log] ---" in result


def test_ask_gemini_cli_smoke(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)
    result = asyncio.run(main_module.ask_gemini_cli("analyze me"))

    assert "gemini-codex-ok:analyze me:analysis:False:True" in result
    assert "--- [Routing Log] ---" in result


def test_ask_claude_code_smoke(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)
    result = asyncio.run(main_module.ask_claude_code("review this"))

    assert "claude_code-codex-ok:review this:analysis:False:True" in result
    assert "--- [Routing Log] ---" in result


def test_ask_ollama_smoke_local_success(monkeypatch):
    monkeypatch.setattr(main_module, "_get_config", _fake_config)
    monkeypatch.setattr(main_module, "_get_adapter", lambda: _FakeAdapter())
    monkeypatch.setattr(
        main_module,
        "_get_installed_ollama_models",
        lambda: (["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"], ""),
    )
    class _AllowAllSanitizer:
        def inspect(self, p, mode="execution"):
            return True, ""

    monkeypatch.setattr(main_module, "_get_sanitizer", lambda: _AllowAllSanitizer())

    result = asyncio.run(main_module.ask_ollama("hello local", model="default"))

    assert result.startswith("[Source: Ollama]")
    assert "ollama:gpt-oss:20b:hello local" in result


def test_list_ollama_models_smoke(monkeypatch):
    monkeypatch.setattr(main_module, "_get_config", _fake_config)
    monkeypatch.setattr(main_module, "_get_installed_ollama_models", lambda: (["gpt-oss:20b"], ""))

    payload = json.loads(main_module.list_ollama_models())

    assert payload["status"] == "ok"
    assert payload["effective_default"] == "gpt-oss:20b"
    assert "qwen3-coder-next:Q4_K_M" in payload["missing"]
