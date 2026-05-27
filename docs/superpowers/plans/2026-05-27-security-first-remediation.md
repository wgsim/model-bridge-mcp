# Security-First Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the validated security findings by constraining `save_path` writes to an application-owned output root, removing dangerous default CLI execution flags from shipped config, and making debug-meta persistence opt-in with stronger secret masking.

**Architecture:** Keep the diff focused on three trust boundaries. First, move all file saves behind a single safe output-root resolver in `src/model_bridge/core/response.py`. Second, ship only non-dangerous default provider commands in `src/model_bridge/config/default.yaml`, while preserving explicit opt-in coverage in unit tests. Third, treat debug-meta logging as a diagnostic feature rather than a default behavior by threading a runtime flag from config into the save path and broadening token masking as defense in depth.

**Tech Stack:** Python 3.11, Pydantic v2 config models, PyYAML, pytest, MCP/FastMCP, subprocess-based provider adapters.

---

## Scope notes

This plan intentionally covers only the **security-first** slice from the audit:
- arbitrary file overwrite via `save_path`
- dangerous shipped defaults for tool-capable CLIs
- debug-meta leakage when `save_path` is used

Create separate follow-up plans for:
- runtime/config drift (`set_config`, SDK env propagation, `ask_batch(save_path=...)` semantics)
- routing/plugin architecture gaps (dead routing config, external plugin registry mismatch)

---

## File map

### Existing files to modify
- `src/model_bridge/core/response.py`
  - Centralize safe save-path resolution.
  - Make debug-meta persistence opt-in.
  - Expand masking coverage for common token/secret fields.
- `src/model_bridge/config/config_loader.py`
  - Add a runtime boolean flag for debug-meta persistence on save.
- `src/model_bridge/config/default.yaml`
  - Remove dangerous provider flags from shipped defaults.
  - Add the new runtime debug-meta flag default.
- `src/model_bridge/main.py`
  - Route all `_save_if_requested(...)` calls through the runtime flag.
- `README.md`
  - Document safe output behavior and local-only opt-in for dangerous CLI flags / debug-meta logging.
- `tests/unit/test_main_save_behavior.py`
  - Cover safe output root, traversal rejection, opt-in debug-meta behavior, and stronger masking.
- `tests/unit/test_config_loader.py`
  - Assert secure defaults in normalized config.
- `tests/unit/test_main_cli_noninteractive_policy.py`
  - Verify default noninteractive policy reports dangerous flags as disabled unless explicitly configured.
- `tests/unit/test_main_list_provider_models.py`
  - Remove stale dangerous-default assumptions from fake configs where they represent shipped defaults.
- `tests/unit/test_agy_provider.py`
  - Keep explicit opt-in `--dangerously-skip-permissions` coverage only in tests that intentionally exercise the warning path.

### No new production modules
This remediation should stay inside the existing response/config/main surfaces. Avoid introducing a new security helper module unless `response.py` becomes unreadable during implementation.

---

### Task 1: Constrain `save_path` to an application-owned output root

**Files:**
- Modify: `src/model_bridge/core/response.py`
- Test: `tests/unit/test_main_save_behavior.py`
- Test: `tests/unit/test_main_helpers.py`

- [ ] **Step 1: Write the failing tests for safe-root behavior**

```python
from pathlib import Path

from model_bridge.main import save_to_file


def test_save_to_file_writes_relative_path_under_output_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out = save_to_file("hello", "reports/result.txt")

    saved = tmp_path / ".model_bridge" / "outputs" / "reports" / "result.txt"
    assert saved.read_text(encoding="utf-8") == "hello"
    assert out.startswith("[FILE SAVED]")


def test_save_to_file_rejects_absolute_user_path(tmp_path: Path):
    out = save_to_file("hello", str(tmp_path / "outside.txt"))
    assert out.startswith("[SECURITY ERROR]")


def test_save_to_file_rejects_parent_traversal(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out = save_to_file("hello", "../escape.txt")

    assert out.startswith("[SECURITY ERROR]")


def test_save_to_file_rejects_symlinked_output_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model_bridge_dir = tmp_path / ".model_bridge"
    model_bridge_dir.mkdir()
    (model_bridge_dir / "outputs").symlink_to(tmp_path / "elsewhere")

    out = save_to_file("hello", "reports/result.txt")

    assert out.startswith("[SECURITY ERROR]")
```

