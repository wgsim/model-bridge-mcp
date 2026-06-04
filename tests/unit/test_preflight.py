"""Unit tests for preflight validation in SubprocessAdapter."""

from __future__ import annotations

import os
import subprocess
import time
from unittest.mock import patch

from model_bridge.adapters.subprocess_adapter import (
    SubprocessAdapter,
    _discover_provider_env_vars,
)


def _build_config():
    return {
        "ollama": {
            "exec": ["ollama", "run"],
            "health": ["ollama", "--version"],
        },
        "gemini": {
            "exec": ["gemini", "-p"],
            "health": ["gemini", "--version"],
        },
    }


class TestPreflightCheck:
    """Test preflight_check method."""

    def test_preflight_passes_when_healthy(self):
        adapter = SubprocessAdapter(_build_config())
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", return_value=completed
        ):
            ok, msg = adapter.preflight_check("ollama")
        assert ok is True
        assert msg == "ok"

    def test_preflight_fails_when_not_installed(self):
        adapter = SubprocessAdapter(_build_config())
        with patch("shutil.which", return_value=None):
            ok, msg = adapter.preflight_check("ollama")
        assert ok is False
        assert "not found" in msg

    def test_preflight_fails_when_health_check_fails(self):
        adapter = SubprocessAdapter(_build_config())
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"")
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", return_value=completed
        ):
            ok, msg = adapter.preflight_check("ollama")
        assert ok is False
        assert "Health check failed" in msg

    def test_preflight_fails_when_health_check_times_out(self):
        adapter = SubprocessAdapter(_build_config())
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=5)
        ):
            ok, msg = adapter.preflight_check("ollama")
        assert ok is False
        assert "timed out" in msg

    def test_preflight_fails_for_unconfigured_service(self):
        adapter = SubprocessAdapter(_build_config())
        ok, msg = adapter.preflight_check("unknown_service")
        assert ok is False
        assert "No command configured" in msg

    def test_preflight_uses_cache(self):
        adapter = SubprocessAdapter(_build_config())
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", return_value=completed
        ) as run_mock:
            ok1, _ = adapter.preflight_check("ollama")
            ok2, _ = adapter.preflight_check("ollama")
        assert ok1 is True
        assert ok2 is True
        # Should only call subprocess.run once due to cache
        assert run_mock.call_count == 1

    def test_preflight_cache_expires(self):
        adapter = SubprocessAdapter(_build_config())
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", return_value=completed
        ) as run_mock:
            ok1, _ = adapter.preflight_check("ollama")
            # Manually expire the cache
            for key in adapter._preflight_cache:
                ok_val, msg_val, _ = adapter._preflight_cache[key]
                adapter._preflight_cache[key] = (ok_val, msg_val, time.time() - 120)
            ok2, _ = adapter.preflight_check("ollama")
        assert ok1 is True
        assert ok2 is True
        assert run_mock.call_count == 2

    def test_preflight_includes_install_hint(self):
        adapter = SubprocessAdapter(_build_config())
        with patch("shutil.which", return_value=None):
            ok, msg = adapter.preflight_check("ollama")
        assert ok is False
        assert "Install:" in msg or "brew" in msg.lower() or "ollama" in msg.lower()

    def test_preflight_uses_adapter_path_for_cli_lookup(self):
        adapter = SubprocessAdapter(_build_config(), env={"PATH": "/usr/bin"})
        adapter.env["PATH"] = "/opt/custom/bin:/usr/bin"
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

        def fake_which(command, path=None):
            assert command == "ollama"
            assert path == adapter.env["PATH"]
            return "/opt/custom/bin/ollama"

        with patch("shutil.which", side_effect=fake_which), patch(
            "subprocess.run", return_value=completed
        ):
            ok, msg = adapter.preflight_check("ollama")

        assert ok is True
        assert msg == "ok"

    def test_preflight_passes_adapter_env_to_health_check(self):
        adapter = SubprocessAdapter(
            _build_config(),
            env={"PATH": "/usr/bin", "OPENAI_API_KEY": "token-from-adapter"},
        )
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

        def fake_run(*args, **kwargs):
            assert kwargs["env"] == adapter.env
            return completed

        with patch("shutil.which", return_value="/usr/bin/ollama"), patch(
            "subprocess.run", side_effect=fake_run
        ):
            ok, msg = adapter.preflight_check("ollama")

        assert ok is True
        assert msg == "ok"

    def test_preflight_uses_subprocess_exec_path_when_env_omits_path(self):
        adapter = SubprocessAdapter(_build_config(), env={})
        adapter.env.pop("PATH", None)
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        expected_path = os.pathsep.join(os.get_exec_path(adapter.env))

        def fake_which(command, path=None):
            assert command == "ollama"
            assert path == expected_path
            return "/usr/bin/ollama"

        with patch("shutil.which", side_effect=fake_which), patch(
            "subprocess.run", return_value=completed
        ):
            ok, msg = adapter.preflight_check("ollama")

        assert ok is True
        assert msg == "ok"


def test_discover_provider_env_vars_collects_multiple_values():
    completed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=google-token\nOPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {
        "GOOGLE_API_KEY": "google-token",
        "OPENAI_API_KEY": "openai-token",
    }
    run_mock.assert_called_once()
    run_args, run_kwargs = run_mock.call_args
    assert run_args[0][1] == "-lc"
    command = run_args[0][2]
    assert "GOOGLE_API_KEY" in command
    assert "OPENAI_API_KEY" in command
    assert run_kwargs["capture_output"] is True
    assert run_kwargs["text"] is True
    assert run_kwargs["timeout"] == 1.0
    assert run_kwargs["check"] is False


def test_discover_provider_env_vars_ignores_blank_values():
    completed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=\nOPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed):
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"OPENAI_API_KEY": "openai-token"}


def test_discover_provider_env_vars_falls_back_to_next_shell_after_non_zero_result():
    failed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=1,
        stdout="",
        stderr="shell failed",
    )
    succeeded = subprocess.CompletedProcess(
        args=["zsh", "-lc", "env-check"],
        returncode=0,
        stdout="OPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", side_effect=[failed, succeeded]) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"OPENAI_API_KEY": "openai-token"}
    assert run_mock.call_count == 2
    assert run_mock.call_args_list[0].args[0][0] == "bash"
    assert run_mock.call_args_list[1].args[0][0] == "zsh"


def test_discover_provider_env_vars_falls_back_to_next_shell_after_empty_output():
    empty = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="",
        stderr="",
    )
    succeeded = subprocess.CompletedProcess(
        args=["zsh", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=google-token\n",
        stderr="",
    )

    with patch("subprocess.run", side_effect=[empty, succeeded]) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"GOOGLE_API_KEY": "google-token"}
    assert run_mock.call_count == 2
