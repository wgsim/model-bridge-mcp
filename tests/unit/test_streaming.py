"""Tests for streaming utilities (P3-3)."""

import asyncio

import pytest

from model_bridge.core.streaming import (
    StreamProgress,
    StreamingBuffer,
    supports_streaming,
    collect_stream,
    run_with_streaming,
)


class TestStreamProgress:
    """Tests for StreamProgress class."""

    def test_init(self):
        """Test initialization."""
        progress = StreamProgress(ctx=None, report_interval=100)
        assert progress.total_chars == 0
        assert progress.last_reported == 0

    @pytest.mark.anyio
    async def test_update_accumulates(self):
        """Test that update accumulates character count."""
        progress = StreamProgress(ctx=None, report_interval=100)

        await progress.update(50)
        assert progress.total_chars == 50

        await progress.update(30)
        assert progress.total_chars == 80

    @pytest.mark.anyio
    async def test_report_interval(self):
        """Test that progress is only reported at interval."""
        reports = []

        class MockContext:
            async def report_progress(self, progress, total):
                reports.append((progress, total))

        ctx = MockContext()
        progress = StreamProgress(ctx=ctx, report_interval=100)

        # First update - 50 chars (below interval)
        await progress.update(50)
        assert len(reports) == 0

        # Second update - total 120 chars (exceeds interval)
        await progress.update(70)
        assert len(reports) == 1
        assert reports[0] == (120, -1)

    @pytest.mark.anyio
    async def test_finalize_sends_total(self):
        """Test that finalize sends total progress."""
        reports = []

        class MockContext:
            async def report_progress(self, progress, total):
                reports.append((progress, total))

        ctx = MockContext()
        progress = StreamProgress(ctx=ctx, report_interval=1000)

        await progress.update(50)
        await progress.finalize()

        assert len(reports) == 1
        assert reports[0] == (50, 50)


class TestStreamingBuffer:
    """Tests for StreamingBuffer class."""

    def test_empty_buffer(self):
        """Test empty buffer."""
        buffer = StreamingBuffer()
        assert len(buffer) == 0
        assert buffer.get_content() == ""

    def test_append_and_get(self):
        """Test appending and getting content."""
        buffer = StreamingBuffer()
        buffer.append("Hello ")
        buffer.append("World")

        assert len(buffer) == 11  # "Hello World" is 11 chars
        assert buffer.get_content() == "Hello World"

    def test_clear(self):
        """Test clearing buffer."""
        buffer = StreamingBuffer()
        buffer.append("test")
        buffer.clear()

        assert len(buffer) == 0
        assert buffer.get_content() == ""


class TestSupportsStreaming:
    """Tests for supports_streaming function."""

    def test_ollama_supports_streaming(self):
        """Test that ollama supports streaming."""
        assert supports_streaming("ollama") is True

    def test_codex_does_not_support_streaming(self):
        """Test that codex does not support streaming."""
        assert supports_streaming("codex") is False

    def test_gemini_does_not_support_streaming(self):
        """Test that gemini does not support streaming."""
        assert supports_streaming("gemini") is False

    def test_unknown_provider_does_not_support_streaming(self):
        """Test that unknown providers don't support streaming."""
        assert supports_streaming("unknown") is False


class TestCollectStream:
    """Tests for collect_stream function."""

    @pytest.mark.anyio
    async def test_collect_empty_stream(self):
        """Test collecting empty stream."""
        async def empty_stream():
            return
            yield  # Make it a generator

        result = await collect_stream(empty_stream())
        assert result == ""

    @pytest.mark.anyio
    async def test_collect_chunks(self):
        """Test collecting multiple chunks."""
        async def chunk_stream():
            yield "Hello "
            yield "World"
            yield "!"

        result = await collect_stream(chunk_stream())
        assert result == "Hello World!"


class TestRunWithStreaming:
    """Tests for run_with_streaming function."""

    @pytest.mark.anyio
    async def test_echo_command(self):
        """Test simple echo command."""
        success, output = await run_with_streaming(
            command_args=["echo", "Hello World"],
        )

        assert success is True
        assert "Hello World" in output

    @pytest.mark.anyio
    async def test_command_with_input(self):
        """Test command with stdin input."""
        success, output = await run_with_streaming(
            command_args=["cat"],
            input_text="Test input",
        )

        assert success is True
        assert "Test input" in output

    @pytest.mark.anyio
    async def test_failed_command(self):
        """Test command that fails."""
        success, output = await run_with_streaming(
            command_args=["ls", "/nonexistent_directory_12345"],
        )

        assert success is False
        assert "No such file" in output or "cannot access" in output or "[STDERR]" in output

    @pytest.mark.anyio
    async def test_timeout(self):
        """Test command timeout."""
        # Use a command that runs longer than timeout
        # sleep 10 seconds with 0.1 second timeout
        # Note: sleep produces no output, so stdout reading finishes quickly
        # but process.wait() should timeout
        success, output = await run_with_streaming(
            command_args=["sh", "-c", "echo starting; sleep 10"],
            timeout=0.5,
        )

        assert success is False
        assert "TIMEOUT" in output

    @pytest.mark.anyio
    async def test_with_progress_reporting(self):
        """Test with progress reporting."""
        reports = []

        class MockContext:
            async def report_progress(self, progress, total):
                reports.append((progress, total))

        ctx = MockContext()

        success, output = await run_with_streaming(
            command_args=["echo", "Test output"],
            ctx=ctx,
            report_interval=1,  # Report every character
        )

        assert success is True
        # Should have at least one progress report
        assert len(reports) >= 1
