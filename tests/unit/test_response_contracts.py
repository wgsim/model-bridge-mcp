import asyncio
import json
import logging
from pathlib import Path

import jsonschema
from model_bridge import main as main_module
from model_bridge.core.failover_manager import FailoverManager


class _ContractAdapter:
    async def run_async(self, service_name, args, input_text):
        if service_name == "codex":
            return False, "primary-fail"
        if service_name == "gemini":
            return True, "secondary-ok"
        return False, "unexpected"


class _AllowSanitizer:
    @staticmethod
    def inspect(prompt, mode="execution"):
        return True, ""


def _config():
    return {
        "routing": {
            "default_chains": {
                "ask_chatgpt_cli": ["codex", "gemini", "ollama"],
                "ask_gemini_cli": ["gemini", "codex", "ollama"],
                "ask_ollama_cloud_fallback": ["codex", "gemini"],
            }
        },
        "models": {
            "ollama_default_model": "gpt-oss:20b",
            "ollama_final_backup_model": "qwen3-coder-next:Q4_K_M",
        },
    }


def test_list_ollama_models_contract_types(monkeypatch):
    monkeypatch.setattr(main_module, "_get_installed_ollama_models", lambda: (["gpt-oss:20b"], ""))
    payload = json.loads(main_module.list_ollama_models())
    schema = json.loads(Path("schemas/list_ollama_models.schema.json").read_text(encoding="utf-8"))

    jsonschema.validate(instance=payload, schema=schema)


def test_failover_manager_emits_structured_telemetry(caplog):
    manager = FailoverManager(adapter=_ContractAdapter(), sanitizer=_AllowSanitizer(), config=_config())

    with caplog.at_level(logging.INFO, logger="model_bridge.telemetry"):
        output = asyncio.run(manager.execute_async("codex", "gemini", "hello", mode="execution"))

    assert "secondary-ok" in output
    assert any("request_id" in rec.message for rec in caplog.records)
    assert any("latency_ms" in rec.message for rec in caplog.records)
    assert any("routing_tier" in rec.message for rec in caplog.records)
