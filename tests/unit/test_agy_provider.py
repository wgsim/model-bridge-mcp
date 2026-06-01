from pathlib import Path
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter
from model_bridge.core.provider_registry import build_default_provider_registry
from model_bridge.main import ask_agy_cli, _ask_with_failover, _dispatch_ask_provider

def _build_agy_config():
    # Keep the dangerous skip-permissions flag explicit here for warning-path coverage.
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
    # agy print mode should keep managed flags before -p and place the prompt last.
    adapter = SubprocessAdapter(
        _build_agy_config()["commands"],
        timeout_seconds=120.0,
        agy_timeout_seconds=300.0,
    )
    completed = subprocess.CompletedProcess(
        args=["agy", "--dangerously-skip-permissions", "--log-file", "/tmp/agy.log", "-p", "what is 1+1"],
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
    prompt_idx = called_cmd.index("-p")
    managed_log_idx = called_cmd.index("--log-file")
    assert called_cmd[0] == "agy"
    assert called_cmd[1] == "--dangerously-skip-permissions"
    assert called_cmd[managed_log_idx + 1]
    assert managed_log_idx < prompt_idx
    assert called_cmd[-2:] == ["-p", "what is 1+1"]

    # Assert Codex recommendation: runtime warning for skip permissions was emitted
    warn_mock.assert_called_once()
    assert "--dangerously-skip-permissions" in warn_mock.call_args.args[0]


def test_agy_temp_log_reader_replaces_invalid_utf8(tmp_path):
    log_path = tmp_path / "agy.log"
    log_path.write_bytes(b"before\xffafter")

    output = SubprocessAdapter._read_temp_log_file(str(log_path))

    assert output == "before�after"


def test_agy_strip_noise_false_preserves_success_stdout():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    stdout = "Loaded cached credentials.\nagy-run-success\n"
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello", strip_noise=False)

    assert ok is True
    assert output == stdout


def test_agy_strip_noise_false_still_classifies_using_cleaned_stdout():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="Loaded cached credentials.\n",
        stderr="non-fatal stderr",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello", strip_noise=False)

    assert ok is False
    assert output == "[PROVIDER ERROR] agy returned no usable stdout response. stderr=non-fatal stderr"


@pytest.mark.parametrize(
    "exec_args",
    [
        ["agy", "-p", "--log-file", "configured.log"],
        ["agy", "-p", "--log-file=configured.log"],
    ],
)
def test_agy_rejects_preconfigured_log_file_flag(exec_args):
    config = _build_agy_config()["commands"]
    config["agy"]["exec"] = exec_args
    adapter = SubprocessAdapter(config)

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run") as run_mock:
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == (
        "Configuration Error: 'agy' command already includes --log-file; "
        "remove it from config because model-bridge manages temporary agy log files."
    )
    run_mock.assert_not_called()


@pytest.mark.parametrize("prompt", ["--log-file", "--log-file=example", "--leading-dash-prompt"])
def test_agy_allows_prompt_values_that_look_like_log_file_flags(prompt):
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "--dangerously-skip-permissions", "--log-file", "/tmp/agy.log", "-p", prompt],
        returncode=0,
        stdout="agy-run-success\n",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed) as run_mock:
        ok, output = adapter.run("agy", [], prompt)

    assert ok is True
    assert output == "agy-run-success"
    run_mock.assert_called_once()
    called_cmd = run_mock.call_args.args[0]
    managed_log_idx = called_cmd.index("--log-file")
    prompt_idx = called_cmd.index("-p")
    assert called_cmd[managed_log_idx + 1]
    assert managed_log_idx < prompt_idx
    assert called_cmd[-2:] == ["-p", prompt]


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
    assert registry.supports_capability("agy", "force_model") is True

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

@pytest.mark.anyio
async def test_ask_agy_cli_rejects_json_format():
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()):
        response = await ask_agy_cli("hello", response_format="json")
        assert "[CAPABILITY_ERROR] Provider 'agy' does not support response_format='json'" in response

@pytest.mark.anyio
async def test_ask_agy_cli_failure_stops_immediately():
    # If agy fails, ask_agy_cli should not attempt failover or Ollama tertiary fallback.
    # It must return the failure immediately due to secondary=None and isolated routing.
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()), \
         patch("model_bridge.adapters.subprocess_adapter.SubprocessAdapter.preflight_check", return_value=(True, "")), \
         patch("model_bridge.adapters.subprocess_adapter.SubprocessAdapter.run_async", return_value=(False, "cli execution failed")):
        response = await ask_agy_cli("hello")
        # Assert routing logs do NOT contain Ollama or Gemini failover attempts
        assert "[1] Primary (agy): Trying..." in response
        assert "    [FAILED]" in response
        assert "Forced Primary (agy) failed" in response
        assert "Secondary" not in response
        assert "Ollama" not in response

