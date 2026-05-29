# agy quota/empty-output handling design

## Goal
Make `ask_agy_cli` return an explicit, conservative provider error when `agy` exits without a usable response, while distinguishing confirmed quota/rate-limit signals from ambiguous empty-output states.

## Problem statement
The `agy` CLI may sometimes return one of these problematic runtime shapes:

1. explicit rate-limit/quota text in stdout or stderr
2. timeout / hang
3. non-zero exit with error output
4. exit code `0` with empty stdout/stderr

Today, the last case is especially problematic because it can look like a silent success or a confusing no-response state. Even when quota exhaustion is the most likely cause, the system cannot honestly claim that with certainty unless `agy` emits a recognizable marker.

## Non-goals
This design does **not** try to:
- implement provider fallback away from `agy`
- auto-retry ambiguous empty-output cases
- redesign the broader MCP transport layer
- change unrelated provider behavior

## User-facing behavior
`ask_agy_cli` should classify outcomes conservatively:

### 1. Confirmed quota / rate-limit
If stdout or stderr contains a known rate-limit/quota marker, return a provider error that clearly says quota/rate-limit is confirmed.

Example:
- `[PROVIDER ERROR] agy quota or rate-limit exceeded.`

### 2. Possible quota / empty provider response
If `agy` exits successfully but produces no usable stdout/stderr payload, return a provider error that does **not** overclaim the root cause.

Example:
- `[PROVIDER ERROR] agy returned no output (possible quota/rate-limit or empty provider response).`

### 3. Generic provider failure
If `agy` times out, exits non-zero, or returns malformed output, preserve the existing failure behavior but ensure the message remains explicit.

## Detection rules
Detection should be applied in this order:

1. **Known quota markers**
   - inspect stderr first, then stdout
   - use a small allowlist of substrings such as:
     - `quota`
     - `rate limit`
     - `usage limit`
     - `limit exceeded`
   - keep the marker matcher easy to extend

2. **Timeout**
   - preserve timeout handling as a distinct provider failure

3. **Non-zero exit**
   - preserve explicit subprocess failure capture

4. **Exit 0 + empty output**
   - classify as `possible quota/rate-limit or empty provider response`

## Implementation shape
Keep the change tightly scoped to `agy` execution surfaces.

### Primary files
- `src/model_bridge/adapters/subprocess_adapter.py`
- `src/model_bridge/main.py` only if the classification must be surfaced above the adapter boundary
- `tests/unit/test_agy_provider.py`

### Preferred design
Add a small helper near the subprocess adapter’s `agy` path that:
- inspects exit code
- inspects stdout/stderr text
- returns either:
  - normal success body
  - confirmed quota error
  - possible quota/empty-response error
  - generic failure

Avoid introducing a large new abstraction unless multiple providers will reuse it immediately.

## Testing strategy
Add focused unit coverage for `agy` only.

Required cases:
1. stderr contains known quota marker → confirmed quota/rate-limit error
2. stdout contains known quota marker → confirmed quota/rate-limit error
3. exit 0 + empty stdout/stderr → possible quota/rate-limit or empty provider response
4. normal stdout body → existing success path preserved
5. non-zero exit with stderr → existing failure path preserved
6. timeout path → existing timeout behavior preserved

## Logging and diagnostics
If practical within the same diff, log or preserve enough context to differentiate:
- exit code
- stdout length
- stderr length
- whether a known quota marker matched

Do not expose sensitive tokens in logs. Reuse existing masking/error formatting patterns where possible.

## Trade-offs considered

### Option A — Conservative classification only (recommended)
Pros:
- smallest diff
- low false-positive risk
- improves operator clarity immediately

Cons:
- ambiguous cases remain ambiguous

### Option B — Retry once before failing
Pros:
- may absorb transient provider hiccups

Cons:
- increases latency
- still does not prove quota root cause
- expands scope beyond the immediate contract problem

### Option C — Fallback to another provider
Pros:
- smoother user experience in some cases

Cons:
- changes `agy` semantics substantially
- blends provider isolation and failover policy
- out of scope for this fix

## Decision
Choose **Option A**.

## Acceptance criteria
This design is complete when:
- `ask_agy_cli` does not silently succeed with an empty response
- quota is only called “confirmed” when a known marker is present
- ambiguous empty-output cases produce a conservative provider error
- existing successful `agy` responses still work unchanged
- focused `agy` tests cover all new branches
