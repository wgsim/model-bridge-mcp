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

## Update Rule (Mandatory)
- If packages are installed, removed, or updated in `model-bridge-mcp_dev`, update `environment/model-bridge-mcp_dev.yml` in the same change.
- Recommended refresh command:
```bash
conda env export -n model-bridge-mcp_dev > environment/model-bridge-mcp_dev.yml
```
- After refresh, review diff and commit together with the package-change commit.

