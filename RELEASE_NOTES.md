# Release Notes

## v0.1.3 - 2026-02-11

### Summary
- Added Phase 3 external orchestrator parallelism policy and capability visibility.

### Highlights
- Added new MCP tool:
  - `list_orchestrator_capabilities()`
- Added orchestrator capability policy document:
  - `docs/skills/orchestrator-parallel-policy.md`
- Updated README with orchestrator capability guidance.
- Added unit test:
  - `tests/unit/test_main_orchestrator_capabilities.py`

## v0.1.2 - 2026-02-11

### Summary
- Added Phase 2 MCP-internal batch orchestration with optional parallel mode.

### Highlights
- Added new MCP tool:
  - `ask_batch(prompts, provider, model, mode, max_concurrency, ...)`
- Added MCP-internal execution modes:
  - `sequential`
  - `parallel` (bounded by `max_concurrency`)
- Added per-job result payload:
  - `job_id`, `status`, `duration_ms`, `content|error`
- Added docs for batch API in `README.md`.
- Added unit tests:
  - `tests/unit/test_main_ask_batch.py`

## v0.1.1 - 2026-02-11

### Summary
- Added Phase 1 skill workflow design assets without parallel execution changes.

### Highlights
- Added workflow skill definitions:
  - `skills/ask-general-workflow/SKILL.md`
  - `skills/ask-review-workflow/SKILL.md`
  - `skills/ask-code-writing-workflow/SKILL.md`
  - `skills/ask-strict-json-workflow/SKILL.md`
  - `skills/ask-batch-workflow/SKILL.md`
  - `skills/ask-provider-routing-workflow/SKILL.md`
- Added skill routing specification:
  - `docs/skills/skill-routing-spec.md`
- Added skill index:
  - `skills/README.md`
- Updated README with Skill Workflows section.

## v0.0.4 - 2026-02-10

### Summary
- Implemented Phase 3 ask UX/efficiency core features.

### Highlights
- Added standardized ask options to `ask_chatgpt_cli`, `ask_gemini_cli`, `ask_ollama`:
  - `timeout_seconds`, `max_output_tokens`, `response_format`, `verbosity`, `stream`
- Added unified tool:
  - `ask(prompt, provider, model, ..., session_id)`
- Added lightweight auto routing for `ask_ollama(model="auto")`.
- Added in-memory prompt cache and session memory modules:
  - `src/model_bridge/core/prompt_cache.py`
  - `src/model_bridge/core/session_memory.py`
- Added failure metadata block in failover errors:
  - `--- [Failure Metadata] ---`
  - `why_failed`, `next_action`

### Tests Added
- `tests/unit/test_main_ask_options.py`
- `tests/unit/test_auto_routing_policy.py`
- `tests/unit/test_prompt_cache.py`
- `tests/unit/test_session_memory.py`
- `tests/unit/test_failover_failure_metadata.py`
- `tests/integration/test_ask_unified_tool.py`
- `tests/integration/test_streaming_mode.py`

### Verification Snapshot
- `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'`
- Result: `73 passed`

## v0.0.3 - 2026-02-10

### Summary
- Completed all items in `DEVELOPMENT_PLAN.md` "Next Candidates".
- Added CI gate, response contract tests, telemetry logging, and documentation examples.

### Highlights
- Added CI workflow:
  - `.github/workflows/ci.yml`
  - runs `pytest -q tests/unit` and `pre-commit run --all-files`
- Added typed response contract tests:
  - `tests/unit/test_response_contracts.py`
- Added JSON Schema contract for MCP JSON output:
  - `schemas/list_ollama_models.schema.json`
- Added integration smoke tests for tool entrypoints:
  - `tests/integration/test_tool_smoke.py`
- Updated local/CI test command from `tests/unit` to `tests`.
- Added structured telemetry in failover manager:
  - logger: `model_bridge.telemetry`
  - fields: `request_id`, `routing_tier`, `latency_ms`, `status`, `error_category`
- Refined runtime initialization in `model_bridge.main`:
  - switched from import-time eager initialization to lazy initialization on first use
- Added `list_ollama_models` usage/parsing examples in `README.md`.

### Verification Snapshot
- `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'`
- Result: `60 passed`

## v0.0.2 - 2026-02-09

### Summary
- Completed modular migration and Phase 2 enhancements.
- Integrated async execution, strict config validation, and improved ollama operations.

### Highlights
- Added strict typed config validation with `pydantic`.
- Added script entrypoint:
  - `model-bridge = model_bridge.main:run`
- Added async subprocess and async failover path.
- Updated `ask_ollama` behavior:
  - alias-first model resolution (`default`, `fast`, `coder`)
  - local install precheck (`ollama list`)
  - local fallback chain before cloud fallback
- Added `list_ollama_models()` MCP tool to report:
  - configured catalog/aliases
  - installed/missing models
  - pull hints
- Updated save behavior:
  - save body-only output to `save_path`
  - save debug meta separately with 48h retention
  - mask sensitive patterns in debug meta logs
- Added/expanded unit tests for all new paths.

### Verification Snapshot
- `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'`
- Result: `39 passed`

## v0.0.1 - 2026-02-09

### Summary
- Initial project bootstrap completed.
- Baseline allocator scripts and migration plan are versioned.

### Included Files
- `archive/coder_ai_allocator_v1.0.py`
- `archive/coder_ai_allocator_v1.1.py`
- `DEVELOPMENT_PLAN.md`

### Highlights
- Added structured development plan for migration to modular `model-bridge-mcp`.
- Clarified current scope baseline (no `server.py`, monolithic scripts as source of truth).
- Defined Phase 1 tasks with explicit verification steps.
- Added Phase 2 improvement backlog:
  - async subprocess path
  - typed config validation
  - script entrypoint
- Added phase boundary policy and MCP transport safety note (`stderr` logging).

### Next Step
- Start Phase 1 Task 1 from `DEVELOPMENT_PLAN.md`:
  - package skeleton under `src/model_bridge`
  - `pyproject.toml`
  - import/install smoke verification
