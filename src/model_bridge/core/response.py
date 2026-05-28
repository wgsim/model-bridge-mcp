"""Response formatting, file-save helpers, and debug-meta utilities."""

from __future__ import annotations

import errno
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

DEBUG_META_DIR = ".model_bridge/tmp"
DEBUG_META_TTL_SECONDS = 48 * 60 * 60
SAFE_OUTPUT_DIR = os.path.join(".model_bridge", "outputs")

__all__ = [
    "DEBUG_META_DIR",
    "DEBUG_META_TTL_SECONDS",
    "_apply_verbosity",
    "_apply_max_output_tokens",
    "_format_stream_fallback",
    "_finalize_response",
    "_split_body_and_meta",
    "_save_debug_meta",
    "_cleanup_old_meta_logs",
    "_save_if_requested",
    "_mask_sensitive_text",
    "clean_markdown_fences",
    "save_to_file",
    "_mark_cached_json_payload",
]

def _apply_verbosity(text: str, verbosity: str) -> str:
    if verbosity == "brief":
        return text[:600].rstrip()
    return text

def _apply_max_output_tokens(text: str, max_output_tokens: int) -> str:
    if max_output_tokens <= 0:
        return text
    tokens = text.split()
    if len(tokens) <= max_output_tokens:
        return text
    return " ".join(tokens[:max_output_tokens])

def _format_stream_fallback(text: str) -> str:
    chunks = [text[i : i + 200] for i in range(0, len(text), 200)] or [""]
    return "[STREAM FALLBACK]\n" + "\n".join(chunks) + "\n[STREAM END]"

def _finalize_response(response: str, provider: str, options: dict, cached: bool = False) -> str:
    body = _apply_verbosity(response, options["verbosity"])
    body = _apply_max_output_tokens(body, options["max_output_tokens"])
    if options["stream"] and options["response_format"] == "text":
        body = _format_stream_fallback(body)
    if options["response_format"] == "json":
        payload = {
            "provider": provider,
            "cached": cached,
            "content": body,
            "meta": {
                "verbosity": options["verbosity"],
                "max_output_tokens": options["max_output_tokens"],
                "stream": bool(options["stream"]),
            },
        }
        return json.dumps(payload, ensure_ascii=False)
    return body

def _split_body_and_meta(response: str) -> tuple[str, str]:
    routing_marker = "\n\n--- [Routing Log] ---\n"
    if response.startswith("[Task Execution Failed]"):
        return "", response
    if response.startswith("[SECURITY BLOCK]"):
        return "", response
    if routing_marker in response:
        body, _ = response.split(routing_marker, 1)
        return body.strip(), response
    if response.startswith("[Source: Ollama]\n"):
        return response.split("\n", 1)[1].strip(), response
    return response.strip(), response

