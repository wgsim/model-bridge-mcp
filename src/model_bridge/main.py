"""MCP entrypoint wired with modular components."""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from mcp.server.fastmcp import FastMCP

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter
from model_bridge.config.config_loader import load_config
from model_bridge.core.failover_manager import FailoverManager
from model_bridge.security.sanitizer import SecuritySanitizer


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("model_bridge.main")

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


def _save_if_requested(response: str, save_path: Optional[str]) -> str:
    if not save_path:
        return response
    return f"{save_to_file(response, save_path)}\n\n{response}"


@mcp.tool()
def ask_chatgpt_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = FAILOVER.execute("codex", "gemini", prompt, "execution", force_primary=force_model)
    return _save_if_requested(response, save_path)


@mcp.tool()
def ask_gemini_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = FAILOVER.execute("gemini", "codex", prompt, "analysis", force_primary=force_model)
    return _save_if_requested(response, save_path)


@mcp.tool()
def ask_ollama(prompt: str, save_path: str = None, model: str = "llama3.2") -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe:
        return sec_msg

    success, output = ADAPTER.run("ollama", [model], prompt)
    if success:
        response = f"[Source: Ollama]\n{output}"
        return _save_if_requested(response, save_path)

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
    return _save_if_requested(response, save_path)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()

