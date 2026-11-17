"""Antigravity model and effort support metadata."""

from __future__ import annotations

from typing import Sequence

ALLOWED_AGY_EFFORT_VALUES: tuple[str, ...] = (
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

DOCUMENTED_AGY_EFFORTS_BY_MODEL: dict[str, tuple[str, ...]] = {
    "default": (),
    "auto": (),
    "gemini-4-argon-low": ("low",),
    "gemini-4-argon-medium": ("medium",),
    "gemini-4-argon-high": ("high",),
    "gemini-4-hydrogen-low": ("low",),
    "gemini-4-hydrogen-medium": ("medium",),
    "gemini-4-hydrogen-high": ("high",),
    "gemini-4-hydrogen-xhigh": ("xhigh",),
    "gemini-pro-orchestrator-g1-pro": (),
    "gemini-3.8-flash-low": ("low",),
    "gemini-3.8-flash-medium": ("medium",),
    "gemini-3.8-flash-high": ("high",),
    "claude-opus-5-5-low": ("low",),
    "claude-opus-5-5-medium": ("medium",),
    "claude-opus-5-5-high": ("high",),
    "claude-sonnet-5-5-low": ("low",),
    "claude-sonnet-5-5-medium": ("medium",),
    "claude-sonnet-5-5-high": ("high",),
    "gpt-oss-120b-medium": ("medium",),
}


def normalize_agy_reasoning_effort(reasoning_effort: str | None) -> str | None:
    token = (reasoning_effort or "").strip().lower()
    if not token:
        return None
    if token not in ALLOWED_AGY_EFFORT_VALUES:
        allowed = ", ".join(ALLOWED_AGY_EFFORT_VALUES)
        raise ValueError(f"reasoning_effort must be one of: {allowed}")
    return token


def get_documented_agy_efforts(model_name: str | None) -> tuple[str, ...] | None:
    token = (model_name or "").strip()
    if not token:
        return None
    return DOCUMENTED_AGY_EFFORTS_BY_MODEL.get(token)


def validate_agy_reasoning_effort(
    model_name: str,
    reasoning_effort: str | None,
) -> str | None:
    normalized = normalize_agy_reasoning_effort(reasoning_effort)
    if normalized is None:
        return None
    supported = get_documented_agy_efforts(model_name)
    if supported is None:
        raise ValueError(
            f"Model '{model_name}' is not in the documented Antigravity reasoning_effort matrix."
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


def filter_agy_models_for_reasoning_effort(
    model_names: Sequence[str],
    reasoning_effort: str | None,
) -> list[str]:
    normalized = normalize_agy_reasoning_effort(reasoning_effort)
    seen: set[str] = set()
    filtered: list[str] = []
    for item in model_names:
        token = (item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        supported = get_documented_agy_efforts(token)
        if normalized is None:
            filtered.append(token)
        elif supported and normalized in supported:
            filtered.append(token)
    return filtered