- [ ] **Step 2: Run the targeted test file and verify the new tests fail for the expected reason**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_main_save_behavior.py -k "output_root or absolute_user_path or parent_traversal"'
```

Expected:
- FAIL because `save_to_file()` currently accepts absolute user-writable paths and does not anchor relative writes under `.model_bridge/outputs`.

- [ ] **Step 3: Write the minimal safe-path implementation in `response.py`**

```python
DEBUG_META_DIR = ".model_bridge/tmp"
SAFE_OUTPUT_DIR = os.path.join(".model_bridge", "outputs")


def _resolve_safe_output_path(path: str, output_root: str = SAFE_OUTPUT_DIR) -> tuple[str | None, str | None]:
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return None, f"[SECURITY ERROR] save_path must be relative to '{output_root}'."

    normalized = os.path.normpath(expanded)
    if normalized in {".", ""} or normalized.startswith(".."):
        return None, f"[SECURITY ERROR] save_path must stay within '{output_root}'."

    root_base = os.path.abspath(output_root)
    if os.path.lexists(root_base) and os.path.islink(root_base):
        return None, f"[SECURITY ERROR] Output root '{output_root}' must not be a symlink."
    os.makedirs(root_base, exist_ok=True)
    root = os.path.realpath(root_base)

    full_path = os.path.realpath(os.path.join(root, normalized))
    if full_path != root and not full_path.startswith(root + os.sep):
        return None, f"[SECURITY ERROR] save_path must stay within '{output_root}'."
    return full_path, None


def save_to_file(content: str, path: str) -> str:
    try:
        full_path, error = _resolve_safe_output_path(path)
        if error:
            return error
        assert full_path is not None
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(clean_markdown_fences(content))
        return f"[FILE SAVED] Successfully saved to: {path}\n(Output root: {SAFE_OUTPUT_DIR})"
    except Exception as exc:
        return f"[FILE ERROR] Failed to save: {exc}"
```

- [ ] **Step 4: Run the save-path test file and verify it passes**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_main_save_behavior.py'
```

Expected:
- PASS
- Existing symlink/system-path test still passes.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/model_bridge/core/response.py tests/unit/test_main_save_behavior.py tests/unit/test_main_helpers.py
git commit -m "fix: restrict save_path writes to safe output root"
```

---

### Task 2: Remove dangerous shipped defaults and keep them local-only opt-in

**Files:**
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `README.md`
- Test: `tests/unit/test_config_loader.py`
- Test: `tests/unit/test_main_cli_noninteractive_policy.py`
- Test: `tests/unit/test_main_list_provider_models.py`
- Test: `tests/unit/test_agy_provider.py`

- [ ] **Step 1: Write the failing tests for secure defaults**

```python
def test_load_config_from_default_succeeds():
    config = load_config()
    assert "--dangerously-bypass-approvals-and-sandbox" not in config["commands"]["codex"]["exec"]
    assert "--dangerously-skip-permissions" not in config["commands"]["claude_code"]["exec"]
    assert "--dangerously-skip-permissions" not in config["commands"]["agy"]["exec"]


def test_list_cli_noninteractive_policy_defaults_do_not_report_skip_flags(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_get_config",
        lambda: {
            "commands": {
                "codex": {"exec": ["codex", "exec", "--skip-git-repo-check"]},
                "gemini": {"exec": ["gemini", "-p"]},
                "claude_code": {"exec": ["claude", "-p"]},
                "agy": {"exec": ["agy", "-p"]},
            }
        },
    )

    payload = json.loads(main_module.list_cli_noninteractive_policy())
    assert payload["providers"]["agy"]["skip_flag_configured"] is False
```

- [ ] **Step 2: Run the secure-default tests and verify they fail for shipped config**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_config_loader.py tests/unit/test_main_cli_noninteractive_policy.py -k "dangerously or skip_flags or default_succeeds"'
```

Expected:
- FAIL because `default.yaml` still ships dangerous flags for `codex` and `claude_code`.

- [ ] **Step 3: Write the minimal default-config and docs changes**

