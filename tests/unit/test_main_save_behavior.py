from pathlib import Path

from model_bridge.main import _save_if_requested


def test_save_if_requested_saves_body_only_and_meta(tmp_path: Path):
    response = "generated body\n\n--- [Routing Log] ---\n[1] Primary (codex): Trying...\n    [SUCCESS]"
    target = tmp_path / "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(response, str(target), tool_name="ask_chatgpt_cli", debug_dir=str(debug_dir))

    assert target.read_text(encoding="utf-8") == "generated body"
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

