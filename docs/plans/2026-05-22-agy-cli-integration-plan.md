# Goal: Add agy CLI provider to model-bridge-mcp

Integrating `agy CLI` as a native, fully routed and failover-enabled CLI provider within the `model-bridge-mcp` package. This allows delegating prompts to the `agy` CLI using the `ask_agy_cli` tool or through universal `ask` routing.

## User Review Required

> [!IMPORTANT]
> The `agy` CLI binary must be globally executable on the user's path (discovered at `/Users/woogwangsim/.local/bin/agy`), or configured in the `commands.agy.exec` section in local overrides to allow proper execution.

## Design Decisions (Resolved)

1. **CLI Execution Option & Flag Order**:
   - `exec: ["agy", "-p", "--dangerously-skip-permissions"]`
   - By specifying `-p` (print mode) and `--dangerously-skip-permissions`, the `agy` CLI runs non-interactively.
   - Note: `-p` / `--print` and `--dangerously-skip-permissions` are boolean flags. The prompt is passed as a trailing positional argument (e.g., `agy -p --dangerously-skip-permissions "prompt"`).
   - *Rationale for `--dangerously-skip-permissions`*: This flag is vital for non-interactive automation. It instructs the `agy` autonomous loop to automatically bypass interactive terminal prompts asking for permissions when launching sub-tasks or tool executions, avoiding deadlocks in MCP execution.

2. **Model Catalog & Override Contract**:
   - Set `agy_model_catalog` to `["default"]` under `models:`.
   - Since `agy` has no model selection flag in its CLI, any non-`default`/`auto` model override passed to `ask(provider="agy", model="...")` will be **explicitly rejected** with a clear error message (`[PROVIDER ERROR] 'agy' does not support model overrides`) to prevent silent misbehavior.
   - This override check is enforced at two distinct validation boundaries: in `ask_agy_cli()` itself and in `_ask_with_failover()` when selecting `agy` as a fallback provider.

3. **JSON Support (`supports_json=False`)**:
   - To avoid downstream parsing errors from agentic CLI outputs, `supports_json` is set to `False` for the `agy` provider since it lacks a native JSON output enforcement flag.

4. **Billing, Quota & Token Cost Warnings for Agentic Loop (Out of Scope for Logic)**:
   - Since `agy` is a fully autonomous agentic CLI, calling it non-interactively via `-p` initiates a complete agentic reasoning and execution loop.
   - This consumes a high volume of input/output tokens, which directly impacts the user's unified Google AI Plan quota (Shared Quota).
   - **Out of Scope**: High-precision token accounting, live quota checks, and programmatic billing limiters inside the `model-bridge-mcp` library are designated as **Out of Scope** to keep the core integration lightweight and avoid high API overhead. We will handle this strictly via user-level awareness warnings in logs and documentation.
   - Per-call timeouts must be significantly higher (recommending >= 300s via `timeout_seconds`).

5. **SDK Transport Isolation (Subprocess Only)**:
   - `agy` CLI has no Python SDK or API binding. 
   - Calling `agy` when `transport_mode == "sdk"` is explicitly rejected with `[PROVIDER ERROR] 'agy' only supports subprocess transport.` at execution time.
   - The validation occurs synchronously inside `ask_agy_cli()` preflight and in `_ask_with_failover()` if `agy` is resolved under SDK transport configs.

6. **Dedicated Timeout Handling (`agy_timeout_seconds`)**:
   - To prevent long-running agentic loops from failing prematurely due to the default `subprocess_timeout_seconds` (120s), we introduce `agy_timeout_seconds: 300` in the configuration.
   - This value is parsed by the loader and applied by the `SubprocessAdapter` when invoking the `agy` binary.

7. **AgyPlugin Design**:
   - The `AgyPlugin` will inherit from the standard plugin loader pattern, wrapping `ask_agy_cli()`. It will respect same parameter checking and reject any custom model overrides or SDK transport settings during plugin loading.

## Proposed Changes

### Configuration Layer

#### [MODIFY] [default.yaml](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/config/default.yaml)
- Add `agy` to command registry with health probe and prompt exec flags (`["agy", "-p", "--dangerously-skip-permissions"]`).
- Add `ask_agy_cli` under `routing.default_chains` (as a fallback option).
- Add `agy_model_catalog` under `models:`.
- Add `agy: false` to `runtime.apply_system_suffix`.
- Add `agy_timeout_seconds: 300` to `runtime:` configuration.

#### [MODIFY] [config_loader.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/config/config_loader.py)
- Update `CommandsConfig` to include `agy: ServiceCommand | None = None`.
- Update `RoutingChains` and `WeightedRoutingChains` to include `ask_agy_cli`.
- Update `ModelsConfig` to include `agy_model_catalog`.
- Update `RuntimeApplySystemSuffix` to include `agy: bool`.
- Update `RuntimeConfig` to include `agy_timeout_seconds: float = Field(default=300.0, gt=0)`.

---

### Core Registry Layer

