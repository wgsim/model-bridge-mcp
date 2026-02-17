import asyncio
import json
import time

from model_bridge.adapters.sdk_adapter import SDKAdapter


def _models_config() -> dict:
    return {
        "codex_model_catalog": ["gpt-5.2-codex", "gpt-5.3-codex"],
        "gemini_model_catalog": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
        "claude_code_model_catalog": ["haiku", "sonnet", "opus"],
        "ollama_default_model": "gpt-oss:20b",
        "ollama_aliases": {"default": "gpt-oss:20b"},
    }


def test_preflight_codex_requires_credentials():
    adapter = SDKAdapter(models_config=_models_config(), env={})

    ok, msg = adapter.preflight_check("codex")

    assert ok is False
    assert "[SDK AUTH ERROR]" in msg


def test_preflight_codex_accepts_api_key():
    adapter = SDKAdapter(models_config=_models_config(), env={"OPENAI_API_KEY": "sk-test"})

    ok, msg = adapter.preflight_check("codex")

    assert ok is True
    assert msg == "ok"


def test_preflight_codex_accepts_access_token():
    adapter = SDKAdapter(models_config=_models_config(), env={"OPENAI_ACCESS_TOKEN": "oauth-token"})

    ok, msg = adapter.preflight_check("codex")

    assert ok is True
    assert msg == "ok"


def test_preflight_gemini_requires_credentials():
    adapter = SDKAdapter(models_config=_models_config(), env={})

    ok, msg = adapter.preflight_check("gemini")

    assert ok is False
    assert "[SDK AUTH ERROR]" in msg


def test_preflight_gemini_accepts_api_key():
    adapter = SDKAdapter(models_config=_models_config(), env={"GEMINI_API_KEY": "gm-test"})

    ok, msg = adapter.preflight_check("gemini")

    assert ok is True
    assert msg == "ok"


def test_preflight_gemini_accepts_google_api_key():
    adapter = SDKAdapter(models_config=_models_config(), env={"GOOGLE_API_KEY": "google-test"})

    ok, msg = adapter.preflight_check("gemini")

    assert ok is True
    assert msg == "ok"


def test_preflight_claude_requires_credentials():
    adapter = SDKAdapter(models_config=_models_config(), env={})

    ok, msg = adapter.preflight_check("claude_code")

    assert ok is False
    assert "[SDK AUTH ERROR]" in msg


def test_preflight_claude_accepts_api_key():
    adapter = SDKAdapter(models_config=_models_config(), env={"ANTHROPIC_API_KEY": "ak-test"})

    ok, msg = adapter.preflight_check("claude_code")

    assert ok is True
    assert msg == "ok"


def test_preflight_claude_accepts_oauth_access_token():
    adapter = SDKAdapter(models_config=_models_config(), env={"ANTHROPIC_OAUTH_ACCESS_TOKEN": "oauth-token"})

    ok, msg = adapter.preflight_check("claude_code")

    assert ok is True
    assert msg == "ok"


def test_preflight_ollama_uses_probe(monkeypatch):
    adapter = SDKAdapter(models_config=_models_config(), env={})
    monkeypatch.setattr(adapter, "_probe_ollama", lambda: (True, "ok"))

    ok, msg = adapter.preflight_check("ollama")

    assert ok is True
    assert msg == "ok"


def test_run_async_codex_posts_payload_and_parses_output_text(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"OPENAI_API_KEY": "sk-test", "OPENAI_BASE_URL": "https://api.openai.com/v1"},
        system_suffix=" [suffix]",
    )

    def _fake_post(url, token, payload, timeout_seconds):
        captured["url"] = url
        captured["token"] = token
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return True, {"output_text": "ok-from-sdk"}

    monkeypatch.setattr(adapter, "_post_json", _fake_post)

    ok, output = asyncio.run(
        adapter.run_async("codex", ["--model", "gpt-5.3-codex"], "hello", timeout_seconds=45)
    )

    assert ok is True
    assert output == "ok-from-sdk"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["token"] == "sk-test"
    assert captured["payload"]["model"] == "gpt-5.3-codex"
    assert captured["payload"]["input"] == "hello [suffix]"
    assert captured["timeout_seconds"] == 45.0


