# Release Notes

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
- `coder_ai_allocator_v1.0.py`
- `coder_ai_allocator_v1.1.py`
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
