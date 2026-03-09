# Codex Model And Reasoning Effort Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update Codex model inventory/default selection to use `gpt-5.4` first and add Codex-only `reasoning_effort` validation/forwarding across sdk and subprocess transports.

**Architecture:** Keep the change narrow and Codex-specific. Add a shared Codex capability table for model defaults and supported `reasoning_effort` values, validate requested effort before failover/model trial execution, and forward the normalized value through existing provider argument plumbing into sdk/subprocess adapters.

**Tech Stack:** Python, pytest, MCP tool wrappers, OpenAI Codex CLI/Responses API integration

---

### Task 1: Add Codex behavior tests first

**Files:**
- Modify: `tests/unit/test_main_ask_options.py`
- Modify: `tests/unit/test_sdk_adapter.py`
- Modify: `tests/unit/test_main_list_provider_models.py`
- Modify: `tests/unit/test_adapter_factory.py`

**Step 1: Write failing tests for Codex catalog/default updates**

Add assertions that the default Codex catalog order starts with `gpt-5.4`, that Codex model trials use the updated order, and that sdk fallback resolves to `gpt-5.4`.

**Step 2: Write failing tests for Codex reasoning effort validation**

Add tests covering:
- accepted Codex values for `gpt-5.4`
- rejection when a model does not support `reasoning_effort`
- rejection when a requested value is not supported by the selected Codex model
- pass-through behavior when `reasoning_effort` is omitted

**Step 3: Write failing tests for transport forwarding**

Add tests that verify:
- subprocess provider args include `-c model_reasoning_effort="..."` for Codex only
- sdk Codex payload includes `{"reasoning": {"effort": ...}}`
- Gemini/Claude paths do not gain the new option

### Task 2: Implement Codex capability and routing changes

**Files:**
- Modify: `src/model_bridge/main.py`
- Modify: `src/model_bridge/adapters/sdk_adapter.py`
- Modify: `src/model_bridge/config/default.yaml`

**Step 1: Add a Codex capability table**

Introduce a shared, local mapping for supported Codex models and per-model `reasoning_effort` values. Mark unsupported/unknown combinations explicitly so validation is deterministic.

**Step 2: Update Codex model defaults**

Change the Codex catalog order to:
- `gpt-5.4`
- `gpt-5.3-codex`
- `gpt-5.2-codex`
- `gpt-5.1-codex-max`
- `gpt-5.2`
- `gpt-5.1-codex-mini`

Update sdk fallback default to `gpt-5.4`.

**Step 3: Thread Codex reasoning effort through ask paths**

Add a Codex-only `reasoning_effort` option to `ask_chatgpt_cli` and unified `ask(provider="codex")`. Validate against the resolved/requested Codex model set before execution, skip incompatible fallback candidates, and forward the normalized option to the active transport.

### Task 3: Update user-facing docs and inventories

**Files:**
- Modify: `README.md`

**Step 1: Update model inventory docs**

Refresh Codex model lists and default-model wording to match the new catalog/default behavior.

**Step 2: Document Codex reasoning effort support**

Document that `reasoning_effort` is currently Codex-only, note transport behavior, and describe validation/error expectations.

### Task 4: Verify targeted behavior

**Files:**
- Test: `tests/unit/test_main_ask_options.py`
- Test: `tests/unit/test_sdk_adapter.py`
- Test: `tests/unit/test_main_list_provider_models.py`
- Test: `tests/unit/test_adapter_factory.py`

**Step 1: Run targeted pytest commands**

Run:
- `pytest tests/unit/test_main_ask_options.py -q`
- `pytest tests/unit/test_sdk_adapter.py -q`
- `pytest tests/unit/test_main_list_provider_models.py -q`
- `pytest tests/unit/test_adapter_factory.py -q`

Expected: all targeted tests pass.

**Step 2: Run any configured pre-hook equivalent if present**

Inspect repository hooks/config and run the relevant project verification command before declaring completion.
