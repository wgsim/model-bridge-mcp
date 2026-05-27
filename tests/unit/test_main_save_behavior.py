from pathlib import Path

from model_bridge.main import _save_if_requested, save_to_file


def test_save_if_requested_saves_body_only_and_meta(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = "generated body\n\n--- [Routing Log] ---\n[1] Primary (codex): Trying...\n    [SUCCESS]"
    target = "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(response, target, tool_name="ask_chatgpt_cli", debug_dir=str(debug_dir))

    saved = tmp_path / ".model_bridge" / "outputs" / target
    assert saved.read_text(encoding="utf-8") == "generated body"
    meta_files = list(debug_dir.glob("*.meta.log"))
    assert len(meta_files) == 1
    meta_text = meta_files[0].read_text(encoding="utf-8")
    assert "tool: ask_chatgpt_cli" in meta_text
    assert "--- [Routing Log] ---" in meta_text
    assert "[FILE SAVED] Successfully saved to:" in out


def test_save_if_requested_skips_body_file_on_failure(tmp_path: Path):
    response = (
        "[Task Execution Failed]\nForced Primary (codex) failed.\nError: sample\n\n"
        "--- [Routing Log] ---\n[1] Primary (codex): Trying...\n    [FAILED]"
    )
    target = tmp_path / "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(response, str(target), tool_name="ask_chatgpt_cli", debug_dir=str(debug_dir))

    assert not target.exists()
    meta_files = list(debug_dir.glob("*.meta.log"))
    assert len(meta_files) == 1
    assert "[FILE SKIPPED] No model body extracted from response." in out


def test_save_if_requested_masks_sensitive_text_in_meta(tmp_path: Path):
    response = (
        "body\n\n--- [Routing Log] ---\n"
        "Authorization: Bearer SECRET_TOKEN\n"
        "api_key=MY_REAL_KEY"
    )
    target = tmp_path / "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    _save_if_requested(response, str(target), tool_name="ask_chatgpt_cli", debug_dir=str(debug_dir))

    meta_files = list(debug_dir.glob("*.meta.log"))
    assert len(meta_files) == 1
    meta_text = meta_files[0].read_text(encoding="utf-8")
    assert "SECRET_TOKEN" not in meta_text
    assert "MY_REAL_KEY" not in meta_text
    assert "***MASKED***" in meta_text


def test_save_to_file_blocks_symlink_path_resolving_to_system_dir(tmp_path: Path):
    etc_link = tmp_path / "etc_link"
    etc_link.symlink_to("/etc")

    out = save_to_file("hello", str(etc_link / "shadow_copy.txt"))

    assert out.startswith("[SECURITY ERROR]")


def test_save_to_file_rejects_symlinked_output_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model_bridge_dir = tmp_path / ".model_bridge"
    model_bridge_dir.mkdir()
    (model_bridge_dir / "outputs").symlink_to(tmp_path / "elsewhere")

    out = save_to_file("hello", "reports/result.txt")

    assert out.startswith("[SECURITY ERROR]")


def test_save_to_file_rejects_symlinked_output_root_parent(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (tmp_path / ".model_bridge").symlink_to(outside)

    out = save_to_file("hello", "reports/result.txt")

    assert out.startswith("[SECURITY ERROR]")
    assert not (outside / "outputs" / "reports" / "result.txt").exists()
