# model-bridge-mcp

This project modularizes the monolithic MCP server from `archive/coder_ai_allocator_v1.0.py` / `archive/coder_ai_allocator_v1.1.py` into the `src/model_bridge` structure.

## Architecture
```text
main.py (MCP tools)
  -> config/config_loader.py
  -> security/sanitizer.py
  -> core/failover_manager.py
  -> adapters/subprocess_adapter.py
```

## Environment
- Standard development environment: `model-bridge-mcp_dev` (conda)
- Environment guide: `ENVIRONMENT.md`
- Environment snapshot: `environment/model-bridge-mcp_dev.yml`

```bash
conda create -n model-bridge-mcp_dev python=3.11 -y
conda activate model-bridge-mcp_dev
python -m pip install mcp PyYAML pytest
```

## Configuration
The default configuration file is `src/model_bridge/config/default.yaml`.

- `commands`: codex/gemini/ollama/claude_code execution and health commands
- `routing.default_chains`: default failover chain per tool
- `models`: default/final-backup ollama models, catalog, aliases, local fallback chain
- `security`: block patterns and sensitive paths
- `runtime.system_suffix`: CLI prompt suffix
- `runtime.apply_system_suffix`: per-service suffix application policy

Config loader verification:
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -m model_bridge.config.config_loader --pretty'
```

## Run
### Import smoke
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -c "from model_bridge.main import mcp; print(type(mcp).__name__)"'
```

Runtime initialization note:
- Runtime dependencies (`config`, `adapter`, `failover`) are initialized lazily on first tool call.
- Importing `model_bridge.main` no longer eagerly loads runtime configuration.

### MCP run
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -m model_bridge.main'
```

## Ollama Model Selection
`ask_ollama` now uses alias-first model resolution.

- Default call: `model="default"`
- Alias examples: `default`, `fast`, `coder`
- Direct model names are allowed only when they exist in `models.ollama_catalog`

Behavior:
- Explicit model request (`model="coder"` etc.) performs local install precheck via `ollama list`.
- If requested model is not installed, it returns:
  - `[MODEL ERROR] ... Install with: ollama pull <model>`
- For `model="default"`, local fallback chain (`models.ollama_local_fallback_chain`) is attempted before cloud fallback.
- For `model="auto"`, alias is selected by lightweight prompt heuristic (`fast`/`coder`/`default`).

## Unified Ask API
You can use the new unified tool:
- `ask(prompt, provider="auto|codex|gemini|ollama|claude_code", model="default|auto|...")`
- For `codex`/`gemini`/`claude_code`, set `model="<provider-model-id>"` to forward model selection to each CLI.
- For `codex`/`gemini`/`claude_code`, model trial policy is:
  - explicit `model` => try that model first, then retry once without `--model`
  - no explicit `model` => try provider catalog models in order, then retry once without `--model`
- Common options across ask tools:
  - `timeout_seconds`
  - `max_output_tokens`
  - `response_format` (`text`/`json`)
  - `verbosity` (`brief`/`normal`/`detailed`)
  - `stream` (fallback chunk mode)
  - `session_id` (for optional session continuity)

Runtime behavior:
- Optional prompt cache (TTL + max entries).
- Optional session memory (TTL + max turns).

## Batch Ask API (MCP-internal Orchestration)
Use `ask_batch(...)` to process multiple prompts in one MCP call.

- `prompts: list[str]` (required)
- `mode: sequential|parallel` (default: `sequential`)
- `max_concurrency` (used when `mode=parallel`)
- Reuses existing ask options: `provider`, `model`, `force_model`, `timeout_seconds`, `response_format`, `verbosity`, `stream`, `session_id`

`ask_batch` executes within MCP server orchestration, so external client parallelism is not required.

Ollama safety behavior:
- For `provider="ollama"` in `mode="parallel"`, concurrency is automatically clamped by runtime resource guard.
- Default conservative start is `1`.
- Guard uses runtime RAM/VRAM visibility and model memory profile from config:
  - `runtime.ollama_resource_guard_*`
  - `runtime.ollama_model_memory_gb`

## Skill Workflows
This repository now includes workflow-oriented skill definitions under `skills/`.

- `ask-general-workflow`
- `ask-review-workflow`
- `ask-code-writing-workflow`
- `ask-strict-json-workflow`
- `ask-batch-workflow`
- `ask-provider-routing-workflow`

Routing/trigger policy is documented in:
- `docs/skills/skill-routing-spec.md`

## Health Check Example
The current operational health check verifies CLI availability from config.

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python - <<\"PY\"
import shutil
from model_bridge.config.config_loader import load_config
cfg = load_config()
print(\"--- CLI Health Check ---\")
for name in [\"codex\", \"gemini\", \"ollama\", \"claude_code\"]:
    cmd = cfg[\"commands\"][name][\"health\"][0]
    status = \"Online\" if shutil.which(cmd) else \"Offline\"
    print(f\"[{name.capitalize()}]: {status}\")
PY'
```

