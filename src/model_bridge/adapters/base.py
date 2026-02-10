"""Adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence, Tuple


class CLIAdapter(ABC):
    """Common interface for CLI-backed model adapters."""

    @abstractmethod
    def run(self, service_name: str, args: Sequence[str], input_text: str) -> Tuple[bool, str]:
        """Run service command and return (success, output)."""

    @abstractmethod
    async def run_async(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> Tuple[bool, str]:
        """Run service command asynchronously and return (success, output)."""
