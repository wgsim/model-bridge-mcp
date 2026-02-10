# Phase 2 Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close all review findings by applying security, reliability, and testability hardening with minimal behavior change.

**Architecture:** Keep public MCP tool signatures unchanged, improve internal adapter/sanitizer/path-safety behavior, and lock changes with direct unit coverage. Execute P0 first to reduce security risk, then P1 for robustness, then P2 for maintainability.

**Tech Stack:** Python 3.11, FastMCP, asyncio, subprocess, pydantic, pytest.

---

### Task 1: Switch Prompt Delivery to `stdin` (P0-1)

**Files:**
- Modify: `src/model_bridge/adapters/base.py`
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`
- Test: `tests/unit/test_subprocess_adapter.py`

1. Write failing tests for `stdin` usage and argv non-leak behavior.
2. Run failing tests only.
   - Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_subprocess_adapter.py -k stdin'`
   - Expected: FAIL (before implementation).
3. Implement minimal adapter change to feed prompt through stdin in sync/async path.
4. Re-run adapter tests and full unit suite.
5. Commit:
   - `git commit -m "fix: pass model prompts through stdin in subprocess adapter"`

### Task 2: Harden `save_to_file` Path Security (P0-2)

**Files:**
- Modify: `src/model_bridge/main.py`
- Test: `tests/unit/test_main_save_behavior.py`

1. Add failing tests for symlink/realpath system-path rejection.
2. Run new test file.
3. Implement `realpath`-based protected-prefix check.
4. Run affected tests + full unit suite.
5. Commit:
   - `git commit -m "fix: enforce realpath-based safe write policy"`

### Task 3: Make Sanitizer Config-Driven (P0-3)

**Files:**
- Modify: `src/model_bridge/security/sanitizer.py`
- Modify: `src/model_bridge/main.py`
- Modify: `src/model_bridge/config/config_loader.py` (if constructor/schema update needed)
- Test: `tests/unit/test_security_sanitizer.py`

1. Add failing tests for config-injected patterns/paths.
2. Implement sanitizer initialization/use from validated config.
3. Keep backward-compatible inspect behavior and error format.
4. Run sanitizer/failover tests + full unit suite.
5. Commit:
   - `git commit -m "refactor: load sanitizer rules from validated config"`

### Task 4: Add Subprocess Timeout Controls (P1-1)

**Files:**
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/config/config_loader.py`
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`
- Test: `tests/unit/test_subprocess_adapter.py`

1. Add timeout config field and schema validation.
2. Add sync/async timeout handling with explicit error text.
3. Add/adjust timeout tests.
4. Run unit tests.
5. Commit:
   - `git commit -m "feat: add configurable subprocess timeouts"`

### Task 5: Strengthen Adapter Type Contracts (P1-2)

**Files:**
- Modify: `src/model_bridge/adapters/base.py`
- Modify: `src/model_bridge/core/failover_manager.py`
- Test: `tests/unit/test_failover_manager.py`

1. Add `run_async` contract to adapter interface.
2. Replace broad `Any` in manager constructor with typed protocol/interface.
3. Update tests/mocks to satisfy new contract.
4. Run failover tests + full unit suite.
5. Commit:
   - `git commit -m "refactor: strengthen adapter interface typing"`

### Task 6: Add Missing Direct Unit Tests (P1-3)

**Files:**
- Modify: `tests/unit/test_main_helpers.py` (new)
- Modify: `tests/unit/test_main_ollama_model_resolution.py`
- Modify: `tests/unit/test_main_save_behavior.py`

1. Add direct tests for:
   - `clean_markdown_fences`
   - `_cleanup_old_meta_logs`
   - `_resolve_fallback_chain`
   - `save_to_file` protected path rejection
   - `ask_ollama` security block early return
2. Run targeted tests then full unit suite.
3. Commit:
   - `git commit -m "test: add direct coverage for main helpers and security paths"`

### Task 7: Apply Dev/Ops Hygiene Updates (P2)

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `RELEASE_NOTES.md`
- Optional: move `coder_ai_allocator_v1.0.py`, `coder_ai_allocator_v1.1.py` to `archive/`

1. Add pytest config for direct local execution.
2. Expand `.gitignore` without removing existing policy.
3. Document legacy script policy or relocate scripts.
4. Update release notes.
5. Run full unit suite and smoke checks.
6. Commit:
   - `git commit -m "chore: improve test ergonomics and repository hygiene"`

### Task 8: Final Verification and Integration

**Files:**
- Verify only (all touched files)

1. Run:
   - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'`
   - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -c "from model_bridge.main import mcp; print(type(mcp).__name__)"'`
2. Confirm no regression in tool signatures and routing log format.
3. Prepare merge summary with risk notes.
