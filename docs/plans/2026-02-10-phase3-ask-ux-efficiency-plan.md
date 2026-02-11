# Phase 3 Ask UX/Efficiency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve ask-tool usability and runtime efficiency by standardizing options, improving failure UX, and adding higher-level orchestration features.

**Architecture:** Keep existing tool signatures backward-compatible while adding opt-in capabilities incrementally. Implement each feature behind small, test-first changes with strict response format stability for existing clients. Extend config/schema first, then runtime behaviors, then user-facing orchestration.

**Tech Stack:** Python 3.11, FastMCP, asyncio, pydantic, pytest.

---

### Task 1: Standardize Common Ask Options (Priority 1)

**Files:**
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/config/config_loader.py`
- Modify: `src/model_bridge/main.py`
- Test: `tests/unit/test_main_ask_options.py` (new)

**Step 1: Write the failing tests**
- Add tests for common options on all ask tools:
  - `timeout_seconds`
  - `max_output_tokens`
  - `response_format` (`text`/`json`)
  - `verbosity` (`brief`/`normal`/`detailed`)
- Ensure existing calls without new options still pass.

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_main_ask_options.py'`
- Expected: FAIL due to missing parameters/behavior.

**Step 3: Implement minimal changes**
- Add runtime option defaults/validation in config.
- Add optional parameters to `ask_chatgpt_cli`, `ask_gemini_cli`, `ask_ollama`.
- Ensure options are propagated without breaking old behavior.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/config/default.yaml src/model_bridge/config/config_loader.py src/model_bridge/main.py tests/unit/test_main_ask_options.py
git commit -m "feat: standardize common options across ask tools"
```

### Task 2: Improve Failure UX with Actionable Metadata (Priority 4)

**Files:**
- Modify: `src/model_bridge/core/failover_manager.py`
- Modify: `src/model_bridge/main.py`
- Test: `tests/unit/test_failover_failure_metadata.py` (new)

**Step 1: Write the failing tests**
- Add tests expecting failure payload metadata:
  - `why_failed`
  - `next_action`
  - optional `install_hint` for model-missing paths

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_failover_failure_metadata.py'`
- Expected: FAIL (metadata absent).

**Step 3: Implement minimal changes**
- Add metadata generation while preserving existing top-level failure markers.
- Keep backward compatibility for current string format consumers.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/core/failover_manager.py src/model_bridge/main.py tests/unit/test_failover_failure_metadata.py
git commit -m "feat: add actionable failure metadata for ask flows"
```

### Task 3: Add Unified `ask` Endpoint (Priority 7)

**Files:**
- Modify: `src/model_bridge/main.py`
- Test: `tests/integration/test_ask_unified_tool.py` (new)
- Modify: `README.md`

**Step 1: Write the failing tests**
- Add tests for new tool:
  - `ask(prompt, provider="auto|codex|gemini|ollama", ...)`
  - delegation to existing tool paths
  - backward compatibility of old tools

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/integration/test_ask_unified_tool.py'`
- Expected: FAIL (`ask` tool missing).

**Step 3: Implement minimal changes**
- Add new MCP tool `ask`.
- For `provider="auto"`, use existing failover strategy entrypoint.
- Reuse standardized options from Task 1.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/main.py tests/integration/test_ask_unified_tool.py README.md
git commit -m "feat: add unified ask endpoint with provider selection"
```

### Task 4: Add Auto Model Routing Policy (Priority 5)

**Files:**
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/config/config_loader.py`
- Modify: `src/model_bridge/main.py`
- Test: `tests/unit/test_auto_routing_policy.py` (new)

**Step 1: Write the failing tests**
- Add policy tests for `auto` model selection using prompt heuristics:
  - short/simple -> `fast`
  - coding-heavy -> `coder`
  - default -> `default`

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_auto_routing_policy.py'`
- Expected: FAIL (policy not implemented).

