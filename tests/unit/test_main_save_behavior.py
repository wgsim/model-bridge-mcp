from pathlib import Path

import pytest

from model_bridge import main as main_module
from model_bridge.core import response as response_module
from model_bridge.core.response import _mask_sensitive_text
from model_bridge.main import _save_if_requested, save_to_file


def test_save_if_requested_saves_body_only_and_meta(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = "generated body\n\n--- [Routing Log] ---\n[1] Primary (codex): Trying...\n    [SUCCESS]"
    target = "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(
        response,
        target,
        tool_name="ask_chatgpt_cli",
        debug_dir=str(debug_dir),
        save_debug_meta=True,
    )

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

    out = _save_if_requested(
        response,
        str(target),
        tool_name="ask_chatgpt_cli",
        debug_dir=str(debug_dir),
        save_debug_meta=True,
    )

    assert not target.exists()
    meta_files = list(debug_dir.glob("*.meta.log"))
    assert len(meta_files) == 1
    assert "[FILE SKIPPED] No model body extracted from response." in out


def test_save_if_requested_skips_debug_meta_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = "body\n\n--- [Routing Log] ---\nAuthorization: Bearer SECRET_TOKEN"
    target = "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(
        response,
        target,
        tool_name="ask_chatgpt_cli",
        debug_dir=str(debug_dir),
        save_debug_meta=False,
    )

    saved = tmp_path / ".model_bridge" / "outputs" / "result.txt"
    assert saved.read_text(encoding="utf-8") == "body"
    assert list(debug_dir.glob("*.meta.log")) == []
    assert "[DEBUG META]" not in out


@pytest.mark.parametrize("runtime_cfg", [{}, {"save_debug_meta_on_save": False}])
def test_save_response_if_requested_forwards_debug_meta_false(monkeypatch, runtime_cfg):
    captured = {}

    monkeypatch.setattr(main_module, "_get_config", lambda: {"runtime": runtime_cfg})

    def fake_save_if_requested(response, save_path, *, tool_name, save_debug_meta, **kwargs):
        captured["response"] = response
        captured["save_path"] = save_path
        captured["tool_name"] = tool_name
        captured["save_debug_meta"] = save_debug_meta
        captured["kwargs"] = kwargs
        return "saved-response"

    monkeypatch.setattr(main_module, "_save_if_requested", fake_save_if_requested)

    out = main_module._save_response_if_requested("body", "result.txt", "ask_chatgpt_cli")

    assert out == "saved-response"
    assert captured == {
        "response": "body",
        "save_path": "result.txt",
        "tool_name": "ask_chatgpt_cli",
        "save_debug_meta": False,
        "kwargs": {},
    }


def test_save_response_if_requested_forwards_debug_meta_true(monkeypatch):
    captured = {}

    monkeypatch.setattr(main_module, "_get_config", lambda: {"runtime": {"save_debug_meta_on_save": True}})

    def fake_save_if_requested(response, save_path, *, tool_name, save_debug_meta, **kwargs):
        captured["response"] = response
        captured["save_path"] = save_path
        captured["tool_name"] = tool_name
        captured["save_debug_meta"] = save_debug_meta
        captured["kwargs"] = kwargs
        return "saved-response"

    monkeypatch.setattr(main_module, "_save_if_requested", fake_save_if_requested)

    out = main_module._save_response_if_requested("body", "result.txt", "ask_chatgpt_cli")

    assert out == "saved-response"
    assert captured == {
        "response": "body",
        "save_path": "result.txt",
        "tool_name": "ask_chatgpt_cli",
        "save_debug_meta": True,
        "kwargs": {},
    }


def test_save_if_requested_masks_sensitive_text_in_meta(tmp_path: Path):
    response = (
        "body\n\n--- [Routing Log] ---\n"
        "Authorization: Bearer SECRET_TOKEN\n"
        "api_key=MY_REAL_KEY"
    )
    target = tmp_path / "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    _save_if_requested(
        response,
        str(target),
        tool_name="ask_chatgpt_cli",
        debug_dir=str(debug_dir),
        save_debug_meta=True,
    )

    meta_files = list(debug_dir.glob("*.meta.log"))
    assert len(meta_files) == 1
    meta_text = meta_files[0].read_text(encoding="utf-8")
    assert "SECRET_TOKEN" not in meta_text
    assert "MY_REAL_KEY" not in meta_text
    assert "***MASKED***" in meta_text


def test_save_debug_meta_rejects_symlinked_debug_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".model_bridge").symlink_to(outside)

    with pytest.raises(OSError):
        response_module._save_debug_meta("routing log", tool_name="ask_chatgpt_cli")

    assert list(outside.rglob("*.meta.log")) == []


def test_save_debug_meta_rejects_symlinked_debug_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model_bridge_dir = tmp_path / ".model_bridge"
    model_bridge_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (model_bridge_dir / "tmp").symlink_to(outside)

    with pytest.raises(OSError):
        response_module._save_debug_meta("routing log", tool_name="ask_chatgpt_cli")

    assert list(outside.glob("*.meta.log")) == []


def test_mask_sensitive_text_masks_common_token_fields():
    masked = _mask_sensitive_text(
        "Authorization: Bearer SECRET\n"
        "x-api-key: APISECRET\n"
        "refresh_token=REFRESHSECRET\n"
        "cookie: session=COOKIESECRET"
    )

    assert "SECRET" not in masked
    assert "APISECRET" not in masked
    assert "REFRESHSECRET" not in masked
    assert "COOKIESECRET" not in masked
    assert masked.count("***MASKED***") >= 4


def test_save_to_file_blocks_symlink_path_resolving_to_system_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    system_dir = tmp_path / "system_dir"
    system_dir.mkdir()
    output_root = tmp_path / ".model_bridge" / "outputs"
    output_root.mkdir(parents=True)
    (output_root / "system").symlink_to(system_dir)

    out = save_to_file("hello", "system/blocked.txt")

    assert out.startswith("[SECURITY ERROR]")
    assert not (system_dir / "blocked.txt").exists()


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


def test_save_to_file_rejects_symlinked_leaf_created_during_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "escaped.txt"
    target_dir = tmp_path / ".model_bridge" / "outputs" / "reports"
    original_open_directory = response_module._open_directory_no_symlink

    def racing_open_directory(path_part: str, dir_fd: int, *, create: bool) -> int:
        opened_fd = original_open_directory(path_part, dir_fd, create=create)
        if path_part == "reports":
            escaped_link = target_dir / "result.txt"
            if not escaped_link.exists() and not escaped_link.is_symlink():
                escaped_link.symlink_to(outside_file)
        return opened_fd

    monkeypatch.setattr(response_module, "_open_directory_no_symlink", racing_open_directory)

    out = save_to_file("hello", "reports/result.txt")

    assert not out.startswith("[FILE SAVED]")
    assert not outside_file.exists()
