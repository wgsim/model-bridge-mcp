# Development Plan: Model Bridge MCP

## Goal
Migrate monolithic allocator scripts (`coder_ai_allocator_v1.0.py`, `coder_ai_allocator_v1.1.py`) into a modular MCP package (`model-bridge-mcp`) while preserving current tool behavior (`ask_chatgpt_cli`, `ask_gemini_cli`, `ask_ollama`), failover flow, and security guarantees.

## Scope Baseline (Current State)
- Python files currently present:
  - `coder_ai_allocator_v1.0.py`
  - `coder_ai_allocator_v1.1.py`
- No `server.py` exists in this repository.
- Current code already includes:
  - `FastMCP` tool registration
  - subprocess-based CLI execution
  - failover routing
  - security sanitizer

## Tasks
- [x] **Task 1: Packaging Foundation First**
    - Create package skeleton: `src/model_bridge/{core,adapters,security,config}`.
    - Add `src/model_bridge/__init__.py`.
    - Add `pyproject.toml` and minimal runtime dependencies (`mcp`, `PyYAML`).
    - → Verify:
      - `python -m pip install -e .` succeeds in venv.
      - `python -c "import model_bridge"` succeeds.

- [x] **Task 2: Configuration Externalization**
    - Create `config/config_loader.py` and `config/default.yaml`.
    - Load packaged YAML via `importlib.resources` (not cwd-relative paths).
    - Move hardcoded CLI command paths, model names, and fallback order from `v1.1` into YAML config.
    - Keep safe defaults aligned with current behavior.
    - → Verify:
      - `python -m model_bridge.config.config_loader` loads YAML and prints normalized config (or exits with clear error).
      - Missing/invalid config path produces deterministic error message.

- [x] **Task 3: Extract Security and Adapter Layers**
    - Move `SecuritySanitizer` logic to `security/sanitizer.py`.
    - Create adapter interface in `adapters/base.py`.
    - Implement subprocess adapter in `adapters/subprocess_adapter.py`.
    - Ensure adapter fully captures child process stdout/stderr and returns content without writing protocol data to MCP stdout.
    - → Verify:
      - `pytest -q tests/unit/test_security_sanitizer.py` passes.
      - `pytest -q tests/unit/test_subprocess_adapter.py` passes with mocked `subprocess.run`.

- [x] **Task 4: Extract Failover Core**
    - Move routing/failover orchestration into `core/failover_manager.py`.
    - Inject adapter/config/security dependencies (no hidden globals).
    - Preserve current priority chain semantics and force-primary behavior.
    - → Verify:
      - `pytest -q tests/unit/test_failover_manager.py` passes.
      - Test explicitly proves secondary fallback is called when primary fails.

- [x] **Task 5: Assemble MCP Entrypoint**
    - Create `src/model_bridge/main.py`.
    - Register MCP tools with unchanged external signatures:
      - `ask_chatgpt_cli(prompt, save_path=None, force_model=False)`
      - `ask_gemini_cli(prompt, save_path=None, force_model=False)`
      - `ask_ollama(prompt, save_path=None, model="llama3.2")`
    - Wire config loader + failover manager + sanitizer.
    - → Verify:
      - Import smoke: `python -c "from model_bridge.main import mcp"` succeeds.
      - Runtime smoke (choose environment-supported option):
        - `mcp run src/model_bridge/main.py` or
        - `python -m model_bridge.main`

- [x] **Task 6: Documentation and Operational Checks**
    - Write `README.md` with setup, config, failover behavior, and security boundaries.
    - Document migration note from `coder_ai_allocator_v1.1.py` to `src/model_bridge/main.py`.
    - → Verify:
      - Fresh setup from README works in clean venv.
      - Health-check output and routing-log examples match actual runtime format.

## Minimal Test Strategy
- Unit tests:
  - `test_config_loader.py`: valid load, missing file, invalid schema.
  - `test_security_sanitizer.py`: destructive patterns and sensitive path blocking.
  - `test_subprocess_adapter.py`: command construction and stdout/stderr handling.
  - `test_failover_manager.py`: primary success, secondary fallback, all-fail path.
- Smoke tests:
  - MCP process starts successfully.
  - One tool call returns expected routing log section.
  - Forced primary mode returns controlled error without fallback.

## Phase 2 Improvements (Post-MVP)
- Phase boundary policy: preserve behavior-compatible modular migration in Phase 1; defer performance/operability enhancements to Phase 2 unless they are required to prevent protocol breakage or correctness issues.
- [ ] **Async Execution Path**
  - Replace blocking `subprocess.run` calls with `asyncio.create_subprocess_exec`.
  - Goal: keep MCP server responsive during long-running model calls.
  - Verify:
    - Concurrent tool-call scenario does not block unrelated requests.

- [ ] **Typed Config Validation**
  - Add `pydantic` models for config schema (CLI commands, models, routing, security options).
  - Goal: fail fast with clear validation errors for missing/invalid keys.
  - Verify:
    - Invalid config fixtures produce deterministic validation errors at startup.

- [ ] **CLI Entrypoint for Operations**
  - Add `[project.scripts]` entry in `pyproject.toml` (for example: `model-bridge = model_bridge.main:run`).
  - Goal: simplify launch/ops flow and reduce command ambiguity.
  - Verify:
    - After install, script-based startup works in clean venv.

## Done When
- [x] `src/model_bridge/` modular structure replaces monolithic flow without tool-level behavior regression.
- [x] Hardcoded runtime config values are moved to YAML with validated loading.
- [x] Unit tests for config/security/adapter/failover pass.
- [x] MCP smoke run is successful in the target environment.
- [x] `README.md` documents setup, config, and migration behavior.

## Notes
- Keep diffs incremental and reviewable; avoid broad rewrites in one commit.
- Preserve existing output format unless a change is explicitly documented.
- Prefer `logging` over `print` for runtime events.
- Configure logging handlers to `stderr` to protect MCP JSON-RPC transport on `stdout`.
- Verification snapshot (2026-02-09):
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'` -> `15 passed`
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -c "from model_bridge.main import mcp; print(type(mcp).__name__)"'` -> `FastMCP`
