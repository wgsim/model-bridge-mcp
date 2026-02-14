"""Unit tests for preflight validation in SubprocessAdapter."""

from __future__ import annotations

import subprocess
import time
from unittest.mock import patch

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter


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
