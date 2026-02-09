"""Subprocess-based CLI adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Mapping, Sequence, Tuple

from .base import CLIAdapter


class SubprocessAdapter(CLIAdapter):
    """Execute configured model CLIs through subprocess."""

    def __init__(
        self,
        cli_config: Mapping[str, Mapping[str, Sequence[str]]],
        env: Mapping[str, str] | None = None,
        system_suffix: str = "",
    ) -> None:
        self.cli_config = cli_config
        self.env = dict(env) if env is not None else os.environ.copy()
        self.system_suffix = system_suffix

    def run(self, service_name: str, args: Sequence[str], input_text: str) -> Tuple[bool, str]:
        config = self.cli_config.get(service_name, {})
        cmd_base = list(config.get("exec", []))
        if not cmd_base:
            return False, f"Configuration Error: No command defined for {service_name}"
        if not shutil.which(cmd_base[0]):
            return False, f"System Error: Command '{cmd_base[0]}' not found."

        full_cmd = cmd_base + list(args) + [input_text + self.system_suffix]
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                env=self.env,
                check=False,
            )
        except Exception as exc:
            return False, str(exc)

        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stdout + result.stderr).strip()

