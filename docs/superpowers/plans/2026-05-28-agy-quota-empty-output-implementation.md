# agy quota/empty-output handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ask_agy_cli` surface confirmed quota/rate-limit failures and ambiguous empty-output provider failures explicitly, instead of silently succeeding or returning an unhelpful empty result.

**Architecture:** Keep the change localized to the `agy` subprocess execution path. Add a small result-classification helper in the subprocess adapter that inspects exit code, stdout, and stderr, then surface the resulting provider error through the existing `ask_agy_cli` / failover flow without changing unrelated providers. Preserve existing timeout and non-zero exit handling, but make empty-output and known quota-marker cases explicit.

**Tech Stack:** Python 3.11, pytest, subprocess-based provider adapter, FastMCP tool surface, existing `agy` provider tests in `tests/unit/test_agy_provider.py`.

---

## File map

### Existing files to modify
- `src/model_bridge/adapters/subprocess_adapter.py`
  - Add a narrowly scoped `agy` result-classification helper for quota markers and empty-output cases.
  - Reuse the existing `run()` / `run_async()` result shape rather than introducing a new abstraction for all providers.
- `tests/unit/test_agy_provider.py`
  - Add regression coverage for:
    - known quota marker in stderr
    - known quota marker in stdout
    - exit `0` + empty stdout/stderr
    - preserving current success/failure/timeout behavior

### Optional file to modify only if required by implementation
- `src/model_bridge/main.py`
  - Only touch this if the adapter-level classification cannot be surfaced cleanly through the current `ask_agy_cli` flow.
  - Do not change other provider behavior.

### Files to leave unchanged
- `src/model_bridge/config/default.yaml`
- `src/model_bridge/core/response.py`
- other provider tests or routing config

---

### Task 1: Add focused failing tests for agy quota and empty-output classification

**Files:**
- Modify: `tests/unit/test_agy_provider.py`
- Test: `tests/unit/test_agy_provider.py`

- [ ] **Step 1: Add failing test for stderr quota marker detection**

```python
def test_agy_zero_exit_with_stderr_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="quota exceeded for current usage tier",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."
```

- [ ] **Step 2: Add failing test for stdout quota marker detection**

```python
def test_agy_zero_exit_with_stdout_quota_marker_is_explicit_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="usage limit reached",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), patch(
        "subprocess.run", return_value=completed
    ):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == "[PROVIDER ERROR] agy quota or rate-limit exceeded."
```

- [ ] **Step 3: Add failing test for empty-output ambiguous failure**

```python
def test_agy_zero_exit_with_empty_output_is_conservative_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])
    completed = subprocess.CompletedProcess(
        args=["agy", "-p"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with patch("shutil.which", return_value="/usr/local/bin/agy"), patch(
        "subprocess.run", return_value=completed):
        ok, output = adapter.run("agy", [], "hello")

    assert ok is False
    assert output == (
        "[PROVIDER ERROR] agy returned no output "
        "(possible quota/rate-limit or empty provider response)."
    )
```

- [ ] **Step 4: Add direct async-path failing tests for classification**