def _mask_sensitive_text(text: str) -> str:
    patterns = [
        (r"(?i)(authorization\s*:\s*bearer\s+)([^\s]+)", r"\1***MASKED***"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(x-api-key\s*:\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(refresh_token\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(access_token\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(cookie\s*:\s*)([^\n]+)", r"\1***MASKED***"),
    ]
    masked = text
    for pattern, repl in patterns:
        masked = re.sub(pattern, repl, masked)
    return masked

def _cleanup_old_meta_logs(debug_dir: str, ttl_seconds: int = DEBUG_META_TTL_SECONDS) -> None:
    if not os.path.isdir(debug_dir):
        return
    now = time.time()
    for entry in os.scandir(debug_dir):
        if not entry.is_file() or not entry.name.endswith(".meta.log"):
            continue
        try:
            if now - entry.stat().st_mtime > ttl_seconds:
                os.remove(entry.path)
        except OSError:
            continue

def _save_debug_meta(
    response: str,
    tool_name: str,
    debug_dir: str = DEBUG_META_DIR,
    ttl_seconds: int = DEBUG_META_TTL_SECONDS,
) -> str:
    os.makedirs(debug_dir, exist_ok=True)
    _cleanup_old_meta_logs(debug_dir, ttl_seconds=ttl_seconds)
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts}_{tool_name}_{time.time_ns()}.meta.log"
    meta_path = os.path.join(debug_dir, filename)
    sanitized_response = _mask_sensitive_text(response)
    with open(meta_path, "w", encoding="utf-8") as handle:
        handle.write(f"tool: {tool_name}\n")
        handle.write(f"created_at_utc: {now_utc.isoformat()}\n")
        handle.write("\n")
        handle.write(sanitized_response)
    return meta_path

def clean_markdown_fences(content: str) -> str:
    pattern = r"^```[a-zA-Z]*\n([\s\S]*?)\n```$"
    match = re.match(pattern, content.strip())
    if match:
        return match.group(1)
    return content

def _split_path_parts(path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", path) if part not in {"", "."}]


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _resolve_safe_output_path(path: str, output_root: str = SAFE_OUTPUT_DIR) -> tuple[list[str] | None, str | None]:
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return None, f"[SECURITY ERROR] save_path must be relative to '{output_root}'."

    relative_parts = _split_path_parts(expanded)
    if not relative_parts or any(part == ".." for part in relative_parts):
        return None, f"[SECURITY ERROR] save_path must stay within '{output_root}'."

    root_base = os.path.abspath(output_root)
    current = root_base
    while True:
        if os.path.lexists(current) and os.path.islink(current):
            return None, f"[SECURITY ERROR] Output root '{output_root}' must not use symlinked path components."
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return relative_parts, None


def _open_directory_no_symlink(path_part: str, dir_fd: int, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(path_part, dir_fd=dir_fd)
        except FileExistsError:
            pass
    return os.open(path_part, _directory_open_flags(), dir_fd=dir_fd)


def _write_safe_output_file(content: str, relative_parts: list[str], output_root: str = SAFE_OUTPUT_DIR) -> None:
    current_fd = os.open(".", _directory_open_flags())
    try:
        for part in _split_path_parts(output_root):
            next_fd = _open_directory_no_symlink(part, current_fd, create=True)
            os.close(current_fd)
            current_fd = next_fd

        for part in relative_parts[:-1]:
            next_fd = _open_directory_no_symlink(part, current_fd, create=True)
            os.close(current_fd)
            current_fd = next_fd

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(relative_parts[-1], flags, 0o644, dir_fd=current_fd)
        with os.fdopen(file_fd, "w", encoding="utf-8") as handle:
            handle.write(clean_markdown_fences(content))
    finally:
        os.close(current_fd)


def save_to_file(content: str, path: str) -> str:
    try:
        relative_parts, error = _resolve_safe_output_path(path)
        if error:
            return error
        assert relative_parts is not None
        _write_safe_output_file(content, relative_parts)
        return f"[FILE SAVED] Successfully saved to: {path}\n(Markdown fences removed automatically)"
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            return f"[SECURITY ERROR] save_path must stay within '{SAFE_OUTPUT_DIR}'."
        return f"[FILE ERROR] Failed to save: {exc}"
    except Exception as exc:
        return f"[FILE ERROR] Failed to save: {exc}"

def _save_if_requested(
    response: str,
    save_path: Optional[str],
    tool_name: str,
    debug_dir: str = DEBUG_META_DIR,
    save_debug_meta: bool = False,
) -> str:
    if not save_path:
        return response
    body, full_response = _split_body_and_meta(response)
    save_result = (
        save_to_file(body, save_path)
        if body
        else "[FILE SKIPPED] No model body extracted from response."
    )
    if not save_debug_meta:
        return f"{save_result}\n\n{response}"
    meta_path = _save_debug_meta(full_response, tool_name=tool_name, debug_dir=debug_dir)
    return f"{save_result}\n[DEBUG META] Saved to: {meta_path}\n\n{response}"

def _mark_cached_json_payload(payload_or_text: object) -> str | None:
    if isinstance(payload_or_text, dict):
        if "content" in payload_or_text:
            payload = dict(payload_or_text)
            payload["cached"] = True
            return json.dumps(payload, ensure_ascii=False)
        return None
    if not isinstance(payload_or_text, str):
        return None
    try:
        parsed = json.loads(payload_or_text)
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict) and "content" in parsed:
        parsed["cached"] = True
        return json.dumps(parsed, ensure_ascii=False)
    return None
