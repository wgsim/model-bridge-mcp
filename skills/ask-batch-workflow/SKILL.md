# ask-batch-workflow

## Goal
Execute multiple independent ask tasks and aggregate deterministic results.

## Trigger
Use when request contains multiple prompts/jobs.

## Steps
1. Normalize each job payload.
2. Execute jobs in declared order (Phase 1 baseline: sequential).
3. Collect per-job status, output, and error.
4. Return aggregate summary + job-level details.

## Output Contract
- Stable list of results with `job_id`, `status`, `content|error`.

## Guardrails
- No silent drop of failed jobs.
- Preserve per-job provenance.