@pytest.mark.anyio
async def test_ask_unified_agy_supports_force_model():
    # Verify that force_model=True capability is now supported by agy and validates correctly
    from model_bridge.main import ask
    
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()), \
         patch("model_bridge.main._dispatch_ask_provider", return_value="success-dispatch"):
        response = await ask("hello", provider="agy", force_model=True)
        assert response == "success-dispatch"


def test_agy_zero_exit_with_stderr_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="quota exceeded for current usage tier",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."


def test_agy_zero_exit_with_stdout_quota_marker_in_provider_error_shape_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="ERROR: usage limit reached",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."


def test_agy_zero_exit_with_stdout_error_like_model_output_still_succeeds():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="ERROR: session unavailable",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is True
    assert output == "ERROR: session unavailable"


def test_agy_zero_exit_with_normal_stdout_mentioning_quota_marker_still_succeeds():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="The phrase usage limit reached appears in docs.",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is True
    assert output == "The phrase usage limit reached appears in docs."


def test_agy_zero_exit_with_log_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="",
    )
    log_path = None

    def _fake_run(cmd, *args, **kwargs):
        nonlocal log_path
        log_idx = cmd.index("--log-file")
        log_path = cmd[log_idx + 1]
        assert cmd[cmd.index("-p") + 1] == "hello"
        assert "--dangerously-skip-permissions" in cmd
        assert log_path
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("RESOURCE_EXHAUSTED (code 429): Individual quota reached")
        return completed

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", side_effect=_fake_run):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."
    assert log_path is not None
    assert not Path(log_path).exists()


def test_agy_zero_exit_with_empty_output_is_conservative_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="",
    )
    log_path = None

    def _fake_run(cmd, *args, **kwargs):
        nonlocal log_path
        log_idx = cmd.index("--log-file")
        log_path = cmd[log_idx + 1]
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("non-quota diagnostic only")
        return completed

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", side_effect=_fake_run):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == (
        "[PROVIDER ERROR] agy returned no output "
        "(possible quota/rate-limit or empty provider response)."
    )
    assert log_path is not None
    assert not Path(log_path).exists()


def test_agy_zero_exit_with_nonquota_stderr_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="session unavailable",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy returned no usable stdout response. stderr=session unavailable"


@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_stderr_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            return b"", b"usage limit reached"

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."


@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_nonquota_stderr_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            return b"", b"session unavailable"

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy returned no usable stdout response. stderr=session unavailable"


@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_stdout_error_like_model_output_still_succeeds():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            return b"ERROR: session unavailable", b""

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is True
    assert output == "ERROR: session unavailable"


@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_log_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    log_path = None

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            return b"", b""

    async def _fake_exec(*args, **kwargs):
        nonlocal log_path
        cmd = list(args)
        log_idx = cmd.index("--log-file")
        log_path = cmd[log_idx + 1]
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("RESOURCE_EXHAUSTED (code 429): Individual quota reached")
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."
    assert log_path is not None
    assert not Path(log_path).exists()


@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_empty_output_is_conservative_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    log_path = None

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            return b"", b""

    async def _fake_exec(*args, **kwargs):
        nonlocal log_path
        cmd = list(args)
        log_idx = cmd.index("--log-file")
        log_path = cmd[log_idx + 1]
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("non-quota diagnostic only")
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), \
         patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is False
    assert output == (
        "[PROVIDER ERROR] agy returned no output "
        "(possible quota/rate-limit or empty provider response)."
    )
    assert log_path is not None
    assert not Path(log_path).exists()


@pytest.mark.anyio
async def test_ask_agy_cli_propagates_async_empty_output_provider_error():
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()), \
         patch("model_bridge.adapters.subprocess_adapter.SubprocessAdapter.preflight_check", return_value=(True, "")), \
         patch(
             "model_bridge.adapters.subprocess_adapter.SubprocessAdapter.run_async",
             return_value=(
                 False,
                 "[PROVIDER ERROR] agy returned no output (possible quota/rate-limit or empty provider response).",
             ),
         ):
        response = await ask_agy_cli("hello")

    assert "possible quota/rate-limit or empty provider response" in response
