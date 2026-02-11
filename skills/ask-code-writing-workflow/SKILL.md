# ask-code-writing-workflow

## Goal
Support implementation tasks with explicit task partition and low-conflict flow.

## Trigger
Use when request requires code creation/modification.

## Steps
1. Define target files and acceptance criteria.
2. Split work into independent chunks (no overlapping file ownership).
3. Run ask per chunk and consolidate patch plan.
4. Validate with tests/lint hooks before completion.

## Output Contract
- Concrete change list, then validation results.

## Guardrails
- Avoid overlapping edits in parallel tracks.
- Keep diffs minimal and reversible.
