# Provider Registry Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a provider registry foundation and `claude_code` onboarding stub without breaking existing ask flows.

**Architecture:** Keep current tool signatures and routing behavior, then insert a thin registry layer for provider discovery/validation. Implement only map-safe, backward-compatible schema extensions in Phase 1, then defer full routing migration to later tasks.

**Tech Stack:** Python 3.11, FastMCP, pydantic, pytest.

---

### Task 1: Add Provider Registry Core (Phase 1 foundation)

**Files:**
- Create: `src/model_bridge/core/provider_registry.py`
- Test: `tests/unit/test_provider_registry.py`

**Step 1: Write the failing tests**
- Add tests for:
  - registering/retrieving provider specs
  - duplicate provider registration rejection
  - default registry listing for baseline providers

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev pytest -q tests/unit/test_provider_registry.py`
- Expected: FAIL (module missing).

**Step 3: Write minimal implementation**
- Add `ProviderCapabilities`, `ProviderSpec`, and `ProviderRegistry`.
- Add helper to build default provider set from config.

**Step 4: Run tests to verify pass**
- Run targeted tests.

**Step 5: Commit**
```bash
git add src/model_bridge/core/provider_registry.py tests/unit/test_provider_registry.py
git commit -m "feat: add provider registry foundation"
```

### Task 2: Extend Config Schema for Optional `claude_code` Stub

**Files:**
- Modify: `src/model_bridge/config/config_loader.py`
- Modify: `src/model_bridge/config/default.yaml`
- Test: `tests/unit/test_config_loader.py`

**Step 1: Write the failing tests**
- Add config tests for optional `claude_code` fields:
  - `commands.claude_code` accepted when present
  - `runtime.apply_system_suffix.claude_code` accepted when present
  - old schema without `claude_code` remains valid

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev pytest -q tests/unit/test_config_loader.py`
- Expected: FAIL on new `claude_code` schema cases.

**Step 3: Write minimal implementation**
- Make `commands.claude_code` optional.
- Make `runtime.apply_system_suffix.claude_code` optional with safe default behavior.
- Keep old config compatibility.

**Step 4: Run tests to verify pass**
- Run targeted tests.

**Step 5: Commit**
```bash
git add src/model_bridge/config/config_loader.py src/model_bridge/config/default.yaml tests/unit/test_config_loader.py
git commit -m "feat: allow optional claude_code config stub"
```

### Task 3: Wire Registry into Main and Add `ask_claude_code` Stub Tool

**Files:**
- Modify: `src/model_bridge/main.py`
- Test: `tests/integration/test_ask_unified_tool.py`
- Test: `tests/unit/test_main_helpers.py`

**Step 1: Write the failing tests**
- Add tests for:
  - unified `ask(provider="claude_code")` path availability
  - unknown provider error message generated from registry provider list
  - unconfigured `claude_code` path returns clear setup error

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev pytest -q tests/integration/test_ask_unified_tool.py tests/unit/test_main_helpers.py`
- Expected: FAIL because claude_code route and registry validation are missing.

**Step 3: Write minimal implementation**
- Add runtime provider registry singleton.
- Add `ask_claude_code` tool with failover to `codex` when configured; setup error when unconfigured.
- Update unified `ask` provider switch to include `claude_code`.
- Replace hardcoded unknown-provider list with registry-derived list.

**Step 4: Run tests to verify pass**
- Run targeted tests.

**Step 5: Commit**
```bash
git add src/model_bridge/main.py tests/integration/test_ask_unified_tool.py tests/unit/test_main_helpers.py
git commit -m "feat: add claude_code ask stub via provider registry"
```

### Task 4: Verification Gate and Phase Log Update

**Files:**
- Modify: `DEVELOPMENT_PLAN.md`
- Modify: `RELEASE_NOTES.md`

**Step 1: Run full validation**
- Run:
  - `conda run -n model-bridge-mcp_dev pytest -q tests`
  - `conda run -n model-bridge-mcp_dev pre-commit run --all-files`

**Step 2: Document scope**
- Record that this phase adds registry foundation and claude stub only (full routing migration deferred).

**Step 3: Commit**
```bash
git add DEVELOPMENT_PLAN.md RELEASE_NOTES.md
git commit -m "docs: record provider registry phase1 rollout"
```

### Task 5: Next Phase Backlog (No Code)

**Files:**
- Modify: `docs/plans/2026-02-11-provider-registry-design.md`

**Step 1: Add explicit deferred items**
- capability negotiation policy engine
- map-based provider config migration
- health policy runtime enforcement

**Step 2: Commit**
```bash
git add docs/plans/2026-02-11-provider-registry-design.md
git commit -m "docs: detail deferred provider registry phase2 items"
```
