# Provider Registry and CLI Capability Design

## Context
- Current `ask` flow in `src/model_bridge/main.py` routes providers via hardcoded branches (`codex`, `gemini`, `ollama`).
- Each CLI has different command style and option semantics, but current design assumes near-uniform behavior.
- Near-term requirement: keep provider expansion open and add `claude_code` safely without repeated branch growth.

## Goal
- Keep one stable external `ask` contract while isolating provider-specific CLI differences.
- Add new providers with minimal core changes.
- Preserve backward compatibility for existing tools and response contracts.

## Non-Goals
- Rewriting all adapters in one step.
- Changing existing MCP tool names/signatures in a breaking way.
- Introducing dynamic plugin loading from remote sources.

## Design Options

### Option A: Keep current hardcoded branching and append providers
- Approach: extend `if/elif` branches in `ask` and provider-specific helpers.
- Pros: lowest short-term diff.
- Cons: branching complexity grows linearly; option mismatch logic duplicated; high regression risk.

### Option B (Recommended): Provider Registry + Capability Negotiation + Adapter Bridge
- Approach: central registry defines provider metadata/capabilities and dispatches to provider adapters.
- Pros: isolates CLI differences; makes `claude_code` add path predictable; simplifies tests by contract.
- Cons: moderate refactor cost in routing/config validation.

### Option C: Full strategy/plugin framework first
- Approach: abstract provider execution into plugin system before feature work.
- Pros: most flexible long-term.
- Cons: over-design for current size; high migration risk now.

## Recommended Architecture (Option B)

### 1) Common Ask Contract (stable)
- Keep canonical request fields:
  - `prompt`, `provider`, `model`, `force_model`, `timeout_seconds`
  - `max_output_tokens`, `response_format`, `verbosity`, `stream`
  - `save_path`, `session_id`
- Continue backward compatibility for existing tool wrappers.

### 2) Provider Registry
- New in-memory registry in runtime layer:
  - `provider_id`: `codex`, `gemini`, `ollama`, `claude_code`, ...
  - `handler`: callable/provider adapter
  - `capabilities`: booleans + policy metadata
  - `defaults`: provider-level defaults when omitted
  - `required_env`: required environment variable names
  - `health_policy`: startup/lazy health-check policy
- `ask(provider=...)` validates against registry keys (dynamic error message).

### 3) Capability Negotiation
- Normalize once, negotiate once:
  - If supported: pass option to adapter.
  - If unsupported: enforce explicit policy (`error` or `degrade`).
- Initial policy recommendation:
  - `response_format=json`: `error` when unsupported.
  - `stream`: `degrade` to non-stream with metadata warning.
  - unknown provider option: hard error.

### 4) Adapter Bridge
- Provider adapter interface:
  - `execute(prompt, options, context) -> ProviderResult`
- Adapter converts common options to provider CLI flags/STDIN contract.
- Existing `SubprocessAdapter` remains execution primitive; provider adapter focuses on translation.
- Add optional normalization shim in adapter:
  - inject provider-specific prompt suffix/prefix when option cannot be expressed as native CLI flag.
  - example: strict JSON instruction shim when provider lacks explicit JSON mode.

### 5) Response Contract
- Unified internal result shape:
  - `provider`, `content`, `cached`, `meta`, optional `warnings`.
- Final output renderer keeps current text/json external behavior unchanged.

### 6) Unified Error Contract
- Normalize provider failures into stable categories:
  - `provider_unavailable`, `auth_failed`, `rate_limited`, `timeout`, `invalid_request`, `execution_error`.
- Keep existing human-readable messages, but include machine-readable `error_code` in metadata path.
- Failover decisions should depend on category:
  - retryable (`provider_unavailable`, `rate_limited`, `timeout`) -> allow next chain.
  - non-retryable (`invalid_request`, policy/security block) -> stop early.

## Config Evolution

### Current pain point
- `CommandsConfig` and `RuntimeApplySystemSuffix` are fixed fields (`codex/gemini/ollama`) and block provider growth.

### Proposed schema direction
- Replace fixed provider fields with map-based config:
  - `commands.providers.<provider_id>.exec/health`
  - `runtime.apply_system_suffix.<provider_id>: bool`
  - `routing.default_chains` accepts provider IDs present in registry/config
  - optional `schema_version` for explicit migration handling
- Validation rules:
  - `provider_id` non-empty and unique.
  - every chain token exists in provider map.
  - `required_env` entries are non-empty; missing variables fail startup with actionable error.
  - required baseline providers can be policy-configured (not hardcoded in model).

## `claude_code` Immediate Onboarding Path
- Add provider entry in config map:
  - `commands.providers.claude_code.exec: [...]`
  - `commands.providers.claude_code.health: [...]`
- Register `claude_code` capability profile (initial conservative):
  - `supports_json`: false (until verified)
  - `supports_stream`: false (until verified)
  - `supports_force_model`: depends on CLI support
- Register required environment variables:
  - `required_env`: verified list (exact names confirmed during implementation)
- Add provider adapter tests and one integration smoke route via unified `ask`.

## Health Check Lifecycle
- Startup check:
  - validate required binaries and required env vars for enabled providers.
- Lazy runtime check:
  - optional per-provider health probe before first execution.
- Degraded runtime policy:
  - if health probe fails, mark provider unavailable for cooldown window and route to next chain entry.

## Migration Plan (Incremental)
1. Introduce registry abstraction while keeping existing wrappers (`ask_chatgpt_cli`, `ask_gemini_cli`, `ask_ollama`).
2. Move unified `ask` routing to registry dispatch.
3. Convert config models to map-based provider definitions with compatibility shim for old schema.
4. Add `claude_code` provider entry and adapter.
5. Remove direct hardcoded provider branching after parity verification.

## Validation Criteria
- Functional:
  - Existing provider paths unchanged for current defaults.
  - `ask(provider=<new>)` works without modifying main routing logic.
- Compatibility:
  - Existing wrappers keep signatures and response behavior.
  - Existing JSON/text response contracts remain valid.
- Reliability:
  - Unsupported options produce deterministic policy outcome (`error`/`degrade`).
  - Failover chain validation catches unknown providers at startup.

## Test Strategy
- Unit:
  - capability negotiation matrix (supported/unsupported option combinations)
  - registry validation and dynamic provider error messaging
  - config schema validation for provider maps and routing links
- Integration:
  - unified `ask` with `codex/gemini/ollama/claude_code` stub adapters
  - fallback behavior with unsupported options and policy metadata
- Contract:
  - response contract snapshot tests for text/json modes

## Risks and Mitigations
- Risk: configuration migration breakage.
  - Mitigation: compatibility loader path for existing schema and strict startup validation.
- Risk: provider capability mis-declaration.
  - Mitigation: provider onboarding checklist + capability tests required for merge.
- Risk: gradual rollout leaves dual paths inconsistent.
  - Mitigation: wrapper functions call registry path internally as soon as available.
- Risk: timeout/process lifecycle mismatch creates stuck subprocesses.
  - Mitigation: define timeout precedence (`request option` > `runtime default` > CLI default) and enforce process kill/wait policy.

## Recommended Next Implementation Tasks
1. Add provider registry module and capability model.
2. Add map-based config schema with backward-compatible loader shim.
3. Refactor unified `ask` to registry dispatch.
4. Add `claude_code` provider adapter and smoke tests.
