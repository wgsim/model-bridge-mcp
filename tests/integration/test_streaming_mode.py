import asyncio

from model_bridge import main as main_module


class _FakeFailover:
    async def execute_async(self, *args, **kwargs):
        return "line1 line2 line3 line4 line5"


def test_streaming_mode_returns_fallback_chunks(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    out = asyncio.run(main_module.ask_chatgpt_cli("hello", stream=True))
    assert out.startswith("[STREAM FALLBACK]")
    assert out.endswith("[STREAM END]")

