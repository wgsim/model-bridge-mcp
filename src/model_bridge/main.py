"""MCP entrypoint wired with modular components."""

from __future__ import annotations

import logging
import os
import re
import time
import json
import shutil
import subprocess
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

CONFIG: Optional[dict] = None
ADAPTER: Optional[SubprocessAdapter] = None
FAILOVER: Optional[FailoverManager] = None


def build_runtime(config: Optional[dict] = None) -> tuple[dict, SubprocessAdapter, FailoverManager]:
    """Build runtime dependencies for production and tests."""
    resolved_config = config if config is not None else load_config()
    SecuritySanitizer.configure(
        block_patterns=resolved_config["security"]["block_patterns"],
        sensitive_paths=resolved_config["security"]["sensitive_paths"],
    )
    adapter = SubprocessAdapter(
        cli_config=resolved_config["commands"],
        env=os.environ.copy(),
        system_suffix=resolved_config["runtime"]["system_suffix"],
        apply_system_suffix_for=resolved_config["runtime"]["apply_system_suffix"],
        timeout_seconds=resolved_config["runtime"]["subprocess_timeout_seconds"],
    )
    failover = FailoverManager(adapter=adapter, sanitizer=SecuritySanitizer, config=resolved_config)
    return resolved_config, adapter, failover


def _ensure_runtime() -> None:
    global CONFIG, ADAPTER, FAILOVER
    if CONFIG is not None and ADAPTER is not None and FAILOVER is not None:
        return
    CONFIG, ADAPTER, FAILOVER = build_runtime()


def _get_config() -> dict:
    _ensure_runtime()
    assert CONFIG is not None
    return CONFIG


def _get_adapter() -> SubprocessAdapter:
    _ensure_runtime()
    assert ADAPTER is not None
    return ADAPTER


def _get_failover() -> FailoverManager:
    _ensure_runtime()
    assert FAILOVER is not None
    return FAILOVER


def clean_markdown_fences(content: str) -> str:
    pattern = r"^```[a-zA-Z]*\n([\s\S]*?)\n```$"
    match = re.match(pattern, content.strip())
    if match:
        return match.group(1)
    return content


def save_to_file(content: str, path: str) -> str:
    try:
        protected_roots = ("/etc", "/var", "/usr", "/bin", "/sbin", "/root")
        protected_prefixes = set(protected_roots)
        # macOS commonly resolves /etc -> /private/etc; include this alias
        protected_prefixes.add(os.path.realpath("/etc"))

        full_path = os.path.abspath(os.path.expanduser(path))
        resolved_path = os.path.realpath(full_path)
        def _under_prefix(candidate: str, prefix: str) -> bool:
            return candidate == prefix or candidate.startswith(prefix + "/")

        if any(_under_prefix(resolved_path, prefix) for prefix in protected_prefixes):
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


def _resolve_ollama_model(model_arg: str) -> tuple[str | None, str]:
    models_cfg = _get_config()["models"]
    aliases = models_cfg.get("ollama_aliases", {})
    catalog = set(models_cfg.get("ollama_catalog", []))
    token = (model_arg or "").strip()
    if not token:
        token = "default"

    if token in aliases:
        resolved = aliases[token]
        return resolved, ""
    if token in catalog:
        return token, ""

    alias_keys = ", ".join(sorted(aliases.keys()))
    model_names = ", ".join(sorted(catalog))
    return (
        None,
        (
            f"[MODEL ERROR] Unknown ollama model/alias: '{token}'. "
            f"Aliases: [{alias_keys}] | Models: [{model_names}]"
        ),
    )


def _mask_sensitive_text(text: str) -> str:
    masked = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)([^\s]+)",
        r"\1***MASKED***",
        text,
    )
    masked = re.sub(
        r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"']+)",
        r"\1***MASKED***",
        masked,
    )
    return masked


def _normalize_model_name(name: str) -> str:
    value = name.strip()
    while value.endswith(":latest"):
        value = value[: -len(":latest")]
    return value


def _resolve_fallback_chain(requested_model: str) -> list[str]:
    models_cfg = _get_config()["models"]
    aliases = models_cfg["ollama_aliases"]
    catalog = set(models_cfg["ollama_catalog"])
    chain_tokens = models_cfg.get("ollama_local_fallback_chain", [])

    ordered: list[str] = []
    seen: set[str] = set()

    def _add_token(token: str) -> None:
        if token in aliases:
            model_name = aliases[token]
        elif token in catalog:
            model_name = token
        else:
            return
        if model_name not in seen:
            seen.add(model_name)
            ordered.append(model_name)

    _add_token(requested_model)
    for token in chain_tokens:
        _add_token(token)
    return ordered


