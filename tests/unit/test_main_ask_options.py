import asyncio
import json

import pytest
from model_bridge import main as main_module


class _FakeFailover:
    async def execute_async(self, *args, **kwargs):
        return json.dumps({
            "provider": "codex",
            "cached": False,
            "content": "hello world from failover",
            "meta": {"verbosity": "brief", "max_output_tokens": 4, "stream": False},
        })


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


class _CaptureProviderArgsFailover:
    def __init__(self):
        self.last = {}

    async def execute_async(self, primary, secondary, prompt, mode, **kwargs):
        self.last = {
            "primary": primary,
            "secondary": secondary,
            "provider_args": kwargs.get("provider_args"),
        }
        return "ok"


class _TrialSequenceFailover:
    def __init__(self):
        self.calls = []

    async def execute_async(self, primary, secondary, prompt, mode, **kwargs):
        provider_args = kwargs.get("provider_args")
        self.calls.append(provider_args)
        if provider_args:
            return "[Task Execution Failed]\nmodel not found"
        return "ok-without-model"


class _NonModelFailureTrialFailover:
    def __init__(self):
        self.calls = []

    async def execute_async(self, primary, secondary, prompt, mode, **kwargs):
        provider_args = kwargs.get("provider_args")
        self.calls.append(provider_args)
        return "[Task Execution Failed]\nauthentication failed"


def test_ask_chatgpt_cli_supports_json_format(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)
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


def test_ask_rejects_invalid_output_mode():
    with pytest.raises(ValueError, match="output_mode must be one of"):
        asyncio.run(main_module.ask("hi", output_mode="invalid"))


def test_ask_claude_code_supports_json_and_force_model(monkeypatch):
    fake_failover = _CaptureClaudeFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    # Mock adapter to pass preflight check
    class FakeAdapter:
        def preflight_check(self, provider):
            return True, ""

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())

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


def test_ask_chatgpt_cli_passes_model_override_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)

    out = asyncio.run(main_module.ask_chatgpt_cli("hi", model="gpt-5"))

    assert out == "ok"
    assert fake_failover.last["primary"] == "codex"
    assert fake_failover.last["provider_args"] == {"codex": ["--model", "gpt-5"]}


def test_ask_chatgpt_cli_passes_reasoning_effort_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)

    out = asyncio.run(
        main_module.ask_chatgpt_cli(
            "hi",
            model="gpt-5.4",
            reasoning_effort="high",
        )
    )

    assert out == "ok"
    assert fake_failover.last["primary"] == "codex"
    assert fake_failover.last["provider_args"] == {
        "codex": ["--model", "gpt-5.4", "--reasoning-effort", "high"]
    }


def test_ask_chatgpt_cli_rejects_reasoning_effort_for_unsupported_codex_model():
    with pytest.raises(ValueError, match="does not support reasoning_effort"):
        asyncio.run(
            main_module.ask_chatgpt_cli(
                "hi",
                model="gpt-5.1-codex-mini",
                reasoning_effort="high",
            )
        )


def test_ask_chatgpt_cli_filters_codex_catalog_by_reasoning_effort(monkeypatch):
    fake_failover = _TrialSequenceFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "models": {
                "codex_model_catalog": ["gpt-5.1-codex-mini", "gpt-5.4", "gpt-5.3-codex"],
            },
            "runtime": {
                "ask_defaults": {
                    "timeout_seconds": 120,
                    "max_output_tokens": 0,
                    "response_format": "text",
                    "verbosity": "normal",
                    "stream": False,
                }
            },
        },
    )

    out = asyncio.run(main_module.ask_chatgpt_cli("hi", reasoning_effort="none"))

    assert out.startswith("[Task Execution Failed]")
    assert fake_failover.calls == [
        {"codex": ["--model", "gpt-5.4", "--reasoning-effort", "none"]},
    ]


def test_ask_chatgpt_cli_keeps_codex_primary_even_if_weighted_selector_differs(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: "gemini")

    class FakeAdapter:
        def preflight_check(self, provider):
            return True, ""

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())
    out = asyncio.run(main_module.ask_chatgpt_cli("hi", model="gpt-5"))

    assert out == "ok"
    assert fake_failover.last["primary"] == "codex"
    assert fake_failover.last["provider_args"] == {"codex": ["--model", "gpt-5"]}


def test_ask_gemini_cli_passes_model_override_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    # Ensure weighted routing returns None to use default provider
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)

    out = asyncio.run(main_module.ask_gemini_cli("hi", model="gemini-2.5-pro"))

    assert out == "ok"
    assert fake_failover.last["primary"] == "gemini"
    assert fake_failover.last["provider_args"] == {"gemini": ["--model", "gemini-2.5-pro"]}


