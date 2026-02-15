"""MCP entrypoint wired with modular components."""

from __future__ import annotations

import logging
import os
import random
import re
import time
import json
import shutil
import subprocess
import inspect
from datetime import datetime, timezone
from typing import Callable, Optional

from mcp.server.fastmcp import FastMCP, Context

from model_bridge.adapters.subprocess_adapter import SubprocessAdapter
from model_bridge.config.config_loader import load_config
from model_bridge.core.batch_executor import (
    BatchExecutor,
    PrioritizedJob,
    parse_priority,
)
from model_bridge.core.failover_manager import FailoverManager, get_last_errors as _get_last_errors_from_buffer
from model_bridge.core.plugin_loader import PluginLoader
from model_bridge.core.provider_registry import ProviderRegistry, build_default_provider_registry
from model_bridge.core.task_tracker import TaskTracker
from model_bridge.core.prompt_cache import PromptCache
from model_bridge.core.rate_limiter import TokenBucket
from model_bridge.core.session_memory import SessionMemory
from model_bridge.security.sanitizer import SecuritySanitizer


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("model_bridge.main")
DEBUG_META_DIR = ".model_bridge/tmp"
DEBUG_META_TTL_SECONDS = 48 * 60 * 60

mcp = FastMCP("Model Bridge MCP")

CONFIG: Optional[dict] = None
ADAPTER: Optional[SubprocessAdapter] = None
FAILOVER: Optional[FailoverManager] = None
PROMPT_CACHE: Optional[PromptCache] = None
SESSION_MEMORY: Optional[SessionMemory] = None
PROVIDER_REGISTRY: Optional[ProviderRegistry] = None
PLUGIN_LOADER: Optional[PluginLoader] = None
TASK_TRACKER: TaskTracker = TaskTracker()


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


def _get_runtime_defaults() -> dict:
    runtime_cfg = _get_config().get("runtime", {})
    return runtime_cfg.get("ask_defaults", {})


def _get_prompt_cache() -> Optional[PromptCache]:
    global PROMPT_CACHE
    runtime_cfg = _get_config().get("runtime", {})
    if not runtime_cfg.get("prompt_cache_enabled", True):
        return None
    if PROMPT_CACHE is None:
        PROMPT_CACHE = PromptCache(
            ttl_seconds=runtime_cfg.get("prompt_cache_ttl_seconds", 300),
            max_entries=runtime_cfg.get("prompt_cache_max_entries", 256),
        )
    return PROMPT_CACHE


def _get_session_memory() -> Optional[SessionMemory]:
    global SESSION_MEMORY
    runtime_cfg = _get_config().get("runtime", {})
    if not runtime_cfg.get("session_memory_enabled", False):
        return None
    if SESSION_MEMORY is None:
        SESSION_MEMORY = SessionMemory(
            ttl_seconds=runtime_cfg.get("session_memory_ttl_seconds", 1800),
            max_turns=runtime_cfg.get("session_memory_max_turns", 6),
        )
    return SESSION_MEMORY


def _get_provider_registry() -> ProviderRegistry:
    global PROVIDER_REGISTRY
    if PROVIDER_REGISTRY is None:
        PROVIDER_REGISTRY = build_default_provider_registry(
            _get_config(),
            handlers=_get_provider_handlers(),
        )
    return PROVIDER_REGISTRY


def _get_plugin_loader() -> PluginLoader | None:
    """Get or initialize PluginLoader for external plugins."""
    global PLUGIN_LOADER
    if PLUGIN_LOADER is None:
        PLUGIN_LOADER = PluginLoader.instance()
        # Load external plugins (not built-in wrappers)
        PLUGIN_LOADER.discover_and_load()
        external_plugins = [
            p for p in PLUGIN_LOADER.list_plugins()
            if p not in {"codex", "gemini", "ollama", "claude_code"}
        ]
        if external_plugins:
            logger.info("Loaded external plugins: %s", external_plugins)
    return PLUGIN_LOADER


def _get_provider_handlers() -> dict[str, Callable]:
    """Get provider handler mappings for registry.

    Combines built-in providers with external plugins.
    Built-in providers are always available; plugins add new providers.
    """
    # Start with built-in dispatchers
    dispatchers = {
        "codex": ask_chatgpt_cli,
        "gemini": ask_gemini_cli,
        "ollama": ask_ollama,
        "claude_code": ask_claude_code,
    }

    # Add external plugins (excluding built-ins that wrap the same functions)
    loader = _get_plugin_loader()
    if loader is not None:
        plugin_handlers = loader.get_handlers()
        for provider_id, handler in plugin_handlers.items():
            if provider_id not in dispatchers:
                dispatchers[provider_id] = handler

    return dispatchers


def _is_provider_configured(provider_id: str) -> bool:
    provider = _get_provider_registry().get(provider_id)
    return bool(provider is not None and provider.configured)


def _known_providers_text() -> str:
    providers = _get_provider_registry().list_provider_ids()
    return "|".join(providers)


async def _dispatch_ask_provider(
    provider_id: str,
    prompt: str,
    *,
    save_path: str | None,
    force_model: bool,
    model: str,
    options: dict,
    output_mode: str,
) -> str:
    registry = _get_provider_registry()
    handler = registry.get_handler(provider_id)
    if handler is None:
        known = registry.list_provider_ids()
        known_str = "|".join(known)
        raise ValueError(f"provider dispatcher not found: {provider_id}. Known providers: {known_str}")

    # Capability validation
    _, json_error = registry.validate_option(provider_id, "response_format", options["response_format"])
    if json_error:
        return json_error

    _, stream_error = registry.validate_option(provider_id, "stream", options["stream"])
    if stream_error:
        # Streaming not supported - will degrade to non-stream
        logger.info("Provider %s does not support streaming, degrading: %s", provider_id, stream_error)

    _, force_model_error = registry.validate_option(provider_id, "force_model", force_model)
    if force_model_error:
        return force_model_error

    common_kwargs = {
        "save_path": save_path,
        "timeout_seconds": options["timeout_seconds"],
        "max_output_tokens": options["max_output_tokens"],
        "response_format": options["response_format"],
        "verbosity": options["verbosity"],
        "stream": options["stream"],
        "output_mode": output_mode,
    }

    if provider_id == "ollama":
        return await handler(
            prompt,
            model=model,
            **common_kwargs,
        )
    return await handler(
        prompt,
        model=model,
        force_model=force_model,
        **common_kwargs,
    )


