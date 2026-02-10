# Environment Guide

## Standard Conda Environment
- Environment name: `model-bridge-mcp_dev`
- Python version: `3.11`
- Package snapshot file: `environment/model-bridge-mcp_dev.yml`

## Create / Activate
```bash
conda create -n model-bridge-mcp_dev python=3.11 -y
conda activate model-bridge-mcp_dev
```

## Validate
```bash
conda run -n model-bridge-mcp_dev python -V
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src python -m model_bridge.config.config_loader --pretty'
```

## Recommended Ollama Models
- Policy aliases:
  - `default` -> `gpt-oss:20b`
  - `fast` -> `glm-4.7-flash:Q8_0`
  - `coder` -> `qwen3-coder-next:Q4_K_M`
- Install command example:
```bash
ollama pull gpt-oss:20b
ollama pull glm-4.7-flash:Q8_0
ollama pull qwen3-coder-next:Q4_K_M
```
- Validate installed list:
```bash
ollama list
```

## Update Rule (Mandatory)
- If packages are installed, removed, or updated in `model-bridge-mcp_dev`, update `environment/model-bridge-mcp_dev.yml` in the same change.
- Recommended refresh command:
```bash
conda env export -n model-bridge-mcp_dev > environment/model-bridge-mcp_dev.yml
```
- After refresh, review diff and commit together with the package-change commit.
