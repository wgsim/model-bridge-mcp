"""Prompt security sanitizer."""

from __future__ import annotations

import logging
import re
from typing import Tuple


class SecuritySanitizer:
    """Block destructive patterns and sensitive path access."""

    BLOCK_PATTERNS = [
        r"rm\s+(-r[a-zA-Z]*f|-f[a-zA-Z]*r)\s+",
        r"mkfs\.",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&",
        r"dd\s+if=",
        r"chmod\s+777",
    ]

    SENSITIVE_PATHS = [
        r"/etc/",
        r"/var/",
        r"/boot/",
        r"/proc/",
        r"/root/",
    ]

    @staticmethod
    def inspect(prompt: str, mode: str = "execution") -> Tuple[bool, str]:
        del mode  # Kept for backward-compatible signature.
        for pattern in SecuritySanitizer.BLOCK_PATTERNS:
            if re.search(pattern, prompt):
                return (
                    False,
                    f"[SECURITY BLOCK] Destructive command pattern detected ({pattern}). Execution blocked.",
                )

        for path in SecuritySanitizer.SENSITIVE_PATHS:
            if path in prompt:
                logging.getLogger("model_bridge.security").warning(
                    "Sensitive path access blocked: %s", path
                )
                return (
                    False,
                    f"[SECURITY BLOCK] Access to critical system path '{path}' is strictly FORBIDDEN.",
                )

        return True, ""

