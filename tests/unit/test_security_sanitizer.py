from model_bridge.security.sanitizer import SecuritySanitizer


def setup_function():
    SecuritySanitizer.configure(
        block_patterns=SecuritySanitizer.DEFAULT_BLOCK_PATTERNS,
        sensitive_paths=SecuritySanitizer.DEFAULT_SENSITIVE_PATHS,
    )


def test_inspect_blocks_destructive_pattern():
    ok, message = SecuritySanitizer.inspect("please run rm -rf /tmp/a")
    assert ok is False
    assert "Destructive command pattern detected" in message


def test_inspect_blocks_sensitive_path():
    ok, message = SecuritySanitizer.inspect("analyze /etc/passwd", mode="analysis")
    assert ok is False
    assert "critical system path '/etc/'" in message


def test_inspect_allows_safe_prompt():
    ok, message = SecuritySanitizer.inspect("write a python function")
    assert ok is True
    assert message == ""


def test_inspect_uses_configured_block_patterns():
    SecuritySanitizer.configure(block_patterns=[r"forbidden_token"], sensitive_paths=["/etc/"])

    ok, message = SecuritySanitizer.inspect("this has forbidden_token")

    assert ok is False
    assert "forbidden_token" in message


def test_inspect_uses_configured_sensitive_paths():
    SecuritySanitizer.configure(
        block_patterns=SecuritySanitizer.DEFAULT_BLOCK_PATTERNS,
        sensitive_paths=["/custom/protected/"],
    )

    ok, message = SecuritySanitizer.inspect("read /custom/protected/data")

    assert ok is False
    assert "critical system path '/custom/protected/'" in message
