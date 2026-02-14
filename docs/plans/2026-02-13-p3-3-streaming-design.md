# P3-3: Multimodal Streaming Design

## Goal

Implement real-time streaming support using MCP progress notifications and SSE-like behavior for long-running requests.

## Current State

```python
def _format_stream_fallback(text: str) -> str:
    chunks = [text[i : i + 200] for i in range(0, len(text), 200)]
    return "[STREAM FALLBACK]\n" + "\n".join(chunks) + "\n[STREAM END]"
```

Currently, `stream=True` just splits the response into chunks after receiving it. No real-time streaming.

## Target Architecture

```
ask() with stream=True
    ↓
FastMCP ctx.report_progress()  →  Real-time progress updates
    ↓
Chunked response as it arrives
```

## MCP Streaming Options

### Option 1: Progress Notifications (Recommended)
- Use `ctx.report_progress(progress, total)` for real-time updates
- Works with current FastMCP infrastructure
- Already used in P2-3 for batch progress

### Option 2: SSE (Server-Sent Events)
- Would require HTTP transport
- More complex setup
- Better for web clients

**Decision:** Use MCP progress notifications (Option 1) - simpler and consistent with existing patterns.

## Design

### Streaming Response Flow

```
1. Client calls ask(prompt, stream=True)
2. Server starts processing
3. Server sends progress updates via ctx.report_progress()
   - progress: characters received so far
   - total: estimated total (or -1 for unknown)
4. Server returns final response
5. Client receives complete response
```

### Implementation

```python
async def ask_streaming(
    prompt: str,
    ctx: Context,
    ...
) -> str:
    """Streaming ask with progress notifications."""

    # Get streaming response from provider
    async for chunk in provider.stream(prompt):
        accumulated += chunk
        await ctx.report_progress(
            progress=len(accumulated),
            total=-1,  # Unknown total
        )

    return accumulated
```

### Provider Support

| Provider | Supports Streaming |
|----------|-------------------|
| codex | ❌ (CLI-based) |
| gemini | ❌ (CLI-based) |
| ollama | ✅ (native streaming) |
| claude_code | ❌ (CLI-based) |

For CLI-based providers, we can only stream at the subprocess level (line-by-line output).

## Implementation Plan

### Step 1: Add streaming infrastructure
- `src/model_bridge/core/streaming.py` - Streaming utilities
- Async generator for subprocess line-by-line reading

### Step 2: Update ask_ollama for streaming
- Add `stream=True` parameter
- Use subprocess async streaming
- Report progress via context

### Step 3: Update ask function
- Accept `ctx: Context` parameter for streaming
- Route to streaming path when `stream=True` and provider supports it

### Step 4: Tests
- `tests/unit/test_streaming.py`

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/model_bridge/core/streaming.py` | CREATE |
| `src/model_bridge/main.py` | MODIFY |
| `tests/unit/test_streaming.py` | CREATE |

## Verification

1. `ask(prompt, stream=True, provider="ollama")` streams progress
2. Non-streaming requests unchanged
3. Progress notifications sent correctly
4. Works with batch operations (P2-3 already uses this)
