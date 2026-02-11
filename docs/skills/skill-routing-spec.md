# Skill Routing Spec

## Purpose
Define deterministic routing from user prompt intent to workflow skill.

## Language Policy
- Detect input language (`ko`, `en`, fallback `en`).
- Keep response language aligned with user input unless explicitly overridden.
- Keep code, identifiers, CLI commands, and schema keys in English.

## Routing Priority
1. `ask-strict-json-workflow`
2. `ask-code-writing-workflow`
3. `ask-review-workflow`
4. `ask-batch-workflow`
5. `ask-provider-routing-workflow`
6. `ask-general-workflow`

## Trigger Rules
### ask-strict-json-workflow
- Trigger when prompt includes: `json`, `schema`, `parse`, `strict format`, `machine readable`.
- Also trigger when caller provides explicit `response_format=json` requirement.

### ask-code-writing-workflow
- Trigger when prompt includes: `implement`, `write code`, `refactor`, `patch`, `fix bug`.
- Trigger for requests that change repository files.

### ask-review-workflow
- Trigger when prompt includes: `review`, `audit`, `risk`, `regression`, `code review`.
- Output must prioritize findings and severity.

### ask-batch-workflow
- Trigger when prompt includes: `batch`, `multiple prompts`, `run all`, `matrix`, `bulk`.
- Trigger when request has two or more independent ask tasks.

### ask-provider-routing-workflow
- Trigger when prompt includes: `provider`, `model selection`, `fallback`, `routing`, `capability`.

### ask-general-workflow
- Default when no higher-priority trigger matches.

## Confidence Gate
- If two or more skills have close score (difference <= 1), route to `ask-provider-routing-workflow` for explicit decision.
- If confidence is low, request a one-line clarification.

## Assumption
Provider/model capabilities can evolve quickly; catalogs must be treated as configurable data, not constants.
