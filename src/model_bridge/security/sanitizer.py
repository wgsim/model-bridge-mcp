"""Prompt security sanitizer."""

from __future__ import annotations

import logging
import re


class SecuritySanitizer:
    """Block destructive patterns and sensitive path access."""

    DEFAULT_BLOCK_PATTERNS = [
        r"rm\s+(-r[a-zA-Z]*f|-f[a-zA-Z]*r)\s+",
        r"mkfs\.",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
        r"dd\s+if=",
        r"chmod\s+777",
    ]

    DEFAULT_SENSITIVE_PATHS = [
        r"/etc/",
        r"/var/",
        r"/boot/",
        r"/proc/",
        r"/root/",
    ]

    def __init__(
        self,
        block_patterns: list[str] | None = None,
        sensitive_paths: list[str] | None = None,
    ) -> None:
        self.block_patterns = list(
            block_patterns if block_patterns is not None else self.DEFAULT_BLOCK_PATTERNS
        )
        self.sensitive_paths = list(
            sensitive_paths if sensitive_paths is not None else self.DEFAULT_SENSITIVE_PATHS
        )

    def inspect(self, prompt: str, mode: str = "execution") -> tuple[bool, str]:
        normalized_mode = (mode or "execution").strip().lower()
        if normalized_mode not in {"execution", "analysis"}:
            logging.getLogger("model_bridge.security").warning(
                "Unknown inspect mode '%s'; using execution safeguards.", mode
            )
        for pattern in self.block_patterns:
            if re.search(pattern, prompt):
                return (
                    False,
                    f"[SECURITY BLOCK] Destructive command pattern detected ({pattern}). Execution blocked.",
                )

        for path in self.sensitive_paths:
            if path in prompt:
                logging.getLogger("model_bridge.security").warning(
                    "Sensitive path access blocked in %s mode: %s", normalized_mode, path
                )
                return (
                    False,
                    f"[SECURITY BLOCK] Access to critical system path '{path}' is strictly FORBIDDEN.",
                )

        return True, ""
