"""Subprocess-based CLI adapter."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import time
from typing import Mapping, Sequence, Tuple

from .base import CLIAdapter

_INSTALL_HINTS: dict[str, str] = {
    "codex": "Install: brew install --cask codex (or npm install -g @openai/codex)",
    "gemini": "Install: brew install gemini-cli (or npm install -g @anthropic/gemini-cli)",
    "ollama": "Install: brew install --cask ollama (or https://ollama.ai/download)",
    "claude": "Install: brew install --cask claude-code (or npm install -g @anthropic/claude-code)",
}


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
        self._preflight_cache: dict[str, tuple[bool, str, float]] = {}

    _PREFLIGHT_CACHE_TTL = 60.0

    def preflight_check(self, service_name: str) -> tuple[bool, str]:
        """Check if a CLI provider is installed and responsive (cached for 60s)."""
        now = time.time()
        cached = self._preflight_cache.get(service_name)
        if cached is not None:
            ok, msg, ts = cached
            if now - ts < self._PREFLIGHT_CACHE_TTL:
                return ok, msg

        config = self.cli_config.get(service_name, {})
        cmd_base = list(config.get("exec", []))
        if not cmd_base:
            result = (False, f"No command configured for {service_name}")
            self._preflight_cache[service_name] = (*result, now)
            return result

        if not shutil.which(cmd_base[0]):
            hint = _INSTALL_HINTS.get(cmd_base[0], "")
            hint_suffix = f" {hint}" if hint else ""
            result = (False, f"Command '{cmd_base[0]}' not found.{hint_suffix}")
            self._preflight_cache[service_name] = (*result, now)
            return result

        health_cmd = list(config.get("health", []))
        if health_cmd:
            try:
                proc = subprocess.run(
                    health_cmd, capture_output=True, timeout=5, check=False
                )
                if proc.returncode != 0:
                    result = (
                        False,
                        f"Health check failed for {service_name} (exit={proc.returncode})",
                    )
                    self._preflight_cache[service_name] = (*result, now)
                    return result
            except subprocess.TimeoutExpired:
                result = (False, f"Health check timed out for {service_name}")
                self._preflight_cache[service_name] = (*result, now)
                return result
            except Exception as exc:
                result = (False, f"Health check error for {service_name}: {exc}")
                self._preflight_cache[service_name] = (*result, now)
                return result

        result = (True, "ok")
        self._preflight_cache[service_name] = (*result, now)
        return result

    _NOISE_LINE_PATTERNS = (
        re.compile(r"^Loaded cached credentials\.?$"),
        re.compile(r"^Loading extension: .+$"),
        re.compile(r"^Server '.+' supports tool updates\. Listening for changes\.\.\.$"),
        re.compile(r"^Server '.+' supports resource updates\. Listening for changes\.\.\.$"),
        re.compile(r"^Hook registry initialized with \d+ hook entries$"),
    )

    @classmethod
    def _strip_known_noise_lines(cls, text: str) -> str:
        if not text:
            return text
        cleaned_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if any(pattern.fullmatch(stripped) for pattern in cls._NOISE_LINE_PATTERNS):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _prepare_command(
        self, service_name: str, args: Sequence[str], input_text: str
    ) -> Tuple[bool, str, list[str], str]:
        config = self.cli_config.get(service_name, {})
        cmd_base = list(config.get("exec", []))
        if not cmd_base:
            return False, f"Configuration Error: No command defined for {service_name}", [], ""
        if not shutil.which(cmd_base[0]):
            hint = _INSTALL_HINTS.get(cmd_base[0], "")
            hint_suffix = f" {hint}" if hint else ""
            return False, f"System Error: Command '{cmd_base[0]}' not found.{hint_suffix}", [], ""
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
        strip_noise: bool = True,
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
            output = result.stdout.strip()
            if strip_noise:
                output = self._strip_known_noise_lines(output)
            return True, output
        output = (result.stdout + result.stderr).strip()
        if strip_noise:
            output = self._strip_known_noise_lines(output)
        return False, output

    async def run_async(
        self,
        service_name: str,
        args: Sequence[str],
        input_text: str,
        timeout_seconds: float | None = None,
        strip_noise: bool = True,
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
            output = stdout.strip()
            if strip_noise:
                output = self._strip_known_noise_lines(output)
            return True, output
        output = (stdout + stderr).strip()
        if strip_noise:
            output = self._strip_known_noise_lines(output)
        return False, output
