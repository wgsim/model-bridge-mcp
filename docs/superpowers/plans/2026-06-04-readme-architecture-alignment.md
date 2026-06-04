# README / Architecture Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `README.md` and `docs/ARCHITECTURE.md` with the current codebase so README stays concise and `docs/ARCHITECTURE.md` remains the single authoritative architecture reference.

**Architecture:** Treat this as documentation-boundary work, not code work. `README.md` should remain a short entry point that links to the architecture reference, while `docs/ARCHITECTURE.md` absorbs the detailed structural updates, especially around adapter/runtime responsibility and the recent env discovery / preflight behavior.

**Tech Stack:** Markdown, git, ripgrep, repository docs (`README.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`).

---

## File map

- `README.md`
  - Operator-facing repository entry point
  - Should keep only a compact architecture pointer and quick subsystem map
- `docs/ARCHITECTURE.md`
  - Single source of truth for system structure and runtime layering
  - Should carry the detailed explanation of adapter/runtime/env discovery responsibilities
- `CLAUDE.md`
  - Reference only for consistency checks; no planned edits in this plan

---

### Task 1: Keep README architecture-light and current

**Files:**
- Modify: `README.md:5-16`
- Verify: `README.md`

- [ ] **Step 1: Replace the current architecture section with the approved compact shape**

Edit `README.md` so the `## Architecture` section reads exactly as follows:

```md
## Architecture
A dedicated architecture reference lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Quick map:
```text
src/model_bridge/main.py
  -> config/            # config loading and runtime defaults
  -> core/              # routing, failover, caching, response shaping
  -> adapters/          # subprocess / SDK execution backends
  -> plugins/           # provider extension surface
  -> security/          # prompt and file/path safety checks
```
```

- [ ] **Step 2: Verify the README architecture section is concise and does not duplicate the full architecture doc**

Run:

```bash
rg -n "^## Architecture|docs/ARCHITECTURE.md|Quick map:" README.md
```

Expected:

```text
The README contains a single short Architecture section with the docs/ARCHITECTURE.md link and the compact quick map.
```

- [ ] **Step 3: Commit the README-only architecture boundary update**

```bash
git add README.md
git commit -m "docs: keep README architecture overview concise"
```

---

### Task 2: Create the architecture reference from committed state and align it to the current implementation

**Files:**
- Create: `docs/ARCHITECTURE.md`
- Verify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Create the full `docs/ARCHITECTURE.md` file from scratch**

Create `docs/ARCHITECTURE.md` with this exact content:

