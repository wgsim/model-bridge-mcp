"""MCP entrypoint wired with modular components."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter
from model_bridge.config.config_loader import load_config
from model_bridge.core.failover_manager import FailoverManager
from model_bridge.security.sanitizer import SecuritySanitizer


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("model_bridge.main")
DEBUG_META_DIR = ".model_bridge/tmp"
DEBUG_META_TTL_SECONDS = 48 * 60 * 60

mcp = FastMCP("Model Bridge MCP")
CONFIG = load_config()
ADAPTER = SubprocessAdapter(
    cli_config=CONFIG["commands"],
    env=os.environ.copy(),
    system_suffix=CONFIG["runtime"]["system_suffix"],
)
FAILOVER = FailoverManager(adapter=ADAPTER, sanitizer=SecuritySanitizer, config=CONFIG)


def clean_markdown_fences(content: str) -> str:
    pattern = r"^```[a-zA-Z]*\n([\s\S]*?)\n```$"
    match = re.match(pattern, content.strip())
    if match:
        return match.group(1)
    return content


def save_to_file(content: str, path: str) -> str:
    try:
        full_path = os.path.abspath(os.path.expanduser(path))
        if full_path.startswith(("/etc", "/var", "/usr", "/bin", "/sbin", "/root")):
            return f"[SECURITY ERROR] Writing to system path '{path}' is forbidden."

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(clean_markdown_fences(content))
        return f"[FILE SAVED] Successfully saved to: {path}\n(Markdown fences removed automatically)"
    except Exception as exc:
        return f"[FILE ERROR] Failed to save: {exc}"


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
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts}_{tool_name}_{time.time_ns()}.meta.log"
    meta_path = os.path.join(debug_dir, filename)
    with open(meta_path, "w", encoding="utf-8") as handle:
        handle.write(f"tool: {tool_name}\n")
        handle.write(f"created_at_utc: {datetime.now(timezone.utc).isoformat()}\n")
        handle.write("\n")
        handle.write(response)
    return meta_path


def _save_if_requested(
    response: str,
    save_path: Optional[str],
    tool_name: str,
    debug_dir: str = DEBUG_META_DIR,
) -> str:
    if not save_path:
        return response
    body, full_response = _split_body_and_meta(response)
    if body:
        save_result = save_to_file(body, save_path)
    else:
        save_result = "[FILE SKIPPED] No model body extracted from response."
    meta_path = _save_debug_meta(full_response, tool_name=tool_name, debug_dir=debug_dir)
    return f"{save_result}\n[DEBUG META] Saved to: {meta_path}\n\n{response}"


@mcp.tool()
def ask_chatgpt_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = FAILOVER.execute("codex", "gemini", prompt, "execution", force_primary=force_model)
    return _save_if_requested(response, save_path, tool_name="ask_chatgpt_cli")


@mcp.tool()
def ask_gemini_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = FAILOVER.execute("gemini", "codex", prompt, "analysis", force_primary=force_model)
    return _save_if_requested(response, save_path, tool_name="ask_gemini_cli")


@mcp.tool()
def ask_ollama(prompt: str, save_path: str = None, model: str = "llama3.2") -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe:
        return sec_msg

    success, output = ADAPTER.run("ollama", [model], prompt)
    if success:
        response = f"[Source: Ollama]\n{output}"
        return _save_if_requested(response, save_path, tool_name="ask_ollama")

    logger.warning("Ollama unreachable. Failing over to cloud chain.")
    cloud_prompt = f"[WARNING: Local Ollama failed. Executing via Cloud Backup] {prompt}"
    response = FAILOVER.execute(
        "codex",
        "gemini",
        cloud_prompt,
        "execution",
        force_primary=False,
        allow_tertiary=False,
    )
    return _save_if_requested(response, save_path, tool_name="ask_ollama")


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