```python
@pytest.mark.anyio
async def test_agy_run_async_zero_exit_with_empty_output_is_conservative_provider_error():
    adapter = SubprocessAdapter(_build_agy_config()["commands"])

    class _Proc:
        returncode = 0
        async def communicate(self, input=None):
            return b"", b""

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    with patch("shutil.which", return_value="/usr/local/bin/agy"), patch(
        "asyncio.create_subprocess_exec", side_effect=_fake_exec
    ):
        ok, output = await adapter.run_async("agy", [], "hello")

    assert ok is False
    assert output == (
        "[PROVIDER ERROR] agy returned no output "
        "(possible quota/rate-limit or empty provider response)."
    )


@pytest.mark.anyio
async def test_ask_agy_cli_propagates_async_empty_output_provider_error():
    with patch("model_bridge.main._get_config", return_value=_build_agy_config()), \
         patch("model_bridge.adapters.subprocess_adapter.SubprocessAdapter.preflight_check", return_value=(True, "")), \
         patch("model_bridge.adapters.subprocess_adapter.SubprocessAdapter.run_async", return_value=(False, "[PROVIDER ERROR] agy returned no output (possible quota/rate-limit or empty provider response).")):
        response = await ask_agy_cli("hello")

    assert "possible quota/rate-limit or empty provider response" in response
```
- [ ] **Step 5: Run the new focused tests to verify they fail for the expected reason**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp/.claude/worktrees/security-first-remediation" && PYTHONPATH=src python -m pytest -q tests/unit/test_agy_provider.py -k "quota_marker or empty_output"'
```

Expected:
- FAIL because the current `agy` path treats exit `0` + output text as success and does not classify quota markers or empty output specially.

- [ ] **Step 6: Commit only after implementation and green verification**

```bash
git status -sb
```

Expected:
- no commit yet at this stage

---

### Task 2: Implement conservative agy result classification in the subprocess adapter

**Files:**
- Modify: `src/model_bridge/adapters/subprocess_adapter.py`
- Test: `tests/unit/test_agy_provider.py`

- [ ] **Step 1: Add a narrow helper for agy output classification**

```python
_AGY_QUOTA_MARKERS = (
    "quota exceeded",
    "rate limit exceeded",
    "usage limit reached",
    "429 too many requests",
    "http 429",
)


def _classify_agy_result(returncode: int, stdout: str, stderr: str) -> tuple[bool, str]:
    stdout_text = stdout.strip()
    stderr_text = stderr.strip()
    stderr_lower = stderr_text.lower()
    stdout_lower = stdout_text.lower()

    if any(marker in stderr_lower for marker in _AGY_QUOTA_MARKERS):
        return False, "[PROVIDER ERROR] agy quota or rate-limit exceeded."

    if stdout_text and any(marker in stdout_lower for marker in _AGY_QUOTA_MARKERS):
        return False, "[PROVIDER ERROR] agy quota or rate-limit exceeded."

    if returncode == 0 and not stdout_text and stderr_text:
        return False, f"[PROVIDER ERROR] agy returned no usable stdout response. stderr={stderr_text}"

    if returncode == 0 and not stdout_text and not stderr_text:
        return False, (
            "[PROVIDER ERROR] agy returned no output "
            "(possible quota/rate-limit or empty provider response)."
        )

    if returncode == 0:
        return True, stdout_text

    output = (stdout + stderr).strip()
    return False, output
```

- [ ] **Step 2: Wire the helper into the synchronous agy path only**

```python
if result.returncode == 0:
    output = result.stdout.strip()
    if strip_noise:
        output = self._strip_known_noise_lines(output)
    if service_name == "agy":
        stderr_output = result.stderr.strip()
        if strip_noise:
            stderr_output = self._strip_known_noise_lines(stderr_output)
        return _classify_agy_result(result.returncode, output, stderr_output)
    return True, output

output = (result.stdout + result.stderr).strip()
if strip_noise:
    output = self._strip_known_noise_lines(output)
return False, output
```

- [ ] **Step 3: Wire the helper into the asynchronous agy path only**

```python
stdout = stdout_bytes.decode("utf-8", errors="replace")
stderr = stderr_bytes.decode("utf-8", errors="replace")
if proc.returncode == 0:
    output = stdout.strip()
    if strip_noise:
        output = self._strip_known_noise_lines(output)
    if service_name == "agy":
        err_output = stderr.strip()
        if strip_noise:
            err_output = self._strip_known_noise_lines(err_output)
        return _classify_agy_result(proc.returncode, output, err_output)
    return True, output
```

- [ ] **Step 4: Keep timeout and non-zero exit behavior unchanged**

```python
assert "Timeout Error:" in output
assert "stderr stacktrace" in output
```

Do not rewrite generic timeout formatting or non-zero subprocess failure behavior for other providers in this task.

- [ ] **Step 5: Run the focused agy tests and verify they pass**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp/.claude/worktrees/security-first-remediation" && PYTHONPATH=src python -m pytest -q tests/unit/test_agy_provider.py'
```

Expected:
- PASS
- existing success, timeout, model-override, and warning-path tests remain green
- direct `run_async` classification coverage is green in addition to `ask_agy_cli` propagation coverage

- [ ] **Step 6: Commit Task 2**