```md
# Architecture

This document is the repository's high-level architecture reference for `model-bridge-mcp`.

## Purpose

`model-bridge-mcp` is a modular MCP server that routes model-provider requests across CLI and SDK backends with failover, caching, rate limiting, and security checks.

## Top-level structure

```text
model-bridge-mcp/
├── src/model_bridge/
│   ├── main.py                  # MCP entrypoint and public tool surface
│   ├── runtime.py               # Runtime dependency container
│   ├── adapters/                # Execution backends (subprocess / SDK)
│   ├── config/                  # Default config + loader for local overrides
│   ├── core/                    # Routing, failover, caching, tracking, response logic
│   ├── plugins/                 # Provider plugin interfaces and extension points
│   └── security/                # Prompt and file/path safety checks
├── tests/
│   ├── integration/             # Tool-level and end-to-end-ish coverage
│   └── unit/                    # Narrow subsystem coverage
├── docs/                        # Plans, guides, and architecture docs
├── environment/                 # Checked-in development environment snapshots
├── schemas/                     # JSON schema artifacts
└── archive/                     # Historical reference only
```

## Runtime layers

### 1. Entry and tool layer

- `src/model_bridge/main.py`
- Registers the MCP tool surface (`ask_*`, `ask`, `ask_batch`, health and inventory helpers).
- Normalizes user-facing options, builds provider handlers, and coordinates response finalization.

### 2. Runtime assembly layer

- `src/model_bridge/main.py`
- `src/model_bridge/runtime.py`
- `src/model_bridge/config/config_loader.py`
- `src/model_bridge/config/default.yaml`
- `main.py` lazily assembles runtime dependencies through `build_runtime()` / `_ensure_runtime()`.
- `runtime.py` defines the runtime dependency container.
- `config_loader.py` and `default.yaml` provide packaged configuration plus machine-local override loading from `~/.model_bridge/local.yaml`.

### 3. Core orchestration layer

- `src/model_bridge/core/provider_registry.py`
- `src/model_bridge/core/plugin_loader.py`
- `src/model_bridge/core/failover_manager.py`
- `src/model_bridge/core/batch_executor.py`
- `src/model_bridge/core/prompt_cache.py`
- `src/model_bridge/core/session_memory.py`
- `src/model_bridge/core/rate_limiter.py`
- `src/model_bridge/core/task_tracker.py`
- `src/model_bridge/core/response.py`
- `src/model_bridge/core/streaming.py`
- Owns request routing, provider capability checks, plugin discovery, failover, prompt/session caching, batch execution, response shaping, and streaming/task lifecycle support.

### 4. Execution backend layer

- `src/model_bridge/adapters/factory.py`
- `src/model_bridge/adapters/subprocess_adapter.py`
- `src/model_bridge/adapters/sdk_adapter.py`
- Selects the transport implementation from `runtime.transport_mode`.
- Owns provider execution details such as subprocess invocation, SDK invocation, CLI/path discovery, and provider environment-variable discovery / preflight behavior.
- Keeps provider execution details out of the tool registration layer.

### 5. Security layer

- `src/model_bridge/security/sanitizer.py`
- Enforces prompt blocking rules, sensitive path protections, and output-destination safety before execution or file save behavior proceeds.

### 6. Extension layer

- `src/model_bridge/plugins/base.py`
- `src/model_bridge/plugins/`
- Defines the provider plugin contract and plugin discovery surface for external providers.
- Plugin-specific guidance lives in `docs/PLUGIN_GUIDE.md`.

### 7. Verification layer

- `tests/unit/`
- `tests/integration/`
- Unit tests cover focused subsystem behavior such as routing helpers, adapter behavior, response shaping, and command-construction logic.
- Integration tests verify public MCP tool behavior and higher-level runtime flows.
- Changes around env discovery / preflight should keep deterministic unit coverage separate from broader runtime-shell behavior checks.

## Request flow

Typical request flow for a tool call:

```text
MCP client
  -> src/model_bridge/main.py
    -> config loader + runtime bootstrap
    -> provider registry / plugin loader
    -> failover manager
    -> adapter factory-selected backend
    -> subprocess or SDK provider execution
    -> response formatting / save handling
```

## Key architectural boundaries

- **Tool surface vs execution**: `main.py` exposes tools; adapters execute providers.
- **Routing vs transport**: `core/` decides how a request should run; `adapters/` decide how it actually runs.
- **Config vs local environment**: checked-in defaults live under `src/model_bridge/config/`; machine-specific secrets and paths belong in `~/.model_bridge/local.yaml`.
- **Security as a gate**: sanitizer checks happen before execution and before persisted output handling.
- **Plugins as extensions**: new providers should integrate through the plugin and provider-registry surfaces rather than by growing ad hoc branching in tool entrypoints.
- **Env discovery / preflight as execution concerns**: login-shell env discovery, subprocess command construction, and provider preflight behavior belong to the adapter/runtime execution boundary, not the public tool-surface layer.

## Related documents

- `README.md` - setup, usage, and operator-facing overview
- `CLAUDE.md` - repository guidance for Claude Code contributors
- `docs/PLUGIN_GUIDE.md` - plugin authoring details
- `docs/plans/` - implementation and design plans for major architectural changes
```

