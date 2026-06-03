# CI Env-Var Discovery Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore CI to green by removing environment-dependent assumptions from the failing preflight unit test, then leave an optional follow-up path for hardening `_discover_provider_env_vars()` if Phase 1 reveals production-facing ambiguity.

**Architecture:** Phase 1 treats the CI failure as a test-boundary problem, not a workflow or runner problem. Keep the runtime helper contract unchanged and move the unit tests to the subprocess boundary by mocking `subprocess.run()` output directly. Phase 2 is explicitly optional and only starts after Phase 1 validation is green; it decomposes env-var parsing into a smaller pure helper and simplifies the shell command shape without changing the public behavior.

**Tech Stack:** Python 3.11, pytest, unittest.mock, GitHub Actions, conda, pre-commit.

---

## File map

- `tests/unit/test_preflight.py`
  - Existing preflight unit coverage for `SubprocessAdapter`
  - Phase 1 ownership: replace the brittle login-shell env discovery assertion with deterministic subprocess-mocked tests
  - Phase 2 ownership: expand parser/helper coverage if helper extraction happens
- `src/model_bridge/adapters/subprocess_adapter.py`
  - Owns `_discover_provider_env_vars()`
  - Phase 1 should avoid modifying this file unless a tiny test-enabling change becomes strictly necessary
  - Phase 2 may add a pure parser helper and a clearer shell command construction path
- `.github/workflows/ci.yml`
  - Read-only context for this effort
  - Do not modify unless Phase 1 evidence unexpectedly proves the workflow is the correct fix boundary
- `.pre-commit-config.yaml`
  - Existing validation gate invoking the full test suite
  - No planned code changes here; use it as a verification target only

## Phase boundaries

- **Phase 1 (required):** CI recovery only. Fix the failing test strategy and prove CI-equivalent validation passes locally.
- **Phase 2 (optional):** Implementation hardening only if requested after Phase 1 or if Phase 1 reveals a real helper-contract problem.

---

### Task 1: Replace the brittle login-shell env test with a deterministic subprocess-mocked test

**Files:**
- Modify: `tests/unit/test_preflight.py:167-176`
- Test: `tests/unit/test_preflight.py`

- [ ] **Step 1: Replace the current failing test with a subprocess-mocked version**

Replace the current `patch.dict(os.environ, ...)`-based test at the end of `tests/unit/test_preflight.py` with this exact test body:

```python
def test_discover_provider_env_vars_collects_multiple_values():
    completed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=google-token\nOPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {
        "GOOGLE_API_KEY": "google-token",
        "OPENAI_API_KEY": "openai-token",
    }
    run_mock.assert_called_once()
```

- [ ] **Step 2: Run the single targeted test to verify the old CI failure is gone**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_preflight.py::test_discover_provider_env_vars_collects_multiple_values'
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Commit the minimal CI-recovery test replacement**

```bash
git add tests/unit/test_preflight.py
git commit -m "test: stabilize provider env discovery unit coverage"
```

---

### Task 2: Add deterministic coverage for blank values, non-zero shell results, and shell fallback behavior

**Files:**
- Modify: `tests/unit/test_preflight.py`
- Test: `tests/unit/test_preflight.py`

- [ ] **Step 1: Add an empty-value filtering test immediately after the multiple-values test**

Insert this exact test below `test_discover_provider_env_vars_collects_multiple_values`:

```python
def test_discover_provider_env_vars_ignores_blank_values():
    completed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=\nOPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed):
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"OPENAI_API_KEY": "openai-token"}
```

- [ ] **Step 2: Add a shell-fallback test that proves a later shell can succeed after an earlier failed shell**

Insert this exact test below the blank-values test:

```python
def test_discover_provider_env_vars_falls_back_to_next_shell_after_non_zero_result():
    failed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=1,
        stdout="",
        stderr="shell failed",
    )
    succeeded = subprocess.CompletedProcess(
        args=["zsh", "-lc", "env-check"],
        returncode=0,
        stdout="OPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", side_effect=[failed, succeeded]) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"OPENAI_API_KEY": "openai-token"}
    assert run_mock.call_count == 2
    assert run_mock.call_args_list[0].args[0][0] == "bash"
    assert run_mock.call_args_list[1].args[0][0] == "zsh"
```

