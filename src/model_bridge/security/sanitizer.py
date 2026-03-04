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

    BLOCK_PATTERNS = list(DEFAULT_BLOCK_PATTERNS)
    SENSITIVE_PATHS = list(DEFAULT_SENSITIVE_PATHS)

    @classmethod
    def configure(cls, block_patterns: list[str], sensitive_paths: list[str]) -> None:
        cls.BLOCK_PATTERNS = list(block_patterns)
        cls.SENSITIVE_PATHS = list(sensitive_paths)

    @classmethod
    def inspect(cls, prompt: str, mode: str = "execution") -> tuple[bool, str]:
        normalized_mode = (mode or "execution").strip().lower()
        if normalized_mode not in {"execution", "analysis"}:
            logging.getLogger("model_bridge.security").warning(
                "Unknown inspect mode '%s'; using execution safeguards.", mode
            )
        for pattern in cls.BLOCK_PATTERNS:
            if re.search(pattern, prompt):
                return (
                    False,
                    f"[SECURITY BLOCK] Destructive command pattern detected ({pattern}). Execution blocked.",
                )

        for path in cls.SENSITIVE_PATHS:
            if path in prompt:
                logging.getLogger("model_bridge.security").warning(
                    "Sensitive path access blocked in %s mode: %s", normalized_mode, path
                )
                return (
                    False,
                    f"[SECURITY BLOCK] Access to critical system path '{path}' is strictly FORBIDDEN.",
                )

        return True, ""
