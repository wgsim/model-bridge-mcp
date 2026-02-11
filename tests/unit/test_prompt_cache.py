import time

from model_bridge.core.prompt_cache import PromptCache


def test_prompt_cache_hit_and_miss():
    cache = PromptCache(ttl_seconds=60, max_entries=8)
    key = cache.build_key({"a": 1})
    assert cache.get(key) is None
    cache.set(key, "value")
    assert cache.get(key) == "value"


def test_prompt_cache_ttl_expiry():
    cache = PromptCache(ttl_seconds=1, max_entries=8)
    key = cache.build_key({"a": 2})
    cache.set(key, "value")
    time.sleep(1.05)
    assert cache.get(key) is None

