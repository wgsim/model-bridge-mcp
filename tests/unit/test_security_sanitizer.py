from model_bridge.security.sanitizer import SecuritySanitizer


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

