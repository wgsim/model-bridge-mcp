import os
import time

from model_bridge import main as main_module


def test_clean_markdown_fences_extracts_inner_content():
    content = "```python\nprint('ok')\n```"
    assert main_module.clean_markdown_fences(content) == "print('ok')"


def test_clean_markdown_fences_keeps_plain_text():
    content = "plain text"
    assert main_module.clean_markdown_fences(content) == "plain text"


def test_cleanup_old_meta_logs_removes_only_expired_meta_files(tmp_path):
    old_meta = tmp_path / "old.meta.log"
    old_meta.write_text("old", encoding="utf-8")
    new_meta = tmp_path / "new.meta.log"
    new_meta.write_text("new", encoding="utf-8")
    keep_txt = tmp_path / "keep.txt"
    keep_txt.write_text("x", encoding="utf-8")

    old_ts = time.time() - 3600
    os.utime(old_meta, (old_ts, old_ts))

    main_module._cleanup_old_meta_logs(str(tmp_path), ttl_seconds=120)

    assert not old_meta.exists()
    assert new_meta.exists()
    assert keep_txt.exists()


def test_resolve_fallback_chain_deduplicates_and_skips_unknown(monkeypatch):
    models_cfg = {
        "ollama_aliases": {"default": "gpt-oss:20b", "coder": "qwen3-coder-next:Q4_K_M"},
        "ollama_catalog": ["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"],
        "ollama_local_fallback_chain": ["default", "unknown", "coder", "default"],
    }
    monkeypatch.setitem(main_module.CONFIG, "models", models_cfg)

    chain = main_module._resolve_fallback_chain("gpt-oss:20b")

    assert chain == ["gpt-oss:20b", "qwen3-coder-next:Q4_K_M"]


def test_save_to_file_rejects_system_path():
    out = main_module.save_to_file("body", "/etc/blocked.txt")
    assert out.startswith("[SECURITY ERROR]")


def test_normalize_model_name_strips_repeated_latest_suffix():
    assert main_module._normalize_model_name("model:latest:latest") == "model"
