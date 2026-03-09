# Gemini 3.1 SDK Effort Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update Gemini defaults to `gemini-3.1-pro-preview` and add Gemini 3.x `reasoning_effort` support for sdk transport only, while keeping Gemini 2.5 thinking control unsupported in this MCP.

**Architecture:** Add a Gemini capability table keyed by model name, distinguishing Gemini 3.x `thinkingLevel` support from Gemini 2.5 `thinkingBudget` models. Reuse the external `reasoning_effort` option but map it to Gemini sdk `thinkingConfig.thinkingLevel`. Keep subprocess transport explicitly unsupported for Gemini `reasoning_effort`.

**Tech Stack:** Python, pytest, MCP tool wrappers, Google Gemini API integration, Gemini CLI compatibility constraints

---

### Task 1: Add failing tests first

**Files:**
- Modify: `tests/unit/test_main_ask_options.py`
- Modify: `tests/unit/test_sdk_adapter.py`
- Modify: `tests/unit/test_subprocess_adapter.py`
- Modify: `tests/unit/test_main_list_provider_models.py`

**Step 1: Add Gemini default/catalog tests**

Cover:
- `gemini-3.1-pro-preview` is the first/default Gemini model
- `list_provider_models()` reports the updated Gemini default

**Step 2: Add ask-layer Gemini reasoning tests**

Cover:
- accepted `reasoning_effort` for `gemini-3.1-pro-preview`
- accepted `reasoning_effort` for `gemini-3-flash-preview`
- rejection for Gemini 2.5 models
- subprocess transport rejection for Gemini `reasoning_effort`

**Step 3: Add sdk forwarding tests**

Verify Gemini sdk payload includes `generationConfig.thinkingConfig.thinkingLevel` for Gemini 3.x and omits Gemini 2.5 support.

### Task 2: Implement Gemini capability guardrails

**Files:**
- Create: `src/model_bridge/core/gemini_capabilities.py`
- Modify: `src/model_bridge/main.py`
- Modify: `src/model_bridge/config/default.yaml`

**Step 1: Add Gemini capability matrix**

Represent:
- `gemini-3.1-pro-preview`: `low|high`
- `gemini-3-flash-preview`: `minimal|low|medium|high`
- Gemini 2.5 family: no MCP `reasoning_effort` support

**Step 2: Update Gemini catalog/default**

Change Gemini catalog order to make `gemini-3.1-pro-preview` the default first entry while keeping other supported models behind it.

**Step 3: Extend ask-layer validation**

Allow Gemini `reasoning_effort` only when the active adapter is sdk and the selected model is in the Gemini 3.x capability matrix.

### Task 3: Implement sdk-only Gemini mapping

**Files:**
- Modify: `src/model_bridge/adapters/sdk_adapter.py`
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`

**Step 1: SDK mapping**

Map MCP `reasoning_effort` to Gemini sdk payload:
- `generationConfig.thinkingConfig.thinkingLevel`

**Step 2: Subprocess handling**

Reject Gemini `reasoning_effort` in subprocess transport with a clear error explaining that per-request Gemini thinking control is not supported through the current CLI bridge.

### Task 4: Update docs and verify

**Files:**
- Modify: `README.md`

**Step 1: Document Gemini defaults and limitations**

Document:
- updated Gemini model list/default
- sdk-only reasoning support
- Gemini 2.5 thinking control not supported by this MCP

**Step 2: Run verification**

Run:
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_main_ask_options.py -q`
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_sdk_adapter.py -q`
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_subprocess_adapter.py -q`
- `conda run -n model-bridge-mcp_dev python -m pytest tests/unit/test_main_list_provider_models.py -q`
- `conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'`

Expected: all pass.