- [ ] **Step 2: Verify the newly created architecture file contains the expected sections and key body markers**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path('docs/ARCHITECTURE.md').read_text()
markers = [
    '## Top-level structure',
    '## Runtime layers',
    '### 4. Execution backend layer',
    '### 7. Verification layer',
    '## Key architectural boundaries',
    'main.py` lazily assembles runtime dependencies',
    'provider environment-variable discovery / preflight behavior',
    'deterministic unit coverage separate from broader runtime-shell behavior checks',
    'Env discovery / preflight as execution concerns',
]
missing = [marker for marker in markers if marker not in text]
for marker in markers:
    print(marker, '->', marker in text)
if missing:
    raise SystemExit(f'Missing architecture markers: {missing}')
PY
```

Expected:

```text
All headings and key body markers print as True, and the command exits 0.
```

- [ ] **Step 3: Commit the architecture-reference alignment**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: align architecture reference with current layers"
```

---

### Task 3: Run a documentation consistency pass across README and ARCHITECTURE

**Files:**
- Modify: `README.md` if wording drift remains
- Modify: `docs/ARCHITECTURE.md` if wording drift remains
- Verify: `README.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`

- [ ] **Step 1: Compare README, ARCHITECTURE, and CLAUDE using a targeted multi-file consistency check**

Run:

```bash
python - <<'PY'
from pathlib import Path

readme = Path('README.md').read_text().splitlines()
arch = Path('docs/ARCHITECTURE.md').read_text()
claude = Path('CLAUDE.md').read_text()

in_section = False
print('== README Architecture section ==')
for line in readme:
    if line.startswith('## '):
        in_section = line == '## Architecture'
    if in_section:
        print(line)

print('\n== ARCHITECTURE markers ==')
for marker in [
    '## Runtime layers',
    '### 4. Execution backend layer',
    '## Key architectural boundaries',
]:
    print(marker, '->', marker in arch)

print('\n== CLAUDE markers ==')
for marker in [
    '## High-level architecture',
    'src/model_bridge/adapters/',
    'src/model_bridge/security/',
]:
    print(marker, '->', marker in claude)
PY
```

Expected:

```text
The README Architecture section stays compact, docs/ARCHITECTURE.md contains the detailed runtime/layer markers, and CLAUDE.md still contains contributor-facing high-level architecture guidance.
```

- [ ] **Step 2: Inspect documentation-scoped status and a combined diff, while tolerating unrelated local changes elsewhere**

Run:

```bash
git status --short -- README.md docs/ARCHITECTURE.md
git diff HEAD -- README.md docs/ARCHITECTURE.md
```

Expected:

```text
The scoped status shows README.md and docs/ARCHITECTURE.md when they are the files changed by this documentation alignment work, and the scoped diff shows the exact staged and unstaged content changes in those two files. Unrelated local changes outside those paths do not block this step.
```

- [ ] **Step 3: Run the repository validation gate before finalizing**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'pre-commit run --all-files'
```

Expected:

```text
unit-tests...............................................................Passed
```

- [ ] **Step 4: Commit the final consistency pass if either file changed during review**

If Task 3 required any wording adjustment, commit it separately:

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: finish README and architecture consistency pass"
```

If no additional wording changed after Tasks 1 and 2, skip this step.

---

## Spec coverage check

- **README remains architecture-light:** covered by Task 1
- **ARCHITECTURE becomes the authoritative structural reference:** covered by Task 2
- **Recent env discovery / adapter-layer behavior is reflected at the right level:** covered by Task 2
- **README / ARCHITECTURE role boundaries remain consistent:** covered by Task 3
- **No code changes required:** preserved throughout all tasks

## Guardrails for the implementer

- Do not edit implementation code as part of this work.
- Do not pull detailed plan-history or changelog content into `docs/ARCHITECTURE.md`.
- Keep README concise even if more detail feels useful; put that detail in `docs/ARCHITECTURE.md` instead.
- If a later code change modifies architecture-significant boundaries, update `docs/ARCHITECTURE.md` in the same work item.
