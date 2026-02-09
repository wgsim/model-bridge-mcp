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
    assert called_cmd == ["ollama", "run", "llama3.2", "hello [suffix]"]


def test_run_returns_error_when_command_missing():
    adapter = SubprocessAdapter(_build_config())
    with patch("shutil.which", return_value=None):
        ok, output = adapter.run("ollama", [], "hello")
    assert ok is False
    assert output == "System Error: Command 'ollama' not found."


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

        async def communicate(self):
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

        async def communicate(self):
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
    assert called_cmd == ["ollama", "run", "llama3.2", "hello"]