def _normalize_ask_options(
    timeout_seconds: float | None,
    max_output_tokens: int | None,
    response_format: str | None,
    verbosity: str | None,
    stream: bool | None,
) -> dict:
    defaults = _get_runtime_defaults()
    resolved = {
        "timeout_seconds": timeout_seconds
        if timeout_seconds is not None
        else defaults.get("timeout_seconds", 120.0),
        "max_output_tokens": max_output_tokens
        if max_output_tokens is not None
        else defaults.get("max_output_tokens", 0),
        "response_format": (response_format or defaults.get("response_format", "text")).strip(),
        "verbosity": (verbosity or defaults.get("verbosity", "normal")).strip(),
        "stream": stream if stream is not None else defaults.get("stream", False),
    }
    if resolved["response_format"] not in {"text", "json"}:
        raise ValueError("response_format must be one of: text, json")
    if resolved["verbosity"] not in {"brief", "normal", "detailed"}:
        raise ValueError("verbosity must be one of: brief, normal, detailed")
    if resolved["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be > 0")
    if resolved["max_output_tokens"] < 0:
        raise ValueError("max_output_tokens must be >= 0")
    return resolved


def _normalize_output_mode(output_mode: str | None) -> str:
    resolved = (output_mode or "clean").strip().lower()
    if resolved not in {"clean", "raw"}:
        raise ValueError("output_mode must be one of: clean, raw")
    return resolved


def _resolve_instruction_preset(instruction_preset: str | None) -> str:
    defaults = _get_runtime_defaults()
    token = instruction_preset if instruction_preset is not None else defaults.get(
        "instruction_preset", "strict_once"
    )
    preset = (token or "none").strip().lower()
    if preset not in {"none", "strict_once"}:
        raise ValueError("instruction_preset must be one of: none, strict_once")
    return preset


def _resolve_output_mode(output_mode: str | None) -> str:
    defaults = _get_runtime_defaults()
    token = output_mode if output_mode is not None else defaults.get("output_mode", "clean")
    return _normalize_output_mode(token)


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


def _select_auto_ollama_alias(prompt: str) -> str:
    runtime_cfg = _get_config().get("runtime", {})
    short_threshold = runtime_cfg.get("auto_routing_short_prompt_threshold", 120)
    low = prompt.lower()
    if any(token in low for token in ("def ", "class ", "function", "python", "code", "bug", "stacktrace")):
        return "coder"
    if len(prompt.strip()) <= short_threshold:
        return "fast"
    return "default"


def _build_prompt_with_session(prompt: str, session_id: str | None) -> str:
    if not session_id:
        return prompt
    memory = _get_session_memory()
    if memory is None:
        return prompt
    history = memory.get_context(session_id)
    if not history:
        return prompt
    context = "\n".join(f"- {item}" for item in history)
    return f"[Session Context]\n{context}\n\n[User Prompt]\n{prompt}"


def _apply_instruction_preset(
    prompt: str,
    instruction_preset: str | None,
    response_format: str,
) -> str:
    preset = (instruction_preset or "none").strip().lower()
    if preset == "none":
        return prompt
    if preset == "strict_once":
        json_rule = (
            "5) Output valid JSON only."
            if response_format == "json"
            else "5) Output plain text only."
        )
        policy = (
            "[MCP EXECUTION POLICY]\n"
            "1) Complete the task in a single response.\n"
            "2) Do not ask follow-up questions.\n"
            "3) If information is missing, proceed with minimal assumptions and label each as 'Assumption'.\n"
            "4) Follow all user constraints exactly.\n"
            f"{json_rule}\n"
        )
        return f"{policy}\n[User Prompt]\n{prompt}"
    raise ValueError("instruction_preset must be one of: none, strict_once")


def _remember_session_turn(session_id: str | None, prompt: str, response: str) -> None:
    if not session_id:
        return
    memory = _get_session_memory()
    if memory is None:
        return
    summary = f"Q: {prompt[:120]} | A: {response[:120]}"
    memory.append_turn(session_id, summary)


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


def _safe_gb(value_bytes: int | None) -> float | None:
    if value_bytes is None:
        return None
    return round(value_bytes / (1024**3), 2)


def _detect_ram_bytes() -> tuple[int | None, int | None]:
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * total_pages, page_size * available_pages
    except (ValueError, OSError, AttributeError):
        return None, None


def _detect_nvidia_vram_bytes() -> tuple[int | None, int | None]:
    if not shutil.which("nvidia-smi"):
        return None, None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return None, None
    if result.returncode != 0:
        return None, None
    total_mib = 0
    free_mib = 0
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            total_mib += int(parts[0])
            free_mib += int(parts[1])
        except ValueError:
            continue
    if total_mib <= 0:
        return None, None
    mib = 1024 * 1024
    return total_mib * mib, free_mib * mib


def _collect_runtime_resources() -> dict:
    ram_total_bytes, ram_free_bytes = _detect_ram_bytes()
    vram_total_bytes, vram_free_bytes = _detect_nvidia_vram_bytes()
    return {
        "ram_total_gb": _safe_gb(ram_total_bytes),
        "ram_free_gb": _safe_gb(ram_free_bytes),
        "vram_total_gb": _safe_gb(vram_total_bytes),
        "vram_free_gb": _safe_gb(vram_free_bytes),
        "vram_detector": "nvidia-smi" if vram_total_bytes is not None else "unavailable",
    }


