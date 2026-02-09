# model-bridge-mcp

This project modularizes the monolithic MCP server from `coder_ai_allocator_v1.0.py` / `coder_ai_allocator_v1.1.py` into the `src/model_bridge` structure.

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
- `models`: default/final-backup ollama models
- `security`: block patterns and sensitive paths
- `runtime.system_suffix`: CLI prompt suffix

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
  - `coder_ai_allocator_v1.0.py`
  - `coder_ai_allocator_v1.1.py`
- New entrypoint:
  - `src/model_bridge/main.py`
- Existing tool signatures are preserved:
  - `ask_chatgpt_cli(prompt, save_path=None, force_model=False)`
  - `ask_gemini_cli(prompt, save_path=None, force_model=False)`
  - `ask_ollama(prompt, save_path=None, model=\"llama3.2\")`
