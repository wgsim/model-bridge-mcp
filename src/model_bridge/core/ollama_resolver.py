"""Ollama model resolution, fallback chains, and resource detection."""

from __future__ import annotations

import shutil
import subprocess

__all__ = [
    "resolve_ollama_model",
    "normalize_model_name",
    "resolve_fallback_chain",
    "select_auto_ollama_alias",
    "parse_ollama_list_output",
    "get_installed_ollama_models",
    "compute_ollama_batch_concurrency",
    "detect_ram_bytes",
    "detect_nvidia_vram_bytes",
    "collect_runtime_resources",
    "safe_gb",
]


def resolve_ollama_model(model_arg: str, config: dict) -> tuple[str | None, str]:
    """Resolve an Ollama model name or alias to the actual model identifier.

    Args:
        model_arg: Model name or alias string (e.g. 'default', 'coder', 'gpt-oss:20b').
        config: Full application config dict.

    Returns:
        Tuple of (resolved_model_name, error_message). On success error is empty.
    """
    models_cfg = config["models"]
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


def normalize_model_name(name: str) -> str:
    """Strip repeated ':latest' suffix from a model name."""
    value = name.strip()
    while value.endswith(":latest"):
        value = value[: -len(":latest")]
    return value


def resolve_fallback_chain(requested_model: str, config: dict) -> list[str]:
    """Build an ordered fallback model list for local Ollama execution.

    Args:
        requested_model: Primary model name to try first.
        config: Full application config dict.

    Returns:
        Ordered list of model names to try (deduplicated).
    """
    models_cfg = config["models"]
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


def select_auto_ollama_alias(prompt: str, config: dict) -> str:
    """Auto-route a prompt to an Ollama alias based on content analysis.

    Args:
        prompt: User prompt text.
        config: Full application config dict.

    Returns:
        Alias string ('coder', 'fast', or 'default').
    """
    runtime_cfg = config.get("runtime", {})
    short_threshold = runtime_cfg.get("auto_routing_short_prompt_threshold", 120)
    low = prompt.lower()
    if any(token in low for token in ("def ", "class ", "function", "python", "code", "bug", "stacktrace")):
        return "coder"
    if len(prompt.strip()) <= short_threshold:
        return "fast"
    return "default"


def parse_ollama_list_output(output: str) -> list[str]:
    """Parse the text output of ``ollama list`` into model name strings."""
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


def get_installed_ollama_models() -> tuple[list[str], str]:
    """Run ``ollama list`` and return (model_names, error_string)."""
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
    return parse_ollama_list_output(proc.stdout), ""


def safe_gb(value_bytes: int | None) -> float | None:
    """Convert bytes to gigabytes, rounded to two decimal places."""
    if value_bytes is None:
        return None
    return round(value_bytes / (1024**3), 2)


def detect_ram_bytes() -> tuple[int | None, int | None]:
    """Detect total and available system RAM via ``os.sysconf``."""
    import os

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * total_pages, page_size * available_pages
    except (ValueError, OSError, AttributeError):
        return None, None


def detect_nvidia_vram_bytes() -> tuple[int | None, int | None]:
    """Detect total and free NVIDIA VRAM via ``nvidia-smi``."""
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


def collect_runtime_resources() -> dict:
    """Aggregate RAM and VRAM info into a summary dict."""
    ram_total_bytes, ram_free_bytes = detect_ram_bytes()
    vram_total_bytes, vram_free_bytes = detect_nvidia_vram_bytes()
    return {
        "ram_total_gb": safe_gb(ram_total_bytes),
        "ram_free_gb": safe_gb(ram_free_bytes),
        "vram_total_gb": safe_gb(vram_total_bytes),
        "vram_free_gb": safe_gb(vram_free_bytes),
        "vram_detector": "nvidia-smi" if vram_total_bytes is not None else "unavailable",
    }


def compute_ollama_batch_concurrency(model: str, requested_max_concurrency: int, config: dict) -> dict:
    """Resource guard for Ollama batch concurrency.

    Args:
        model: Ollama model name or alias.
        requested_max_concurrency: Desired parallel request count.
        config: Full application config dict.

    Returns:
        Dict with resolved_model, applied_max_concurrency, reason, and resources.
    """
    runtime_cfg = config.get("runtime", {})
    default_max = int(runtime_cfg.get("ollama_resource_guard_default_max_concurrency", 1))
    hard_cap = int(runtime_cfg.get("ollama_resource_guard_hard_cap", 2))
    guard_enabled = bool(runtime_cfg.get("ollama_resource_guard_enabled", True))
    requested = max(1, int(requested_max_concurrency))
    resolved_model, _ = resolve_ollama_model(model, config)
    if resolved_model is None:
        resolved_model = config["models"]["ollama_default_model"]

    if not guard_enabled:
        applied = max(1, min(requested, hard_cap))
        return {
            "resolved_model": resolved_model,
            "applied_max_concurrency": applied,
            "reason": "resource_guard_disabled",
            "resources": collect_runtime_resources(),
        }

    resources = collect_runtime_resources()
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