def _compute_ollama_batch_concurrency(model: str, requested_max_concurrency: int) -> dict:
    runtime_cfg = _get_config().get("runtime", {})
    default_max = int(runtime_cfg.get("ollama_resource_guard_default_max_concurrency", 1))
    hard_cap = int(runtime_cfg.get("ollama_resource_guard_hard_cap", 2))
    guard_enabled = bool(runtime_cfg.get("ollama_resource_guard_enabled", True))
    requested = max(1, int(requested_max_concurrency))
    resolved_model, _ = _resolve_ollama_model(model)
    if resolved_model is None:
        resolved_model = _get_config()["models"]["ollama_default_model"]

    if not guard_enabled:
        applied = max(1, min(requested, hard_cap))
        return {
            "resolved_model": resolved_model,
            "applied_max_concurrency": applied,
            "reason": "resource_guard_disabled",
            "resources": _collect_runtime_resources(),
        }

    resources = _collect_runtime_resources()
    model_mem_map = runtime_cfg.get("ollama_model_memory_gb", {})
    model_mem_gb = model_mem_map.get(resolved_model)
    ram_free_gb = resources.get("ram_free_gb")
    reserve_ram_gb = float(runtime_cfg.get("ollama_resource_guard_reserve_ram_gb", 2.0))
    safety_factor = float(runtime_cfg.get("ollama_resource_guard_safety_factor", 0.6))

    allowed = default_max
    reason = "default_conservative_guard"

    if model_mem_gb and ram_free_gb is not None:
        usable_gb = max(0.0, float(ram_free_gb) - reserve_ram_gb)
        if model_mem_gb > 0:
            estimated = int((usable_gb * safety_factor) // float(model_mem_gb))
            allowed = max(default_max, estimated)
            reason = "resource_based_estimation"
    elif ram_free_gb is None:
        reason = "ram_unavailable_default_guard"
    else:
        reason = "model_profile_missing_default_guard"

    allowed = max(1, min(allowed, hard_cap))
    applied = max(1, min(requested, allowed))
    return {
        "resolved_model": resolved_model,
        "applied_max_concurrency": applied,
        "reason": reason,
        "resources": resources,
    }


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


def _select_provider_by_weight(chain_name: str) -> str | None:
    """Select a provider from weighted chain using weighted random selection.

    Args:
        chain_name: Name of the chain (e.g., 'ask_chatgpt_cli')

    Returns:
        Selected provider ID, or None if weighted chains not configured
    """
    config = _get_config()
    weighted_chains = config.get("routing", {}).get("weighted_chains")

    if not weighted_chains:
        return None

    chain = weighted_chains.get(chain_name)
    if not chain:
        return None

    # Calculate total weight and select provider
    total_weight = sum(entry.get("weight", 100) for entry in chain)
    if total_weight == 0:
        return None

    rand = random.uniform(0, total_weight)
    cumulative = 0.0

    for entry in chain:
        weight = entry.get("weight", 100)
        cumulative += weight
        if rand <= cumulative:
            return entry.get("provider")

    return chain[-1].get("provider") if chain else None


async def _run_ollama_with_timeout(
    model_name: str,
    prompt: str,
    timeout_seconds: float,
    output_mode: str = "clean",
) -> tuple[bool, str]:
    adapter = _get_adapter()
    run_async = adapter.run_async
    params = inspect.signature(run_async).parameters
    supports_timeout = "timeout_seconds" in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    supports_strip_noise = "strip_noise" in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    kwargs: dict[str, object] = {}
    if supports_timeout:
        kwargs["timeout_seconds"] = timeout_seconds
    if supports_strip_noise:
        kwargs["strip_noise"] = output_mode != "raw"
    task_id = TASK_TRACKER.register("ollama", prompt)
    try:
        return await run_async("ollama", [model_name], prompt, **kwargs)
    finally:
        TASK_TRACKER.deregister(task_id)


async def _execute_failover_with_timeout(
    primary: str,
    secondary: str,
    prompt: str,
    mode: str,
    *,
    force_primary: bool = False,
    allow_tertiary: bool = True,
    timeout_seconds: float,
    provider_args: dict[str, list[str]] | None = None,
    output_mode: str = "clean",
) -> str:
    # Preflight check on primary provider
    try:
        adapter = _get_adapter()
        pf_ok, pf_msg = adapter.preflight_check(primary)
        if not pf_ok and force_primary:
            return f"[PREFLIGHT FAILED] {primary}: {pf_msg}"
    except Exception:
        pass  # preflight is best-effort; proceed to failover

    failover = _get_failover()
    execute_async = failover.execute_async
    params = inspect.signature(execute_async).parameters
    supports_timeout = "timeout_seconds" in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    supports_provider_args = "provider_args" in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    supports_output_mode = "output_mode" in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    kwargs: dict[str, object] = {}
    if supports_timeout:
        kwargs["timeout_seconds"] = timeout_seconds
    if supports_provider_args and provider_args is not None:
        kwargs["provider_args"] = provider_args
    if supports_output_mode:
        kwargs["output_mode"] = output_mode
    task_id = TASK_TRACKER.register(primary, prompt)
    try:
        return await execute_async(
            primary,
            secondary,
            prompt,
            mode,
            force_primary=force_primary,
            allow_tertiary=allow_tertiary,
            **kwargs,
        )
    finally:
        TASK_TRACKER.deregister(task_id)


def _normalize_model_override(provider: str, model: str | None) -> str | None:
    token = (model or "").strip()
    if not token:
        return None
    if provider != "ollama" and token in {"default", "auto"}:
        return None
    return token


def _build_provider_model_args(provider: str, model: str | None) -> list[str]:
    if not model:
        return []
    if provider in {"codex", "gemini", "claude_code"}:
        return ["--model", model]
    return []


def _is_task_execution_failed(response: str) -> bool:
    return response.startswith("[Task Execution Failed]")


def _is_model_selection_failure(response: str) -> bool:
    if not _is_task_execution_failed(response):
        return False
    low = response.lower()
    markers = (
        "model not found",
        "unknown model",
        "invalid model",
        "unsupported model",
        "invalid value for '--model'",
        "unrecognized option '--model'",
        "unknown option '--model'",
    )
    return any(marker in low for marker in markers)


def _build_provider_model_trials(provider: str, requested_model: str | None) -> list[str | None]:
    explicit = _normalize_model_override(provider, requested_model)
    trials: list[str | None] = []
    if explicit:
        trials.append(explicit)
    else:
        catalog_key = f"{provider}_model_catalog"
        catalog = _get_config().get("models", {}).get(catalog_key, [])
        for item in catalog:
            token = (item or "").strip()
            if token and token not in trials:
                trials.append(token)
    if None not in trials:
        trials.append(None)
    return trials


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


def _list_static_provider_models(provider_id: str) -> dict:
    models_cfg = _get_config()["models"]
    commands_cfg = _get_config()["commands"]
    catalog_key = f"{provider_id}_model_catalog"
    catalog = models_cfg.get(catalog_key, [])
    return {
        "configured": _is_provider_configured(provider_id),
        "source": "config",
        "model_flag": "--model",
        "catalog": catalog,
        "catalog_count": len(catalog),
        "command": commands_cfg.get(provider_id, {}).get("exec", []),
    }


@mcp.tool()
async def ask_chatgpt_cli(
    prompt: str,
    save_path: str = None,
    force_model: bool = False,
    model: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    output_mode: str = "clean",
) -> str:
    """Send a prompt to ChatGPT/Codex CLI with automatic failover to Gemini and Ollama.

    Args:
        prompt: The text prompt to send.
        save_path: Optional file path to save the response.
        force_model: If True, skip failover and only use the primary provider.
        model: Model name override (e.g. 'gpt-4o'). None uses config default.
        timeout_seconds: Per-call timeout in seconds. Default from config (~120s).
        max_output_tokens: Limit response tokens (provider-dependent).
        response_format: 'json' for JSON output, None for plain text.
        verbosity: 'verbose' for extra metadata, None for standard.
        stream: Reserved for future streaming support.
        output_mode: 'clean' (default, strips CLI noise) or 'raw' (preserves all output).

    Returns:
        Provider response text with routing metadata appended.
    """
    options = _normalize_ask_options(
        timeout_seconds, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _normalize_output_mode(output_mode)

    # P2-1: Use weighted routing if configured
    primary_provider = _select_provider_by_weight("ask_chatgpt_cli")
    if primary_provider is None:
        primary_provider = "codex"
    secondary_provider = "gemini"

    response = ""
    for trial_model in _build_provider_model_trials(primary_provider, model):
        provider_args = (
            {primary_provider: _build_provider_model_args(primary_provider, trial_model)}
            if trial_model is not None
            else None
        )
        response = await _execute_failover_with_timeout(
            primary_provider,
            secondary_provider,
            prompt,
            "execution",
            force_primary=force_model,
            allow_tertiary=True,
            timeout_seconds=options["timeout_seconds"],
            provider_args=provider_args,
            output_mode=normalized_output_mode,
        )
        if not _is_task_execution_failed(response):
            break
        if not _is_model_selection_failure(response):
            break
    response = _save_if_requested(response, save_path, tool_name="ask_chatgpt_cli")
    return _finalize_response(response, primary_provider, options)


@mcp.tool()
async def ask_gemini_cli(
    prompt: str,
    save_path: str = None,
    force_model: bool = False,
    model: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    output_mode: str = "clean",
) -> str:
    """Send a prompt to Gemini CLI with automatic failover to Codex and Ollama.

    Args:
        prompt: The text prompt to send.
        save_path: Optional file path to save the response.
        force_model: If True, skip failover and only use the primary provider.
        model: Model name override (e.g. 'gemini-2.5-pro'). None uses config default.
        timeout_seconds: Per-call timeout in seconds. Default from config (~120s).
        max_output_tokens: Limit response tokens (provider-dependent).
        response_format: 'json' for JSON output, None for plain text.
        verbosity: 'verbose' for extra metadata, None for standard.
        stream: Reserved for future streaming support.
        output_mode: 'clean' (default, strips CLI noise) or 'raw' (preserves all output).

    Returns:
        Provider response text with routing metadata appended.
    """
    options = _normalize_ask_options(
        timeout_seconds, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _normalize_output_mode(output_mode)

    # P2-1: Use weighted routing if configured
    primary_provider = _select_provider_by_weight("ask_gemini_cli")
    if primary_provider is None:
        primary_provider = "gemini"
    secondary_provider = "codex"

    response = ""
    for trial_model in _build_provider_model_trials(primary_provider, model):
        provider_args = (
            {primary_provider: _build_provider_model_args(primary_provider, trial_model)}
            if trial_model is not None
            else None
        )
        response = await _execute_failover_with_timeout(
            primary_provider,
            secondary_provider,
            prompt,
            "analysis",
            force_primary=force_model,
            allow_tertiary=True,
            timeout_seconds=options["timeout_seconds"],
            provider_args=provider_args,
            output_mode=normalized_output_mode,
        )
        if not _is_task_execution_failed(response):
            break
        if not _is_model_selection_failure(response):
            break
    response = _save_if_requested(response, save_path, tool_name="ask_gemini_cli")
    return _finalize_response(response, primary_provider, options)


@mcp.tool()
async def ask_ollama(
    prompt: str,
    save_path: str = None,
    model: str = "default",
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    output_mode: str = "clean",
) -> str:
    """Send a prompt to a local Ollama model with cloud failover on failure.

    Args:
        prompt: The text prompt to send.
        save_path: Optional file path to save the response.
        model: Ollama model name or alias. 'default' uses config default, 'auto' selects by prompt.
        timeout_seconds: Per-call timeout. Default from config ollama_timeout_seconds (~300s).
        max_output_tokens: Limit response tokens (provider-dependent).
        response_format: 'json' for JSON output, None for plain text.
        verbosity: 'verbose' for extra metadata, None for standard.
        stream: Reserved for future streaming support.
        output_mode: 'clean' (default) or 'raw'.

    Returns:
        Provider response text. Falls back to cloud providers if Ollama is unreachable.
    """
    effective_timeout = timeout_seconds
    if effective_timeout is None:
        runtime_cfg = _get_config().get("runtime", {})
        effective_timeout = runtime_cfg.get("ollama_timeout_seconds")
    options = _normalize_ask_options(
        effective_timeout, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _normalize_output_mode(output_mode)
    is_safe, sec_msg = SecuritySanitizer.inspect(prompt, mode="execution")
    if not is_safe:
        return _finalize_response(sec_msg, "ollama", options)

    requested_token = (model or "").strip() or "default"
    if requested_token == "auto":
        requested_token = _select_auto_ollama_alias(prompt)
    resolved_model, model_error = _resolve_ollama_model(requested_token)
    if resolved_model is None:
        return _finalize_response(model_error, "ollama", options)

    installed_models_raw, installed_error = _get_installed_ollama_models()
    installed_normalized = {_normalize_model_name(name) for name in installed_models_raw}
    local_chain = _resolve_fallback_chain(resolved_model)

    if not installed_error:
        requested_installed = _normalize_model_name(resolved_model) in installed_normalized
        if not requested_installed and requested_token != "default":
            pull_cmd = f"ollama pull {resolved_model}"
            return _finalize_response(
                f"[MODEL ERROR] Requested model '{resolved_model}' is not installed locally. "
                f"Install with: {pull_cmd}",
                "ollama",
                options,
            )
        local_chain = [m for m in local_chain if _normalize_model_name(m) in installed_normalized]
        if not local_chain:
            pull_cmd = f"ollama pull {resolved_model}"
            return _finalize_response(
                f"[MODEL ERROR] Requested model '{resolved_model}' is not installed locally. "
                f"Install with: {pull_cmd}",
                "ollama",
                options,
            )

    last_local_error = ""
    for local_model in local_chain:
        success, output = await _run_ollama_with_timeout(
            local_model, prompt, options["timeout_seconds"], output_mode=normalized_output_mode
        )
        if success:
            response = f"[Source: Ollama]\n{output}"
            response = _save_if_requested(response, save_path, tool_name="ask_ollama")
            return _finalize_response(response, "ollama", options)
        last_local_error = output

    logger.warning("Ollama unreachable. Failing over to cloud chain.")
    cloud_prompt = f"[WARNING: Local Ollama failed. Executing via Cloud Backup] {prompt}"
    if last_local_error:
        cloud_prompt = f"{cloud_prompt}\n\n[Local Error Summary]\n{last_local_error}"
    response = await _execute_failover_with_timeout(
        "codex",
        "gemini",
        cloud_prompt,
        "execution",
        force_primary=False,
        allow_tertiary=False,
        timeout_seconds=options["timeout_seconds"],
        output_mode=normalized_output_mode,
    )
    response = _save_if_requested(response, save_path, tool_name="ask_ollama")
    return _finalize_response(response, "ollama", options)


@mcp.tool()
async def ask_claude_code(
    prompt: str,
    save_path: str = None,
    force_model: bool = False,
    model: str | None = None,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    output_mode: str = "clean",
) -> str:
    """Send a prompt to Claude Code CLI with automatic failover to Codex and Ollama.

    Args:
        prompt: The text prompt to send.
        save_path: Optional file path to save the response.
        force_model: If True, skip failover and only use Claude Code.
        model: Model name override. None uses config default.
        timeout_seconds: Per-call timeout in seconds. Default from config (~120s).
        max_output_tokens: Limit response tokens (provider-dependent).
        response_format: 'json' for JSON output, None for plain text.
        verbosity: 'verbose' for extra metadata, None for standard.
        stream: Reserved for future streaming support.
        output_mode: 'clean' (default) or 'raw'.

    Returns:
        Provider response text with routing metadata appended.
    """
    options = _normalize_ask_options(
        timeout_seconds, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _normalize_output_mode(output_mode)
    if not _is_provider_configured("claude_code"):
        return _finalize_response(
            "[PROVIDER ERROR] 'claude_code' is not configured in commands. "
            "Add commands.claude_code.exec/health in config to enable it.",
            "claude_code",
            options,
        )
    response = ""
    for trial_model in _build_provider_model_trials("claude_code", model):
        provider_args = (
            {"claude_code": _build_provider_model_args("claude_code", trial_model)}
            if trial_model is not None
            else None
        )
        response = await _execute_failover_with_timeout(
            "claude_code",
            "codex",
            prompt,
            "analysis",
            force_primary=force_model,
            allow_tertiary=True,
            timeout_seconds=options["timeout_seconds"],
            provider_args=provider_args,
            output_mode=normalized_output_mode,
        )
        if not _is_task_execution_failed(response):
            break
        if not _is_model_selection_failure(response):
            break
    response = _save_if_requested(response, save_path, tool_name="ask_claude_code")
    return _finalize_response(response, "claude_code", options)


@mcp.tool()
async def ask(
    prompt: str,
    provider: str = "auto",
    model: str = "default",
    save_path: str = None,
    force_model: bool = False,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    session_id: str | None = None,
    instruction_preset: str | None = None,
    output_mode: str | None = None,
) -> str:
    """Universal ask tool - routes prompt to any provider with smart failover.

    Args:
        prompt: The text prompt to send.
        provider: 'auto' (default, routes to codex), 'codex', 'gemini', 'ollama', 'claude_code'.
        model: Model name or 'default'/'auto'. Provider-specific (e.g. 'gpt-4o', 'gemini-2.5-pro').
        save_path: Optional file path to save the response.
        force_model: If True, skip failover chain.
        timeout_seconds: Per-call timeout in seconds. Default from config.
        max_output_tokens: Limit response tokens.
        response_format: 'json' for JSON output, None for plain text.
        verbosity: 'verbose' for extra metadata, None for standard.
        stream: Reserved for future streaming support.
        session_id: Optional session ID for multi-turn conversation memory.
        instruction_preset: 'strict_once' or 'none'. Default from config.
        output_mode: 'clean' (default) or 'raw'.

    Returns:
        Provider response text with routing metadata.
    """
    options = _normalize_ask_options(
        timeout_seconds, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _resolve_output_mode(output_mode)
    normalized_instruction_preset = _resolve_instruction_preset(instruction_preset)
    requested_provider = (provider or "auto").strip().lower()
    normalized_provider = "codex" if requested_provider == "auto" else requested_provider
    effective_prompt = _build_prompt_with_session(prompt, session_id)
    effective_prompt = _apply_instruction_preset(
        effective_prompt, normalized_instruction_preset, options["response_format"]
    )

    cache = _get_prompt_cache()
    cache_key = None
    if cache is not None:
        cache_key = PromptCache.build_key(
            {
                "provider": normalized_provider,
                "model": model,
                "prompt": effective_prompt,
                "force_model": force_model,
                "options": json.dumps(options, sort_keys=True),
                "output_mode": normalized_output_mode,
                "instruction_preset": normalized_instruction_preset,
            }
        )
        cached = cache.get(cache_key)
        if cached is not None:
            if options["response_format"] == "json":
                normalized_cached = _mark_cached_json_payload(cached)
                if normalized_cached is not None:
                    return normalized_cached
                return _finalize_response(cached, normalized_provider, options, cached=True)
            return cached

    if requested_provider != "auto" and _get_provider_registry().get(normalized_provider) is None:
        return _finalize_response(
            f"[PROVIDER ERROR] Unknown provider '{provider}'. Use: auto|{_known_providers_text()}",
            normalized_provider,
            options,
        )
    raw = await _dispatch_ask_provider(
        normalized_provider,
        effective_prompt,
        save_path=save_path,
        force_model=force_model,
        model=model,
        options=options,
        output_mode=normalized_output_mode,
    )

    if cache is not None and cache_key is not None:
        cache.set(cache_key, raw)
    _remember_session_turn(session_id, prompt, raw)
    return raw


@mcp.tool()
async def ask_batch(
    prompts: list[str],
    provider: str = "auto",
    model: str = "default",
    mode: str = "sequential",
    max_concurrency: int = 3,
    save_path: str = None,
    force_model: bool = False,
    timeout_seconds: float | None = None,
    max_output_tokens: int | None = None,
    response_format: str | None = None,
    verbosity: str | None = None,
    stream: bool | None = None,
    session_id: str | None = None,
    instruction_preset: str | None = None,
    output_mode: str | None = None,
    priority: str = "normal",
    stream_results: bool = False,
    rate_limit_rps: float | None = None,
    ctx: Context | None = None,
) -> str:
    """Send multiple prompts in batch (sequential or parallel).

    Args:
        prompts: List of text prompts to send.
        provider: 'auto' (default), 'codex', 'gemini', 'ollama', 'claude_code'.
        model: Model name or 'default'/'auto'.
        mode: 'sequential' (default) or 'parallel'.
        max_concurrency: Max parallel requests when mode='parallel' (default 3).
        save_path: Optional file path to save combined results.
        force_model: If True, skip failover chain.
        timeout_seconds: Per-call timeout in seconds.
        max_output_tokens: Limit response tokens.
        response_format: 'json' for JSON output.
        verbosity: 'verbose' for extra metadata.
        stream: Reserved for future streaming support.
        session_id: Optional session ID for conversation memory.
        instruction_preset: 'strict_once' or 'none'.
        output_mode: 'clean' (default) or 'raw'.
        priority: 'high', 'normal' (default), or 'low' - job priority for scheduling.
        stream_results: If True, report progress via MCP progress notifications.
        rate_limit_rps: Optional rate limit in requests per second.
        ctx: MCP context for progress reporting.

    Returns:
        JSON array of results with index, status, and response for each prompt.
    """
    options = _normalize_ask_options(
        timeout_seconds, max_output_tokens, response_format, verbosity, stream
    )
    normalized_output_mode = _resolve_output_mode(output_mode)
    normalized_instruction_preset = _resolve_instruction_preset(instruction_preset)
    normalized_mode = (mode or "sequential").strip().lower()
    if normalized_mode not in {"sequential", "parallel"}:
        return json.dumps(
            {
                "status": "error",
                "error": "mode must be one of: sequential, parallel",
            },
            ensure_ascii=False,
        )
    if max_concurrency < 1:
        return json.dumps(
            {"status": "error", "error": "max_concurrency must be >= 1"},
            ensure_ascii=False,
        )
    if not prompts:
        return json.dumps(
            {"status": "error", "error": "prompts must contain at least one item"},
            ensure_ascii=False,
        )

    cleaned_prompts = [str(item).strip() for item in prompts if str(item).strip()]
    if not cleaned_prompts:
        return json.dumps(
            {"status": "error", "error": "prompts must contain non-empty items"},
            ensure_ascii=False,
        )
    effective_max_concurrency = max_concurrency
    concurrency_meta = None
    if provider.strip().lower() == "ollama":
        concurrency_meta = _compute_ollama_batch_concurrency(model, max_concurrency)
        effective_max_concurrency = concurrency_meta["applied_max_concurrency"]

    async def _run_one(idx: int, prompt_text: str) -> dict:
        job_session_id = f"{session_id}:job-{idx}" if session_id else None
        started = time.perf_counter()
        try:
            content = await ask(
                prompt=prompt_text,
                provider=provider,
                model=model,
                save_path=save_path,
                force_model=force_model,
                timeout_seconds=options["timeout_seconds"],
                max_output_tokens=options["max_output_tokens"],
                response_format=options["response_format"],
                verbosity=options["verbosity"],
                stream=options["stream"],
                session_id=job_session_id,
                instruction_preset=normalized_instruction_preset,
                output_mode=normalized_output_mode,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "job_id": idx,
                "status": "ok",
                "duration_ms": duration_ms,
                "content": content,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "job_id": idx,
                "status": "error",
                "duration_ms": duration_ms,
                "error": str(exc),
            }

    # Build progress callback for streaming results
    async def _report_progress(completed: int, total: int) -> None:
        if stream_results and ctx:
            await ctx.report_progress(progress=completed, total=total)

    # Build rate limiter if requested
    rate_limiter = None
    if rate_limit_rps is not None and rate_limit_rps > 0:
        rate_limiter = TokenBucket(rate=rate_limit_rps, capacity=min(rate_limit_rps, 10.0))

    # Build prioritized jobs
    parsed_priority = parse_priority(priority)
    jobs = [
        PrioritizedJob(job_id=idx, prompt=p, priority=parsed_priority, _insertion_order=idx)
        for idx, p in enumerate(cleaned_prompts)
    ]

    # Use BatchExecutor for execution
    executor = BatchExecutor(
        rate_limiter=rate_limiter,
        max_concurrency=effective_max_concurrency,
    )

    if normalized_mode == "sequential":
        results = await executor.execute_sequential(jobs, _run_one, _report_progress)
    else:
        results = await executor.execute_parallel(jobs, _run_one, _report_progress)

    ok_count = sum(1 for item in results if item["status"] == "ok")
    err_count = len(results) - ok_count
    payload = {
        "status": "ok",
        "mode": normalized_mode,
        "provider": provider,
        "model": model,
        "requested_max_concurrency": max_concurrency,
        "applied_max_concurrency": effective_max_concurrency,
        "total_jobs": len(results),
        "ok_jobs": ok_count,
        "error_jobs": err_count,
        "results": results,
    }
    if concurrency_meta is not None:
        payload["concurrency_guard"] = concurrency_meta
    if rate_limit_rps is not None:
        payload["rate_limit_rps"] = rate_limit_rps
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_ollama_models() -> str:
    """List available Ollama models, aliases, installed status, and pull commands for missing models.

    Returns:
        JSON with default_model, aliases, catalog, installed models, and missing models with pull commands.
    """
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


@mcp.tool()
def list_provider_models(provider: str = "all") -> str:
    """List available models for one or all providers.

    Args:
        provider: 'all' (default), 'codex', 'gemini', 'ollama', or 'claude_code'.

    Returns:
        JSON with model catalogs and availability per provider.
    """
    normalized = (provider or "all").strip().lower()
    allowed = {"all", "codex", "gemini", "ollama", "claude_code"}
    if normalized not in allowed:
        return json.dumps(
            {
                "status": "error",
                "error": f"Unknown provider '{provider}'. Use one of: all|codex|gemini|ollama|claude_code",
            },
            ensure_ascii=False,
        )

    if normalized == "all":
        targets = ["codex", "gemini", "ollama", "claude_code"]
    else:
        targets = [normalized]

    providers_payload: dict[str, dict] = {}
    for target in targets:
        if target == "ollama":
            providers_payload[target] = json.loads(list_ollama_models())
        else:
            providers_payload[target] = _list_static_provider_models(target)

    return json.dumps(
        {
            "status": "ok",
            "requested_provider": normalized,
            "providers": providers_payload,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def list_orchestrator_capabilities() -> str:
    """List orchestrator parallel execution capabilities and recommended policies.

    Returns:
        JSON describing per-orchestrator parallel support and recommended usage patterns.
    """
    payload = {
        "status": "ok",
        "recommended_policy": {
            "default_execution_mode": "single_mcp_call",
            "parallel_execution_owner": "mcp_internal",
            "rationale": "Keep behavior deterministic regardless of client-side parallel orchestration support."
        },
        "orchestrators": {
            "codex": {
                "external_parallel_tool_calls": "assume_limited",
                "guidance": "Prefer one MCP call and use ask_batch(mode=parallel) for fan-out."
            },
            "gemini": {
                "external_parallel_tool_calls": "assume_limited",
                "guidance": "Prefer one MCP call and use ask_batch(mode=parallel) for fan-out."
            },
            "claude_code": {
                "external_parallel_tool_calls": "possible",
                "guidance": "Still prefer MCP-internal orchestration for stable cross-client behavior."
            }
        },
        "fallback_rule": "If external parallel behavior is unclear, route all fan-out through ask_batch.",
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_cli_noninteractive_policy() -> str:
    """List CLI non-interactive mode configuration and trust/auth skip flags per provider.

    Returns:
        JSON with configured exec commands, noninteractive modes, and trust-skip flags.
    """
    commands_cfg = _get_config().get("commands", {})
    codex_exec = commands_cfg.get("codex", {}).get("exec", [])
    gemini_exec = commands_cfg.get("gemini", {}).get("exec", [])
    claude_exec = commands_cfg.get("claude_code", {}).get("exec", [])
    payload = {
        "status": "ok",
        "providers": {
            "codex": {
                "configured_exec": codex_exec,
                "noninteractive_mode": "codex exec",
                "skip_trust_like_prompt_flag": "--skip-git-repo-check",
                "skip_flag_configured": "--skip-git-repo-check" in codex_exec,
            },
            "gemini": {
                "configured_exec": gemini_exec,
                "noninteractive_mode": "gemini -p/--prompt",
                "documented_workspace_trust_skip_flag": None,
                "note": "Complete one-time trust/auth interactively if non-interactive calls stall.",
            },
            "claude_code": {
                "configured_exec": claude_exec,
                "noninteractive_mode": "claude -p/--print",
                "workspace_trust_prompt_skipped_in_print_mode": "-p" in claude_exec
                or "--print" in claude_exec,
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_prompt_execution_policy() -> str:
    """List prompt execution policy presets and current runtime defaults.

    Returns:
        JSON with available instruction_presets, output_modes, and current defaults.
    """
    defaults = _get_runtime_defaults()
    payload = {
        "status": "ok",
        "runtime_defaults": {
            "instruction_preset": defaults.get("instruction_preset", "strict_once"),
            "output_mode": defaults.get("output_mode", "clean"),
        },
        "instruction_presets": {
            "none": {
                "description": "No additional execution policy block is injected."
            },
            "strict_once": {
                "description": "Inject a fixed policy block for single-shot execution and assumption labeling.",
                "recommended_for": ["ask", "ask_batch"],
                "recommended_args": {
                    "instruction_preset": "strict_once",
                    "response_format": "json",
                },
            },
        },
        "guidance": "Set runtime.ask_defaults to avoid repeating these args in every MCP call.",
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_runtime_resources(model: str = "default", requested_max_concurrency: int = 1) -> str:
    """Check Ollama resource availability and recommended batch concurrency.

    Args:
        model: Ollama model name to check resources for (default: 'default').
        requested_max_concurrency: Desired parallel request count (default: 1).

    Returns:
        JSON with resource status and recommended concurrency settings.
    """
    ollama_meta = _compute_ollama_batch_concurrency(model, requested_max_concurrency)
    payload = {
        "status": "ok",
        "requested_model": model,
        "requested_max_concurrency": requested_max_concurrency,
        "ollama_recommendation": ollama_meta,
    }
    return json.dumps(payload, ensure_ascii=False)


_PROVIDER_INSTALL_HINTS = {
    "codex": "brew install --cask codex (or npm install -g @openai/codex)",
    "gemini": "brew install gemini-cli (or npm install -g @anthropic/gemini-cli)",
    "ollama": "brew install --cask ollama (or https://ollama.ai/download)",
    "claude_code": "brew install --cask claude-code (or npm install -g @anthropic/claude-code)",
}


@mcp.tool()
def health_check() -> str:
    """Check health status of model-bridge and available providers.

    Returns:
        JSON with health status, available providers (with version and install hints),
        ollama_running status, and current config defaults.
    """
    config = _get_config()
    commands = config.get("commands", {})
    runtime = config.get("runtime", {})

    providers_status = {}
    for provider in ["codex", "gemini", "ollama", "claude_code"]:
        cmd_config = commands.get(provider, {})
        health_cmd = cmd_config.get("health", [])
        exec_cmd = cmd_config.get("exec", [])

        if not health_cmd:
            entry: dict = {
                "available": False,
                "error": "not configured",
            }
            hint = _PROVIDER_INSTALL_HINTS.get(provider)
            if hint:
                entry["install_hint"] = hint
            providers_status[provider] = entry
            continue

        # Check if CLI binary is installed
        bin_name = exec_cmd[0] if exec_cmd else health_cmd[0]
        if not shutil.which(bin_name):
            entry = {
                "available": False,
                "error": f"CLI '{bin_name}' not found in PATH",
            }
            hint = _PROVIDER_INSTALL_HINTS.get(provider)
            if hint:
                entry["install_hint"] = hint
            providers_status[provider] = entry
            continue

        try:
            result = subprocess.run(
                health_cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            entry = {
                "available": result.returncode == 0,
                "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if result.returncode == 0 and result.stdout.strip():
                entry["version"] = result.stdout.strip().splitlines()[0][:120]
            elif result.returncode != 0:
                entry["error"] = f"health command exited with code {result.returncode}"
            providers_status[provider] = entry
        except subprocess.TimeoutExpired:
            providers_status[provider] = {
                "available": False,
                "error": "health check timed out (5s)",
                "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except Exception as e:
            providers_status[provider] = {
                "available": False,
                "error": str(e),
                "last_check": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    # Ollama-specific: distinguish "not installed" vs "not running"
    ollama_entry = providers_status.get("ollama", {})
    ollama_running = ollama_entry.get("available", False)
    if not ollama_running and shutil.which("ollama"):
        ollama_entry["note"] = "Ollama CLI is installed but service may not be running. Try: ollama serve"

    any_available = any(p.get("available", False) for p in providers_status.values())

    payload = {
        "status": "healthy" if any_available else "degraded",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "0.1.4",
        "providers": providers_status,
        "ollama_running": ollama_running,
        "config_defaults": {
            "subprocess_timeout_seconds": runtime.get("subprocess_timeout_seconds"),
            "ollama_timeout_seconds": runtime.get("ollama_timeout_seconds"),
            "system_suffix_enabled": bool(runtime.get("system_suffix")),
        },
    }

    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def set_config(
    timeout_seconds: float | None = None,
    ollama_timeout_seconds: float | None = None,
) -> str:
    """Update runtime configuration (timeout defaults) without restarting the server.

    Args:
        timeout_seconds: New default subprocess timeout in seconds (e.g. 180.0).
        ollama_timeout_seconds: New default Ollama-specific timeout in seconds.

    Returns:
        JSON with the new effective configuration values.
    """
    global CONFIG, ADAPTER
    config = _get_config()
    runtime = config.get("runtime", {})
    changes = {}

    if timeout_seconds is not None:
        runtime["subprocess_timeout_seconds"] = timeout_seconds
        changes["subprocess_timeout_seconds"] = timeout_seconds
        adapter = _get_adapter()
        adapter.timeout_seconds = timeout_seconds

    if ollama_timeout_seconds is not None:
        runtime["ollama_timeout_seconds"] = ollama_timeout_seconds
        changes["ollama_timeout_seconds"] = ollama_timeout_seconds

    return json.dumps(
        {
            "status": "ok",
            "changes": changes,
            "effective": {
                "subprocess_timeout_seconds": runtime.get("subprocess_timeout_seconds"),
                "ollama_timeout_seconds": runtime.get("ollama_timeout_seconds"),
            },
        },
        ensure_ascii=False,
    )


@mcp.tool()
def list_last_errors(count: int = 5) -> str:
    """Return recent error details from the in-memory error buffer.

    Args:
        count: Number of recent errors to return (default 5, max 50).

    Returns:
        JSON array of recent errors with timestamp, provider, category, and message.
    """
    errors = _get_last_errors_from_buffer(count)
    return json.dumps(
        {"status": "ok", "count": len(errors), "errors": errors},
        ensure_ascii=False,
    )


@mcp.tool()
def list_active_tasks() -> str:
    """List currently running subprocess calls with provider, elapsed time, and prompt preview.

    Returns:
        JSON with active task count and task details.
    """
    tasks = TASK_TRACKER.list_active()
    return json.dumps(
        {"status": "ok", "active_count": len(tasks), "tasks": tasks},
        ensure_ascii=False,
    )


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