**Step 3: Implement minimal changes**
- Add configurable policy thresholds/rules in config.
- Implement resolver in `main.py` (small, deterministic function).

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/config/default.yaml src/model_bridge/config/config_loader.py src/model_bridge/main.py tests/unit/test_auto_routing_policy.py
git commit -m "feat: add configurable auto model routing policy"
```

### Task 5: Add Prompt Cache for Repeated Queries (Priority 2)

**Files:**
- Create: `src/model_bridge/core/prompt_cache.py`
- Modify: `src/model_bridge/main.py`
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/config/config_loader.py`
- Test: `tests/unit/test_prompt_cache.py` (new)

**Step 1: Write the failing tests**
- Add tests for cache hit/miss/ttl expiry behavior.
- Verify cache key includes prompt + provider + major options.

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_prompt_cache.py'`
- Expected: FAIL (module/behavior missing).

**Step 3: Implement minimal changes**
- Add in-memory TTL cache with bounded size.
- Integrate into ask flow as opt-in via config.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/core/prompt_cache.py src/model_bridge/main.py src/model_bridge/config/default.yaml src/model_bridge/config/config_loader.py tests/unit/test_prompt_cache.py
git commit -m "feat: add bounded ttl prompt cache for ask requests"
```

### Task 6: Add Streaming Response Mode (Priority 3)

**Files:**
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`
- Modify: `src/model_bridge/main.py`
- Test: `tests/integration/test_streaming_mode.py` (new)
- Modify: `README.md`

**Step 1: Write the failing tests**
- Add integration tests for streaming mode:
  - chunked output path
  - fallback to non-streaming when unsupported

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/integration/test_streaming_mode.py'`
- Expected: FAIL (streaming absent).

**Step 3: Implement minimal changes**
- Add `stream=True/False` option in ask path.
- Implement line/chunk emission strategy compatible with MCP response constraints.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/adapters/subprocess_adapter.py src/model_bridge/main.py tests/integration/test_streaming_mode.py README.md
git commit -m "feat: add optional streaming response mode for ask tools"
```

### Task 7: Add Session Context Memory (Priority 6)

**Files:**
- Create: `src/model_bridge/core/session_memory.py`
- Modify: `src/model_bridge/main.py`
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/config/config_loader.py`
- Test: `tests/unit/test_session_memory.py` (new)
- Modify: `README.md`

**Step 1: Write the failing tests**
- Add tests for `session_id`-based rolling memory:
  - append summary
  - bounded history
  - expiration/cleanup

**Step 2: Run tests to verify failure**
- Run: `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_session_memory.py'`
- Expected: FAIL (feature missing).

**Step 3: Implement minimal changes**
- Add small in-memory session store with max turns + ttl.
- Add optional `session_id` parameter to unified ask path.

**Step 4: Run tests to verify pass**
- Run targeted tests, then full suite.

**Step 5: Commit**
```bash
git add src/model_bridge/core/session_memory.py src/model_bridge/main.py src/model_bridge/config/default.yaml src/model_bridge/config/config_loader.py tests/unit/test_session_memory.py README.md
git commit -m "feat: add optional session memory for ask continuity"
```

### Task 8: Final Verification and Release Prep

**Files:**
- Modify: `DEVELOPMENT_PLAN.md`
- Modify: `RELEASE_NOTES.md`

**Step 1: Run full validation**
- Run:
  - `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'`
  - `conda run -n model-bridge-mcp_dev pre-commit run --all-files`

**Step 2: Verify backward compatibility**
- Confirm existing tools still work:
  - `ask_chatgpt_cli`
  - `ask_gemini_cli`
  - `ask_ollama`
  - `list_ollama_models`

**Step 3: Update docs/changelog**
- Mark Phase 3 progress in `DEVELOPMENT_PLAN.md`.
- Add release summary in `RELEASE_NOTES.md`.

**Step 4: Commit**
```bash
git add DEVELOPMENT_PLAN.md RELEASE_NOTES.md
git commit -m "docs: record phase3 ask ux and efficiency rollout"
```

