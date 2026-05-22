# Goal: Add agy CLI provider to model-bridge-mcp

Integrating `agy CLI` as a native, fully routed and failover-enabled CLI provider within the `model-bridge-mcp` package. This allows delegating prompts to the `agy` CLI using the `ask_agy_cli` tool or through universal `ask` routing.

## User Review Required

> [!IMPORTANT]
> The `agy` CLI binary must be globally executable on the user's path (discovered at `/Users/woogwangsim/.local/bin/agy`), or configured in the `commands.agy.exec` section in local overrides to allow proper execution.

## Design Decisions (Resolved)

1. **CLI Execution Option**:
   - `exec: ["agy", "-p", "--dangerously-skip-permissions"]`
   - By specifying `-p` (print mode) and `--dangerously-skip-permissions`, the `agy` CLI will run completely non-interactively without prompt hang-ups.
2. **Model Catalog**:
   - Set to `["default"]` under `models:`.

## Proposed Changes

### Configuration Layer

#### [MODIFY] [default.yaml](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/config/default.yaml)
- Add `agy` to command registry with health probe and prompt exec flags (`["agy", "-p", "--dangerously-skip-permissions"]`).
- Add `ask_agy_cli` under `routing.default_chains`.
- Add `agy_model_catalog` under `models:`.
- Add `agy: false` to `runtime.apply_system_suffix`.

#### [MODIFY] [config_loader.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/config/config_loader.py)
- Update `CommandsConfig` to include `agy: ServiceCommand | None = None`.
- Update `RoutingChains` and `WeightedRoutingChains` to include `ask_agy_cli`.
- Update `ModelsConfig` to include `agy_model_catalog`.
- Update `RuntimeApplySystemSuffix` to include `agy: bool`.

---

### Core Registry Layer

#### [MODIFY] [provider_registry.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/core/provider_registry.py)
- Register `agy` as a default provider inside `build_default_provider_registry` with `supports_json=True`, `supports_stream=False`, `supports_force_model=True`.

---

### Subprocess Adapter Layer

#### [MODIFY] [subprocess_adapter.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/adapters/subprocess_adapter.py)
- Add `"agy"` hint to `INSTALL_HINTS`.
- Add `agy` to subprocess arguments parsing and flag placement (`-p` flag).

---

### Main Entrypoint & MCP Tool

#### [MODIFY] [main.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/main.py)
- Add `@mcp.tool() async def ask_agy_cli` tool.
- Integrate `agy` into the global provider registries, known provider sets, and option handlers.

---

### Plugin Wrapper Layer

#### [MODIFY] [__init__.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/plugins/builtins/__init__.py)
- Add `AgyPlugin` wrapping `ask_agy_cli` to support plugin-based executions.

---

## Verification Plan

### Automated Tests
- Run unit and integration tests to ensure configuration validation passes and tool registration does not break existing features.
  `pytest tests/unit/test_config_loader.py`
  `pytest tests/unit/test_failover_manager.py`

### Manual Verification
- Execute `agy --version` or basic prompt check to ensure command dispatch works smoothly.
