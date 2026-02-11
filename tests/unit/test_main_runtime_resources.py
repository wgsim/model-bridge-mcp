import json

from model_bridge import main as main_module


def test_list_runtime_resources_returns_contract(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_compute_ollama_batch_concurrency",
        lambda model, requested: {
            "resolved_model": "gpt-oss:20b",
            "applied_max_concurrency": 1,
            "reason": "test",
            "resources": {
                "ram_total_gb": 64.0,
                "ram_free_gb": 32.0,
                "vram_total_gb": None,
                "vram_free_gb": None,
                "vram_detector": "unavailable",
            },
        },
    )

    payload = json.loads(
        main_module.list_runtime_resources(model="default", requested_max_concurrency=4)
    )

    assert payload["status"] == "ok"
    assert payload["requested_model"] == "default"
    assert payload["requested_max_concurrency"] == 4
    assert payload["ollama_recommendation"]["applied_max_concurrency"] == 1
