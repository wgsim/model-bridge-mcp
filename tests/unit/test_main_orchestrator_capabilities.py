import json

from model_bridge import main as main_module


def test_list_orchestrator_capabilities_contract():
    payload = json.loads(main_module.list_orchestrator_capabilities())

    assert payload["status"] == "ok"
    assert payload["recommended_policy"]["parallel_execution_owner"] == "mcp_internal"
    assert set(payload["orchestrators"].keys()) == {"codex", "gemini", "claude_code"}
    assert "fallback_rule" in payload
