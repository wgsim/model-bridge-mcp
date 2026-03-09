"""Gemini 3.x reasoning support metadata and helpers."""

from __future__ import annotations

ALLOWED_GEMINI_REASONING_EFFORT_VALUES: tuple[str, ...] = (
    "minimal",
    "low",
    "medium",
    "high",
)

DOCUMENTED_GEMINI_REASONING_EFFORTS_BY_MODEL: dict[str, tuple[str, ...]] = {
    "gemini-3.1-pro-preview": ("low", "high"),
    "gemini-3-pro-preview": ("low", "high"),
    "gemini-3-flash-preview": ("minimal", "low", "medium", "high"),
    "gemini-2.5-pro": (),
    "gemini-2.5-flash": (),
    "gemini-2.5-flash-lite": (),
}

GEMINI_THINKING_LEVELS: dict[str, str] = {
    "minimal": "MINIMAL",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


def normalize_gemini_reasoning_effort(reasoning_effort: str | None) -> str | None:
    token = (reasoning_effort or "").strip().lower()
    if not token:
        return None
    if token not in ALLOWED_GEMINI_REASONING_EFFORT_VALUES:
        allowed = ", ".join(ALLOWED_GEMINI_REASONING_EFFORT_VALUES)
        raise ValueError(f"reasoning_effort must be one of: {allowed}")
    return token


def get_documented_gemini_efforts(model_name: str | None) -> tuple[str, ...] | None:
    token = (model_name or "").strip()
    if not token:
        return None
    return DOCUMENTED_GEMINI_REASONING_EFFORTS_BY_MODEL.get(token)


def validate_gemini_reasoning_effort(
    model_name: str,
    reasoning_effort: str | None,
) -> str | None:
    normalized = normalize_gemini_reasoning_effort(reasoning_effort)
    if normalized is None:
        return None
    supported = get_documented_gemini_efforts(model_name)
    if supported is None:
        raise ValueError(
            f"Model '{model_name}' is not in the documented Gemini reasoning_effort matrix."
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


def get_gemini_thinking_level(reasoning_effort: str) -> str:
    normalized = normalize_gemini_reasoning_effort(reasoning_effort)
    assert normalized is not None
    return GEMINI_THINKING_LEVELS[normalized]
