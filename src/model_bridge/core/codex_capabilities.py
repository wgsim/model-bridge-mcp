"""Codex model defaults and documented reasoning-effort support."""

from __future__ import annotations

from typing import Sequence

DEFAULT_CODEX_MODEL = "gpt-5.4"

ALLOWED_REASONING_EFFORT_VALUES: tuple[str, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)

# Empty tuple means this MCP does not enable reasoning_effort for that model.
DOCUMENTED_REASONING_EFFORTS_BY_MODEL: dict[str, tuple[str, ...]] = {
    "gpt-5.4": ("none", "low", "medium", "high", "xhigh"),
    "gpt-5.3-codex": ("low", "medium", "high", "xhigh"),
    "gpt-5.2-codex": ("low", "medium", "high", "xhigh"),
    "gpt-5.2": ("none", "low", "medium", "high", "xhigh"),
    "gpt-5.1-codex-max": (),
    "gpt-5.1-codex-mini": (),
}


def normalize_codex_reasoning_effort(reasoning_effort: str | None) -> str | None:
    token = (reasoning_effort or "").strip().lower()
    if not token:
        return None
    if token not in ALLOWED_REASONING_EFFORT_VALUES:
        allowed = ", ".join(ALLOWED_REASONING_EFFORT_VALUES)
        raise ValueError(f"reasoning_effort must be one of: {allowed}")
    return token


def get_documented_reasoning_efforts(model_name: str | None) -> tuple[str, ...] | None:
    token = (model_name or "").strip()
    if not token:
        return None
    return DOCUMENTED_REASONING_EFFORTS_BY_MODEL.get(token)


def validate_codex_reasoning_effort(
    model_name: str,
    reasoning_effort: str | None,
) -> str | None:
    normalized = normalize_codex_reasoning_effort(reasoning_effort)
    if normalized is None:
        return None
    supported = get_documented_reasoning_efforts(model_name)
    if supported is None:
        raise ValueError(
            f"Model '{model_name}' is not in the documented Codex reasoning_effort matrix."
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


def filter_codex_models_for_reasoning_effort(
    model_names: Sequence[str],
    reasoning_effort: str | None,
) -> list[str]:
    normalized = normalize_codex_reasoning_effort(reasoning_effort)
    seen: set[str] = set()
    filtered: list[str] = []
    for item in model_names:
        token = (item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        supported = get_documented_reasoning_efforts(token)
        if normalized is None:
            filtered.append(token)
            continue
        if supported and normalized in supported:
            filtered.append(token)
    return filtered
