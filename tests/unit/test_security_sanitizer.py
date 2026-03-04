from model_bridge.security.sanitizer import SecuritySanitizer


def test_inspect_blocks_destructive_pattern():
    sanitizer = SecuritySanitizer()
    ok, message = sanitizer.inspect("please run rm -rf /tmp/a")
    assert ok is False
    assert "Destructive command pattern detected" in message


def test_inspect_blocks_sensitive_path():
    sanitizer = SecuritySanitizer()
    ok, message = sanitizer.inspect("analyze /etc/passwd", mode="analysis")
    assert ok is False
    assert "critical system path '/etc/'" in message


def test_inspect_allows_safe_prompt():
    sanitizer = SecuritySanitizer()
    ok, message = sanitizer.inspect("write a python function")
    assert ok is True
    assert message == ""


def test_inspect_uses_configured_block_patterns():
    sanitizer = SecuritySanitizer(block_patterns=[r"forbidden_token"], sensitive_paths=["/etc/"])

    ok, message = sanitizer.inspect("this has forbidden_token")

    assert ok is False
    assert "forbidden_token" in message


def test_inspect_uses_configured_sensitive_paths():
    sanitizer = SecuritySanitizer(sensitive_paths=["/custom/protected/"])

    ok, message = sanitizer.inspect("read /custom/protected/data")

    assert ok is False
    assert "critical system path '/custom/protected/'" in message


def test_inspect_accepts_unknown_mode_without_crash():
    sanitizer = SecuritySanitizer()
    ok, message = sanitizer.inspect("safe prompt", mode="custom_mode")
    assert ok is True
    assert message == ""
