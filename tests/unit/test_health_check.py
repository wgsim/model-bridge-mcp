"""Unit tests for health_check tool (P2-2)."""

from __future__ import annotations

import json
import pytest

from model_bridge import main as main_module


class TestHealthCheck:
    """Test health_check tool."""

    def test_health_check_returns_valid_json(self, monkeypatch):
        """Test that health_check returns valid JSON."""
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                    "gemini": {"exec": ["gemini"], "health": ["gemini", "--version"]},
                    "ollama": {"exec": ["ollama"], "health": ["ollama", "--version"]},
                }
            },
        )

        # Mock subprocess to avoid actual command execution
        import subprocess
        mock_result = type("MockResult", (), {"returncode": 0})()
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)

        result = main_module.health_check()
        payload = json.loads(result)

        assert "status" in payload
        assert payload["status"] in ("healthy", "degraded")
        assert "timestamp" in payload
        assert "version" in payload
        assert "providers" in payload

    def test_health_check_reports_healthy_when_provider_available(self, monkeypatch):
        """Test that status is healthy when at least one provider is available."""
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                }
            },
        )

        import subprocess
        mock_result = type("MockResult", (), {"returncode": 0})()
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "healthy"
        assert payload["providers"]["codex"]["available"] is True

    def test_health_check_reports_degraded_when_no_provider_available(self, monkeypatch):
        """Test that status is degraded when no provider is available."""
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                }
            },
        )

        import subprocess
        mock_result = type("MockResult", (), {"returncode": 1})()
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        assert payload["providers"]["codex"]["available"] is False

    def test_health_check_handles_timeout(self, monkeypatch):
        """Test that health_check handles command timeout gracefully."""
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                }
            },
        )

        import subprocess
        import subprocess as sp_module

        def raise_timeout(*args, **kwargs):
            raise sp_module.TimeoutExpired(cmd="codex", timeout=5)

        monkeypatch.setattr(subprocess, "run", raise_timeout)

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        assert payload["providers"]["codex"]["available"] is False
        assert "error" in payload["providers"]["codex"]

    def test_health_check_handles_unconfigured_provider(self, monkeypatch):
        """Test that health_check handles unconfigured providers."""
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {"commands": {}},
        )

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        for provider in ["codex", "gemini", "ollama", "claude_code"]:
            assert provider in payload["providers"]
            assert payload["providers"][provider]["available"] is False
            assert payload["providers"][provider].get("error") == "not configured"
