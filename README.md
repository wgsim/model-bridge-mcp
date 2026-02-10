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

- `commands`: codex/gemini/ollama execution and health commands
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

## Health Check Example
The current operational health check verifies CLI availability from config.

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python - <<\"PY\"
import shutil
from model_bridge.config.config_loader import load_config
cfg = load_config()
print(\"--- CLI Health Check ---\")
for name in [\"codex\", \"gemini\", \"ollama\"]:
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

## Security Boundaries
- Destructive pattern blocking (`rm -rf`, `mkfs`, `dd if=`, `chmod 777`, fork bomb)
- Sensitive system path access blocking (`/etc/`, `/var/`, `/boot/`, `/proc/`, `/root/`)
- Restricted save destinations (`/etc`, `/var`, `/usr`, `/bin`, `/sbin`, `/root`)

## Tests
```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit'
```

## Migration Note
- Legacy source:
  - `archive/coder_ai_allocator_v1.0.py`
  - `archive/coder_ai_allocator_v1.1.py`
- New entrypoint:
  - `src/model_bridge/main.py`
- Existing tool signatures are preserved:
  - `ask_chatgpt_cli(prompt, save_path=None, force_model=False)`
  - `ask_gemini_cli(prompt, save_path=None, force_model=False)`
  - `ask_ollama(prompt, save_path=None, model=\"default\")`