def test_ask_gemini_cli_passes_reasoning_effort_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: None)

    class FakeSdkAdapter:
        def preflight_check(self, provider):
            return True, ""

        def probe_reasoning_effort(self, service_name, model_name, reasoning_effort):
            return "supported", "ok"

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeSdkAdapter())

    out = asyncio.run(
        main_module.ask_gemini_cli(
            "hi",
            model="gemini-3.1-pro-preview",
            reasoning_effort="high",
        )
    )

    assert out == "ok"
    assert fake_failover.last["provider_args"] == {
        "gemini": ["--model", "gemini-3.1-pro-preview", "--reasoning-effort", "high"]
    }


def test_ask_gemini_cli_rejects_reasoning_effort_for_gemini_2_5():
    with pytest.raises(ValueError, match="does not support reasoning_effort"):
        asyncio.run(
            main_module.ask_gemini_cli(
                "hi",
                model="gemini-2.5-pro",
                reasoning_effort="high",
            )
        )


def test_ask_gemini_cli_rejects_reasoning_effort_for_subprocess_transport(monkeypatch):
    class FakeSubprocessAdapter:
        def preflight_check(self, provider):
            return True, ""

        def probe_reasoning_effort(self, service_name, model_name, reasoning_effort):
            return "unsupported", "Gemini reasoning_effort is sdk-only in this MCP."

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeSubprocessAdapter())

    with pytest.raises(ValueError, match="sdk-only"):
        asyncio.run(
            main_module.ask_gemini_cli(
                "hi",
                model="gemini-3.1-pro-preview",
                reasoning_effort="high",
            )
        )


def test_ask_gemini_cli_keeps_gemini_primary_even_if_weighted_selector_differs(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_select_provider_by_weight", lambda chain: "codex")

    class FakeAdapter:
        def preflight_check(self, provider):
            return True, ""

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())
    out = asyncio.run(main_module.ask_gemini_cli("hi", model="gemini-2.5-pro"))

    assert out == "ok"
    assert fake_failover.last["primary"] == "gemini"
    assert fake_failover.last["provider_args"] == {
        "gemini": ["--model", "gemini-2.5-pro"]
    }


def test_ask_claude_code_passes_model_override_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    out = asyncio.run(main_module.ask_claude_code("hi", model="sonnet"))

    assert out == "ok"
    assert fake_failover.last["primary"] == "claude_code"
    assert fake_failover.last["provider_args"] == {
        "claude_code": ["--model", "sonnet"]
    }


def test_ask_claude_code_passes_reasoning_effort_to_primary_provider(monkeypatch):
    fake_failover = _CaptureProviderArgsFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    out = asyncio.run(
        main_module.ask_claude_code(
            "hi",
            model="sonnet",
            reasoning_effort="high",
        )
    )

    assert out == "ok"
    assert fake_failover.last["provider_args"] == {
        "claude_code": ["--model", "sonnet", "--reasoning-effort", "high"]
    }


def test_ask_claude_code_rejects_reasoning_effort_for_haiku():
    with pytest.raises(ValueError, match="does not support reasoning_effort"):
        asyncio.run(
            main_module.ask_claude_code(
                "hi",
                model="haiku",
                reasoning_effort="high",
            )
        )


def test_ask_claude_code_rejects_max_reasoning_effort_for_sonnet():
    with pytest.raises(ValueError, match="does not support reasoning_effort='max'"):
        asyncio.run(
            main_module.ask_claude_code(
                "hi",
                model="sonnet",
                reasoning_effort="max",
            )
        )


def test_ask_claude_code_rejects_runtime_unsupported_reasoning_effort(monkeypatch):
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)

    class FakeAdapter:
        def preflight_check(self, provider):
            return True, ""

        def probe_reasoning_effort(self, service_name, model_name, reasoning_effort):
            return "unsupported", 'Effort level "max" is not available for Claude.ai subscribers.'

    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())

    with pytest.raises(ValueError, match="not available for Claude.ai subscribers"):
        asyncio.run(
            main_module.ask_claude_code(
                "hi",
                model="opus",
                reasoning_effort="max",
            )
        )


