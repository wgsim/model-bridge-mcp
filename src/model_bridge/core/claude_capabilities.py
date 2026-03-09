"""Claude 4.6 effort support metadata and validation helpers."""

from __future__ import annotations

from typing import Sequence

ALLOWED_CLAUDE_EFFORT_VALUES: tuple[str, ...] = (
    "low",
    "medium",
    "high",
    "max",
)

# Empty tuple means this MCP does not enable effort for that model.
DOCUMENTED_CLAUDE_EFFORTS_BY_MODEL: dict[str, tuple[str, ...]] = {
    "haiku": (),
    "sonnet": ("low", "medium", "high"),
    "opus": ("low", "medium", "high", "max"),
    "claude-sonnet-4-6": ("low", "medium", "high"),
    "claude-opus-4-6": ("low", "medium", "high", "max"),
}

ADAPTIVE_THINKING_MODELS: set[str] = {
    "sonnet",
    "opus",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
}

CLAUDE_UNSUPPORTED_EFFORT_MARKERS: tuple[str, ...] = (
    "not available for claude.ai subscribers",
    "not available for this account",
    "does not support effort",
    "does not support the effort",
    "unsupported effort",
    "effort is not supported",
    "output_config.effort",
)


def normalize_claude_reasoning_effort(reasoning_effort: str | None) -> str | None:
    token = (reasoning_effort or "").strip().lower()
    if not token:
        return None
    if token not in ALLOWED_CLAUDE_EFFORT_VALUES:
        allowed = ", ".join(ALLOWED_CLAUDE_EFFORT_VALUES)
        raise ValueError(f"reasoning_effort must be one of: {allowed}")
    return token


def get_documented_claude_efforts(model_name: str | None) -> tuple[str, ...] | None:
    token = (model_name or "").strip()
    if not token:
        return None
    return DOCUMENTED_CLAUDE_EFFORTS_BY_MODEL.get(token)


def validate_claude_reasoning_effort(
    model_name: str,
    reasoning_effort: str | None,
) -> str | None:
    normalized = normalize_claude_reasoning_effort(reasoning_effort)
    if normalized is None:
        return None
    supported = get_documented_claude_efforts(model_name)
    if supported is None:
        raise ValueError(
            f"Model '{model_name}' is not in the documented Claude reasoning_effort matrix."
        )
    if not supported:
        raise ValueError(f"Model '{model_name}' does not support reasoning_effort.")
    if normalized not in supported:
        allowed = ", ".join(supported)
        raise ValueError(
            f"Model '{model_name}' does not support reasoning_effort='{normalized}'. "
            f"Allowed values: {allowed}"
        )
    return normalized


def filter_claude_models_for_reasoning_effort(
    model_names: Sequence[str],
    reasoning_effort: str | None,
) -> list[str]:
    normalized = normalize_claude_reasoning_effort(reasoning_effort)
    seen: set[str] = set()
    filtered: list[str] = []
    for item in model_names:
        token = (item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        supported = get_documented_claude_efforts(token)
        if normalized is None:
            filtered.append(token)
            continue
        if supported and normalized in supported:
            filtered.append(token)
    return filtered


def get_claude_thinking_config(
    model_name: str,
    reasoning_effort: str | None,
) -> dict[str, str] | None:
    normalized = validate_claude_reasoning_effort(model_name, reasoning_effort)
    if normalized is None:
        return None
    token = (model_name or "").strip()
    if token in ADAPTIVE_THINKING_MODELS:
        return {"type": "adaptive"}
    return None


def is_claude_effort_unsupported_message(message: str | None) -> bool:
    low = (message or "").strip().lower()
    if not low:
        return False
    return any(marker in low for marker in CLAUDE_UNSUPPORTED_EFFORT_MARKERS)
