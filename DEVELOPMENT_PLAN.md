# Development Plan: Model Bridge MCP

## Goal
Migrate monolithic allocator scripts (`archive/coder_ai_allocator_v1.0.py`, `archive/coder_ai_allocator_v1.1.py`) into a modular MCP package (`model-bridge-mcp`) while preserving current tool behavior (`ask_chatgpt_cli`, `ask_gemini_cli`, `ask_ollama`), failover flow, and security guarantees.

## Scope Baseline (Current State)
- Python files currently present:
  - `archive/coder_ai_allocator_v1.0.py`
  - `archive/coder_ai_allocator_v1.1.py`
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
      - `ask_ollama(prompt, save_path=None, model="default")`
    - Wire config loader + failover manager + sanitizer.
    - → Verify:
      - Import smoke: `python -c "from model_bridge.main import mcp"` succeeds.
      - Runtime smoke (choose environment-supported option):
        - `mcp run src/model_bridge/main.py` or
        - `python -m model_bridge.main`

- [x] **Task 6: Documentation and Operational Checks**
    - Write `README.md` with setup, config, failover behavior, and security boundaries.
    - Document migration note from `archive/coder_ai_allocator_v1.1.py` to `src/model_bridge/main.py`.
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
- [x] **Async Execution Path**
  - Replace blocking `subprocess.run` calls with `asyncio.create_subprocess_exec`.
  - Goal: keep MCP server responsive during long-running model calls.
  - Verify:
    - Concurrent tool-call scenario does not block unrelated requests.

- [x] **Typed Config Validation**
  - Add `pydantic` models for config schema (CLI commands, models, routing, security options).
  - Goal: fail fast with clear validation errors for missing/invalid keys.
  - Verify:
    - Invalid config fixtures produce deterministic validation errors at startup.

- [x] **CLI Entrypoint for Operations**
  - Add `[project.scripts]` entry in `pyproject.toml` (for example: `model-bridge = model_bridge.main:run`).
  - Goal: simplify launch/ops flow and reduce command ambiguity.
  - Verify:
    - After install, script-based startup works in clean venv.

## Next Candidates
- [x] Add CI workflow (pytest + pre-commit run) for PR gate.
- [x] Add typed response contract tests for MCP tool outputs.
- [x] Add structured operational telemetry (request id, routing tier, latency).
- [x] Add `list_ollama_models` usage examples to client integration docs.

## Phase 2 Checklist (Security, Reliability, Testability)
### P0 (Start First)
- [x] **P0-1: Prevent prompt leakage in process args**
  - Change adapter execution to send prompt via `stdin` instead of argv tail.
  - Keep command signature compatibility for `codex`, `gemini`, `ollama run <model>`.
  - Verify:
    - Subprocess unit tests pass with `stdin` assertions.
    - Prompt text is not present in process argument construction path.

- [x] **P0-2: Harden file write path validation**
  - In `save_to_file`, resolve destination using `realpath` before security path checks.
  - Reject writes resolving to protected system prefixes.
  - Verify:
    - Symlink-based bypass test fails as expected.
    - Legitimate project-local paths still save successfully.

- [x] **P0-3: Wire sanitizer rules from config**
  - Remove hardcoded sanitizer rule sources as runtime truth.
  - Load `security.block_patterns` and `security.sensitive_paths` from validated config.
  - Verify:
    - Config override fixture changes sanitizer behavior deterministically.
    - Missing/invalid security fields fail with clear validation errors.

### P1 (After P0)
- [x] **P1-1: Add subprocess timeout controls**
  - Add configurable timeout in YAML/runtime for sync + async subprocess execution.
  - Return controlled timeout error message for failover handling.
  - Verify:
    - Timeout unit tests for sync and async paths.

- [x] **P1-2: Tighten adapter interface contract**
  - Extend `CLIAdapter` with async method contract (`run_async`).
  - Reduce `Any` usage in `FailoverManager` via protocol/type-safe interfaces.
  - Verify:
    - Type-check and unit tests pass with no behavioral change.

- [x] **P1-3: Add missing direct unit tests (high-value targets)**
  - Add tests for:
    - `clean_markdown_fences`
    - `_cleanup_old_meta_logs`
    - `_resolve_fallback_chain`
    - `save_to_file` path rejection
    - `ask_ollama` security-block early return
  - Verify:
    - Added tests fail before implementation (where applicable) and pass after fix.

### P2 (Maintainability / Ops)
- [x] **P2-1: Improve test/dev ergonomics**
  - Add pytest config in `pyproject.toml` (pythonpath/testpaths).
  - Expand `.gitignore` for common Python/dev artifacts.

- [x] **P2-2: Refine initialization design**
  - Move import-time global initialization to lazy-init/factory pattern.
  - Preserve MCP external behavior and tool signatures.

- [x] **P2-3: Clean legacy layout**
  - Move legacy scripts to `archive/` or document deprecation policy clearly.
  - Keep migration traceability in README/release notes.

### Tracking and Execution
- Canonical execution plan: `docs/plans/2026-02-10-phase2-hardening-plan.md`
- Recommended order: `P0-1 -> P0-2 -> P0-3 -> P1-* -> P2-*`
- Validation gate for each task:
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'`
- Completion status (2026-02-10):
  - `c467465` (`stdin` prompt delivery)
  - `fd32f93` (realpath-based write hardening)
  - `0341a52` (config-driven sanitizer)
  - `fdbccc0` (timeouts, type contract hardening, direct coverage, archive migration)
  - `878371e` (plan/doc/hygiene sync)

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
- Verification snapshot (2026-02-10):
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'` -> `52 passed`
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -c "from model_bridge.main import mcp; print(type(mcp).__name__)"'` -> `FastMCP`

## Phase 3 Plan
- Implementation plan: `docs/plans/2026-02-10-phase3-ask-ux-efficiency-plan.md`
