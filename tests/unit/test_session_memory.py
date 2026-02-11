import time

from model_bridge.core.session_memory import SessionMemory


def test_session_memory_append_and_limit():
    mem = SessionMemory(ttl_seconds=60, max_turns=2)
    mem.append_turn("s1", "first")
    mem.append_turn("s1", "second")
    mem.append_turn("s1", "third")
    assert mem.get_context("s1") == ["second", "third"]


def test_session_memory_expiry():
    mem = SessionMemory(ttl_seconds=1, max_turns=3)
    mem.append_turn("s2", "first")
    time.sleep(1.05)
    assert mem.get_context("s2") == []

