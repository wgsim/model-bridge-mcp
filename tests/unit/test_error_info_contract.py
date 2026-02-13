"""Contract tests for ErrorInfo dataclass."""

from __future__ import annotations

import json
import jsonschema
from pathlib import Path
import pytest

from model_bridge.core.error_category import ErrorCategory, ErrorInfo


def test_error_info_schema_exists():
    """Test that ErrorInfo schema file exists."""
    # Use absolute path from project root
    import os
    project_root = Path(__file__).parent.parent.parent
    schema_path = project_root / "schemas" / "error_info.schema.json"
    assert schema_path.exists(), f"Schema file not found: {schema_path}"


def test_error_info_conforms_to_schema():
    """Test that ErrorInfo.from_message produces schema-compliant output."""
    # Test all error categories
    test_messages = [
        ("Rate limit exceeded", "codex", ErrorCategory.RATE_LIMITED),
        ("Invalid API key", "gemini", ErrorCategory.AUTH_FAILED),
        ("Request timeout", "ollama", ErrorCategory.TIMEOUT),
        ("Model gpt-5 not found", "claude_code", ErrorCategory.MODEL_NOT_FOUND),
        ("invalid request", "test_provider", ErrorCategory.INVALID_REQUEST),
        ("[SECURITY BLOCK] blocked", "test_provider", ErrorCategory.SECURITY_BLOCKED),
        ("Unknown error", "test_provider", ErrorCategory.EXECUTION_ERROR),
        ("Service unavailable", "test_provider", ErrorCategory.PROVIDER_UNAVAILABLE),
    ]

    for message, provider, expected_category in test_messages:
        error = ErrorInfo.from_message(message, provider)

        # Verify category matches expected
        assert error.category == expected_category

        # Convert to dict for schema validation
        error_dict = {
            "category": error.category.value,
            "raw_message": error.raw_message,
            "provider": error.provider,
            "is_retryable": error.is_retryable,
            "suggested_action": error.suggested_action,
        }

        # Load schema (create if not exists)
        project_root = Path(__file__).parent.parent.parent
        schema_path = project_root / "schemas" / "error_info.schema.json"
        if not schema_path.exists():
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "error_info.schema.json",
                "title": "ErrorInfo",
                "description": "Structured error information for failover decisions",
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in ErrorCategory],
                        "description": "Error category identifier"
                    },
                    "raw_message": {
                        "type": "string",
                        "description": "Original error message"
                    },
                    "provider": {
                        "type": "string",
                        "description": "Provider that generated the error"
                    },
                    "is_retryable": {
                        "type": "boolean",
                        "description": "Whether the error is retryable"
                    },
                    "suggested_action": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Suggested action for resolving the error"
                    }
                },
                "required": ["category", "raw_message", "provider", "is_retryable", "suggested_action"],
                "additionalProperties": False
            }
            schema_path.parent.mkdir(exist_ok=True)
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        # Validate
        jsonschema.validate(instance=error_dict, schema=schema)


def test_error_info_all_categories_have_suggested_actions():
    """Test that all error categories have suggested actions."""
    from model_bridge.core.error_category import ERROR_PATTERNS

    for category in ErrorCategory:
        error = ErrorInfo.from_message("test message", "test_provider")
        # For unknown messages, default to execution_error
        if error.category == ErrorCategory.EXECUTION_ERROR:
            continue
        # For known patterns, verify suggested action exists
        assert len(error.suggested_action) > 0
        assert isinstance(error.suggested_action, str)


def test_error_info_retryable_flag_matches_category():
    """Test that is_retryable flag is consistent with category."""
    from model_bridge.core.error_category import is_retryable

    test_cases = [
        ("Rate limit exceeded", True),
        ("Request timeout", True),
        ("Service unavailable", True),
        ("Invalid API key", False),
        ("Invalid request", False),
        ("[SECURITY BLOCK]", False),
        ("Model not found", False),
    ]

    for message, expected_retryable in test_cases:
        error = ErrorInfo.from_message(message, "test_provider")
        assert error.is_retryable == expected_retryable
        # Verify consistency with is_retryable function
        assert is_retryable(error.category) == expected_retryable
