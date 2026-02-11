import json

from model_bridge import main as main_module


def _fake_config():
    return {
        "commands": {
            "codex": {"exec": ["codex", "exec"]},
            "gemini": {"exec": ["gemini", "-p"]},
            "ollama": {"exec": ["ollama", "run"]},
            "claude_code": {"exec": ["claude", "-p"]},
        },
        "models": {
            "ollama_default_model": "gpt-oss:20b",
            "ollama_final_backup_model": "qwen3-coder-next:Q4_K_M",
            "ollama_catalog": ["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"],
            "ollama_aliases": {"default": "gpt-oss:20b", "coder": "qwen3-coder-next:Q4_K_M"},
            "ollama_local_fallback_chain": ["default", "coder"],
            "codex_model_catalog": ["gpt-5", "o3"],
            "gemini_model_catalog": ["gemini-2.5-pro"],
            "claude_code_model_catalog": ["sonnet"],
        },
    }


def test_list_provider_models_all_returns_mixed_dynamic_and_static(monkeypatch):
    monkeypatch.setattr(main_module, "_get_config", _fake_config)
    monkeypatch.setattr(main_module, "_get_installed_ollama_models", lambda: (["gpt-oss:20b"], ""))
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    payload = json.loads(main_module.list_provider_models("all"))

    assert payload["status"] == "ok"
    assert set(payload["providers"].keys()) == {"codex", "gemini", "ollama", "claude_code"}
    assert payload["providers"]["codex"]["catalog"] == ["gpt-5", "o3"]
    assert payload["providers"]["gemini"]["catalog"] == ["gemini-2.5-pro"]
    assert payload["providers"]["claude_code"]["catalog"] == ["sonnet"]
    assert payload["providers"]["ollama"]["status"] == "ok"


def test_list_provider_models_single_provider(monkeypatch):
    monkeypatch.setattr(main_module, "_get_config", _fake_config)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: provider_id != "gemini")

    payload = json.loads(main_module.list_provider_models("gemini"))

    assert payload["status"] == "ok"
    assert set(payload["providers"].keys()) == {"gemini"}
    assert payload["providers"]["gemini"]["configured"] is False
    assert payload["providers"]["gemini"]["model_flag"] == "--model"


def test_list_provider_models_rejects_unknown_provider():
    payload = json.loads(main_module.list_provider_models("bad-provider"))
    assert payload["status"] == "error"
    assert "Unknown provider" in payload["error"]
