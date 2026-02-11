from model_bridge import main as main_module


def test_select_auto_ollama_alias_prefers_coder_for_code_prompt():
    assert main_module._select_auto_ollama_alias("write python function for sorting") == "coder"


def test_select_auto_ollama_alias_prefers_fast_for_short_prompt(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {"runtime": {"auto_routing_short_prompt_threshold": 500}, "models": {}},
    )
    assert main_module._select_auto_ollama_alias("short ask") == "fast"