def test_run_async_codex_extracts_nested_output_blocks(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"OPENAI_API_KEY": "sk-test"},
    )

    def _fake_post(url, token, payload, timeout_seconds):  # pylint: disable=unused-argument
        return True, {
            "output": [
                {"content": [{"type": "output_text", "text": "line-1"}]},
                {"content": [{"type": "output_text", "text": "line-2"}]},
            ]
        }

    monkeypatch.setattr(adapter, "_post_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("codex", [], "hello"))

    assert ok is True
    assert output == "line-1\nline-2"


def test_run_async_codex_returns_request_error_from_transport(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"OPENAI_API_KEY": "sk-test"},
    )

    monkeypatch.setattr(
        adapter,
        "_post_json",
        lambda *args, **kwargs: (False, "[SDK REQUEST ERROR] provider=codex status=401"),
    )

    ok, output = asyncio.run(adapter.run_async("codex", [], "hello"))

    assert ok is False
    assert output == "[SDK REQUEST ERROR] provider=codex status=401"


def test_run_async_gemini_posts_payload_and_parses_candidates(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"GEMINI_API_KEY": "gm-test"},
        system_suffix=" [suffix]",
    )

    def _fake_post(model, api_key, payload, timeout_seconds):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return True, {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "gemini line 1"},
                            {"text": "gemini line 2"},
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(adapter, "_post_gemini_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("gemini", ["--model", "gemini-2.5-pro"], "hello", timeout_seconds=33))

    assert ok is True
    assert output == "gemini line 1\ngemini line 2"
    assert captured["model"] == "gemini-2.5-pro"
    assert captured["api_key"] == "gm-test"
    assert captured["payload"]["contents"][0]["parts"][0]["text"] == "hello [suffix]"
    assert captured["timeout_seconds"] == 33.0


def test_run_async_gemini_returns_auth_error_without_key():
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={},
    )

    ok, output = asyncio.run(adapter.run_async("gemini", [], "hello"))

    assert ok is False
    assert "[SDK AUTH ERROR]" in output


def test_run_async_gemini_accepts_oauth_access_token(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"GEMINI_OAUTH_ACCESS_TOKEN": "oauth-token"},
    )

    def _fake_post(model, api_key, payload, timeout_seconds):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return True, {"candidates": [{"content": {"parts": [{"text": "oauth-ok"}]}}]}

    monkeypatch.setattr(adapter, "_post_gemini_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("gemini", ["--model", "gemini-2.5-flash"], "hello"))

    assert ok is True
    assert output == "oauth-ok"
    assert captured["api_key"] == ""


def test_run_async_gemini_returns_request_error_from_transport(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"GEMINI_API_KEY": "gm-test"},
    )

    monkeypatch.setattr(
        adapter,
        "_post_gemini_json",
        lambda *args, **kwargs: (False, "[SDK REQUEST ERROR] provider=gemini status=403"),
    )

    ok, output = asyncio.run(adapter.run_async("gemini", [], "hello"))

    assert ok is False
    assert output == "[SDK REQUEST ERROR] provider=gemini status=403"


def test_run_async_claude_posts_payload_and_parses_content(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={
            "ANTHROPIC_API_KEY": "ak-test",
            "ANTHROPIC_MODEL_SONNET": "claude-sonnet-4",
            "ANTHROPIC_MAX_TOKENS": "2048",
        },
        system_suffix=" [suffix]",
    )

    def _fake_post(payload, api_key, access_token, timeout_seconds):
        captured["payload"] = payload
        captured["api_key"] = api_key
        captured["access_token"] = access_token
        captured["timeout_seconds"] = timeout_seconds
        return True, {"content": [{"type": "text", "text": "claude-ok"}]}

    monkeypatch.setattr(adapter, "_post_claude_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("claude_code", ["--model", "sonnet"], "hello", timeout_seconds=27))

    assert ok is True
    assert output == "claude-ok"
    assert captured["payload"]["model"] == "claude-sonnet-4"
    assert captured["payload"]["max_tokens"] == 2048
    assert captured["payload"]["messages"][0]["content"] == "hello [suffix]"
    assert captured["api_key"] == "ak-test"
    assert captured["access_token"] == ""
    assert captured["timeout_seconds"] == 27.0


def test_run_async_claude_returns_auth_error_without_key():
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={},
    )

    ok, output = asyncio.run(adapter.run_async("claude_code", [], "hello"))

    assert ok is False
    assert "[SDK AUTH ERROR]" in output


