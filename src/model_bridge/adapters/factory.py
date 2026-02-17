"""Adapter factory for runtime transport mode selection."""

from __future__ import annotations

import os
from typing import Mapping

from .base import BaseAdapter
from .sdk_adapter import SDKAdapter
from .subprocess_adapter import SubprocessAdapter


def build_adapter(
    config: dict,
    *,
    env: Mapping[str, str] | None = None,
) -> BaseAdapter:
    """Create adapter based on runtime transport mode."""
    runtime = config.get("runtime", {})
    mode = str(runtime.get("transport_mode", "subprocess")).strip().lower()

    if mode == "sdk":
        return SDKAdapter(
            models_config=config.get("models", {}),
            env=env if env is not None else os.environ.copy(),
            system_suffix=runtime.get("system_suffix", ""),
            apply_system_suffix_for=runtime.get("apply_system_suffix", {}),
            timeout_seconds=runtime.get("subprocess_timeout_seconds"),
        )

    if mode == "subprocess":
        return SubprocessAdapter(
            cli_config=config.get("commands", {}),
            env=env if env is not None else os.environ.copy(),
            system_suffix=runtime.get("system_suffix", ""),
            apply_system_suffix_for=runtime.get("apply_system_suffix", {}),
            timeout_seconds=runtime.get("subprocess_timeout_seconds"),
        )

    raise ValueError(f"Unsupported runtime.transport_mode: {mode}")
