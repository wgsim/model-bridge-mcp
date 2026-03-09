# Claude 4.6 Effort Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Claude 4.6 reasoning-effort support to `claude_code` with guardrails that reflect current Opus 4.6 / Sonnet 4.6 capabilities while keeping the external MCP option name stable.

**Architecture:** Reuse the external `reasoning_effort` option, but map it internally to Anthropic-specific surfaces. Introduce a Claude capability table keyed by alias/full model name, validate requested effort before execution and fallback selection, forward to subprocess as `claude --effort <level>`, and forward to sdk as Anthropic `output_config.effort` plus the appropriate `thinking` shape for 4.6 models.

**Tech Stack:** Python, pytest, MCP tool wrappers, Claude Code CLI, Anthropic Messages API integration

---

### Task 1: Add failing tests first

**Files:**
- Modify: `tests/unit/test_main_ask_options.py`
- Modify: `tests/unit/test_sdk_adapter.py`
- Modify: `tests/unit/test_subprocess_adapter.py`

**Step 1: Add ask-layer Claude validation tests**

Cover:
- accepted `reasoning_effort` for `sonnet` and `opus`
- rejection for `haiku`
- rejection for unsupported Claude effort levels per model
- filtering of incompatible Claude fallback candidates

**Step 2: Add subprocess forwarding tests**

Verify `claude_code` rewrites/forwards to `--effort <level>` without changing non-Claude providers.

**Step 3: Add sdk forwarding tests**

Verify Anthropic sdk payload includes:
- `output_config.effort`
- `thinking={"type":"adaptive"}` for Claude 4.6 aliases
- no effort/thinking additions when `reasoning_effort` is omitted

### Task 2: Implement Claude capability guardrails

**Files:**
- Create: `src/model_bridge/core/claude_capabilities.py`
- Modify: `src/model_bridge/main.py`

**Step 1: Add a Claude 4.6 capability table**

Model assumptions for this phase:
- `opus` alias => `Claude Opus 4.6`
- `sonnet` alias => `Claude Sonnet 4.6`
- `haiku` => effort unsupported

Represent per-model supported effort levels and the sdk `thinking` mode to send.

**Step 2: Extend ask-layer validation**

Allow `reasoning_effort` for `claude_code` as well as `codex`. Validate explicit model overrides, skip incompatible catalog candidates, and keep provider-specific handling isolated.

### Task 3: Implement transport-specific Claude mapping

**Files:**
- Modify: `src/model_bridge/adapters/sdk_adapter.py`
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`

**Step 1: Subprocess mapping**

Map MCP `reasoning_effort` to CLI `--effort <level>` for `claude_code`.

**Step 2: SDK mapping**

Map MCP `reasoning_effort` to Anthropic payload:
- `output_config.effort = <level>`
- `thinking = {"type": "adaptive"}` for Claude 4.6 aliases

### Task 4: Update docs and verify

**Files:**
- Modify: `README.md`

**Step 1: Update public docs**

Document that `reasoning_effort` is now supported for:
- Codex
- Claude Code (`claude_code`)

Include current Claude 4.6 model-specific support notes.

**Step 2: Run verification**

Run:
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_main_ask_options.py -q`
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_sdk_adapter.py -q`
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_subprocess_adapter.py -q`
- `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'`

Expected: all pass.
