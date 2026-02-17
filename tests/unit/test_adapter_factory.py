import asyncio

import pytest

from model_bridge.adapters.factory import build_adapter
from model_bridge.adapters.sdk_adapter import SDKAdapter
from model_bridge.adapters.subprocess_adapter import SubprocessAdapter


def _base_config() -> dict:
    return {
        "commands": {
            "codex": {"exec": ["codex", "exec"], "health": ["codex", "--version"]},
            "gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]},
            "ollama": {"exec": ["ollama", "run"], "health": ["ollama", "--version"]},
            "claude_code": {"exec": ["claude", "-p"], "health": ["claude", "--version"]},
        },
        "models": {
            "ollama_default_model": "gpt-oss:20b",
            "ollama_aliases": {"default": "gpt-oss:20b"},
            "codex_model_catalog": ["gpt-5.2-codex"],
        },
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
        },
    }


def test_build_adapter_selects_subprocess_mode():
    adapter = build_adapter(_base_config(), env={})
    assert isinstance(adapter, SubprocessAdapter)


def test_build_adapter_selects_sdk_mode():
    config = _base_config()
    config["runtime"]["transport_mode"] = "sdk"
    adapter = build_adapter(config, env={})
    assert isinstance(adapter, SDKAdapter)


def test_build_adapter_rejects_unknown_mode():
    config = _base_config()
    config["runtime"]["transport_mode"] = "invalid-mode"
    with pytest.raises(ValueError, match="Unsupported runtime.transport_mode"):
        build_adapter(config, env={})


def test_sdk_adapter_returns_auth_error_for_codex_without_credentials():
    config = _base_config()
    config["runtime"]["transport_mode"] = "sdk"
    adapter = build_adapter(config, env={})

    ok, output = asyncio.run(adapter.run_async("codex", ["--model", "gpt-5.2"], "hello"))

    assert ok is False
    assert "[SDK AUTH ERROR]" in output


def test_sdk_adapter_returns_not_implemented_for_non_codex_provider():
    config = _base_config()
    config["runtime"]["transport_mode"] = "sdk"
    adapter = build_adapter(config, env={})

    ok, output = asyncio.run(adapter.run_async("custom_provider", [], "hello"))

    assert ok is False
    assert "[SDK NOT IMPLEMENTED]" in output
    assert "provider=custom_provider" in output
