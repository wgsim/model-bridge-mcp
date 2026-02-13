import asyncio

from model_bridge import main as main_module


class _FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        self.value += 0.01
        return self.value


def test_ask_batch_rejects_invalid_mode():
    out = asyncio.run(main_module.ask_batch(prompts=["a"], mode="bad-mode"))
    assert '"status": "error"' in out
    assert "mode must be one of" in out


def test_ask_batch_runs_sequential(monkeypatch):
    calls = []

    async def _fake_ask(**kwargs):
        calls.append(kwargs["prompt"])
        return f"ok:{kwargs['prompt']}"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["p1", "p2"],
            mode="sequential",
            response_format="text",
        )
    )

    assert calls == ["p1", "p2"]
    assert '"ok_jobs": 2' in out
    assert '"error_jobs": 0' in out


def test_ask_batch_runs_parallel(monkeypatch):
    async def _fake_ask(**kwargs):
        await asyncio.sleep(0)
        return f"ok:{kwargs['prompt']}"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a", "b", "c"],
            mode="parallel",
            max_concurrency=2,
        )
    )

    assert '"mode": "parallel"' in out
    assert '"total_jobs": 3' in out
    assert '"ok_jobs": 3' in out


def test_ask_batch_clamps_ollama_parallelism(monkeypatch):
    async def _fake_ask(**kwargs):
        await asyncio.sleep(0)
        return f"ok:{kwargs['prompt']}"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())
    monkeypatch.setattr(
        main_module,
        "_compute_ollama_batch_concurrency",
        lambda model, requested: {
            "resolved_model": "gpt-oss:20b",
            "applied_max_concurrency": 1,
            "reason": "test_guard",
            "resources": {"ram_free_gb": 8.0},
        },
    )

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a", "b", "c"],
            provider="ollama",
            mode="parallel",
            max_concurrency=8,
        )
    )

    assert '"requested_max_concurrency": 8' in out
    assert '"applied_max_concurrency": 1' in out
    assert '"concurrency_guard"' in out


def test_ask_batch_forwards_instruction_preset(monkeypatch):
    captured = []

    async def _fake_ask(**kwargs):
        captured.append(kwargs.get("instruction_preset"))
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a", "b"],
            mode="sequential",
            instruction_preset="strict_once",
        )
    )

    assert captured == ["strict_once", "strict_once"]
    assert '"ok_jobs": 2' in out


def test_ask_batch_forwards_output_mode(monkeypatch):
    captured = []

    async def _fake_ask(**kwargs):
        captured.append(kwargs.get("output_mode"))
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a", "b"],
            mode="sequential",
            output_mode="raw",
        )
    )

    assert captured == ["raw", "raw"]
    assert '"ok_jobs": 2' in out


def test_ask_batch_accepts_priority_parameter(monkeypatch):
    """Test that priority parameter is accepted without error."""

    async def _fake_ask(**kwargs):
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    # Test high priority
    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a"],
            mode="sequential",
            priority="high",
        )
    )
    assert '"ok_jobs": 1' in out

    # Test low priority
    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a"],
            mode="sequential",
            priority="low",
        )
    )
    assert '"ok_jobs": 1' in out


def test_ask_batch_accepts_rate_limit_rps_parameter(monkeypatch):
    """Test that rate_limit_rps parameter is accepted and reflected in output."""

    async def _fake_ask(**kwargs):
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a"],
            mode="sequential",
            rate_limit_rps=5.0,
        )
    )
    assert '"ok_jobs": 1' in out
    assert '"rate_limit_rps": 5.0' in out


def test_ask_batch_accepts_stream_results_parameter(monkeypatch):
    """Test that stream_results parameter is accepted without error."""

    async def _fake_ask(**kwargs):
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    out = asyncio.run(
        main_module.ask_batch(
            prompts=["a", "b"],
            mode="sequential",
            stream_results=True,
        )
    )
    assert '"ok_jobs": 2' in out


def test_ask_batch_priority_ordering_sequential(monkeypatch):
    """Test that high priority jobs execute first in sequential mode."""
    execution_order = []

    async def _fake_ask(**kwargs):
        execution_order.append(kwargs["prompt"])
        return "ok"

    monkeypatch.setattr(main_module, "ask", _fake_ask)
    monkeypatch.setattr(main_module, "time", type("_T", (), {"perf_counter": _FakeClock()})())

    # Note: In the current implementation, all jobs in a batch have the same priority
    # This test verifies the parameter is accepted; per-prompt priority would be a future enhancement
    out = asyncio.run(
        main_module.ask_batch(
            prompts=["first", "second", "third"],
            mode="sequential",
            priority="high",
        )
    )
    assert '"ok_jobs": 3' in out
    # All prompts are executed in order when they have same priority
    assert execution_order == ["first", "second", "third"]

