"""Adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class BaseAdapter(ABC):
    """Common execution interface for transport adapters."""

    @abstractmethod
    def run(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        strip_noise: bool = True,
    ) -> tuple[bool, str]:
        """Run service command and return (success, output)."""

    @abstractmethod
    async def run_async(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        strip_noise: bool = True,
    ) -> tuple[bool, str]:
        """Run service command asynchronously and return (success, output)."""

    @abstractmethod
    def preflight_check(self, service_name: str) -> Tuple[bool, str]:
        """Validate provider readiness for this transport."""

    def probe_reasoning_effort(
        self,
        service_name: str,
        model_name: str,
        reasoning_effort: str,
    ) -> tuple[str, str]:
        """Probe provider-specific reasoning support.

        Returns:
            Tuple of (status, message) where status is one of:
            - "supported"
            - "unsupported"
            - "unknown"
        """
        return "unknown", ""


# Backward-compat alias used by existing imports/tests.
CLIAdapter = BaseAdapter
