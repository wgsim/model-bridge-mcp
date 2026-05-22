"""Subprocess-based CLI adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence, Tuple

from .base import CLIAdapter
from model_bridge.core.claude_capabilities import (
    is_claude_effort_unsupported_message,
    normalize_claude_reasoning_effort,
)
from model_bridge.core.codex_capabilities import normalize_codex_reasoning_effort
from model_bridge.core.gemini_capabilities import normalize_gemini_reasoning_effort

logger = logging.getLogger("model_bridge.subprocess_adapter")

INSTALL_HINTS: dict[str, str] = {
    "codex": "brew install --cask codex (or npm install -g @openai/codex)",
    "gemini": "brew install gemini-cli (or npm install -g @anthropic/gemini-cli)",
    "ollama": "brew install --cask ollama (or https://ollama.ai/download)",
    "claude": "brew install --cask claude-code (or npm install -g @anthropic/claude-code)",
    "claude_code": "brew install --cask claude-code (or npm install -g @anthropic/claude-code)",
    "agy": "Make sure agy CLI is globally installed on your system PATH.",
}


# Shells to try for login shell discovery (in order of preference)
_LOGIN_SHELLS = ["bash", "zsh", "sh"]

# Common version manager directory patterns to scan directly
_VERSION_MANAGER_DIRS = [
    # Node.js - nvm
    ("~/.nvm/versions/node", "bin"),  # nvm versions
    ("~/.fnm", "bin"),                 # fnm
    ("~/.volta", "bin"),               # volta
    # Python
    ("~/.pyenv/versions", "bin"),      # pyenv versions
    ("~/.pyenv", "shims"),             # pyenv shims
    ("~/miniconda3", "bin"),           # conda
    ("~/anaconda3", "bin"),
    # Ruby
    ("~/.rbenv", "shims"),             # rbenv
    ("~/.rbenv", "bin"),
    ("~/.rvm", "bin"),                 # rvm
    # Rust
    ("~/.cargo", "bin"),               # cargo/rustup
    # Go
    ("~/.go", "bin"),
    ("~/go", "bin"),
    # User local
    ("~/.local", "bin"),
]

# Environment variables to inherit from login shell for provider authentication
_PROVIDER_ENV_VARS = [
    # Google Cloud / Gemini
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS",
    # OpenAI / Codex
    "OPENAI_API_KEY",
    # Anthropic / Claude
    "ANTHROPIC_API_KEY",
    # AWS
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    # Azure
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
]


def _is_safe_command_name(name: str) -> bool:
    """Validate command name contains only safe characters to prevent injection."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))


def _is_safe_env_var_name(name: str) -> bool:
    """Validate env var name contains only safe characters."""
    return bool(re.match(r"^[A-Z][A-Z0-9_]*$", name))


