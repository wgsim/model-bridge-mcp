"""Unit tests for enhanced health_check tool."""

from __future__ import annotations

import json
import subprocess

import pytest

from model_bridge import main as main_module


class TestHealthCheck:
    """Test enhanced health_check tool."""

    def test_health_check_returns_valid_json(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                    "gemini": {"exec": ["gemini"], "health": ["gemini", "--version"]},
                    "ollama": {"exec": ["ollama"], "health": ["ollama", "--version"]},
                },
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="v1.0.0\n", stderr=""
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        result = main_module.health_check()
        payload = json.loads(result)

        assert "status" in payload
        assert payload["status"] in ("healthy", "degraded")
        assert "timestamp" in payload
        assert "version" in payload
        assert "providers" in payload
        assert "ollama_running" in payload
        assert "config_defaults" in payload

    def test_health_check_reports_healthy_when_provider_available(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                },
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="v2.0\n", stderr=""
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "healthy"
        assert payload["providers"]["codex"]["available"] is True
        assert "version" in payload["providers"]["codex"]

    def test_health_check_reports_degraded_when_no_provider_available(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                },
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        assert payload["providers"]["codex"]["available"] is False

    def test_health_check_handles_timeout(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                },
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="codex", timeout=5)

        monkeypatch.setattr(subprocess, "run", raise_timeout)
        monkeypatch.setattr("shutil.which", lambda x: f"/usr/bin/{x}")

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        assert payload["providers"]["codex"]["available"] is False
        assert "error" in payload["providers"]["codex"]

    def test_health_check_handles_unconfigured_provider(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        for provider in ["codex", "gemini", "ollama", "claude_code", "agy"]:
            assert provider in payload["providers"]
            assert payload["providers"][provider]["available"] is False
            assert payload["providers"][provider].get("error") == "not configured"

    def test_health_check_shows_install_hint_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )

        result = main_module.health_check()
        payload = json.loads(result)

        # At least some unconfigured providers should have install hints
        has_hint = any(
            "install_hint" in payload["providers"].get(p, {})
            for p in ["codex", "gemini", "ollama", "claude_code", "agy"]
        )
        assert has_hint

    def test_health_check_shows_cli_not_found(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {
                    "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
                },
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )
        monkeypatch.setattr("shutil.which", lambda x: None)

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["providers"]["codex"]["available"] is False
        assert "not found" in payload["providers"]["codex"].get("error", "").lower()

    def test_health_check_includes_config_defaults(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "test",
                },
            },
        )

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["config_defaults"]["subprocess_timeout_seconds"] == 120
        assert payload["config_defaults"]["ollama_timeout_seconds"] == 300
        assert payload["config_defaults"]["system_suffix_enabled"] is True
        assert payload["config_defaults"]["transport_mode"] == "subprocess"

    def test_health_check_uses_runtime_package_version(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )
        monkeypatch.setattr(main_module, "_get_model_bridge_version", lambda: "9.9.9")

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["version"] == "9.9.9"

    def test_health_check_uses_sdk_preflight_in_sdk_mode(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "transport_mode": "sdk",
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )

        class FakeAdapter:
            def __init__(self):
                self.calls: list[str] = []

            def preflight_check(self, service_name: str):
                self.calls.append(service_name)
                if service_name == "ollama":
                    return False, "ollama offline"
                return True, "ok"

        adapter = FakeAdapter()
        monkeypatch.setattr(main_module, "_get_adapter", lambda: adapter)
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: pytest.fail("subprocess.run should not be called in sdk mode"),
        )

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "healthy"
        assert payload["providers"]["codex"]["available"] is True
        assert payload["providers"]["codex"]["transport"] == "sdk"
        assert payload["providers"]["codex"]["auth"] == "configured"
        assert payload["providers"]["ollama"]["available"] is False
        assert payload["providers"]["ollama"]["error"] == "ollama offline"
        assert adapter.calls == ["codex", "gemini", "ollama", "claude_code", "agy"]

    def test_health_check_sdk_mode_degraded_when_auth_missing(self, monkeypatch):
        monkeypatch.setattr(
            main_module,
            "_get_config",
            lambda: {
                "commands": {},
                "runtime": {
                    "transport_mode": "sdk",
                    "subprocess_timeout_seconds": 120,
                    "ollama_timeout_seconds": 300,
                    "system_suffix": "",
                },
            },
        )

        class FakeAdapter:
            def preflight_check(self, service_name: str):  # pylint: disable=unused-argument
                return False, "missing credentials"

        monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())

        result = main_module.health_check()
        payload = json.loads(result)

        assert payload["status"] == "degraded"
        assert payload["providers"]["codex"]["available"] is False
        assert payload["providers"]["codex"]["error"] == "missing credentials"
