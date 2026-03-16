# Contributing

## Development Setup

Use the documented conda environment:

```bash
conda create -n model-bridge-mcp_dev python=3.11 -y
conda activate model-bridge-mcp_dev
python -m pip install -e ".[dev]" pytest pre-commit
```

## Local Validation

Run the same checks used by the repository before opening a change:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'
conda run -n model-bridge-mcp_dev pre-commit run --all-files
```

## Change Scope

- Keep diffs focused and minimal.
- Update documentation when behavior or configuration changes.
- Do not commit secrets, local machine paths, or environment-specific credentials.

## Pull Requests

- Describe the intent of the change clearly.
- Link related issues when applicable.
- Include validation details for code or configuration changes.
- Prefer small pull requests over large refactors.
