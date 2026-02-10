"""Subprocess-based CLI adapter."""

from __future__ import annotations

import asyncio
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
        apply_system_suffix_for: Mapping[str, bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.cli_config = cli_config
        self.env = dict(env) if env is not None else os.environ.copy()
        self.system_suffix = system_suffix
        self.apply_system_suffix_for = dict(apply_system_suffix_for or {})
        self.timeout_seconds = timeout_seconds

    def _prepare_command(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> Tuple[bool, str, list[str], str]:
        config = self.cli_config.get(service_name, {})
        cmd_base = list(config.get("exec", []))
        if not cmd_base:
            return False, f"Configuration Error: No command defined for {service_name}", [], ""
        if not shutil.which(cmd_base[0]):
            return False, f"System Error: Command '{cmd_base[0]}' not found.", [], ""
        if self.apply_system_suffix_for.get(service_name, True):
            full_input = input_text + self.system_suffix
        else:
            full_input = input_text
        full_cmd = cmd_base + list(args)
        return True, "", full_cmd, full_input

    def run(self, service_name: str, args: Sequence[str], input_text: str) -> Tuple[bool, str]:
        ok, err, full_cmd, full_input = self._prepare_command(service_name, args, input_text)
        if not ok:
            return False, err
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                input=full_input,
                env=self.env,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return False, f"Timeout Error: Command '{service_name}' exceeded {self.timeout_seconds}s"
        except Exception as exc:
            return False, str(exc)

        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stdout + result.stderr).strip()

    async def run_async(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> Tuple[bool, str]:
        ok, err, full_cmd, full_input = self._prepare_command(service_name, args, input_text)
        if not ok:
            return False, err
        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            if self.timeout_seconds is None:
                stdout_bytes, stderr_bytes = await proc.communicate(full_input.encode("utf-8"))
            else:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(full_input.encode("utf-8")),
                    timeout=self.timeout_seconds,
                )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False, f"Timeout Error: Command '{service_name}' exceeded {self.timeout_seconds}s"
        except Exception as exc:
            return False, str(exc)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if proc.returncode == 0:
            return True, stdout.strip()
        return False, (stdout + stderr).strip()
