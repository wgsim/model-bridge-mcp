import asyncio
import json

import pytest
from model_bridge import main as main_module


class _FakeFailover:
    async def execute_async(self, *args, **kwargs):
        return "hello world from failover"


def test_ask_chatgpt_cli_supports_json_format(monkeypatch):
    monkeypatch.setattr(main_module, "_get_failover", lambda: _FakeFailover())
    out = asyncio.run(
        main_module.ask_chatgpt_cli(
            "hi",
            response_format="json",
            timeout_seconds=10,
            max_output_tokens=4,
            verbosity="brief",
        )
    )
    payload = json.loads(out)
    assert payload["provider"] == "codex"
    assert "content" in payload


def test_ask_gemini_cli_rejects_invalid_verbosity():
    with pytest.raises(ValueError, match="verbosity must be one of"):
        asyncio.run(main_module.ask_gemini_cli("hi", verbosity="invalid"))
