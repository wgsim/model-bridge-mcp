# ask-general-workflow

## Goal
Handle standard user asks with minimal routing overhead.

## Trigger
Use when no specialized workflow trigger is stronger.

## Steps
1. Normalize ask options (`timeout`, `verbosity`, `response_format`, `stream`).
2. Select provider (`auto` unless user pins provider/model).
3. Execute ask and return concise result.
4. Preserve routing log in response.

## Output Contract
- Human-readable answer by default.
- JSON only when explicitly requested.

## Guardrails
- Do not invent provider/model IDs.
- If provider is unknown, return provider error with valid options.