def _parse_ollama_list_output(output: str) -> list[str]:
    names: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("NAME "):
            continue
        name = line.split()[0]
        if name and name not in names:
            names.append(name)
    return names


def _get_installed_ollama_models() -> tuple[list[str], str]:
    if not shutil.which("ollama"):
        return [], "ollama command not found"
    try:
        proc = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return [], str(exc)
    if proc.returncode != 0:
        return [], (proc.stdout + proc.stderr).strip() or f"exit_code={proc.returncode}"
    return _parse_ollama_list_output(proc.stdout), ""


@mcp.tool()
async def ask_chatgpt_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = await _get_failover().execute_async(
        "codex", "gemini", prompt, "execution", force_primary=force_model
    )
    return _save_if_requested(response, save_path, tool_name="ask_chatgpt_cli")


@mcp.tool()
async def ask_gemini_cli(prompt: str, save_path: str = None, force_model: bool = False) -> str:
    response = await _get_failover().execute_async(
        "gemini", "codex", prompt, "analysis", force_primary=force_model
    )
    return _save_if_requested(response, save_path, tool_name="ask_gemini_cli")


@mcp.tool()
async def ask_ollama(prompt: str, save_path: str = None, model: str = "default") -> str:
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe:
        return sec_msg

    requested_token = (model or "").strip() or "default"
    resolved_model, model_error = _resolve_ollama_model(requested_token)
    if resolved_model is None:
        return model_error

    installed_models_raw, installed_error = _get_installed_ollama_models()
    installed_normalized = {_normalize_model_name(name) for name in installed_models_raw}
    local_chain = _resolve_fallback_chain(resolved_model)

    if not installed_error:
        requested_installed = _normalize_model_name(resolved_model) in installed_normalized
        if not requested_installed and requested_token != "default":
            pull_cmd = f"ollama pull {resolved_model}"
            return (
                f"[MODEL ERROR] Requested model '{resolved_model}' is not installed locally. "
                f"Install with: {pull_cmd}"
            )
        local_chain = [m for m in local_chain if _normalize_model_name(m) in installed_normalized]
        if not local_chain:
            pull_cmd = f"ollama pull {resolved_model}"
            return (
                f"[MODEL ERROR] Requested model '{resolved_model}' is not installed locally. "
                f"Install with: {pull_cmd}"
            )

    last_local_error = ""
    for local_model in local_chain:
        success, output = await _get_adapter().run_async("ollama", [local_model], prompt)
        if success:
            response = f"[Source: Ollama]\n{output}"
            return _save_if_requested(response, save_path, tool_name="ask_ollama")
        last_local_error = output

    logger.warning("Ollama unreachable. Failing over to cloud chain.")
    cloud_prompt = f"[WARNING: Local Ollama failed. Executing via Cloud Backup] {prompt}"
    if last_local_error:
        cloud_prompt = f"{cloud_prompt}\n\n[Local Error Summary]\n{last_local_error}"
    response = await _get_failover().execute_async(
        "codex",
        "gemini",
        cloud_prompt,
        "execution",
        force_primary=False,
        allow_tertiary=False,
    )
    return _save_if_requested(response, save_path, tool_name="ask_ollama")


@mcp.tool()
def list_ollama_models() -> str:
    models_cfg = _get_config()["models"]
    default_model = models_cfg["ollama_default_model"]
    aliases = models_cfg["ollama_aliases"]
    catalog = models_cfg["ollama_catalog"]

    installed, error = _get_installed_ollama_models()
    installed_normalized = {_normalize_model_name(name) for name in installed}
    missing = [name for name in catalog if _normalize_model_name(name) not in installed_normalized]
    effective_default = aliases.get("default", default_model)
    recommended_aliases = _get_config()["models"].get("ollama_local_fallback_chain", [])

    status = "ok" if not error else "unavailable"
    payload = {
        "status": status,
        "default_model": default_model,
        "effective_default": effective_default,
        "aliases": aliases,
        "recommended_aliases": recommended_aliases,
        "catalog": catalog,
        "installed": installed,
        "missing": missing,
    }
    if missing:
        payload["pull_commands"] = [f"ollama pull {name}" for name in missing]
    if error:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