Example output:
```text
--- CLI Health Check ---
[Codex]: Online
[Gemini]: Online
[Ollama]: Online
[Claude_code]: Online
```

## Routing Log Example
Response format example for `ask_chatgpt_cli(prompt, force_model=True)`:

```text
[Task Execution Failed]
Forced Primary (codex) failed.
Error: <service error>

--- [Routing Log] ---
[1] Primary (codex): Trying...
    [FAILED]
```

Security block example:
```text
[SECURITY BLOCK] Access to critical system path '/etc/' is strictly FORBIDDEN.
```

## Ollama Inventory Tool
The MCP tool `list_ollama_models()` returns both configured and runtime availability info.

Includes:
- `default_model`
- `effective_default`
- `aliases`
- `recommended_aliases`
- `catalog`
- `installed`
- `missing`
- `pull_commands`
- `status` / `error`

JSON output contract:
- `schemas/list_ollama_models.schema.json`
- Unit validation: `tests/unit/test_response_contracts.py`

Example invocation and parsing:
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python - <<\"PY\"
import json
from model_bridge.main import list_ollama_models
payload = json.loads(list_ollama_models())
print(\"status:\", payload[\"status\"])
print(\"effective_default:\", payload[\"effective_default\"])
print(\"installed_count:\", len(payload[\"installed\"]))
print(\"missing:\", payload[\"missing\"])
print(\"pull_commands:\", payload.get(\"pull_commands\", []))
PY'
```

Interpretation guide:
- `status="ok"`: runtime `ollama list` succeeded.
- `status="unavailable"`: local runtime inventory failed; see `error`.
- `missing`: configured models not currently installed.
- `pull_commands`: ready-to-run install commands for missing models.

## Provider Model Inventory Tool
Use `list_provider_models(provider="all|codex|gemini|ollama|claude_code")` to inspect model options per provider.

- `ollama`: dynamic runtime inventory (`installed`, `missing`, `pull_commands`).
- `codex/gemini/claude_code`: config-based catalog from:
  - `models.codex_model_catalog`
  - `models.gemini_model_catalog`
  - `models.claude_code_model_catalog`
- Each non-ollama provider includes `model_flag="--model"` and configured command metadata.
- Current default catalogs:
  - `codex`: `gpt-5.1-codex-mini`, `gpt-5.1-codex-max`, `gpt-5.2`, `gpt-5.2-codex`, `gpt-5.3-codex`
  - `gemini`: `gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-flash-preview`, `gemini-3-pro-preview`
  - `claude_code`: `haiku`, `sonnet`, `opus`
- Note: some Gemini preview models may require additional internal flags/account enablement.

## Orchestrator Capability Tool
Use `list_orchestrator_capabilities()` to inspect external orchestrator assumptions and the recommended execution policy.

- Recommended default: one MCP call + internal fan-out via `ask_batch(mode="parallel")`
- Capability matrix included for:
  - `codex`
  - `gemini`
  - `claude_code`
- Fallback rule:
  - if external parallel behavior is uncertain, use MCP-internal parallel orchestration

## Runtime Resource Tool
Use `list_runtime_resources(model=\"default\", requested_max_concurrency=1)` to inspect runtime resource snapshot and ollama concurrency recommendation.

- Returns:
  - `ram_total_gb`, `ram_free_gb`
  - `vram_total_gb`, `vram_free_gb`, `vram_detector`
  - `ollama_recommendation.applied_max_concurrency`

Telemetry note:
- `model_bridge.telemetry` logs structured events to stderr.
- Current fields include `request_id`, `routing_tier`, `status`, `error_category`, and `latency_ms`.

## Security Boundaries
- Destructive pattern blocking (`rm -rf`, `mkfs`, `dd if=`, `chmod 777`, fork bomb)
- Sensitive system path access blocking (`/etc/`, `/var/`, `/boot/`, `/proc/`, `/root/`)
- Restricted save destinations (`/etc`, `/var`, `/usr`, `/bin`, `/sbin`, `/root`)

## Tests
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'
```

Integration smoke coverage:
- `tests/integration/test_tool_smoke.py`
- verifies `ask_chatgpt_cli`, `ask_gemini_cli`, `ask_claude_code`, `ask_ollama`, and `list_ollama_models` entrypoint paths with minimal mocks.

## Migration Note
- Legacy source:
  - `archive/coder_ai_allocator_v1.0.py`
  - `archive/coder_ai_allocator_v1.1.py`
- New entrypoint:
  - `src/model_bridge/main.py`
- Existing tool signatures are preserved:
  - `ask_chatgpt_cli(prompt, save_path=None, force_model=False, model=None)`
  - `ask_gemini_cli(prompt, save_path=None, force_model=False, model=None)`
  - `ask_claude_code(prompt, save_path=None, force_model=False, model=None)`
  - `ask_ollama(prompt, save_path=None, model=\"default\")`