def test_ask_claude_code_filters_catalog_by_reasoning_effort(monkeypatch):
    fake_failover = _TrialSequenceFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(main_module, "_is_provider_configured", lambda provider_id: True)
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "models": {"claude_code_model_catalog": ["haiku", "sonnet", "opus"]},
            "runtime": {
                "ask_defaults": {
                    "timeout_seconds": 120,
                    "max_output_tokens": 0,
                    "response_format": "text",
                    "verbosity": "normal",
                    "stream": False,
                }
            },
        },
    )
    monkeypatch.setattr(
        main_module,
        "_get_adapter",
        lambda: type(
            "FakeAdapter",
            (),
            {
                "preflight_check": lambda self, provider: (True, ""),
                "probe_reasoning_effort": lambda self, service_name, model_name, reasoning_effort: (
                    "unsupported",
                    'Effort level "max" is not available for Claude.ai subscribers.',
                ) if model_name == "opus" else ("supported", "ok"),
            },
        )(),
    )

    with pytest.raises(ValueError, match="Runtime probe rejected"):
        asyncio.run(main_module.ask_claude_code("hi", reasoning_effort="max"))


def test_ask_gemini_cli_falls_back_to_no_model_after_catalog_failures(monkeypatch):
    fake_failover = _TrialSequenceFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "models": {"gemini_model_catalog": ["gemini-2.5-flash", "gemini-2.5-pro"]},
            "runtime": {"ask_defaults": {"timeout_seconds": 120, "max_output_tokens": 0, "response_format": "text", "verbosity": "normal", "stream": False}},
        },
    )

    out = asyncio.run(main_module.ask_gemini_cli("hi"))

    assert out == "ok-without-model"
    assert fake_failover.calls == [
        {"gemini": ["--model", "gemini-2.5-flash"]},
        {"gemini": ["--model", "gemini-2.5-pro"]},
        None,
    ]


def test_ask_gemini_cli_does_not_retry_models_on_non_model_failure(monkeypatch):
    fake_failover = _NonModelFailureTrialFailover()
    monkeypatch.setattr(main_module, "_get_failover", lambda: fake_failover)
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "models": {"gemini_model_catalog": ["gemini-2.5-flash", "gemini-2.5-pro"]},
            "runtime": {"ask_defaults": {"timeout_seconds": 120, "max_output_tokens": 0, "response_format": "text", "verbosity": "normal", "stream": False}},
        },
    )

    out = asyncio.run(main_module.ask_gemini_cli("hi"))

    assert out.startswith("[Task Execution Failed]")
    assert fake_failover.calls == [{"gemini": ["--model", "gemini-2.5-flash"]}]


def test_ask_unified_codex_passes_reasoning_effort(monkeypatch):
    captured = {}

    async def _fake_dispatch(provider_id, prompt, **kwargs):
        captured["provider_id"] = provider_id
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _fake_dispatch)

    out = asyncio.run(
        main_module.ask(
            "hi",
            provider="codex",
            model="gpt-5.4",
            reasoning_effort="low",
        )
    )

    assert out == "ok"
    assert captured["provider_id"] == "codex"
    assert captured["kwargs"]["model"] == "gpt-5.4"
    assert captured["kwargs"]["reasoning_effort"] == "low"


def test_ask_unified_claude_passes_reasoning_effort(monkeypatch):
    captured = {}

    async def _fake_dispatch(provider_id, prompt, **kwargs):
        captured["provider_id"] = provider_id
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _fake_dispatch)

    out = asyncio.run(
        main_module.ask(
            "hi",
            provider="claude_code",
            model="sonnet",
            reasoning_effort="medium",
        )
    )

    assert out == "ok"
    assert captured["provider_id"] == "claude_code"
    assert captured["kwargs"]["model"] == "sonnet"
    assert captured["kwargs"]["reasoning_effort"] == "medium"


def test_ask_unified_gemini_passes_reasoning_effort(monkeypatch):
    captured = {}

    async def _fake_dispatch(provider_id, prompt, **kwargs):
        captured["provider_id"] = provider_id
        captured["kwargs"] = kwargs
        return "ok"

    class FakeSdkAdapter:
        def probe_reasoning_effort(self, service_name, model_name, reasoning_effort):
            return "supported", "ok"

    monkeypatch.setattr(main_module, "_dispatch_ask_provider", _fake_dispatch)
    monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeSdkAdapter())

    out = asyncio.run(
        main_module.ask(
            "hi",
            provider="gemini",
            model="gemini-3.1-pro-preview",
            reasoning_effort="high",
        )
    )

    assert out == "ok"
    assert captured["provider_id"] == "gemini"
    assert captured["kwargs"]["model"] == "gemini-3.1-pro-preview"
    assert captured["kwargs"]["reasoning_effort"] == "high"
