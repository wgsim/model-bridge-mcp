# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Repository purpose

`model-bridge-mcp` is a modular MCP server that routes model-provider requests across CLI and SDK backends with failover, caching, and security gating. The current package is the extracted successor to the legacy monolith in `archive/`.

## High-level architecture

- `src/model_bridge/main.py` is the MCP entrypoint. It registers the public tool surface (`ask_*`, `ask`, `ask_batch`, health/listing utilities) and lazily assembles runtime dependencies.
- `src/model_bridge/config/` loads packaged YAML config from `default.yaml` and merges machine-local overrides from `~/.model_bridge/local.yaml`.
- `src/model_bridge/core/` contains the runtime orchestration pieces:
  - provider routing / failover
  - provider registry and plugin loading
  - prompt cache and session memory
  - rate limiting, task tracking, health / inventory helpers
  - response formatting and save/debug metadata handling
- `src/model_bridge/adapters/` isolates execution backends. The factory selects subprocess vs SDK adapters so provider-specific execution stays out of the tool layer.
- `src/model_bridge/security/` contains the sanitizer and path/pattern checks that block unsafe prompts and destinations before execution.
- `src/model_bridge/plugins/` is the extension surface for built-in and user provider plugins.
- `tests/unit/` holds narrow behavior tests; `tests/integration/` covers smoke paths and end-to-end-ish tool behavior.
- `archive/` is historical reference only; do not treat it as the source of truth for current behavior.

## Common commands

Assumption: this repo does not define a dedicated build wrapper. Use standard Python packaging tooling when you need artifacts.

### Environment setup

```bash
conda create -n model-bridge-mcp_dev python=3.11 -y
conda activate model-bridge-mcp_dev
python -m pip install -e ".[dev]" pytest pre-commit
```

### Run the app

Source checkout form:

```bash
PYTHONPATH=src python -m model_bridge.main
```

Installed console-script form (after `python -m pip install -e .`):

```bash
model-bridge
```

### Import smoke

```bash
PYTHONPATH=src python -c "from model_bridge.main import mcp; print(type(mcp).__name__)"
```

### Tests

Run the full suite:

```bash
PYTHONPATH=src pytest -q tests
```

Run unit tests only:

```bash
PYTHONPATH=src pytest -q tests/unit
```

Run a single test by node id:

```bash
PYTHONPATH=src pytest -q tests/unit/test_main_helpers.py::test_save_to_file_writes_relative_path_under_output_root
```

### Quality gate / linting

The repository's configured hook check is:

```bash
pre-commit run --all-files
```

CI runs the same test command plus pre-commit. There is no separate ruff/mypy target configured in the repo at the moment.

### Build artifacts

Use the standard packaging command if you need a wheel or sdist:

```bash
python -m build
```

## Repo-specific operational notes

- The checked-in development environment is Python 3.11 (`ENVIRONMENT.md` and `environment/model-bridge-mcp_dev.yml` are the reference). `pyproject.toml` allows Python `>=3.10`, but CI and the documented dev env use 3.11.
- If installed dependencies change in the dev environment, refresh `environment/model-bridge-mcp_dev.yml` in the same change.
- Response saves are written under `.model_bridge/outputs`, and debug metadata is written under `.model_bridge/debug_meta`. Keep the reported destination strings aligned with those real persisted locations.
- `save_path` and output handling are security-sensitive: the sanitizer and save helpers deliberately reject protected system paths and symlink tricks.
- `README.md`, `CONTRIBUTING.md`, and `ENVIRONMENT.md` contain the project-specific setup and operational details that should stay in sync with implementation changes.
- Local artifact roots such as `.cross_audit/`, `.serena/`, `.review_runtime*/`, `.review_runtime_abs/`, `.antigravitycli/`, and `.claude/worktrees/` are intentionally untracked; treat them as disposable local state unless a task explicitly says to preserve or inspect them.
