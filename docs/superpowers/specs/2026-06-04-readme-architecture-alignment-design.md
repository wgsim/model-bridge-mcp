# README / Architecture Alignment Design

## Goal

Bring `README.md` and `docs/ARCHITECTURE.md` into a consistent, current state after the recent CI env discovery stabilization work, while keeping each document focused on a distinct audience and purpose.

## Problem statement

The repository currently has two documentation changes in progress:

- `README.md` now links to `docs/ARCHITECTURE.md` and includes a compact architecture quick map.
- `docs/ARCHITECTURE.md` exists as a new high-level architecture reference.

The remaining work is not to invent a new documentation system, but to finish aligning both files with the actual codebase and with each other.

Without an explicit design, the likely failure modes are:

1. `README.md` grows into a second detailed architecture document
2. `docs/ARCHITECTURE.md` drifts from current implementation boundaries
3. recent implementation changes (especially around env discovery, adapter/runtime boundaries, and test responsibilities) are not reflected clearly enough
4. the roles of `README.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, and `docs/PLUGIN_GUIDE.md` become blurred

## Decision

Use a **README-light / ARCHITECTURE-authoritative** model.

- `README.md` remains the operator-facing entry point and should only carry a compact architecture overview plus a link to the dedicated architecture document.
- `docs/ARCHITECTURE.md` becomes the single repository-level source of truth for system structure, runtime layers, request flow, and architectural boundaries.

## Scope

### In scope

- update `README.md` architecture wording only as needed to keep it accurate and concise
- update `docs/ARCHITECTURE.md` so it matches the current repository structure and recent implementation changes
- ensure the architecture document reflects current responsibilities in:
  - `main.py`
  - `runtime.py`
  - `config/`
  - `core/`
  - `adapters/`
  - `plugins/`
  - `security/`
  - `tests/`
- explicitly place recent env discovery / preflight behavior in the correct architectural layer
- keep document boundaries consistent with existing repo docs

### Out of scope

- code changes
- shell command redesign work
- major rewrite of `docs/PLUGIN_GUIDE.md`
- major rewrite of `CLAUDE.md`
- broader documentation IA reorganization beyond these two files

## Recommended approach

### 1. Keep README shallow

`README.md` should:

- retain a short `Architecture` section
- point readers to `docs/ARCHITECTURE.md`
- include only a compact quick map of the main subsystems
- avoid repeating the full layered explanation, request-flow explanation, and boundary notes already covered in `docs/ARCHITECTURE.md`

The README should answer:

- what this repo is
- where the main architecture reference lives
- roughly which major code areas exist

It should not try to become the full design reference.

### 2. Make ARCHITECTURE.md the single structural reference

`docs/ARCHITECTURE.md` should be the only place that fully explains:

- top-level repository structure
- runtime layers and their responsibilities
- request flow through the system
- architectural boundaries and separation of concerns
- how execution, configuration, plugins, and safety checks fit together

This file should reflect the current codebase, not historical plans.

### 3. Explicitly capture recent CI/env discovery learnings at the architecture level

The recent CI stabilization work highlighted a concrete architectural boundary worth documenting:

- env discovery and CLI preflight behavior belong to the **adapter/runtime execution layer**, not the tool-surface layer
- tests around that behavior should distinguish between:
  - deterministic unit coverage
  - command-construction logic
  - runtime shell behavior

The architecture doc does not need to include test-case details, but it should make the responsibility boundary clear enough that future changes land in the right layer.

## Alternatives considered

### Option A — README-light + ARCHITECTURE-authoritative (recommended)

**Pros**
- one clear source of truth for architecture
- lower drift risk
- keeps README readable for first-time users
- easier to maintain over time

**Cons**
- readers wanting deep structure must click into another document

### Option B — keep both README and ARCHITECTURE detailed

**Pros**
- architecture context visible in more places
- README-only readers get more detail immediately

**Cons**
- duplicate maintenance burden
- much higher drift risk
- more chances for contradictory wording

### Option C — move most architecture content back into README

**Pros**
- one fewer document to maintain

**Cons**
- README becomes overloaded
- structural reference is harder to keep concise
- less clean separation between usage/onboarding vs. architecture reference

## File responsibilities after alignment

### `README.md`

Primary audience:
- users, operators, contributors scanning the repository quickly

Responsibility:
- concise product/repo overview
- setup and usage entry point
- short architecture summary and pointer to the full architecture doc

### `docs/ARCHITECTURE.md`

Primary audience:
- contributors who need structural understanding before modifying the system

Responsibility:
- repository-wide structure
- runtime layering
- request flow
- subsystem boundaries
- relationship between configuration, routing, execution backends, plugins, and safety checks

### `CLAUDE.md`

Primary audience:
- Claude Code / agent contributors

Responsibility:
- implementation guidance, workflows, operational notes, commands
- not the canonical public architecture document

### `docs/PLUGIN_GUIDE.md`

Primary audience:
- plugin authors

Responsibility:
- plugin-specific extension behavior only
- not the whole-system architecture reference

## Proposed edits

### README.md

Keep or refine the current compact architecture section so it remains:

- accurate
- brief
- linked to `docs/ARCHITECTURE.md`

Expected shape:
- one sentence pointing to the dedicated architecture doc
- one compact tree-style quick map of major subsystems

### docs/ARCHITECTURE.md

Review and adjust:

1. **Top-level structure**
   - ensure it still reflects the checked-in directories that matter architecturally
2. **Runtime layers**
   - verify each layer description matches real code ownership
3. **Execution/backend responsibilities**
   - clarify that adapter/runtime behavior includes env discovery and subprocess execution details
4. **Verification layer**
   - keep tests described at the right altitude: unit vs integration responsibilities, not test-by-test detail
5. **Architectural boundaries**
   - ensure the separation between tool surface, orchestration, transport, security, and plugin extension points is current

## Validation criteria

This work is complete when:

- `README.md` and `docs/ARCHITECTURE.md` do not materially contradict each other
- `README.md` remains concise and architecture-light
- `docs/ARCHITECTURE.md` is the clear single source of truth for architecture
- the architecture doc accurately reflects the current code structure and recent env discovery / adapter-layer behavior
- no code changes are required

## Risks

### Risk: README becomes too detailed again

Mitigation:
- treat README as a navigational and onboarding document, not the structural reference

### Risk: architecture doc starts duplicating low-level plan details

Mitigation:
- document subsystem responsibilities and boundaries, not implementation-task history

### Risk: recent changes are documented too specifically

Mitigation:
- mention env discovery / preflight behavior only at the layer/responsibility level, not as a changelog

## Implementation note

The follow-up implementation plan should be documentation-only and should preserve the rule that architecture-significant code changes require `docs/ARCHITECTURE.md` review/update in the same work item.
