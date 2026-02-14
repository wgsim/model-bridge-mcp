"""Unit tests for error ring buffer and list_last_errors tool."""

from __future__ import annotations

import json

from model_bridge.core import failover_manager as fm_module
from model_bridge import main as main_module


class TestErrorBuffer:
    """Test the error ring buffer in failover_manager."""

    def setup_method(self):
        fm_module._ERROR_BUFFER.clear()

    def test_record_error_adds_entry(self):
        fm_module.record_error("codex", "timeout", "Request timeout", 120.0)
        errors = fm_module.get_last_errors(1)
        assert len(errors) == 1
        assert errors[0]["provider"] == "codex"
        assert errors[0]["error_category"] == "timeout"
        assert errors[0]["raw_message"] == "Request timeout"
        assert errors[0]["timeout_value"] == 120.0

    def test_get_last_errors_returns_most_recent(self):
        for i in range(10):
            fm_module.record_error(f"provider_{i}", "error", f"msg_{i}")
        errors = fm_module.get_last_errors(3)
        assert len(errors) == 3
        assert errors[-1]["provider"] == "provider_9"

    def test_get_last_errors_caps_at_buffer_size(self):
        fm_module.record_error("a", "error", "msg")
        errors = fm_module.get_last_errors(100)
        assert len(errors) == 1

    def test_buffer_maxlen_is_50(self):
        for i in range(60):
            fm_module.record_error(f"p{i}", "error", f"msg_{i}")
        assert len(fm_module._ERROR_BUFFER) == 50

    def test_record_error_truncates_long_message(self):
        long_msg = "x" * 1000
        fm_module.record_error("test", "error", long_msg)
        errors = fm_module.get_last_errors(1)
        assert len(errors[0]["raw_message"]) == 500

    def test_record_error_includes_timestamp(self):
        fm_module.record_error("test", "error", "msg")
        errors = fm_module.get_last_errors(1)
        assert "timestamp" in errors[0]
        assert "T" in errors[0]["timestamp"]

    def test_empty_buffer_returns_empty_list(self):
        errors = fm_module.get_last_errors(5)
        assert errors == []


class TestListLastErrorsTool:
    """Test the list_last_errors MCP tool."""

    def setup_method(self):
        fm_module._ERROR_BUFFER.clear()

    def test_list_last_errors_returns_valid_json(self, monkeypatch):
        monkeypatch.setattr(
            main_module, "_get_config", lambda: {"commands": {}, "runtime": {}}
        )
        fm_module.record_error("codex", "timeout", "test error")
        result = main_module.list_last_errors(5)
        payload = json.loads(result)
        assert payload["status"] == "ok"
        assert payload["count"] == 1
        assert len(payload["errors"]) == 1
