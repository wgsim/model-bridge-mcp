"""Unit tests for set_config MCP tool."""

from __future__ import annotations

import json

from model_bridge import main as main_module


class TestSetConfig:
    """Test set_config runtime configuration tool."""

    def _mock_config(self):
        return {
            "commands": {
                "codex": {"exec": ["codex"], "health": ["codex", "--version"]},
            },
            "runtime": {
                "subprocess_timeout_seconds": 120.0,
                "ollama_timeout_seconds": 300.0,
                "system_suffix": "",
                "apply_system_suffix": {},
            },
            "security": {"block_patterns": [], "sensitive_paths": []},
            "models": {"ollama_default_model": "llama3.2"},
        }

    def test_set_timeout_updates_config(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        class FakeAdapter:
            timeout_seconds = 120.0

        monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())

        result = main_module.set_config(timeout_seconds=180.0)
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert payload["changes"]["subprocess_timeout_seconds"] == 180.0
        assert payload["effective"]["subprocess_timeout_seconds"] == 180.0

    def test_set_ollama_timeout_updates_config(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        result = main_module.set_config(ollama_timeout_seconds=600.0)
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert payload["changes"]["ollama_timeout_seconds"] == 600.0
        assert payload["effective"]["ollama_timeout_seconds"] == 600.0

    def test_set_both_timeouts(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        class FakeAdapter:
            timeout_seconds = 120.0

        monkeypatch.setattr(main_module, "_get_adapter", lambda: FakeAdapter())

        result = main_module.set_config(timeout_seconds=200.0, ollama_timeout_seconds=500.0)
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert len(payload["changes"]) == 2

    def test_set_config_no_changes(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        result = main_module.set_config()
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert payload["changes"] == {}

    def test_set_config_updates_adapter_timeout(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        class FakeAdapter:
            timeout_seconds = 120.0

        adapter = FakeAdapter()
        monkeypatch.setattr(main_module, "_get_adapter", lambda: adapter)

        main_module.set_config(timeout_seconds=250.0)
        assert adapter.timeout_seconds == 250.0
