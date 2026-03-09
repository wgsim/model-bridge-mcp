import subprocess
import asyncio
from unittest.mock import patch

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter


def _build_config():
    return {
        "ollama": {
            "exec": ["ollama", "run"],
            "health": ["ollama", "--version"],
        }
    }


def test_run_returns_success_stdout():
    adapter = SubprocessAdapter(_build_config(), env={"X": "1"}, system_suffix=" [suffix]")
    completed = subprocess.CompletedProcess(
        args=["ollama", "run"],
        returncode=0,
        stdout="ok-output\n",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run("ollama", ["llama3.2"], "hello")

    assert ok is True
    assert output == "ok-output"
    run_mock.assert_called_once()
    called_cmd = run_mock.call_args.args[0]
    assert called_cmd == ["ollama", "run", "llama3.2"]
    assert run_mock.call_args.kwargs["input"] == "hello [suffix]"


def test_run_returns_error_when_command_missing():
    adapter = SubprocessAdapter(_build_config())
    with patch("shutil.which", return_value=None):
        ok, output = adapter.run("ollama", [], "hello")
    assert ok is False
    assert "System Error: Command 'ollama' not found." in output
    assert "Install:" in output


def test_run_returns_install_hint_for_known_commands():
    adapter = SubprocessAdapter({"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}})
    with patch("shutil.which", return_value=None):
        ok, output = adapter.run("gemini", [], "hello")
    assert ok is False
    assert "gemini" in output.lower()
    assert "Install:" in output


def test_run_returns_no_install_hint_for_unknown_commands():
    adapter = SubprocessAdapter({"custom": {"exec": ["my_custom_cli"], "health": ["my_custom_cli", "--version"]}})
    with patch("shutil.which", return_value=None):
        ok, output = adapter.run("custom", [], "hello")
    assert ok is False
    assert output == "System Error: Command 'my_custom_cli' not found."


def test_run_returns_combined_output_on_nonzero_exit():
    adapter = SubprocessAdapter(_build_config())
    completed = subprocess.CompletedProcess(
        args=["ollama", "run"],
        returncode=1,
        stdout="partial out\n",
        stderr="failure\n",
    )
    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("ollama", ["llama3.2"], "hello")
    assert ok is False
    assert output == "partial out\nfailure"


def test_run_handles_subprocess_exception():
    adapter = SubprocessAdapter(_build_config())
    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "subprocess.run", side_effect=RuntimeError("boom")
    ):
        ok, output = adapter.run("ollama", ["llama3.2"], "hello")
    assert ok is False
    assert output == "boom"


def test_run_returns_config_error_for_unknown_service():
    adapter = SubprocessAdapter(_build_config())
    ok, output = adapter.run("gemini", [], "hello")
    assert ok is False
    assert output == "Configuration Error: No command defined for gemini"


def test_run_async_returns_success_stdout():
    adapter = SubprocessAdapter(_build_config(), env={"X": "1"}, system_suffix=" [suffix]")

    class _Proc:
        returncode = 0

        async def communicate(self, input=None):
            assert input == b"hello [suffix]"
            return b"async-ok\n", b""

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "asyncio.create_subprocess_exec", side_effect=_fake_exec
    ):
        ok, output = asyncio.run(adapter.run_async("ollama", ["llama3.2"], "hello"))

    assert ok is True
    assert output == "async-ok"


def test_run_async_returns_combined_output_on_nonzero_exit():
    adapter = SubprocessAdapter(_build_config())

    class _Proc:
        returncode = 1

        async def communicate(self, input=None):
            assert input == b"hello"
            return b"partial async\n", b"async fail\n"

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "asyncio.create_subprocess_exec", side_effect=_fake_exec
    ):
        ok, output = asyncio.run(adapter.run_async("ollama", ["llama3.2"], "hello"))

    assert ok is False
    assert output == "partial async\nasync fail"


def test_run_skips_suffix_when_service_flag_is_false():
    adapter = SubprocessAdapter(
        _build_config(),
        system_suffix=" [suffix]",
        apply_system_suffix_for={"ollama": False},
    )
    completed = subprocess.CompletedProcess(
        args=["ollama", "run"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, _ = adapter.run("ollama", ["llama3.2"], "hello")

    assert ok is True
    called_cmd = run_mock.call_args.args[0]
    assert called_cmd == ["ollama", "run", "llama3.2"]
    assert run_mock.call_args.kwargs["input"] == "hello"


def test_run_returns_timeout_error_when_subprocess_hangs():
    adapter = SubprocessAdapter(_build_config(), timeout_seconds=3.0)
    timeout_exc = subprocess.TimeoutExpired(cmd=["ollama", "run"], timeout=3.0)
    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "subprocess.run", side_effect=timeout_exc
    ):
        ok, output = adapter.run("ollama", ["llama3.2"], "hello")

    assert ok is False
    assert output.startswith("Timeout Error: Command 'ollama' exceeded 3.0s")


def test_run_async_returns_timeout_error_when_subprocess_hangs():
    adapter = SubprocessAdapter(_build_config(), timeout_seconds=2.0)

    class _Proc:
        returncode = None

        def __init__(self):
            self.killed = False
            self.waited = False

        async def communicate(self, input=None):  # pragma: no cover
            return b"", b""

        def kill(self):
            self.killed = True

        async def wait(self):
            self.waited = True

    proc = _Proc()

    async def _fake_exec(*args, **kwargs):
        return proc

    async def _fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
        "asyncio.create_subprocess_exec", side_effect=_fake_exec
    ), patch("asyncio.wait_for", side_effect=_fake_wait_for):
        ok, output = asyncio.run(adapter.run_async("ollama", ["llama3.2"], "hello"))

    assert ok is False
    assert output.startswith("Timeout Error: Command 'ollama' exceeded 2.0s")
    assert proc.killed is True


