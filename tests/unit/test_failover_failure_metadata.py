from model_bridge.core.failover_manager import FailoverManager


class _AlwaysFailAdapter:
    async def run_async(self, service_name, args, input_text):
        return False, f"{service_name}-failed"


class _AllowSanitizer:
    @staticmethod
    def inspect(prompt, mode="execution"):
        return True, ""


def _config():
    return {
        "models": {"ollama_final_backup_model": "qwen3-coder-next:Q4_K_M"},
        "routing": {"default_chains": {}},
    }


def test_failover_error_contains_failure_metadata_block():
    manager = FailoverManager(adapter=_AlwaysFailAdapter(), sanitizer=_AllowSanitizer(), config=_config())
    out = manager.execute("codex", "gemini", "hello", mode="execution", allow_tertiary=False)

    assert "[Task Execution Failed]" in out
    assert "--- [Failure Metadata] ---" in out
    assert "why_failed:" in out
    assert "next_action:" in out
    assert "primary_error: codex-failed" in out
    assert "secondary_error: gemini-failed" in out


def test_failover_error_contains_tertiary_error_when_enabled():
    manager = FailoverManager(adapter=_AlwaysFailAdapter(), sanitizer=_AllowSanitizer(), config=_config())
    out = manager.execute("codex", "gemini", "hello", mode="execution", allow_tertiary=True)

    assert "primary_error: codex-failed" in out
    assert "secondary_error: gemini-failed" in out
    assert "tertiary_error: ollama-failed" in out