- [ ] **Step 3: Add a no-output fallback test that proves the helper continues when the first shell returns no usable stdout**

Insert this exact test below the non-zero fallback test:

```python
def test_discover_provider_env_vars_falls_back_to_next_shell_after_empty_output():
    empty = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="",
        stderr="",
    )
    succeeded = subprocess.CompletedProcess(
        args=["zsh", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=google-token\n",
        stderr="",
    )

    with patch("subprocess.run", side_effect=[empty, succeeded]) as run_mock:
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {"GOOGLE_API_KEY": "google-token"}
    assert run_mock.call_count == 2
```

- [ ] **Step 4: Run the full preflight test file to verify the env-discovery tests stay deterministic alongside existing preflight coverage**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_preflight.py'
```

Expected:

```text
all tests in tests/unit/test_preflight.py pass
```

- [ ] **Step 5: Commit the expanded deterministic env-discovery coverage**

```bash
git add tests/unit/test_preflight.py
git commit -m "test: cover provider env discovery shell fallbacks"
```

---

### Task 3: Prove the CI recovery patch passes the same gates CI uses

**Files:**
- Modify: none
- Test: `tests/unit/test_preflight.py`
- Test: `tests/`
- Verify: `.pre-commit-config.yaml`

- [ ] **Step 1: Run the full repository test suite through the same conda command pattern CI uses**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'
```

Expected:

```text
0 failed
```

- [ ] **Step 2: Run the repository quality gate exactly as configured**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'pre-commit run --all-files'
```

Expected:

```text
all configured hooks pass
```

- [ ] **Step 3: Inspect the final diff to ensure Phase 1 stayed narrowly scoped to test stabilization**

Run:

```bash
git diff -- tests/unit/test_preflight.py src/model_bridge/adapters/subprocess_adapter.py .github/workflows/ci.yml
```

Expected:

```text
only tests/unit/test_preflight.py changed for Phase 1
```

- [ ] **Step 4: Commit the validated Phase 1 recovery state if the previous task commits were intentionally deferred**

If Tasks 1 and 2 were already committed separately, skip this step. Otherwise use:

```bash
git add tests/unit/test_preflight.py
git commit -m "test: stabilize CI env discovery coverage"
```

---

### Task 4: Optional Phase 2 — extract a pure parser helper for env-discovery stdout

**Files:**
- Modify: `src/model_bridge/adapters/subprocess_adapter.py:99-152`
- Modify: `tests/unit/test_preflight.py`
- Test: `tests/unit/test_preflight.py`

> **Only start this task after Task 3 is green and only if the human explicitly wants implementation hardening now, or if Task 1-3 reveal a real helper-contract ambiguity that cannot be left as-is.**

- [ ] **Step 1: Add a pure parser helper above `_discover_provider_env_vars()`**

Insert this helper above `_discover_provider_env_vars()` in `src/model_bridge/adapters/subprocess_adapter.py`:

```python
def _parse_provider_env_output(stdout: str) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for line in stdout.strip().splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if _is_safe_env_var_name(name) and value:
            discovered[name] = value
    return discovered
```

- [ ] **Step 2: Update `_discover_provider_env_vars()` to delegate parsing to the new helper**

Replace the parsing block inside `_discover_provider_env_vars()` with this exact code:

```python
            if result.returncode == 0 and result.stdout.strip():
                discovered.update(_parse_provider_env_output(result.stdout))
                if discovered:
                    break  # Success, no need to try other shells
```

Keep the surrounding timeout / file-not-found / generic exception handling intact.

- [ ] **Step 3: Add direct parser coverage to the preflight test file**

Update the import block in `tests/unit/test_preflight.py` to include `_parse_provider_env_output`:

```python
from model_bridge.adapters.subprocess_adapter import (
    SubprocessAdapter,
    _discover_provider_env_vars,
    _parse_provider_env_output,
)
```

Then add these exact tests below the Phase 1 env-discovery tests:

```python
def test_parse_provider_env_output_collects_safe_non_empty_values():
    stdout = "GOOGLE_API_KEY=google-token\nOPENAI_API_KEY=openai-token\n"

    assert _parse_provider_env_output(stdout) == {
        "GOOGLE_API_KEY": "google-token",
        "OPENAI_API_KEY": "openai-token",
    }