```bash
git add src/model_bridge/adapters/subprocess_adapter.py tests/unit/test_agy_provider.py
git commit -m "fix: classify agy quota and empty-output failures"
```

---

### Task 3: Verify the real agy MCP surface with a conservative empty-output contract

**Files:**
- Modify: none
- Test: runtime verification only

- [ ] **Step 1: Re-run direct agy CLI observation**

Run:
```bash
python - <<'PY'
import subprocess
r = subprocess.run(
    ["agy", "-p", "Return exactly AGY_RUNTIME_OK and nothing else."],
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)
print("EXIT", r.returncode)
print("STDOUT", r.stdout)
print("STDERR", r.stderr)
PY
```

Expected:
- either a normal stdout body or a provider-specific quota message
- no silent ambiguity about whether the CLI returned anything

- [ ] **Step 2: Re-run end-to-end MCP verification over stdio**

Run:
```bash
cat > /tmp/verify_agy_mcp_jsonl.py <<'PY'
import json, subprocess, sys, time
from pathlib import Path
cwd = Path.cwd()
proc = subprocess.Popen(
    [sys.executable, '-u', '-m', 'model_bridge.main'],
    cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
)
def send(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
def recv(timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if line:
            obj = json.loads(line)
            if obj.get('id') is not None or obj.get('result') is not None or obj.get('error') is not None:
                return obj
    raise TimeoutError('timeout waiting for JSON-RPC response')
send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'verify-client','version':'0.0'}}})
print('INIT', json.dumps(recv(20), ensure_ascii=False))
send({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})
send({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'ask_agy_cli','arguments':{'prompt':'Return exactly AGY_RUNTIME_OK and nothing else.','timeout_seconds':90}}})
print('CALL', json.dumps(recv(120), ensure_ascii=False))
proc.terminate()
PY
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp/.claude/worktrees/security-first-remediation" && PYTHONPATH=src python /tmp/verify_agy_mcp_jsonl.py'
```

Expected:
- success path returns a normal MCP tool result
- quota path returns an explicit provider error
- empty-output path returns the conservative provider error instead of a silent empty success

- [ ] **Step 3: Probe the adjacent failure modes intentionally**

Run one or more of:
```bash
# JSON unsupported path
# Expect capability error, not hang

# model override path
# Expect provider error, not silent success
```

Expected:
- existing adjacent guardrails still behave explicitly and consistently

- [ ] **Step 4: Commit only if Task 3 required a verifier/test harness file checked into the repo**

```bash
git status -sb
```

Expected:
- no production changes from runtime verification itself
- if no tracked changes, do not create an extra commit

---

### Task 4: Final targeted audit and branch validation

**Files:**
- Modify: none (unless review uncovers a small follow-up)

- [ ] **Step 1: Run the focused branch regression suite**

Run:
```bash
conda run --no-capture-output -n model-bridge-mcp_dev bash -lc 'cd "/Users/wsim/git_clones/model-bridge-mcp/.claude/worktrees/security-first-remediation" && PYTHONPATH=src python -m pytest -q tests/unit/test_agy_provider.py tests/unit/test_main_save_behavior.py tests/unit/test_main_helpers.py tests/unit/test_config_loader.py'
```

Expected:
- PASS

- [ ] **Step 2: Run `/cross-audit-review` on the latest agy fix commit**

Operator workflow in Claude Code:
- run `/cross-audit-review`
- if new P1/P2 findings appear in the agy quota/empty-output scope, fix them before closing the work

Expected:
- no new P1/P2 issues on the agy classification slice

- [ ] **Step 3: Confirm branch is ready for merge or broader integration**

Run:
```bash
git log --oneline -n 12
git status -sb
```

Expected:
- commits are logically grouped
- no unintended tracked changes remain
- only known local artifacts (`.cross_audit/`, `.serena/`, etc.) remain untracked if present

---

## Self-review checklist

- Spec coverage:
  - confirmed quota marker handling: Task 1 + Task 2
  - ambiguous empty-output handling: Task 1 + Task 2
  - no silent empty success: Task 2 + Task 3
  - runtime surface verification: Task 3
- Placeholder scan:
  - no TBD/TODO placeholders remain
- Type consistency:
  - conservative error wording is consistent across tests and implementation
  - the helper/classifier remains specific to `agy`
