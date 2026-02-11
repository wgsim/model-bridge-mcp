# Orchestrator Parallel Policy (Phase 3)

## Goal
Define how `model-bridge-mcp` behaves when client-side orchestrators have different tool parallelism capabilities.

## Policy
- Default to a single MCP call from the orchestrator.
- Execute fan-out inside MCP via `ask_batch(mode="parallel")`.
- Keep external orchestrator behavior advisory, not required.

## Capability Matrix (Operational Assumption)
- Codex: external parallel tool calls may be limited or session-dependent.
- Gemini: external parallel tool calls may be limited or session-dependent.
- Claude Code: external parallel tool calls may be available.

## Determinism Rule
When behavior differs across orchestrators, MCP-internal orchestration is the source of truth.

## Failure Handling
- If external orchestrator parallel behavior is unclear, fallback to single-call `ask_batch`.
- Keep per-job status in batch output for replayability.

## Assumption
Orchestrator capabilities can change by client/runtime version. Re-validate periodically.
