"""Unit tests for error categorization and retry policy."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from model_bridge.core.error_category import (
    ErrorCategory,
    ErrorInfo,
)


class TestErrorCategory:
    """Test ErrorCategory enum values."""

    def test_retryable_categories(self):
        """Test that retryable error categories are correctly identified."""
        retryable_messages = [
            ("rate limit exceeded", ErrorCategory.RATE_LIMITED),
            ("request timeout", ErrorCategory.TIMEOUT),
            ("service unavailable", ErrorCategory.PROVIDER_UNAVAILABLE),
        ]
        for message, expected_category in retryable_messages:
            error = ErrorInfo.from_message(message, "test_provider")
            assert error.category == expected_category
            assert error.is_retryable is True

    def test_non_retryable_categories(self):
        """Test that non-retryable error categories are correctly identified."""
        non_retryable_messages = [
            ("invalid api key", ErrorCategory.AUTH_FAILED),
            ("invalid request", ErrorCategory.INVALID_REQUEST),
            ("[SECURITY BLOCK] blocked", ErrorCategory.SECURITY_BLOCKED),
            ("some unknown error xyz", ErrorCategory.EXECUTION_ERROR),
            ("model gpt-5 not found", ErrorCategory.MODEL_NOT_FOUND),
            ("max tokens exceeded", ErrorCategory.TOKEN_LIMIT_EXCEEDED),
        ]
        for message, expected_category in non_retryable_messages:
            error = ErrorInfo.from_message(message, "test_provider")
            assert error.category == expected_category
            assert error.is_retryable is False


class TestErrorInfo:
    """Test ErrorInfo creation and categorization."""

    def test_categorize_rate_limit_error(self):
        """Test categorization of rate limit errors."""
        error = ErrorInfo.from_message("Rate limit exceeded", "test_provider")
        assert error.category == ErrorCategory.RATE_LIMITED
        assert error.is_retryable is True
        assert error.provider == "test_provider"
        assert "wait" in error.suggested_action.lower()

    def test_categorize_auth_error(self):
        """Test categorization of authentication errors."""
        error = ErrorInfo.from_message("Invalid API key", "test_provider")
        assert error.category == ErrorCategory.AUTH_FAILED
        assert error.is_retryable is False
        assert "credentials" in error.suggested_action.lower()

    def test_categorize_timeout_error(self):
        """Test categorization of timeout errors."""
        error = ErrorInfo.from_message("Request timeout", "test_provider")
        assert error.category == ErrorCategory.TIMEOUT
        assert error.is_retryable is True

    def test_categorize_model_not_found_error(self):
        """Test categorization of model not found errors."""
        error = ErrorInfo.from_message("Model gpt-5 not found", "test_provider")
        assert error.category == ErrorCategory.MODEL_NOT_FOUND
        assert error.is_retryable is False

    def test_categorize_security_blocked_error(self):
        """Test categorization of security blocked errors."""
        error = ErrorInfo.from_message("[SECURITY BLOCK] Destructive command", "test_provider")
        assert error.category == ErrorCategory.SECURITY_BLOCKED
        assert error.is_retryable is False

    def test_categorize_unknown_error(self):
        """Test that unknown errors default to execution_error."""
        error = ErrorInfo.from_message("Unknown error occurred", "test_provider")
        assert error.category == ErrorCategory.EXECUTION_ERROR
        assert error.is_retryable is False

    def test_categorize_429_error(self):
        """Test that HTTP 429 is categorized as rate limit."""
        error = ErrorInfo.from_message("HTTP 429", "test_provider")
        assert error.category == ErrorCategory.RATE_LIMITED

    def test_categorize_401_error(self):
        """Test that HTTP 401 is categorized as auth error."""
        error = ErrorInfo.from_message("HTTP 401 Unauthorized", "test_provider")
        assert error.category == ErrorCategory.AUTH_FAILED

    def test_categorize_connection_refused(self):
        """Test that connection refused is categorized as provider unavailable."""
        error = ErrorInfo.from_message("Connection refused", "test_provider")
        assert error.category == ErrorCategory.PROVIDER_UNAVAILABLE
        assert error.is_retryable is True

    def test_categorize_case_insensitive(self):
        """Test that categorization is case-insensitive."""
        error = ErrorInfo.from_message("RATE LIMIT Exceeded", "test_provider")
        assert error.category == ErrorCategory.RATE_LIMITED

    def test_categorize_token_limit_max_tokens(self):
        """Test that max tokens error is categorized as token limit."""
        error = ErrorInfo.from_message("max tokens exceeded", "test_provider")
        assert error.category == ErrorCategory.TOKEN_LIMIT_EXCEEDED
        assert error.is_retryable is False

    def test_categorize_token_limit_context_length(self):
        """Test that context length error is categorized as token limit."""
        error = ErrorInfo.from_message("context length exceeded", "test_provider")
        assert error.category == ErrorCategory.TOKEN_LIMIT_EXCEEDED

    def test_categorize_token_limit_output_truncated(self):
        """Test that output truncated error is categorized as token limit."""
        error = ErrorInfo.from_message("output truncated due to length", "test_provider")
        assert error.category == ErrorCategory.TOKEN_LIMIT_EXCEEDED

    def test_categorize_token_limit_suggested_action(self):
        """Test that token limit errors suggest reducing prompt length."""
        error = ErrorInfo.from_message("token limit reached", "test_provider")
        assert "max_output_tokens" in error.suggested_action.lower() or "reduce" in error.suggested_action.lower()


class TestErrorInfoPropertyBased:
    """Property-based tests for ErrorInfo using Hypothesis."""

    @given(
        message=st.text(min_size=1),
        provider=st.text(min_size=1, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"),
    )
    def test_from_message_always_returns_valid_error_info(self, message, provider):
        """Test that from_message always returns a valid ErrorInfo."""
        error = ErrorInfo.from_message(message, provider)

        assert error.category in ErrorCategory
        assert error.raw_message == message
        assert error.provider == provider
        assert isinstance(error.is_retryable, bool)
        assert isinstance(error.suggested_action, str)
        assert len(error.suggested_action) > 0

    @given(
        message=st.sampled_from([
            "rate limit exceeded",
            "too many requests",
            "429",
            "quota exceeded",
            "throttled",
            "request timeout",
            "timed out",
            "deadline exceeded",
            "service unavailable",
            "503",
            "connection refused",
            "connection reset",
        ])
    )
    def test_retryable_errors_are_always_marked_retryable(self, message):
        """Test that known retryable errors are marked as retryable."""
        error = ErrorInfo.from_message(message, "test_provider")
        assert error.is_retryable is True

    @given(
        message=st.sampled_from([
            "invalid api key",
            "unauthorized",
            "401",
            "invalid request",
            "malformed",
            "[SECURITY BLOCK]",
            "model xyz not found",
            "max tokens exceeded",
            "context length exceeded",
            "output truncated",
        ])
    )
    def test_non_retryable_errors_are_always_marked_non_retryable(self, message):
        """Test that known non-retryable errors are marked as non-retryable."""
        error = ErrorInfo.from_message(message, "test_provider")
        assert error.is_retryable is False

    @given(st.text())
    def test_suggested_action_is_never_empty(self, message):
        """Test that suggested_action is always provided."""
        error = ErrorInfo.from_message(message, "test_provider")
        assert len(error.suggested_action) > 0