```yaml
commands:
  codex:
    exec: ["codex", "exec", "--skip-git-repo-check"]
    health: ["codex", "--version"]
  claude_code:
    exec: ["claude", "-p"]
    health: ["claude", "--version"]
  agy:
    exec: ["agy", "-p"]
    health: ["agy", "--version"]
```

### Local opt-in for dangerous provider flags

If you intentionally want approval-bypass flags for local experimentation, set them only in `~/.model_bridge/local.yaml`:

```yaml
commands:
  codex:
    exec: ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
  claude_code:
    exec: ["claude", "-p", "--dangerously-skip-permissions"]
  agy:
    exec: ["agy", "-p", "--dangerously-skip-permissions"]
```

- [ ] **Step 4: Update tests that intentionally cover dangerous flags so they use explicit test fixtures, not shipped defaults**

```python
def _build_agy_config():
    return {
        "commands": {
            "agy": {
                "exec": ["agy", "-p", "--dangerously-skip-permissions"],
                "health": ["agy", "--version"],
            }
        },
        ...
    }
```

Keep that explicit fixture in `tests/unit/test_agy_provider.py` for warning-path coverage, but remove stale dangerous-flag assumptions from tests that represent normalized shipped defaults.

- [ ] **Step 5: Run the targeted config and policy tests and verify they pass**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_config_loader.py tests/unit/test_main_cli_noninteractive_policy.py tests/unit/test_main_list_provider_models.py tests/unit/test_agy_provider.py'
```

Expected:
- PASS
- Explicit warning-path tests still pass because they create their own dangerous fixture.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/model_bridge/config/default.yaml README.md tests/unit/test_config_loader.py tests/unit/test_main_cli_noninteractive_policy.py tests/unit/test_main_list_provider_models.py tests/unit/test_agy_provider.py
git commit -m "fix: remove dangerous provider flags from shipped defaults"
```

---

### Task 3: Make debug-meta persistence opt-in and strengthen masking

**Files:**
- Modify: `src/model_bridge/core/response.py`
- Modify: `src/model_bridge/config/config_loader.py`
- Modify: `src/model_bridge/config/default.yaml`
- Modify: `src/model_bridge/main.py`
- Test: `tests/unit/test_main_save_behavior.py`
- Test: `tests/unit/test_config_loader.py`

- [ ] **Step 1: Write the failing tests for opt-in debug-meta logging and broader masking**

```python
def test_save_if_requested_skips_debug_meta_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = "body\n\n--- [Routing Log] ---\nAuthorization: Bearer SECRET_TOKEN"
    target = "result.txt"
    debug_dir = tmp_path / ".tmp-debug"

    out = _save_if_requested(
        response,
        target,
        tool_name="ask_chatgpt_cli",
        debug_dir=str(debug_dir),
        save_debug_meta=False,
    )

    saved = tmp_path / ".model_bridge" / "outputs" / "result.txt"
    assert saved.read_text(encoding="utf-8") == "body"
    assert list(debug_dir.glob("*.meta.log")) == []
    assert "[DEBUG META]" not in out


def test_mask_sensitive_text_masks_common_token_fields():
    masked = _mask_sensitive_text(
        "Authorization: Bearer SECRET\n"
        "x-api-key: APISECRET\n"
        "refresh_token=REFRESHSECRET\n"
        "cookie: session=COOKIESECRET"
    )

    assert "SECRET" not in masked
    assert "APISECRET" not in masked
    assert "REFRESHSECRET" not in masked
    assert "COOKIESECRET" not in masked
    assert masked.count("***MASKED***") >= 4
```

- [ ] **Step 2: Run the targeted tests and verify they fail against current behavior**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_main_save_behavior.py -k "debug_meta or sensitive_text"'
```

Expected:
- FAIL because `_save_if_requested()` always writes debug meta and `_mask_sensitive_text()` only covers a narrow subset of auth fields.

- [ ] **Step 3: Add the runtime flag to the config model and defaults**

```python
class RuntimeConfig(BaseModel):
    ...
    save_debug_meta_on_save: bool = False
```

```yaml
runtime:
  ...
  save_debug_meta_on_save: false
