# Release Notes

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
