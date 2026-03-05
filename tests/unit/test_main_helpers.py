import asyncio
import json
import os
import time

import pytest

from model_bridge import main as main_module
from model_bridge.adapters.sdk_adapter import SDKAdapter


@pytest.fixture
def reset_provider_registry(monkeypatch):
    """Reset PROVIDER_REGISTRY before each test that needs it."""
    monkeypatch.setattr(main_module, "PROVIDER_REGISTRY", None)


def _make_fake_handlers(fake_codex):
    """Create fake provider handlers dict with fake codex handler."""
    return {
        "codex": fake_codex,
        "gemini": lambda *a, **k: "gemini-result",
        "ollama": lambda *a, **k: "ollama-result",
        "claude_code": lambda *a, **k: "claude-code-result",
    }


def test_clean_markdown_fences_extracts_inner_content():
    content = "```python\nprint('ok')\n```"
    assert main_module.clean_markdown_fences(content) == "print('ok')"


def test_clean_markdown_fences_keeps_plain_text():
    content = "plain text"
    assert main_module.clean_markdown_fences(content) == "plain text"


def test_cleanup_old_meta_logs_removes_only_expired_meta_files(tmp_path):
    old_meta = tmp_path / "old.meta.log"
    old_meta.write_text("old", encoding="utf-8")
    new_meta = tmp_path / "new.meta.log"
    new_meta.write_text("new", encoding="utf-8")
    keep_txt = tmp_path / "keep.txt"
    keep_txt.write_text("x", encoding="utf-8")

    old_ts = time.time() - 3600
    os.utime(old_meta, (old_ts, old_ts))

    main_module._cleanup_old_meta_logs(str(tmp_path), ttl_seconds=120)

    assert not old_meta.exists()
    assert new_meta.exists()
    assert keep_txt.exists()


def test_resolve_fallback_chain_deduplicates_and_skips_unknown(monkeypatch):
    models_cfg = {
        "ollama_aliases": {"default": "gpt-oss:20b", "coder": "qwen3-coder-next:Q4_K_M"},
        "ollama_catalog": ["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"],
        "ollama_local_fallback_chain": ["default", "unknown", "coder", "default"],
    }
    monkeypatch.setattr(main_module, "_get_config", lambda: {"models": models_cfg})

    chain = main_module._resolve_fallback_chain("gpt-oss:20b")

    assert chain == ["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"]


def test_save_to_file_rejects_system_path():
    out = main_module.save_to_file("body", "/etc/blocked.txt")
    assert out.startswith("[SECURITY ERROR]")


def test_normalize_model_name_strips_repeated_latest_suffix():
    assert main_module._normalize_model_name("model:latest:latest") == "model"


def test_runtime_is_initialized_lazily_once(monkeypatch):
    calls = {"count": 0}
    fake_config = {"models": {}}

    class _Adapter:
        pass

    class _Failover:
        pass

    class _Sanitizer:
        pass

    def _fake_build_runtime(config=None):
        calls["count"] += 1
        return fake_config, _Adapter(), _Failover(), _Sanitizer()

    monkeypatch.setattr(main_module, "build_runtime", _fake_build_runtime)
    monkeypatch.setattr(main_module, "CONFIG", None)
    monkeypatch.setattr(main_module, "ADAPTER", None)
    monkeypatch.setattr(main_module, "FAILOVER", None)
    monkeypatch.setattr(main_module, "SANITIZER", None)

    assert main_module._get_config() is fake_config
    assert isinstance(main_module._get_adapter(), _Adapter)
    assert isinstance(main_module._get_failover(), _Failover)
    assert calls["count"] == 1


def test_runtime_rebuilds_when_sanitizer_missing(monkeypatch):
    calls = {"count": 0}
    fake_config = {"models": {}}

    class _Adapter:
        pass

    class _Failover:
        pass

    class _Sanitizer:
        pass

    def _fake_build_runtime(config=None):
        calls["count"] += 1
        return fake_config, _Adapter(), _Failover(), _Sanitizer()

    monkeypatch.setattr(main_module, "build_runtime", _fake_build_runtime)
    monkeypatch.setattr(main_module, "CONFIG", fake_config)
    monkeypatch.setattr(main_module, "ADAPTER", _Adapter())
    monkeypatch.setattr(main_module, "FAILOVER", _Failover())
    monkeypatch.setattr(main_module, "SANITIZER", None)

    assert isinstance(main_module._get_sanitizer(), _Sanitizer)
    assert calls["count"] == 1