def _discover_provider_env_vars(timeout: float = 3.0) -> dict[str, str]:
    """
    Discover provider authentication env vars from login shell.

    This allows MCP server to inherit authentication that users have
    configured in their shell profiles (.bashrc, .zshrc, etc.).

    Security considerations:
    - Only reads whitelisted env vars (_PROVIDER_ENV_VARS)
    - Values are never logged
    - Used only for subprocess execution within user's own system

    Args:
        timeout: Maximum time to wait for shell response

    Returns:
        Dict of env var name -> value (only non-empty values)
    """
    discovered: dict[str, str] = {}

    for shell in _LOGIN_SHELLS:
        try:
            # Build a command that prints all whitelisted env vars
            # Format: NAME=value (one per line, only if set)
            var_checks = " || ".join(
                f'[ -n "${var}" ] && echo "{var}=${var}"'
                for var in _PROVIDER_ENV_VARS
            )
            cmd = f'{var_checks}'

            result = subprocess.run(
                [shell, "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    if "=" in line:
                        name, value = line.split("=", 1)
                        if _is_safe_env_var_name(name) and value:
                            discovered[name] = value
                break  # Success, no need to try other shells

        except subprocess.TimeoutExpired:
            logger.debug("Login shell %s timed out while discovering env vars", shell)
        except FileNotFoundError:
            logger.debug("Shell %s not found, trying next", shell)
        except Exception as e:
            logger.debug("Error using %s to discover env vars: %s", shell, e)

    return discovered


def _discover_cli_path_via_login_shell(command: str, timeout: float = 3.0) -> str | None:
    """
    Discover CLI path using login shell (loads .bashrc/.zshrc).

    This allows finding CLIs installed via version managers (nvm, pyenv, etc.)
    that add paths dynamically in shell config files.

    Args:
        command: CLI command name to find (e.g., 'codex', 'gemini')
        timeout: Maximum time to wait for shell response

    Returns:
        Absolute path to CLI or None if not found
    """
    if not _is_safe_command_name(command):
        logger.warning("Invalid command name rejected: %s", command)
        return None

    for shell in _LOGIN_SHELLS:
        try:
            result = subprocess.run(
                [shell, "-lc", f"which {command}"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().split("\n")[0]  # Take first match
                if os.path.isabs(path) and os.path.exists(path):
                    logger.debug("Found %s via %s login shell: %s", command, shell, path)
                    return path
        except subprocess.TimeoutExpired:
            logger.debug("Login shell %s timed out while searching for %s", shell, command)
        except FileNotFoundError:
            logger.debug("Shell %s not found, trying next", shell)
        except Exception as e:
            logger.debug("Error using %s to find %s: %s", shell, command, e)

    return None


def _discover_cli_path_by_direct_scan(command: str) -> str | None:
    """
    Discover CLI path by directly scanning common version manager directories.

    This is a fallback when login shell discovery fails (e.g., when .bashrc
    has an interactive shell guard that prevents nvm from loading).

    Args:
        command: CLI command name to find (e.g., 'codex', 'gemini')

    Returns:
        Absolute path to CLI or None if not found
    """
    if not _is_safe_command_name(command):
        return None

    home = Path.home()

    for base_pattern, subdir in _VERSION_MANAGER_DIRS:
        base_dir = Path(base_pattern.replace("~", str(home)))

        if not base_dir.exists():
            continue

        # Handle version directories (e.g., nvm/versions/node/v24.13.1/bin)
        if base_dir.is_dir():
            # Check if it's a version container (has version subdirs)
            try:
                version_dirs = sorted(
                    [d for d in base_dir.iterdir() if d.is_dir()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                # Check version subdirs first (most recent)
                for version_dir in version_dirs[:5]:  # Limit to 5 most recent
                    candidate = version_dir / subdir / command
                    if candidate.exists() and candidate.is_file():
                        logger.debug(
                            "Found %s via direct scan: %s", command, candidate
                        )
                        return str(candidate)
                # Also check base_dir/subdir directly
                candidate = base_dir / subdir / command
                if candidate.exists() and candidate.is_file():
                    logger.debug("Found %s via direct scan: %s", command, candidate)
                    return str(candidate)
            except (OSError, PermissionError):
                continue

    return None


def _discover_cli_path(command: str) -> str | None:
    """
    Discover CLI path using multiple strategies.

    1. First try login shell (may work if .bashrc has no interactive guard)
    2. Fall back to direct directory scanning (handles nvm/pyenv/etc)

    Args:
        command: CLI command name to find

    Returns:
        Absolute path to CLI or None if not found
    """
    # Strategy 1: Login shell
    path = _discover_cli_path_via_login_shell(command)
    if path:
        return path

    # Strategy 2: Direct scan of version manager directories
    path = _discover_cli_path_by_direct_scan(command)
    if path:
        return path

    return None


def _expand_path_with_discovered_clis(
    cli_commands: Sequence[str],
    current_path: str,
    extra_paths: Sequence[str] | None = None,
) -> str:
    """
    Expand PATH with directories containing discovered CLI tools.

    Priority order (highest first):
    1. User-specified extra_paths
    2. Auto-discovered version manager paths
    3. Current PATH

    Args:
        cli_commands: List of CLI command names to discover
        current_path: Current PATH value
        extra_paths: User-specified additional paths (highest priority)

    Returns:
        Expanded PATH with discovered CLI directories prepended
    """
    paths_to_add: list[str] = []

    # 1. User-specified extra paths (highest priority)
    if extra_paths:
        for p in extra_paths:
            expanded = Path(p).expanduser()
            if expanded.exists() and str(expanded) not in current_path:
                if str(expanded) not in paths_to_add:
                    paths_to_add.append(str(expanded))
                    logger.info("Added user-specified path: %s", expanded)

    # 2. Auto-discovered CLI paths
    for cmd in cli_commands:
        path = _discover_cli_path(cmd)
        if path:
            cmd_dir = os.path.dirname(path)
            if cmd_dir not in current_path and cmd_dir not in paths_to_add:
                paths_to_add.append(cmd_dir)
                logger.info("Discovered CLI path for '%s': %s", cmd, cmd_dir)

    if paths_to_add:
        return ":".join(paths_to_add) + ":" + current_path
    return current_path


class SubprocessAdapter(CLIAdapter):
    """Execute configured model CLIs through subprocess."""

    def __init__(
        self,
        cli_config: Mapping[str, Mapping[str, Sequence[str]]],
        env: Mapping[str, str] | None = None,
        system_suffix: str = "",
        apply_system_suffix_for: Mapping[str, bool] | None = None,
        timeout_seconds: float | None = None,
        extra_path: Sequence[str] | None = None,
        extra_env_vars: Mapping[str, str] | None = None,
        agy_timeout_seconds: float | None = None,
    ) -> None:
        self.cli_config = cli_config
        self.env = dict(env) if env is not None else os.environ.copy()
        self.system_suffix = system_suffix
        self.apply_system_suffix_for = dict(apply_system_suffix_for or {})
        self.timeout_seconds = timeout_seconds
        self.agy_timeout_seconds = agy_timeout_seconds

        self._preflight_cache: dict[str, tuple[bool, str, float]] = {}
        self._reasoning_probe_cache: dict[tuple[str, str, str], tuple[str, str, float]] = {}
        self._extra_path = list(extra_path) if extra_path else None
        self._extra_env_vars = dict(extra_env_vars) if extra_env_vars else None

        # Discover CLI paths and expand PATH
        self._expand_path_with_cli_discovery()

    def _expand_path_with_cli_discovery(self) -> None:
        """Expand PATH with directories from discovered CLI tools."""
        # Extract unique command names from cli_config
        commands_to_discover: set[str] = set()
        for service_config in self.cli_config.values():
            exec_cmd = service_config.get("exec", [])
            if exec_cmd:
                commands_to_discover.add(exec_cmd[0])

        if not commands_to_discover and not self._extra_path:
            return

        current_path = self.env.get("PATH", "")
        expanded_path = _expand_path_with_discovered_clis(
            list(commands_to_discover),
            current_path,
            self._extra_path,
        )

        if expanded_path != current_path:
            self.env["PATH"] = expanded_path
            logger.info("PATH expanded with discovered CLI directories")

        # Discover provider authentication env vars from login shell
        self._discover_provider_env_vars()

        # Apply user-specified extra_env_vars (highest priority)
        if self._extra_env_vars:
            self.env.update(self._extra_env_vars)
            logger.info("Applied %d user-configured env vars", len(self._extra_env_vars))

    def _discover_provider_env_vars(self) -> None:
        """Discover and inject provider authentication env vars from login shell."""
        discovered = _discover_provider_env_vars()
        if discovered:
            self.env.update(discovered)
            # Log without exposing values
            logger.info("Discovered %d provider env vars from login shell", len(discovered))

    _PREFLIGHT_CACHE_TTL = 60.0
    _REASONING_PROBE_CACHE_TTL = 300.0

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
            hint = INSTALL_HINTS.get(cmd_base[0], "")
            hint_suffix = f" Install: {hint}" if hint else ""
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

    def probe_reasoning_effort(
        self,
        service_name: str,
        model_name: str,
        reasoning_effort: str,
    ) -> tuple[str, str]:
        if service_name == "gemini":
            normalize_gemini_reasoning_effort(reasoning_effort)
            return "unsupported", "Gemini reasoning_effort is sdk-only in this MCP."
        if service_name != "claude_code":
            return "unknown", ""
        normalized_effort = normalize_claude_reasoning_effort(reasoning_effort)
        if normalized_effort is None:
            return "supported", ""
        cache_key = (service_name, model_name.strip(), normalized_effort)
        now = time.time()
        cached = self._reasoning_probe_cache.get(cache_key)
        if cached is not None:
            status, message, ts = cached
            if now - ts < self._REASONING_PROBE_CACHE_TTL:
                return status, message

        ok, err, full_cmd, full_input = self._prepare_command(
            service_name,
            ["--model", model_name, "--reasoning-effort", normalized_effort],
            "ping",
        )
        if not ok:
            result = ("unknown", err)
            self._reasoning_probe_cache[cache_key] = (*result, now)
            return result
        try:
            proc = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                input=full_input,
                env=self.env,
                check=False,
                timeout=1.5,
            )
        except subprocess.TimeoutExpired:
            result = ("unknown", "probe timed out")
            self._reasoning_probe_cache[cache_key] = (*result, now)
            return result
        except Exception as exc:
            result = ("unknown", str(exc))
            self._reasoning_probe_cache[cache_key] = (*result, now)
            return result

        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            result = ("supported", "ok")
        elif is_claude_effort_unsupported_message(output):
            result = ("unsupported", output or "runtime probe rejected effort")
        else:
            result = ("unknown", output)
        self._reasoning_probe_cache[cache_key] = (*result, now)
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
            hint = INSTALL_HINTS.get(cmd_base[0], "")
            hint_suffix = f" Install: {hint}" if hint else ""
            return False, f"System Error: Command '{cmd_base[0]}' not found.{hint_suffix}", [], ""
        if self.apply_system_suffix_for.get(service_name, True):
            full_input = input_text + self.system_suffix
        else:
            full_input = input_text
        rewritten_args = list(args)
        if service_name == "codex":
            ok, err, rewritten_args = self._rewrite_codex_args(rewritten_args)
            if not ok:
                return False, err, [], ""
        elif service_name == "gemini":
            ok, err, rewritten_args = self._rewrite_gemini_args(rewritten_args)
            if not ok:
                return False, err, [], ""
        elif service_name == "claude_code":
            ok, err, rewritten_args = self._rewrite_claude_args(rewritten_args)
            if not ok:
                return False, err, [], ""
        full_cmd = cmd_base + rewritten_args
        stdin_input = full_input
        # agy execution details
        if service_name == "agy":
            if any(flag in cmd_base for flag in ("-p", "--print")):
                full_cmd = full_cmd + [full_input]
                stdin_input = ""
            if "--dangerously-skip-permissions" in full_cmd:
                logger.warning(
                    "[WARNING] 'agy' provider is running with '--dangerously-skip-permissions', "
                    "allowing autonomous sub-tasks and tool executions without confirmation. "
                    "Monitor execution to prevent unintended workspace actions and token costs."
                )
        # Gemini expects prompt value immediately after -p/--prompt.
        elif service_name == "gemini" and any(flag in cmd_base for flag in ("-p", "--prompt")):
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
    def _rewrite_codex_args(args: Sequence[str]) -> tuple[bool, str, list[str]]:
        args_list = list(args)
        rewritten: list[str] = []
        idx = 0
        while idx < len(args_list):
            token = args_list[idx]
            if token != "--reasoning-effort":
                rewritten.append(token)
                idx += 1
                continue
            if idx + 1 >= len(args_list):
                return False, "Configuration Error: Missing value for --reasoning-effort", []
            effort = normalize_codex_reasoning_effort(args_list[idx + 1])
            if not effort:
                return False, "Configuration Error: Missing value for --reasoning-effort", []
            rewritten.extend(["-c", f'model_reasoning_effort="{effort}"'])
            idx += 2
        return True, "", rewritten

    @staticmethod
    def _rewrite_gemini_args(args: Sequence[str]) -> tuple[bool, str, list[str]]:
        args_list = list(args)
        if "--reasoning-effort" not in args_list:
            return True, "", args_list
        idx = args_list.index("--reasoning-effort")
        if idx + 1 >= len(args_list):
            return False, "Configuration Error: Missing value for --reasoning-effort", []
        normalize_gemini_reasoning_effort(args_list[idx + 1])
        return False, "[MODEL ERROR] Gemini reasoning_effort is sdk-only in this MCP.", []

    @staticmethod
    def _rewrite_claude_args(args: Sequence[str]) -> tuple[bool, str, list[str]]:
        args_list = list(args)
        rewritten: list[str] = []
        idx = 0
        while idx < len(args_list):
            token = args_list[idx]
            if token != "--reasoning-effort":
                rewritten.append(token)
                idx += 1
                continue
            if idx + 1 >= len(args_list):
                return False, "Configuration Error: Missing value for --reasoning-effort", []
            effort = normalize_claude_reasoning_effort(args_list[idx + 1])
            if not effort:
                return False, "Configuration Error: Missing value for --reasoning-effort", []
            rewritten.extend(["--effort", effort])
            idx += 2
        return True, "", rewritten

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
        effective_timeout = timeout_seconds
        if effective_timeout is None:
            if service_name == "agy" and self.agy_timeout_seconds is not None:
                effective_timeout = self.agy_timeout_seconds
            else:
                effective_timeout = self.timeout_seconds
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
        effective_timeout = timeout_seconds
        if effective_timeout is None:
            if service_name == "agy" and self.agy_timeout_seconds is not None:
                effective_timeout = self.agy_timeout_seconds
            else:
                effective_timeout = self.timeout_seconds
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
