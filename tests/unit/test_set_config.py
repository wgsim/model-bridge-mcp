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
                "transport_mode": "subprocess",
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
        assert payload["effective"]["transport_mode"] == "subprocess"
        assert payload["changes"]["subprocess_timeout_seconds"] == 180.0
        assert payload["effective"]["subprocess_timeout_seconds"] == 180.0

    def test_set_ollama_timeout_updates_config(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        result = main_module.set_config(ollama_timeout_seconds=600.0)
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert payload["effective"]["transport_mode"] == "subprocess"
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
        assert payload["effective"]["transport_mode"] == "subprocess"

    def test_set_config_updates_adapter_timeout(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        class FakeAdapter:
            timeout_seconds = 120.0

        adapter = FakeAdapter()
        monkeypatch.setattr(main_module, "_get_adapter", lambda: adapter)

        main_module.set_config(timeout_seconds=250.0)
        assert adapter.timeout_seconds == 250.0

    def test_set_config_transport_mode_rebuilds_adapter(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        class FakeAdapter:
            timeout_seconds = 120.0

        class FakeSanitizer:
            def inspect(self, prompt, mode="execution"):
                return True, ""

        fake_sanitizer = FakeSanitizer()
        monkeypatch.setattr(main_module, "_get_sanitizer", lambda: fake_sanitizer)

        captured = {}

        class FakeFailover:
            def __init__(self, adapter, sanitizer, config):  # pylint: disable=unused-argument
                self.adapter = adapter
                captured["sanitizer"] = sanitizer

        monkeypatch.setattr(main_module, "build_adapter", lambda cfg, env=None: FakeAdapter())
        monkeypatch.setattr(main_module, "FailoverManager", FakeFailover)

        result = main_module.set_config(transport_mode="sdk")
        payload = json.loads(result)

        assert payload["status"] == "ok"
        assert payload["changes"]["transport_mode"] == "sdk"
        assert payload["effective"]["transport_mode"] == "sdk"
        assert config["runtime"]["transport_mode"] == "sdk"
        assert captured["sanitizer"] is fake_sanitizer, "sanitizer must be an instance, not a class"

    def test_set_config_rejects_invalid_transport_mode(self, monkeypatch):
        config = self._mock_config()
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        result = main_module.set_config(transport_mode="cli")
        payload = json.loads(result)

        assert payload["status"] == "error"
        assert "transport_mode must be one of" in payload["error"]

    def test_set_config_invalid_transport_mode_is_atomic(self, monkeypatch):
        config = self._mock_config()
        before_runtime = dict(config["runtime"])
        monkeypatch.setattr(main_module, "_get_config", lambda: config)

        result = main_module.set_config(timeout_seconds=180.0, transport_mode="cli")
        payload = json.loads(result)

        assert payload["status"] == "error"
        assert config["runtime"]["transport_mode"] == before_runtime["transport_mode"]
        assert (
            config["runtime"]["subprocess_timeout_seconds"]
            == before_runtime["subprocess_timeout_seconds"]
        )
