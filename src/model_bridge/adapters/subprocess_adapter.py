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
        stdin_input = full_input
        # Gemini expects prompt value immediately after -p/--prompt.
        if service_name == "gemini" and any(flag in cmd_base for flag in ("-p", "--prompt")):
            prompt_flag = "-p" if "-p" in cmd_base else "--prompt"
            idx = full_cmd.index(prompt_flag)
            full_cmd = full_cmd[: idx + 1] + [full_input] + full_cmd[idx + 1 :]
            stdin_input = ""
        # Claude print mode uses positional prompt.
        elif service_name == "claude_code" and any(
            flag in cmd_base for flag in ("-p", "--print")
        ):
            full_cmd = full_cmd + [full_input]
            stdin_input = ""
        return True, "", full_cmd, stdin_input

    @staticmethod
    def _provider_timeout_hint(service_name: str, details: str) -> str:
        low = details.lower()
        if "trust this folder" in low or "trusted folder" in low or "workspace trust" in low:
            return (
                "Hint: The CLI is waiting for one-time workspace trust confirmation. "
                "Run the provider once in interactive mode in this directory and accept trust."
            )
        if "authorization code" in low or "visit the following url" in low:
            return (
                "Hint: The CLI is waiting for interactive OAuth login. "
                "Complete auth once in a real TTY shell, then retry."
            )
        if "raw mode is not supported" in low:
            return (
                "Hint: This CLI requires TTY/raw mode and may fail in non-interactive subprocess calls."
            )
        if service_name in {"gemini", "claude_code"}:
            return (
                "Hint: This provider may require interactive login/TTY initialization before non-interactive use."
            )
        return ""

    @classmethod
    def _format_timeout_error(
        cls, service_name: str, timeout_seconds: float | None, details: str = ""
    ) -> str:
        timeout_label = f"{timeout_seconds}" if timeout_seconds is not None else "unknown"
        base = f"Timeout Error: Command '{service_name}' exceeded {timeout_label}s"
        trimmed = details.strip()
        parts = [base]
        if trimmed:
            snippet = " ".join(trimmed.split())
            if len(snippet) > 240:
                snippet = snippet[:240].rstrip() + "..."
            parts.append(f"partial_output={snippet}")
        hint = cls._provider_timeout_hint(service_name, trimmed)
        if hint:
            parts.append(hint)
        return " | ".join(parts)

    def run(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
    ) -> Tuple[bool, str]:
        ok, err, full_cmd, full_input = self._prepare_command(service_name, args, input_text)
        if not ok:
            return False, err
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                input=full_input,
                env=self.env,
                check=False,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            details = ""
            if exc.stdout:
                details += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
            if exc.stderr:
                details += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            timeout_value = effective_timeout if effective_timeout is not None else getattr(exc, "timeout", None)
            return False, self._format_timeout_error(service_name, timeout_value, details)
        except Exception as exc:
            return False, str(exc)

        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stdout + result.stderr).strip()

    async def run_async(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
    ) -> Tuple[bool, str]:
        ok, err, full_cmd, full_input = self._prepare_command(service_name, args, input_text)
        if not ok:
            return False, err
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            if effective_timeout is None:
                stdout_bytes, stderr_bytes = await proc.communicate(full_input.encode("utf-8"))
            else:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(full_input.encode("utf-8")),
                    timeout=effective_timeout,
                )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            details = stdout_bytes.decode("utf-8", errors="replace") + stderr_bytes.decode(
                "utf-8", errors="replace"
            )
            return False, self._format_timeout_error(service_name, effective_timeout, details)
        except Exception as exc:
            return False, str(exc)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if proc.returncode == 0:
            return True, stdout.strip()
        return False, (stdout + stderr).strip()
