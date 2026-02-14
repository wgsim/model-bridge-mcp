"""Streaming utilities for real-time response delivery (P3-3)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = logging.getLogger("model_bridge.streaming")


class StreamProgress:
    """Tracks streaming progress and sends notifications."""

    def __init__(
        self,
        ctx: Context | None = None,
        report_interval: int = 100,  # Report every N characters
    ) -> None:
        """Initialize stream progress tracker.

        Args:
            ctx: MCP context for progress notifications
            report_interval: Minimum characters between progress reports
        """
        self.ctx = ctx
        self.report_interval = report_interval
        self.total_chars = 0
        self.last_reported = 0

    async def update(self, new_chars: int) -> None:
        """Update progress with new characters received.

        Args:
            new_chars: Number of new characters received
        """
        self.total_chars += new_chars

        # Only report if we've exceeded the interval
        if self.ctx and (self.total_chars - self.last_reported) >= self.report_interval:
            await self.ctx.report_progress(
                progress=self.total_chars,
                total=-1,  # Unknown total
            )
            self.last_reported = self.total_chars

    async def finalize(self) -> None:
        """Send final progress update."""
        if self.ctx and self.total_chars != self.last_reported:
            await self.ctx.report_progress(
                progress=self.total_chars,
                total=self.total_chars,
            )


async def stream_subprocess_output(
    process: asyncio.subprocess.Process,
    progress: StreamProgress | None = None,
) -> AsyncIterator[str]:
    """Stream output from a subprocess line by line.

    Args:
        process: Subprocess to stream from
        progress: Optional progress tracker

    Yields:
        Lines from stdout
    """
    if process.stdout is None:
        return

    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            decoded = line.decode("utf-8", errors="replace")
            if progress:
                await progress.update(len(decoded))

            yield decoded

    except asyncio.CancelledError:
        logger.debug("Stream cancelled")
        raise
    except Exception as e:
        logger.error("Error streaming subprocess output: %s", e)
        raise


async def collect_stream(stream: AsyncIterator[str]) -> str:
    """Collect all chunks from a stream into a single string.

    Args:
        stream: Async iterator of string chunks

    Returns:
        Combined string
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return "".join(chunks)


class StreamingBuffer:
    """Buffer for accumulating streaming content."""

    def __init__(self) -> None:
        """Initialize empty buffer."""
        self._chunks: list[str] = []

    def append(self, chunk: str) -> None:
        """Add a chunk to the buffer."""
        self._chunks.append(chunk)

    def get_content(self) -> str:
        """Get all buffered content."""
        return "".join(self._chunks)

    def clear(self) -> None:
        """Clear the buffer."""
        self._chunks.clear()

    def __len__(self) -> int:
        """Return total buffered length."""
        return sum(len(c) for c in self._chunks)


def supports_streaming(provider_id: str) -> bool:
    """Check if a provider supports real streaming.

    Args:
        provider_id: Provider identifier

    Returns:
        True if provider supports streaming
    """
    # Only Ollama supports native streaming currently
    # CLI-based providers (codex, gemini, claude_code) don't support streaming
    streaming_providers = {"ollama"}
    return provider_id in streaming_providers


async def run_with_streaming(
    command_args: list[str],
    input_text: str | None = None,
    timeout: float = 120.0,
    ctx: Context | None = None,
    report_interval: int = 500,
) -> tuple[bool, str]:
    """Run a command with streaming output.

    Uses asyncio.create_subprocess_exec (not shell) for safety.

    Args:
        command_args: Command and arguments as list
        input_text: Optional input to pipe to stdin
        timeout: Timeout in seconds
        ctx: MCP context for progress notifications
        report_interval: Characters between progress reports

    Returns:
        Tuple of (success, output)
    """
    progress = StreamProgress(ctx=ctx, report_interval=report_interval)
    buffer = StreamingBuffer()
    process = None

    try:
        # Use exec (not shell) for safety - command_args is a list, not a string
        process = await asyncio.create_subprocess_exec(
            *command_args,
            stdin=asyncio.subprocess.PIPE if input_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Send input if provided
        if input_text and process.stdin:
            process.stdin.write(input_text.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

        # Create a task for streaming stdout
        async def stream_and_collect():
            async for line in stream_subprocess_output(process, progress):
                buffer.append(line)

        # Run streaming with overall timeout
        await asyncio.wait_for(stream_and_collect(), timeout=timeout)

        # Wait for process to complete (with small remaining timeout)
        remaining_timeout = max(0.1, timeout)
        await asyncio.wait_for(process.wait(), timeout=remaining_timeout)

        # Collect stderr for error reporting
        stderr = ""
        if process.stderr:
            stderr_bytes = await process.stderr.read()
            stderr = stderr_bytes.decode("utf-8", errors="replace")

        await progress.finalize()

        success = process.returncode == 0
        output = buffer.get_content()

        if not success:
            logger.warning(
                "Command failed with code %d: %s",
                process.returncode,
                stderr[:200],
            )
            # Include stderr in output for error context
            if stderr:
                output = output + "\n[STDERR]\n" + stderr

        return success, output

    except asyncio.TimeoutError:
        logger.error("Command timed out after %s seconds", timeout)
        # Kill the process if it's still running
        if process and process.returncode is None:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
        return False, f"[TIMEOUT] Command exceeded {timeout} seconds"
    except Exception as e:
        logger.error("Command execution failed: %s", e)
        return False, f"[ERROR] {e}"