def test_parse_provider_env_output_ignores_blank_and_unsafe_names():
    stdout = "GOOGLE_API_KEY=\nOPENAI_API_KEY=openai-token\nnot_safe=value\n"

    assert _parse_provider_env_output(stdout) == {
        "OPENAI_API_KEY": "openai-token",
    }
```

- [ ] **Step 4: Re-run targeted and full validation after helper extraction**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_preflight.py'
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'
conda run -n model-bridge-mcp_dev bash -lc 'pre-commit run --all-files'
```

Expected:

```text
all three commands pass
```

- [ ] **Step 5: Commit the optional hardening as a separate changeset**

```bash
git add src/model_bridge/adapters/subprocess_adapter.py tests/unit/test_preflight.py
git commit -m "refactor: extract provider env discovery parser"
```

---

### Task 5: Optional Phase 2b — simplify shell command construction only if Task 4 still leaves ambiguity

**Files:**
- Modify: `src/model_bridge/adapters/subprocess_adapter.py:119-127`
- Modify: `tests/unit/test_preflight.py`
- Test: `tests/unit/test_preflight.py`

> **Only do this if Task 4 uncovered a concrete ambiguity in the current chained `&&` / `||` command shape. Do not perform this task as cleanup-for-cleanup's-sake.**

- [ ] **Step 1: Replace the chained command string with a shell loop snippet**

Replace the current `var_checks` / `cmd` construction with this exact shape:

```python
            vars_list = " ".join(_PROVIDER_ENV_VARS)
            cmd = (
                f'for var in {vars_list}; do '
                f'value=$(printenv "$var" 2>/dev/null || true); '
                f'[ -n "$value" ] && echo "$var=$value"; '
                f'done'
            )
```

- [ ] **Step 2: Add or update one subprocess-mocked test to assert the helper still parses multiple values correctly after the command rewrite**

Use this exact expectation in a direct test if no existing test already proves it after Task 4:

```python
def test_discover_provider_env_vars_collects_multiple_values_after_command_rewrite():
    completed = subprocess.CompletedProcess(
        args=["bash", "-lc", "env-check"],
        returncode=0,
        stdout="GOOGLE_API_KEY=google-token\nOPENAI_API_KEY=openai-token\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed):
        discovered = _discover_provider_env_vars(timeout=1.0)

    assert discovered == {
        "GOOGLE_API_KEY": "google-token",
        "OPENAI_API_KEY": "openai-token",
    }
```

- [ ] **Step 3: Re-run validation if and only if this task was needed**

Run:

```bash
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests/unit/test_preflight.py'
conda run -n model-bridge-mcp_dev bash -lc 'PYTHONPATH=src pytest -q tests'
conda run -n model-bridge-mcp_dev bash -lc 'pre-commit run --all-files'
```

Expected:

```text
all commands pass
```

- [ ] **Step 4: Commit the shell-command simplification separately**

```bash
git add src/model_bridge/adapters/subprocess_adapter.py tests/unit/test_preflight.py
git commit -m "refactor: simplify provider env discovery shell command"
```

---

## Spec coverage check

- **CI red recovery:** covered by Tasks 1-3
- **Environment-independent unit coverage:** covered by Tasks 1-2
- **Validation against repository gates:** covered by Task 3
- **Optional helper hardening:** covered by Task 4
- **Optional command-shape hardening:** covered by Task 5

## Guardrails for the implementer

- Stop after Task 3 if Phase 1 is green and no human asked for Phase 2 work yet.
- Do not touch `.github/workflows/ci.yml` during Phase 1.
- Do not widen Phase 1 into runtime behavior changes unless a new reproduction proves a production-facing bug.
- Keep Phase 2 commits separate from Phase 1 recovery so rollback stays easy.