```

Also extend `tests/unit/test_config_loader.py`:

```python
assert config["runtime"]["save_debug_meta_on_save"] is False
```

- [ ] **Step 4: Write the minimal implementation to gate debug-meta and expand masking**

```python
def _mask_sensitive_text(text: str) -> str:
    patterns = [
        (r"(?i)(authorization\s*:\s*bearer\s+)([^\s]+)", r"\1***MASKED***"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(x-api-key\s*:\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(refresh_token\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(access_token\s*[:=]\s*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(?i)(cookie\s*:\s*)([^\n]+)", r"\1***MASKED***"),
    ]
    masked = text
    for pattern, repl in patterns:
        masked = re.sub(pattern, repl, masked)
    return masked


def _save_if_requested(
    response: str,
    save_path: Optional[str],
    tool_name: str,
    debug_dir: str = DEBUG_META_DIR,
    save_debug_meta: bool = False,
) -> str:
    if not save_path:
        return response
    body, full_response = _split_body_and_meta(response)
    save_result = save_to_file(body, save_path) if body else "[FILE SKIPPED] No model body extracted from response."
    if not save_debug_meta:
        return f"{save_result}\n\n{response}"
    meta_path = _save_debug_meta(full_response, tool_name=tool_name, debug_dir=debug_dir)
    return f"{save_result}\n[DEBUG META] Saved to: {meta_path}\n\n{response}"
```

In `src/model_bridge/main.py`, introduce one helper and use it at all current save call sites:

```python
def _save_response_if_requested(response: str, save_path: str | None, tool_name: str) -> str:
    runtime_cfg = _get_config().get("runtime", {})
    return _save_if_requested(
        response,
        save_path,
        tool_name=tool_name,
        save_debug_meta=runtime_cfg.get("save_debug_meta_on_save", False),
    )
```

- [ ] **Step 5: Run the targeted save/config tests and verify they pass**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_main_save_behavior.py tests/unit/test_config_loader.py'
```

Expected:
- PASS
- Meta files are absent by default.
- Common token fields are masked when meta logging is explicitly enabled in tests.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/model_bridge/core/response.py src/model_bridge/config/config_loader.py src/model_bridge/config/default.yaml src/model_bridge/main.py tests/unit/test_main_save_behavior.py tests/unit/test_config_loader.py
 git commit -m "fix: make debug meta saves opt-in and harden masking"
```

---

### Task 4: Run the full security-first verification sweep

**Files:**
- Modify: none
- Test: `tests/unit/test_main_save_behavior.py`
- Test: `tests/unit/test_config_loader.py`
- Test: `tests/unit/test_main_cli_noninteractive_policy.py`
- Test: `tests/unit/test_main_list_provider_models.py`
- Test: `tests/unit/test_agy_provider.py`
- Test: `tests/unit/test_main_helpers.py`

- [ ] **Step 1: Run the focused regression suite for all three security fixes**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q tests/unit/test_main_save_behavior.py tests/unit/test_config_loader.py tests/unit/test_main_cli_noninteractive_policy.py tests/unit/test_main_list_provider_models.py tests/unit/test_agy_provider.py tests/unit/test_main_helpers.py'
```

Expected:
- PASS with no failures.

- [ ] **Step 2: Run the full suite to catch unintended regressions**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp" && PYTHONPATH=src python -m pytest -q'
```

Expected:
- PASS
- No new failures in provider dispatch, save behavior, or config loading.

- [ ] **Step 3: Re-run the dedicated security review after the code lands**

Operator workflow in Claude Code:
- Run `/cross-audit-review` after the commits above land.
- If the review reports new P1/P2 issues in this security-first scope, fix them before moving on.

Expected:
- no new P1/P2 findings on the security-first slice
- any remaining issues should belong to the separate runtime-consistency or architecture plans, not this plan’s scope

- [ ] **Step 4: Commit only if Task 4 required doc/test adjustments**

```bash
git status -sb
```

Expected:
- no uncommitted production changes
- if there are no diffs, do not create an extra commit

---

## Self-review checklist

- Spec coverage:
  - arbitrary file overwrite: covered by Task 1
  - dangerous shipped defaults: covered by Task 2
  - debug-meta persistence / masking: covered by Task 3
  - regression verification: covered by Task 4
- Placeholder scan:
  - no `TODO`, `TBD`, or “appropriate handling” placeholders remain
- Type consistency:
  - `save_debug_meta_on_save` is the only new runtime flag name used throughout
  - `_save_response_if_requested(...)` is the single main-entry helper name used throughout