def test_build_runtime_uses_sdk_adapter_when_transport_mode_sdk():
    config = {
        "commands": {},
        "security": {"block_patterns": ["rm"], "sensitive_paths": ["/etc/"]},
        "runtime": {
            "system_suffix": "",
            "transport_mode": "sdk",
            "apply_system_suffix": {
                "codex": True,
                "gemini": True,
                "ollama": False,
                "claude_code": True,
            },
            "subprocess_timeout_seconds": 120.0,
        },
        "models": {
            "ollama_default_model": "gpt-oss:20b",
            "ollama_aliases": {"default": "gpt-oss:20b"},
            "ollama_catalog": ["gpt-oss:20b"],
            "ollama_final_backup_model": "gpt-oss:20b",
            "ollama_local_fallback_chain": ["default"],
        },
        "routing": {
            "default_chains": {
                "ask_chatgpt_cli": ["codex", "gemini", "ollama"],
                "ask_gemini_cli": ["gemini", "codex", "ollama"],
                "ask_ollama_cloud_fallback": ["codex", "gemini"],
            }
        },
    }

    _, adapter, _, _ = main_module.build_runtime(config=config)

    assert isinstance(adapter, SDKAdapter)


def test_build_runtime_forwards_extra_path_and_env_vars_to_factory(monkeypatch):
    captured: dict = {}

    class FakeAdapter:
        pass

    class FakeFailover:
        def __init__(self, adapter, sanitizer, config):  # pylint: disable=unused-argument
            self.adapter = adapter

    def fake_build_adapter(config, *, env=None, extra_path=None, extra_env_vars=None):
        captured["env"] = env
        captured["extra_path"] = extra_path
        captured["extra_env_vars"] = extra_env_vars
        return FakeAdapter()

    monkeypatch.setattr(main_module, "build_adapter", fake_build_adapter)
    monkeypatch.setattr(main_module, "FailoverManager", FakeFailover)

    config = {
        "commands": {},
        "security": {"block_patterns": ["rm"], "sensitive_paths": ["/etc/"]},
        "runtime": {
            "transport_mode": "subprocess",
            "system_suffix": "",
            "apply_system_suffix": {
                "codex": True,
                "gemini": True,
                "ollama": False,
                "claude_code": True,
            },
            "subprocess_timeout_seconds": 120.0,
            "extra_path": ["/opt/custom/bin"],
            "extra_env_vars": {"GOOGLE_CLOUD_PROJECT": "demo-project"},
        },
        "models": {},
        "routing": {"default_chains": {}},
    }

    _, adapter, _, _ = main_module.build_runtime(config=config)

    assert isinstance(adapter, FakeAdapter)
    assert isinstance(captured["env"], dict)
    assert captured["extra_path"] == ["/opt/custom/bin"]
    assert captured["extra_env_vars"] == {"GOOGLE_CLOUD_PROJECT": "demo-project"}


def test_ask_claude_code_returns_setup_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: False)

    out = asyncio.run(main_module.ask_claude_code("hi"))

    assert "[PROVIDER ERROR]" in out
    assert "not configured" in out


def test_ask_unknown_provider_uses_registry_provider_list(monkeypatch):
    class _FakeRegistry:
        def get(self, provider_id):
            return None

        def list_provider_ids(self):
            return ["claude_code", "codex", "gemini", "ollama"]

    monkeypatch.setattr(main_module, "_get_provider_registry", lambda: _FakeRegistry())

    out = asyncio.run(main_module.ask("hello", provider="unknown-provider"))

    assert "auto|claude_code|codex|gemini|ollama" in out


def test_apply_instruction_preset_strict_once_includes_policy_and_prompt():
    out = main_module._apply_instruction_preset(
        "do work",
        "strict_once",
        "json",
    )

    assert "[MCP EXECUTION POLICY]" in out
    assert "Output valid JSON only." in out
    assert "[User Prompt]\ndo work" in out


def test_ask_applies_instruction_preset_before_dispatch(monkeypatch, reset_provider_registry):
    captured = {}

    async def _fake_codex(prompt, **kwargs):
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: _make_fake_handlers(_fake_codex),
    )

    out = asyncio.run(
        main_module.ask(
            "final task",
            provider="codex",
            instruction_preset="strict_once",
            response_format="json",
        )
    )

    assert out == "ok"
    assert "[MCP EXECUTION POLICY]" in captured["prompt"]
    assert "Output valid JSON only." in captured["prompt"]


def test_ask_uses_runtime_default_instruction_preset_when_omitted(monkeypatch, reset_provider_registry):
    captured = {}

    async def _fake_codex(prompt, **kwargs):
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(
        main_module,
        "_get_provider_handlers",
        lambda: _make_fake_handlers(_fake_codex),
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
                    "instruction_preset": "strict_once",
                    "output_mode": "clean",
                }
            }
        },
    )

    out = asyncio.run(main_module.ask("final task", provider="codex"))

    assert out == "ok"
    assert "[MCP EXECUTION POLICY]" in captured["prompt"]


def test_list_prompt_execution_policy_contract():
    payload = json.loads(main_module.list_prompt_execution_policy())

    assert payload["status"] == "ok"
    assert "strict_once" in payload["instruction_presets"]
