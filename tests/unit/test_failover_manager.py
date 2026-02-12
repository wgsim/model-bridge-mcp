import asyncio

from model_bridge.core.failover_manager import FailoverManager


class _FakeAdapter:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def run(self, service_name, args, input_text):
        self.calls.append((service_name, list(args), input_text))
        return self.responses[(service_name, tuple(args))]

    async def run_async(self, service_name, args, input_text):
        return self.run(service_name, args, input_text)


class _AllowAllSanitizer:
    @staticmethod
    def inspect(prompt, mode="execution"):
        return True, ""


class _BlockAllSanitizer:
    @staticmethod
    def inspect(prompt, mode="execution"):
        return False, "[SECURITY BLOCK] blocked"


def _base_config():
    return {
        "routing": {
            "default_chains": {
                "ask_chatgpt_cli": ["codex", "gemini", "ollama"],
                "ask_gemini_cli": ["gemini", "codex", "ollama"],
                "ask_ollama_cloud_fallback": ["codex", "gemini"],
            }
        },
        "models": {
            "ollama_default_model": "llama3.2",
            "ollama_final_backup_model": "qwen3-coder:30b-a3b-q8_0",
        },
    }


def test_execute_returns_primary_success():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (True, "primary-ok"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution")

    assert "primary-ok" in out
    assert "[1] Primary (codex): Trying..." in out
    assert "    [SUCCESS]" in out
    assert len(adapter.calls) == 1


def test_execute_falls_back_to_secondary():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (False, "primary-fail"),
            ("gemini", ()): (True, "secondary-ok"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution")

    assert "secondary-ok" in out
    assert "[2] Secondary (gemini): Trying..." in out
    assert adapter.calls[1][2].startswith("[Context: codex failed] ")


def test_execute_uses_tertiary_ollama_with_backup_model():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (False, "primary-fail"),
            ("gemini", ()): (False, "secondary-fail"),
            ("ollama", ("qwen3-coder:30b-a3b-q8_0",)): (True, "tertiary-ok"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution")

    assert "tertiary-ok" in out
    assert "[3] Ollama: Trying..." in out
    assert adapter.calls[-1][1] == ["qwen3-coder:30b-a3b-q8_0"]


def test_execute_returns_error_when_forced_primary_fails():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (False, "primary-fail"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution", force_primary=True)

    assert "[Task Execution Failed]" in out
    assert "Forced Primary (codex) failed." in out
    assert len(adapter.calls) == 1


def test_execute_returns_security_block_without_adapter_call():
    adapter = _FakeAdapter({})
    manager = FailoverManager(adapter=adapter, sanitizer=_BlockAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution")

    assert out == "[SECURITY BLOCK] blocked"
    assert adapter.calls == []


def test_execute_returns_all_failed_error():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (False, "primary-fail"),
            ("gemini", ()): (False, "secondary-fail"),
            ("ollama", ("qwen3-coder:30b-a3b-q8_0",)): (False, "tertiary-fail"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution")

    assert "[Task Execution Failed]" in out
    assert "All services failed. Last Error: tertiary-fail" in out


def test_execute_skips_tertiary_when_disabled():
    adapter = _FakeAdapter(
        {
            ("codex", ()): (False, "primary-fail"),
            ("gemini", ()): (False, "secondary-fail"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = manager.execute("codex", "gemini", "hello", mode="execution", allow_tertiary=False)

    assert "[Task Execution Failed]" in out
    assert "All services failed. Last Error: secondary-fail" in out
    assert len(adapter.calls) == 2


def test_execute_async_uses_async_adapter_path():
    class _AsyncOnlyAdapter:
        def __init__(self):
            self.calls = []

        async def run_async(self, service_name, args, input_text):
            self.calls.append((service_name, list(args), input_text))
            return True, "async-primary-ok"

        def run(self, service_name, args, input_text):  # pragma: no cover
            raise AssertionError("sync run should not be used")

    adapter = _AsyncOnlyAdapter()
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = asyncio.run(manager.execute_async("codex", "gemini", "hello", mode="execution"))

    assert "async-primary-ok" in out
    assert len(adapter.calls) == 1


def test_execute_async_passes_provider_specific_args():
    adapter = _FakeAdapter(
        {
            ("codex", ("--model", "gpt-5")): (False, "primary-fail"),
            ("gemini", ("--model", "gemini-2.5-pro")): (True, "secondary-ok"),
        }
    )
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = asyncio.run(
        manager.execute_async(
            "codex",
            "gemini",
            "hello",
            mode="execution",
            allow_tertiary=False,
            provider_args={
                "codex": ["--model", "gpt-5"],
                "gemini": ["--model", "gemini-2.5-pro"],
            },
        )
    )

    assert "secondary-ok" in out
    assert adapter.calls[0] == ("codex", ["--model", "gpt-5"], "hello")
    assert adapter.calls[1][0] == "gemini"
    assert adapter.calls[1][1] == ["--model", "gemini-2.5-pro"]


def test_execute_async_raw_mode_disables_noise_stripping():
    class _CaptureStripNoiseAdapter:
        def __init__(self):
            self.flags = []

        async def run_async(
            self,
            service_name,
            args,
            input_text,
            timeout_seconds=None,
            strip_noise=True,
        ):
            self.flags.append(strip_noise)
            return True, "ok"

    adapter = _CaptureStripNoiseAdapter()
    manager = FailoverManager(adapter=adapter, sanitizer=_AllowAllSanitizer(), config=_base_config())

    out = asyncio.run(
        manager.execute_async("codex", "gemini", "hello", mode="execution", output_mode="raw")
    )

    assert "ok" in out
    assert adapter.flags == [False]