def test_run_async_claude_accepts_oauth_access_token(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"ANTHROPIC_OAUTH_ACCESS_TOKEN": "oauth-token"},
    )

    def _fake_post(payload, api_key, access_token, timeout_seconds):  # pylint: disable=unused-argument
        captured["api_key"] = api_key
        captured["access_token"] = access_token
        return True, {"content": [{"type": "text", "text": "oauth-claude-ok"}]}

    monkeypatch.setattr(adapter, "_post_claude_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("claude_code", ["--model", "sonnet"], "hello"))

    assert ok is True
    assert output == "oauth-claude-ok"
    assert captured["api_key"] == ""
    assert captured["access_token"] == "oauth-token"


def test_run_async_claude_returns_request_error_from_transport(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"ANTHROPIC_API_KEY": "ak-test"},
    )

    monkeypatch.setattr(
        adapter,
        "_post_claude_json",
        lambda *args, **kwargs: (False, "[SDK REQUEST ERROR] provider=claude_code status=400"),
    )

    ok, output = asyncio.run(adapter.run_async("claude_code", [], "hello"))

    assert ok is False
    assert output == "[SDK REQUEST ERROR] provider=claude_code status=400"


def test_run_async_ollama_posts_payload_and_parses_response(monkeypatch):
    captured = {}
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={},
        system_suffix=" [suffix]",
        apply_system_suffix_for={"ollama": False},
    )

    def _fake_post(model, prompt, timeout_seconds):
        captured["model"] = model
        captured["prompt"] = prompt
        captured["timeout_seconds"] = timeout_seconds
        return True, {"response": "ollama-ok"}

    monkeypatch.setattr(adapter, "_post_ollama_json", _fake_post)

    ok, output = asyncio.run(adapter.run_async("ollama", ["gpt-oss:20b"], "hello", timeout_seconds=21))

    assert ok is True
    assert output == "ollama-ok"
    assert captured["model"] == "gpt-oss:20b"
    assert captured["prompt"] == "hello"
    assert captured["timeout_seconds"] == 21.0


def test_run_async_ollama_respects_system_suffix_policy(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={},
        system_suffix=" [suffix]",
        apply_system_suffix_for={"ollama": True},
    )

    captured = {}

    def _fake_post(model, prompt, timeout_seconds):  # pylint: disable=unused-argument
        captured["prompt"] = prompt
        return True, {"response": "ok"}

    monkeypatch.setattr(adapter, "_post_ollama_json", _fake_post)
    ok, output = asyncio.run(adapter.run_async("ollama", ["gpt-oss:20b"], "hello"))

    assert ok is True
    assert output == "ok"
    assert captured["prompt"] == "hello [suffix]"


def test_run_async_ollama_returns_request_error_from_transport(monkeypatch):
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={},
    )

    monkeypatch.setattr(
        adapter,
        "_post_ollama_json",
        lambda *args, **kwargs: (False, "[SDK REQUEST ERROR] provider=ollama status=500"),
    )

    ok, output = asyncio.run(adapter.run_async("ollama", ["gpt-oss:20b"], "hello"))

    assert ok is False
    assert output == "[SDK REQUEST ERROR] provider=ollama status=500"


def test_resolve_oauth_access_token_refreshes_expired_file(tmp_path, monkeypatch):
    token_file = tmp_path / "openai_oauth.json"
    token_file.write_text(
        json.dumps(
            {
                "access_token": "expired-token",
                "expires_at": time.time() - 300,
                "refresh_token": "refresh-1",
                "token_url": "https://auth.example/token",
            }
        ),
        encoding="utf-8",
    )
    adapter = SDKAdapter(
        models_config=_models_config(),
        env={"OPENAI_OAUTH_TOKEN_FILE": str(token_file)},
    )

    monkeypatch.setattr(
        adapter,
        "_oauth_refresh_token",
        lambda **kwargs: {
            "access_token": "new-token",
            "refresh_token": "refresh-2",
            "expires_at": time.time() + 3600,
        },
    )

    token = adapter._resolve_oauth_access_token("OPENAI")

    assert token == "new-token"
    persisted = json.loads(token_file.read_text(encoding="utf-8"))
    assert persisted["access_token"] == "new-token"
    assert persisted["refresh_token"] == "refresh-2"
