# CI env-var discovery stabilization design

## Goal

Stabilize the failing CI path around provider environment-variable discovery without bundling unrelated runtime refactors.

The immediate objective is to restore CI to green by removing environment-dependent assumptions from the failing unit test. A secondary objective is to document a follow-up hardening path for the underlying implementation so the same class of shell/profile sensitivity can be reduced deliberately instead of opportunistically.

## Problem summary

The failing CI test is:

- `tests/unit/test_preflight.py::test_discover_provider_env_vars_collects_multiple_values`

Observed CI symptom:

- `KeyError: 'GOOGLE_API_KEY'`
- all other tests pass
- the same failure appears on consecutive CI runs, including commits that only touched docs

The test currently uses `patch.dict(os.environ, ...)` and then calls `_discover_provider_env_vars()`. The helper does not read `os.environ` directly. Instead, it launches a new login shell (`bash -lc`, `zsh -lc`, then `sh -lc`) and parses stdout from that shell.

In GitHub Actions, `setup-miniconda` rewrites login-shell startup files and injects environment activation behavior into `.profile`/shell init scripts. As a result, the test is not validating only the helper logic. It is validating a much stronger assumption: that patched Python process environment variables remain visible and stable after CI-specific login-shell startup behavior runs.

That assumption is too brittle for a unit test.

## Root cause

### Direct root cause of the CI failure

The unit test depends on real login-shell behavior and therefore on the CI runner's shell/profile initialization state.

The failing assertion is not proving pure parsing or helper logic. It is proving that:

1. `patch.dict(os.environ, ...)` affects the current Python process
2. a newly launched login shell inherits those values exactly as expected
3. GitHub Actions shell/profile mutations do not alter or suppress the expected variables

CI evidence shows that the login-shell environment is modified by `setup-miniconda`, including profile removal/recreation and automatic `conda activate` wiring. That makes the test environment-sensitive even though it is located in a unit-test file.

### Structural contributor

`_discover_provider_env_vars()` builds a shell command using chained `&&` / `||` clauses and then parses the resulting stdout lines. This makes the helper more sensitive to shell semantics and startup behavior than a pure function would be.

This does not yet prove the implementation is wrong for production use, but it does make the current test strategy fragile.

## Non-goals

This design does **not** try to:

- redesign the full provider-auth discovery flow
- remove login-shell discovery entirely in the same change
- change unrelated preflight behavior
- modify broader CI environment setup unless investigation proves it is the only safe fix
- bundle opportunistic cleanup unrelated to the failing test path

## Recommended approach

Use a two-phase approach.

### Phase 1 — CI recovery (required)

Make the failing test environment-independent so CI no longer depends on GitHub runner login-shell behavior.

### Phase 2 — implementation hardening (optional follow-up)

Evaluate whether `_discover_provider_env_vars()` should be simplified or decomposed so shell/profile sensitivity is reduced and future tests can target smaller units.

## Approach options considered

### Option A — Two-phase fix with test stabilization first (recommended)

Phase 1 fixes the CI failure by rewriting the brittle unit test to mock the subprocess boundary. Phase 2 is explicitly documented as optional hardening for the helper implementation.

**Pros**
- smallest path to green CI
- keeps root-cause fix scoped to the failing assumption
- separates urgent recovery from deeper design improvement
- easier to review and verify

**Cons**
- implementation complexity remains temporarily until Phase 2 is taken

### Option B — Fix the test and refactor the helper in one change

Rewrite the unit test and simultaneously refactor `_discover_provider_env_vars()` into smaller helpers or a simpler command shape.

**Pros**
- may leave the area cleaner immediately
- can align tests and implementation in one pass

**Cons**
- larger diff
- harder to tell whether CI recovery came from test isolation or implementation behavior changes
- increases scope under a currently failing branch

### Option C — Change CI environment instead of the test

Attempt to preserve the test by changing workflow shell setup or GitHub Actions environment handling.

**Pros**
- minimal code diff in application/tests

**Cons**
- treats CI environment as the bug even though the unit test is over-coupled to shell startup behavior
- likely brittle across runner/action updates
- does not improve local determinism

## Decision

Choose **Option A**.

The immediate fix should target the unstable assumption in the unit test. Implementation hardening should be documented and intentionally scoped as follow-up work, not implicitly bundled into the CI recovery change.

## Phase 1 — CI recovery design

### Intent

Convert the failing test from an environment-coupled shell integration test into a deterministic unit test.

### Files in scope

- `tests/unit/test_preflight.py`
- `src/model_bridge/adapters/subprocess_adapter.py` only if a tiny, test-enabling change is strictly necessary

