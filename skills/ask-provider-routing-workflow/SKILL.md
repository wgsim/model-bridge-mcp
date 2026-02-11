# ask-provider-routing-workflow

## Goal
Choose provider/model/fallback path using explicit policy.

## Trigger
Use when request asks about provider capabilities, model selection, or routing policy.

## Steps
1. Resolve requested provider/model.
2. Check provider availability and configured catalogs.
3. Apply fallback policy when model/provider fails.
4. Return routing decision and rationale.

## Output Contract
- Selected provider/model.
- Fallback chain and reason.

## Guardrails
- Never claim unsupported models.
- Prefer config-defined catalog and runtime checks.
