import asyncio
import json

import pytest
from model_bridge import main as main_module


class _FakeFailover:
    async def execute_async(self, *args, **kwargs):
        return "hello world from failover"


class _CaptureTimeoutFailover:
    def __init__(self):
        self.last_timeout = None

    async def execute_async(self, *args, **kwargs):
        self.last_timeout = kwargs.get("timeout_seconds")
        return "ok"


class _TypeErrorOnTimeoutFailover:
    async def execute_async(
        self,
        primary,
        secondary,
        prompt,
        mode,
        force_primary=False,
        allow_tertiary=True,
        timeout_seconds=None,
    ):
        if timeout_seconds is not None:
            raise TypeError("internal type error")
        return "unexpected success"


class _CaptureClaudeFailover:
    def __init__(self):
        self.last = {}

    async def execute_async(self, primary, secondary, prompt, mode, **kwargs):
        self.last = {
            "primary": primary,
            "secondary": secondary,
            "prompt": prompt,
            "mode": mode,
            "force_primary": kwargs.get("force_primary"),
            "timeout_seconds": kwargs.get("timeout_seconds"),
        }
        return "claude ok"


def test_ask_chatgpt_cli_supports_json_format(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    out = asyncio.run(
        main_module.ask_chatgpt_cli(
            "hi",
            response_format="json",
            timeout_seconds=10,
            max_output_tokens=4,
            verbosity="brief",
        )
    )
    payload = json.loads(out)
    assert payload["provider"] == "codex"
    assert "content" in payload


def test_ask_chatgpt_cli_passes_timeout_without_mutating_adapter(monkeypatch):
    fake_failover = _CaptureTimeoutFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)

    def _forbidden_adapter_access():
        raise AssertionError("adapter timeout should not be mutated in ask_chatgpt_cli")

    monkeypatch.setattr(main_module, "_get_adapter", _forbidden_adapter_access)
    out = asyncio.run(main_module.ask_chatgpt_cli("hi", timeout_seconds=7))
    assert out == "ok"
    assert fake_failover.last_timeout == 7


def test_ask_chatgpt_cli_does_not_swallow_internal_typeerror(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _TypeErrorOnTimeoutFailover())
    with pytest.raises(TypeError, match="internal type error"):
        asyncio.run(main_module.ask_chatgpt_cli("hi", timeout_seconds=7))


def test_ask_gemini_cli_rejects_invalid_verbosity():
    with pytest.raises(ValueError, match="verbosity must be one of"):
        asyncio.run(main_module.ask_gemini_cli("hi", verbosity="invalid"))


def test_ask_claude_code_supports_json_and_force_model(monkeypatch):
    fake_failover = _CaptureClaudeFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    out = asyncio.run(
        main_module.ask_claude_code(
            "review me",
            force_model=True,
            timeout_seconds=9,
            response_format="json",
        )
    )
    payload = json.loads(out)
    assert payload["provider"] == "claude_code"
    assert payload["content"] == "claude ok"
    assert fake_failover.last["primary"] == "claude_code"
    assert fake_failover.last["secondary"] == "codex"
    assert fake_failover.last["force_primary"] is True
    assert fake_failover.last["timeout_seconds"] == 9
