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

- [ ] **Step 1: Create `docs/ARCHITECTURE.md` with the approved top-level structure section**

Create `docs/ARCHITECTURE.md` and ensure its `## Top-level structure` block includes this exact structure:

```md
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
```

- [ ] **Step 2: Add the execution backend section with env discovery / preflight responsibilities**

Add the following content under `### 4. Execution backend layer`:

```md
### 4. Execution backend layer

- `src/model_bridge/adapters/factory.py`
- `src/model_bridge/adapters/subprocess_adapter.py`
- `src/model_bridge/adapters/sdk_adapter.py`
- Selects the transport implementation from `runtime.transport_mode`.
- Owns provider execution details such as subprocess invocation, SDK invocation, CLI/path discovery, and provider environment-variable discovery / preflight behavior.
- Keeps provider execution details out of the tool registration layer.
```

- [ ] **Step 3: Add the verification layer so unit and integration responsibilities stay at the right altitude**

Add the following content under `### 7. Verification layer`:

```md
### 7. Verification layer

- `tests/unit/`
- `tests/integration/`
- Unit tests cover focused subsystem behavior such as routing helpers, adapter behavior, response shaping, and command-construction logic.
- Integration tests verify public MCP tool behavior and higher-level runtime flows.
- Changes around env discovery / preflight should keep deterministic unit coverage separate from broader runtime-shell behavior checks.
```

- [ ] **Step 4: Add the architectural boundaries section to place env discovery at the adapter/runtime boundary**

Add the following boundary section:

```md
## Key architectural boundaries

- **Tool surface vs execution**: `main.py` exposes tools; adapters execute providers.
- **Routing vs transport**: `core/` decides how a request should run; `adapters/` decide how it actually runs.
- **Config vs local environment**: checked-in defaults live under `src/model_bridge/config/`; machine-specific secrets and paths belong in `~/.model_bridge/local.yaml`.
- **Security as a gate**: sanitizer checks happen before execution and before persisted output handling.
- **Plugins as extensions**: new providers should integrate through the plugin and provider-registry surfaces rather than by growing ad hoc branching in tool entrypoints.
- **Env discovery / preflight as execution concerns**: login-shell env discovery, subprocess command construction, and provider preflight behavior belong to the adapter/runtime execution boundary, not the public tool-surface layer.
```

- [ ] **Step 5: Commit the architecture-reference alignment**

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

- [ ] **Step 1: Compare the two docs using a section-scoped check for README’s `## Architecture` block**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path('README.md').read_text().splitlines()
in_section = False
for line in text:
    if line.startswith('## '):
        in_section = line == '## Architecture'
    if in_section:
        print(line)
PY
```

Expected:

```text
The README Architecture block contains only the short link sentence and the compact quick map, while deeper structural detail lives in docs/ARCHITECTURE.md.
```

- [ ] **Step 2: Inspect the whole working tree for doc-only scope**

Run:

```bash
git status --short
```

Expected:

```text
Only README.md and docs/ARCHITECTURE.md appear as working-tree changes for this documentation alignment work.
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