#### [MODIFY] [provider_registry.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/core/provider_registry.py)
- Register `agy` as a default provider inside `build_default_provider_registry` with `supports_json=False`, `supports_stream=False`, `supports_force_model=True`.

---

### Subprocess Adapter Layer

#### [MODIFY] [subprocess_adapter.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/adapters/subprocess_adapter.py)
- Add `"agy"` hint to `INSTALL_HINTS`.
- Add `agy` to subprocess argument handling. Since `-p`/`--print` in `agy` are boolean flags, the prompt is appended as a positional argument at the end of the argument array.
- Implement specific subprocess timeout mapping: when provider is `agy`, use the configured `agy_timeout_seconds` (default 300.0) instead of the generic `subprocess_timeout_seconds`.

---

### Main Entrypoint & MCP Tool

#### [MODIFY] [main.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/main.py)
- **Tool Definition**: Add `@mcp.tool() async def ask_agy_cli` tool with failover and configuration checks.
- **Provider Registry & Handlers**: Add `"agy"` to the built-in providers set and map it in `_get_provider_handlers()`.
- **Model Override & SDK Transport Validation**:
  - In `ask_agy_cli` and `_ask_with_failover`, explicitly check `model`. If it's not `None`, `"default"`, or `"auto"`, raise `[PROVIDER ERROR] 'agy' does not support model overrides`.
  - In `ask_agy_cli` and `_ask_with_failover`, check `transport_mode`. If `transport_mode == "sdk"`, raise `[PROVIDER ERROR] 'agy' only supports subprocess transport.`.
  - Ensure `_build_provider_args` does not emit model flags for `agy`.
  - Update `_list_static_provider_models` to report `"model_flag": None` when `provider_id == "agy"`.
- **Introspection Surfaces**:
  - Update `list_provider_models()` tool's `allowed` and `targets` lists to include `"agy"`.
  - Update `list_cli_noninteractive_policy()` to include non-interactive CLI details and the `--dangerously-skip-permissions` skip flag for `"agy"`.
  - Update `health_check()` and `_PROVIDER_INSTALL_HINTS` to include `"agy"` check and install hint.
  - Update `_health_entry_from_sdk_preflight()` to set `"auth": "configured"` for `"agy"`.

---

### Plugin Wrapper Layer

#### [MODIFY] [__init__.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/src/model_bridge/plugins/builtins/__init__.py)
- Add `AgyPlugin` wrapping `ask_agy_cli` to support plugin-based executions, asserting transport validation during loading/preflight.

---

### Test Suite & Test Modifications

#### [NEW] [test_agy_provider.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_agy_provider.py)
- Add mock-based unit tests verifying:
  1. Correct subprocess argument formatting for `agy` (positional prompt placement).
  2. Failure handling when `agy` returns a non-zero exit code (capturing stdout/stderr correctly).
  3. Integration into `ProviderRegistry`, correct rejection of non-default model overrides, and correct rejection of SDK transport mode.
  4. Proper application of `agy_timeout_seconds` in adapter subprocess invocation.
  5. Distinction between agy crash (non-zero exit) vs. successful execution with internal warnings on stderr.

#### [MODIFY] [test_main_list_provider_models.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_main_list_provider_models.py)
- Update `_fake_config()` mock to include `agy` exec, `agy_model_catalog` fields, and `agy_timeout_seconds`.
- Update exact-set assertions on provider keys to include `"agy"`.

#### [MODIFY] [test_main_cli_noninteractive_policy.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_main_cli_noninteractive_policy.py)
- Update mock config to include `"agy"` exec command.
- Assert `"agy"`'s noninteractive policy attributes (`--dangerously-skip-permissions` detection).

#### [MODIFY] [test_health_check.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_health_check.py)
- Update list of providers in health assertions to include `"agy"`.

#### [MODIFY] [test_ask_unified_tool.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/integration/test_ask_unified_tool.py)
- Ensure unified provider listings and exact-set assertions include `"agy"`.

#### [MODIFY] [test_config_loader.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_config_loader.py)
- Assert that default yaml loading properly parses new `agy` fields and `agy_timeout_seconds`.

#### [MODIFY] [test_failover_manager.py](file:///Users/woogwangsim/AI_development/model-bridge-mcp/.worktrees/feat-agy-request/tests/unit/test_failover_manager.py)
- Assert that failover routing handles `agy` correctly, gracefully isolating it when transport is SDK or model is overridden.

---

## Verification Plan

### Automated Tests
- Run the new test suite and all modified contract test suites:
  `pytest tests/unit/test_agy_provider.py`
  `pytest tests/unit/test_main_list_provider_models.py`
  `pytest tests/unit/test_main_cli_noninteractive_policy.py`
  `pytest tests/unit/test_health_check.py`
  `pytest tests/integration/test_ask_unified_tool.py`
  `pytest tests/unit/test_config_loader.py`
  `pytest tests/unit/test_failover_manager.py`

### Manual Verification
- Verify `agy` command argument parsing and flag behavior:
  `agy -p --dangerously-skip-permissions "what is 1+1"`
  Assert that the command parses cleanly and triggers non-interactive execution immediately.