### Design

Replace the current test strategy:

- current strategy: patch `os.environ`, invoke real login shell, expect specific env vars to survive startup behavior

with a subprocess-boundary strategy:

- mock `subprocess.run()` to return controlled stdout/stderr payloads
- verify `_discover_provider_env_vars()` correctly parses multiple provider env vars from stdout
- keep the test focused on the helper's actual responsibility: handling command result text and filtering/collecting valid env entries

### Expected test shape

Required coverage in Phase 1:

1. **multiple discovered values**
   - mocked stdout contains at least `GOOGLE_API_KEY=...` and `OPENAI_API_KEY=...`
   - function returns both values

2. **empty values ignored**
   - mocked stdout contains blank-valued entries
   - function excludes them

3. **non-zero shell result ignored**
   - mocked subprocess returns non-zero
   - function falls through safely / returns empty dict unless a later shell succeeds

4. **next-shell fallback behavior preserved**
   - first mocked shell gives no usable output
   - next mocked shell returns valid env payload
   - function returns discovered values

### Why this is sufficient for CI recovery

The current CI failure is caused by a unit test asserting behavior outside its control boundary. By mocking the subprocess boundary, the test stops depending on GitHub Actions login-shell startup behavior. That directly removes the unstable dependency causing the CI red state.

## Phase 2 — Optional implementation hardening design

### Intent

Reduce shell-semantic sensitivity inside `_discover_provider_env_vars()` and make future tests easier to write and reason about.

### Files likely in scope

- `src/model_bridge/adapters/subprocess_adapter.py`
- `tests/unit/test_preflight.py`

### Hardening candidates

#### Candidate 1 — Extract stdout parsing into a pure helper

Example shape:

- `_parse_provider_env_output(stdout: str) -> dict[str, str]`

Then test parsing independently from shell invocation.

**Benefits**
- isolates deterministic logic
- makes malformed/blank/unsafe-name cases easier to test directly
- reduces need for shell-heavy unit tests

#### Candidate 2 — Simplify shell command construction

Replace the long chained `&&` / `||` expression with a more explicit loop or shell snippet whose stdout shape is easier to reason about.

**Benefits**
- lowers dependence on nuanced shell operator behavior
- makes command intent clearer

**Constraint**
- any shell rewrite must preserve the existing production contract: discover only whitelisted env vars, avoid logging values, and keep timeout/error behavior bounded

#### Candidate 3 — Narrow integration coverage intentionally

If real-shell behavior still deserves coverage, add a clearly labeled integration-style test that is optional, narrowly scoped, or resilient to environment differences. Do **not** keep that behavior disguised as a pure unit test.

### Phase 2 recommendation

If Phase 1 restores CI cleanly, Phase 2 should be evaluated as a separate small follow-up rather than forced into the same recovery patch.

## Risks and trade-offs

### Risk: Phase 1 could hide a real production issue

Mitigation:
- Phase 1 only changes the test strategy if the implementation contract remains the same
- preserve or add targeted subprocess-result tests for non-zero return, fallback, and blank values
- keep Phase 2 documented so implementation review is not forgotten

### Risk: helper behavior is actually wrong in production too

Mitigation:
- treat Phase 2 as an explicit follow-up item
- if Phase 1 investigation reveals real production misbehavior while implementing the test fix, stop and re-scope before bundling larger refactors

### Trade-off accepted

This design intentionally prioritizes deterministic CI recovery over immediate cleanup of all shell-related design rough edges.

## Validation plan

### Phase 1 validation

Run at minimum:

```bash
PYTHONPATH=src pytest -q tests/unit/test_preflight.py::test_discover_provider_env_vars_collects_multiple_values
PYTHONPATH=src pytest -q tests/unit/test_preflight.py
PYTHONPATH=src pytest -q tests
pre-commit run --all-files
```

Expected result:

- the previously failing preflight test passes
- no regression in the rest of the suite
- pre-commit remains green

### Phase 2 validation (if taken)

Add targeted tests for any extracted parser helper or rewritten shell-command construction, then rerun the same full validation gate.

## Implementation guidance

- Keep the first patch as small as possible.
- Do not mix README/docs cleanups into the CI recovery diff.
- Do not treat runner-specific shell/profile behavior as the unit under test in `tests/unit/`.
- If a real integration test is desired later, make that explicit in naming and scope.

## Follow-up decision gate

After Phase 1:

- if CI is green and the helper contract is adequately covered, Phase 2 can be deferred safely
- if investigation during implementation uncovers production-facing helper ambiguity, Phase 2 should be scheduled immediately as a focused second change
