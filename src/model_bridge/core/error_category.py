"""Error categorization for intelligent retry and failover decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from re import search


class ErrorCategory(Enum):
    """Categories of errors that determine retry behavior."""

    # Retryable errors - transient issues that may resolve on retry
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"

    # Non-retryable errors - persistent issues that won't resolve on retry
    AUTH_FAILED = "auth_failed"
    INVALID_REQUEST = "invalid_request"
    SECURITY_BLOCKED = "security_blocked"
    EXECUTION_ERROR = "execution_error"
    MODEL_NOT_FOUND = "model_not_found"
    CONFIGURATION_ERROR = "configuration_error"
    TOKEN_LIMIT_EXCEEDED = "token_limit_exceeded"


# Patterns for detecting error categories from error messages
ERROR_PATTERNS = {
    ErrorCategory.RATE_LIMITED: [
        r"rate.?limit",
        r"too.?many.?requests",
        r"429",
        r"quota.?exceeded",
        r"throttl",
    ],
    ErrorCategory.AUTH_FAILED: [
        r"auth",
        r"unauth",
        r"401",
        r"403",
        r"invalid.?api.?key",
        r"missing.?credentials?",
    ],
    ErrorCategory.TIMEOUT: [
        r"timeout",
        r"timed.?out",
        r"deadline.?exceeded",
        r"request.?timeout",
    ],
    ErrorCategory.PROVIDER_UNAVAILABLE: [
        r"service.?unavailable",
        r"503",
        r"connection.?(refused|reset|closed|timeout)",
        r"dns.?fail",
        r"host.?unreachable",
    ],
    ErrorCategory.TOKEN_LIMIT_EXCEEDED: [
        r"max.?tokens?",
        r"token.?limit",
        r"context.?(length|window|limit)",
        r"output.?truncat",
        r"maximum.?context",
    ],
    ErrorCategory.MODEL_NOT_FOUND: [
        r"model\s+[\w-]+\s+not\s+(found|exist)",
        r"unknown\s+model",
        r"invalid\s+model",
        r"no\s+such\s+model",
    ],
    ErrorCategory.INVALID_REQUEST: [
        r"invalid.?request",
        r"malformed",
        r"bad.?request",
        r"400",
    ],
    ErrorCategory.SECURITY_BLOCKED: [
        r"\[SECURITY\s+BLOCK\]",
        r"security.?block",
        r"forbidden",
        r"dangerous",
    ],
}


@dataclass(frozen=True)
class ErrorInfo:
    """Structured error information for failover decisions."""

    category: ErrorCategory
    raw_message: str
    provider: str
    is_retryable: bool
    suggested_action: str

    @classmethod
    def from_message(cls, message: str, provider: str) -> "ErrorInfo":
        """
        Categorize an error message into ErrorInfo.

        Args:
            message: The error message to categorize
            provider: The provider that generated the error

        Returns:
            ErrorInfo with category, retryability, and suggested action
        """
        low_msg = message.lower()

        for category, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                if search(pattern, low_msg):
                    is_retryable = category in {
                        ErrorCategory.RATE_LIMITED,
                        ErrorCategory.TIMEOUT,
                        ErrorCategory.PROVIDER_UNAVAILABLE,
                    }

                    suggested_action = cls._get_suggested_action(category)
                    return ErrorInfo(
                        category=category,
                        raw_message=message,
                        provider=provider,
                        is_retryable=is_retryable,
                        suggested_action=suggested_action,
                    )

        # Default to execution error if no pattern matches
        return ErrorInfo(
            category=ErrorCategory.EXECUTION_ERROR,
            raw_message=message,
            provider=provider,
            is_retryable=False,
            suggested_action="Check provider configuration and logs",
        )

    @staticmethod
    def _get_suggested_action(category: ErrorCategory) -> str:
        """Get suggested action for an error category."""
        actions = {
            ErrorCategory.RATE_LIMITED: "Wait before retrying (exponential backoff)",
            ErrorCategory.AUTH_FAILED: "Check API credentials and configuration",
            ErrorCategory.TIMEOUT: "Retry with longer timeout or check connectivity",
            ErrorCategory.PROVIDER_UNAVAILABLE: "Retry immediately or check provider status",
            ErrorCategory.INVALID_REQUEST: "Fix request format and retry",
            ErrorCategory.SECURITY_BLOCKED: "Review prompt content and security settings",
            ErrorCategory.EXECUTION_ERROR: "Check provider logs and configuration",
            ErrorCategory.MODEL_NOT_FOUND: "Verify model name and availability",
            ErrorCategory.CONFIGURATION_ERROR: "Fix provider configuration",
            ErrorCategory.TOKEN_LIMIT_EXCEEDED: "Reduce prompt length or increase max_output_tokens",
        }
        return actions.get(category, "Contact support")


def is_retryable(category: ErrorCategory) -> bool:
    """Check if an error category is retryable."""
    return category in {
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.TIMEOUT,
        ErrorCategory.PROVIDER_UNAVAILABLE,
    }