def test_timeout_error_includes_interactive_auth_hint_for_gemini():
    adapter = SubprocessAdapter({"gemini": {"exec": ["gemini"], "health": ["gemini", "--version"]}})
    timeout_exc = subprocess.TimeoutExpired(
        cmd=["gemini"],
        timeout=4.0,
        output="Please visit the following URL to authorize the application",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", side_effect=timeout_exc
    ):
        ok, output = adapter.run("gemini", [], "hello")

    assert ok is False
    assert "Timeout Error: Command 'gemini' exceeded 4.0s" in output
    assert "interactive OAuth login" in output


def test_timeout_error_includes_workspace_trust_hint():
    adapter = SubprocessAdapter({"gemini": {"exec": ["gemini"], "health": ["gemini", "--version"]}})
    timeout_exc = subprocess.TimeoutExpired(
        cmd=["gemini"],
        timeout=4.0,
        output="Please trust this folder to continue",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", side_effect=timeout_exc
    ):
        ok, output = adapter.run("gemini", [], "hello")

    assert ok is False
    assert "workspace trust confirmation" in output


def test_run_passes_prompt_as_argument_for_gemini_p_mode():
    adapter = SubprocessAdapter(
        {"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}},
        system_suffix=" [suffix]",
    )
    completed = subprocess.CompletedProcess(
        args=["gemini", "-p", "hello [suffix]"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run("gemini", [], "hello")

    assert ok is True
    assert output == "ok"
    assert run_mock.call_args.args[0] == ["gemini", "-p", "hello [suffix]"]
    assert run_mock.call_args.kwargs["input"] == ""


def test_run_places_gemini_prompt_before_model_flag_args():
    adapter = SubprocessAdapter(
        {"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}},
        system_suffix=" [suffix]",
    )
    completed = subprocess.CompletedProcess(
        args=["gemini", "-p", "hello [suffix]", "--model", "gemini-2.5-pro"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run("gemini", ["--model", "gemini-2.5-pro"], "hello")

    assert ok is True
    assert output == "ok"
    assert run_mock.call_args.args[0] == [
        "gemini",
        "-p",
        "hello [suffix]",
        "--model",
        "gemini-2.5-pro",
    ]
    assert run_mock.call_args.kwargs["input"] == ""


def test_run_rewrites_codex_reasoning_effort_to_config_override():
    adapter = SubprocessAdapter(
        {"codex": {"exec": ["codex", "exec", "--skip-git-repo-check"], "health": ["codex", "--version"]}},
        system_suffix=" [suffix]",
    )
    completed = subprocess.CompletedProcess(
        args=["codex", "exec", "--skip-git-repo-check", "--model", "gpt-5.4"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/codex"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run(
            "codex",
            ["--model", "gpt-5.4", "--reasoning-effort", "high"],
            "hello",
        )

    assert ok is True
    assert output == "ok"
    assert run_mock.call_args.args[0] == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.4",
        "-c",
        'model_reasoning_effort="high"',
    ]
    assert run_mock.call_args.kwargs["input"] == "hello [suffix]"


def test_run_passes_prompt_as_argument_for_claude_p_mode():
    adapter = SubprocessAdapter(
        {"claude_code": {"exec": ["claude", "-p"], "health": ["claude", "--version"]}},
        system_suffix=" [suffix]",
    )
    completed = subprocess.CompletedProcess(
        args=["claude", "-p", "hello [suffix]"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/claude"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run("claude_code", [], "hello")

    assert ok is True
    assert output == "ok"
    assert run_mock.call_args.args[0] == ["claude", "-p", "hello [suffix]"]
    assert run_mock.call_args.kwargs["input"] == ""


def test_run_passes_effort_flag_for_claude_p_mode():
    adapter = SubprocessAdapter(
        {"claude_code": {"exec": ["claude", "-p"], "health": ["claude", "--version"]}},
        system_suffix=" [suffix]",
    )
    completed = subprocess.CompletedProcess(
        args=["claude", "-p", "--model", "sonnet", "--effort", "high", "hello [suffix]"],
        returncode=0,
        stdout="ok\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/claude"), patch(
        "subprocess.run", return_value=completed
    ) as run_mock:
        ok, output = adapter.run(
            "claude_code",
            ["--model", "sonnet", "--reasoning-effort", "high"],
            "hello",
        )

    assert ok is True
    assert output == "ok"
    assert run_mock.call_args.args[0] == [
        "claude",
        "-p",
        "--model",
        "sonnet",
        "--effort",
        "high",
        "hello [suffix]",
    ]
    assert run_mock.call_args.kwargs["input"] == ""


def test_probe_reasoning_effort_for_claude_subprocess_detects_runtime_unsupported():
    adapter = SubprocessAdapter(
        {"claude_code": {"exec": ["claude", "-p"], "health": ["claude", "--version"]}},
    )
    completed = subprocess.CompletedProcess(
        args=["claude", "-p", "--model", "opus", "--effort", "max", "ping"],
        returncode=1,
        stdout="",
        stderr='Error: Effort level "max" is not available for Claude.ai subscribers.',
    )
    with patch("shutil.which", return_value="/usr/bin/claude"), patch(
        "subprocess.run", return_value=completed
    ):
        status, message = adapter.probe_reasoning_effort("claude_code", "opus", "max")

    assert status == "unsupported"
    assert "not available for Claude.ai subscribers" in message


def test_probe_reasoning_effort_for_claude_subprocess_returns_unknown_on_timeout():
    adapter = SubprocessAdapter(
        {"claude_code": {"exec": ["claude", "-p"], "health": ["claude", "--version"]}},
    )
    timeout_exc = subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=1.5)
    with patch("shutil.which", return_value="/usr/bin/claude"), patch(
        "subprocess.run", side_effect=timeout_exc
    ):
        status, message = adapter.probe_reasoning_effort("claude_code", "opus", "max")

    assert status == "unknown"
    assert "timed out" in message


def test_run_strips_known_gemini_startup_noise_lines():
    adapter = SubprocessAdapter(
        {"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}},
    )
    noisy_output = (
        "Loaded cached credentials.\n"
        "Loading extension: Stitch\n"
        "Server 'playwriter@latest' supports tool updates. Listening for changes...\n"
        "Server 'playwriter@latest' supports resource updates. Listening for changes...\n"
        "Hook registry initialized with 0 hook entries\n"
        "\n"
        "OK\n"
    )
    completed = subprocess.CompletedProcess(
        args=["gemini", "-p", "hello"],
        returncode=0,
        stdout=noisy_output,
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("gemini", [], "hello")

    assert ok is True
    assert output == "OK"


def test_run_keeps_regular_provider_output_lines():
    adapter = SubprocessAdapter(
        {"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}},
    )
    completed = subprocess.CompletedProcess(
        args=["gemini", "-p", "hello"],
        returncode=0,
        stdout="first line\nsecond line\n",
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("gemini", [], "hello")

    assert ok is True
    assert output == "first line\nsecond line"


def test_run_raw_mode_keeps_startup_noise_lines():
    adapter = SubprocessAdapter(
        {"gemini": {"exec": ["gemini", "-p"], "health": ["gemini", "--version"]}},
    )
    noisy_output = (
        "Loaded cached credentials.\n"
        "Hook registry initialized with 0 hook entries\n"
        "OK\n"
    )
    completed = subprocess.CompletedProcess(
        args=["gemini", "-p", "hello"],
        returncode=0,
        stdout=noisy_output,
        stderr="",
    )
    with patch("shutil.which", return_value="/usr/bin/gemini"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("gemini", [], "hello", strip_noise=False)

    assert ok is True
    assert output == noisy_output.strip()


def test_extra_env_vars_are_passed_to_subprocess():
    """Test that extra_env_vars are applied to subprocess environment."""
    adapter = SubprocessAdapter(
        _build_config(),
        env={"PATH": "/usr/bin"},
        extra_env_vars={
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
        },
    )

    # Check that env vars are in adapter's environment
    assert adapter.env["GOOGLE_CLOUD_PROJECT"] == "test-project"
    assert adapter.env["GOOGLE_CLOUD_LOCATION"] == "us-central1"


def test_extra_env_vars_override_existing_values():
    """Test that extra_env_vars take precedence over existing env values."""
    adapter = SubprocessAdapter(
        _build_config(),
        env={"PATH": "/usr/bin", "GOOGLE_CLOUD_PROJECT": "old-project"},
        extra_env_vars={"GOOGLE_CLOUD_PROJECT": "new-project"},
    )

    assert adapter.env["GOOGLE_CLOUD_PROJECT"] == "new-project"


def test_extra_env_vars_empty_by_default():
    """Test that adapter works without extra_env_vars."""
    adapter = SubprocessAdapter(_build_config(), env={"PATH": "/usr/bin"})

    # Should not have provider env vars unless discovered
    assert "GOOGLE_CLOUD_PROJECT" not in adapter.env
