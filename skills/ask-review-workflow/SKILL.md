# ask-review-workflow

## Goal
Run analysis/review tasks and return issue-first findings.

## Trigger
Use for code review, design review, risk audit, and regression checks.

## Steps
1. Identify artifact scope and risk level.
2. Run analysis-focused ask with deterministic options.
3. Report findings ordered by severity.
4. Add assumptions and validation gaps.

## Output Contract
- Findings first.
- Then open questions and short summary.

## Guardrails
- Do not hide uncertainty.
- Prefer reproducible evidence and file references.
