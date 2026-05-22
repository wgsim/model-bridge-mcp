import subprocess
import pytest
from unittest.mock import patch, MagicMock

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter
from model_bridge.core.provider_registry import build_default_provider_registry
from model_bridge.main import ask_agy_cli, _ask_with_failover, _dispatch_ask_provider

def _build_agy_config():
    return {
        "commands": {
            "agy": {
                "exec": ["agy", "-p", "--dangerously-skip-permissions"],
                "health": ["agy", "--version"],
            }
        },
        "runtime": {
            "subprocess_timeout_seconds": 120.0,
            "agy_timeout_seconds": 300.0,
            "transport_mode": "subprocess",
        },
        "models": {
            "agy_model_catalog": ["default"],
        }
    }

def test_agy_subprocess_argument_ordering_and_warning_log():
    # agy expects prompt as trailing positional argument when running non-interactively
    adapter = SubprocessAdapter(
        _build_agy_config()["commands"],
        timeout_seconds=120.0,
        agy_timeout_seconds=300.0,
    )
    completed = subprocess.CompletedProcess(
        args=["agy", "-p", "--dangerously-skip-permissions"],
        returncode=0,
        stdout="agy-run-success\n",
        stderr="warning: non-fatal message",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed) as run_mock, \
         patch("logging.Logger.warning") as warn_mock:
        
        ok, output = adapter.run("agy", [], "what is 1+1")

    assert ok is True
    assert output == "agy-run-success"
    run_mock.assert_called_once()
    called_cmd = run_mock.call_args.args[0]
    # Check flag order: boolean flags first, positional prompt last
    assert called_cmd == ["agy", "-p", "--dangerously-skip-permissions", "what is 1+1"]
    
    # Assert Codex recommendation: runtime warning for skip permissions was emitted
    warn_mock.assert_called_once()
    assert "--dangerously-skip-permissions" in warn_mock.call_args.args[0]

def test_agy_subprocess_applies_correct_timeout():
    adapter = SubprocessAdapter(
        _build_agy_config()["commands"],
        timeout_seconds=120.0,
        agy_timeout_seconds=300.0,
    )
    completed = subprocess.CompletedProcess(
        args=["agy", "-p", "--dangerously-skip-permissions"],
        returncode=0,
        stdout="ok",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed) as run_mock:
        
        ok, output = adapter.run("agy", [], "hello")

    # Assert that the custom 300s timeout is passed, not the generic 120s
    assert run_mock.call_args.kwargs["timeout"] == 300.0

def test_agy_non_zero_exit_capture():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=1,
        stdout="stdout trace",
        stderr="stderr stacktrace",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert "stdout trace" in output
    assert "stderr stacktrace" in output

def test_agy_registry_capabilities():
    config = _build_agy_config()
    registry = build_default_provider_registry(config)
    
    # Codex review: force model must be False for agy registry specs
    assert registry.supports_capability("agy", "json") is False
    assert registry.supports_capability("agy", "stream") is False
    assert registry.supports_capability("agy", "force_model") is False

@pytest.mark.anyio
async def test_ask_agy_cli_rejects_model_override():
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()):
        # Model override check at ask_agy_cli boundary
        response = await ask_agy_cli("hello", model="gpt-4")
        assert "[PROVIDER ERROR] 'agy' does not support model overrides" in response

@pytest.mark.anyio
async def test_ask_agy_cli_rejects_sdk_transport():
    sdk_config = _build_agy_config()
    sdk_config["runtime"]["transport_mode"] = "sdk"

    with patch("model_bridge.main._get_config", return_value=sdk_config):
        # SDK transport check at ask_agy_cli boundary
        response = await ask_agy_cli("hello")
        assert "[PROVIDER ERROR] 'agy' only supports subprocess transport." in response

@pytest.mark.anyio
async def test_dispatch_ask_provider_enforces_bounds():
    # Dispatch boundaries check
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()):
        resp_model = await _dispatch_ask_provider(
            "agy", "hello", save_path=None, force_model=False,
            model="claude-3", reasoning_effort=None,
            options={"timeout_seconds": 120, "max_output_tokens": 0, "response_format": "text", "verbosity": "normal", "stream": False},
            output_mode="clean"
        )
        assert "[PROVIDER ERROR] 'agy' does not support model overrides" in resp_model

    sdk_config = _build_agy_config()
    sdk_config["runtime"]["transport_mode"] = "sdk"
    with patch("model_bridge.main._get_config", return_value=sdk_config):
        resp_sdk = await _dispatch_ask_provider(
            "agy", "hello", save_path=None, force_model=False,
            model="default", reasoning_effort=None,
            options={"timeout_seconds": 120, "max_output_tokens": 0, "response_format": "text", "verbosity": "normal", "stream": False},
            output_mode="clean"
        )
        assert "[PROVIDER ERROR] 'agy' only supports subprocess transport." in resp_sdk
