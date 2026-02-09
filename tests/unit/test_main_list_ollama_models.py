import json
import subprocess

from model_bridge import main as main_module


def test_parse_ollama_list_output():
    sample = (
        "NAME                        ID              SIZE      MODIFIED\n"
        "llama3.2:latest            abcdef123456    2.0 GB    2 days ago\n"
        "qwen3-coder:30b-a3b-q8_0   fedcba654321    18 GB     1 day ago\n"
    )
    names = main_module._parse_ollama_list_output(sample)
    assert names == ["llama3.2:latest", "qwen3-coder:30b-a3b-q8_0"]


def test_list_ollama_models_reports_installed_and_missing(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_installed_ollama_models",
        lambda: (["llama3.2"], ""),
    )
    result = json.loads(main_module.list_ollama_models())
    assert result["status"] == "ok"
    assert "llama3.2" in result["installed"]
    assert "qwen3-coder:30b-a3b-q8_0" in result["missing"]
    assert "default_model" in result
    assert "aliases" in result
    assert "catalog" in result


def test_list_ollama_models_reports_unavailable_with_error(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_installed_ollama_models",
        lambda: ([], "ollama command not found"),
    )
    result = json.loads(main_module.list_ollama_models())
    assert result["status"] == "unavailable"
    assert result["installed"] == []
    assert result["error"] == "ollama command not found"


def test_get_installed_ollama_models_handles_nonzero_exit(monkeypatch):
    monkeypatch.setattr(main_module.shutil, "which", lambda _: "/usr/bin/ollama")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(main_module.subprocess, "run", _fake_run)
    models, err = main_module._get_installed_ollama_models()
    assert models == []
    assert err == "boom"

