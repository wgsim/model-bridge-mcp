# Architecture

This document is the repository's high-level architecture reference for `model-bridge-mcp`.

## Purpose

`model-bridge-mcp` is a modular MCP server that routes model-provider requests across CLI and SDK backends with failover, caching, rate limiting, and security checks. It is the extracted successor to the legacy monolith preserved under `archive/`.

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
- `src/model_bridge/core/cache/`
- `src/model_bridge/core/prompt_cache.py` (compatibility-focused shim around prompt caching behavior)
- `src/model_bridge/core/session_memory.py`
- `src/model_bridge/core/rate_limiter.py`
- `src/model_bridge/core/task_tracker.py`
- `src/model_bridge/core/response.py`
- `src/model_bridge/core/streaming.py`
- Owns request routing, provider capability checks, plugin discovery, failover, prompt/session caching, batch execution, response shaping, and streaming/task lifecycle support.
- `src/model_bridge/core/cache/` contains backend-oriented cache implementations and factories that are available for broader integration, while the active public request path still uses the prompt-cache wiring described in `main.py` / `prompt_cache.py`.

### 4. Execution backend layer

- `src/model_bridge/adapters/factory.py`
- `src/model_bridge/adapters/subprocess_adapter.py`
- `src/model_bridge/adapters/sdk_adapter.py`
- Selects the transport implementation from `runtime.transport_mode`.
- Owns most provider execution details such as subprocess invocation, SDK invocation, CLI/path discovery, and provider environment-variable discovery behavior.
- Some CLI health/probing logic still lives in `main.py` health tooling, so preflight responsibility is currently split between the adapter layer and the public runtime health surface.
- Keeps provider execution details out of the tool registration layer as much as the current implementation allows.

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
