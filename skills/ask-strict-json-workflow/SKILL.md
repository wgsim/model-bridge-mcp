# ask-strict-json-workflow

## Goal
Produce parse-safe JSON responses for automation paths.

## Trigger
Use when structured output is mandatory.

## Steps
1. Enforce `response_format=json`.
2. Bind to required schema keys.
3. Reject extra wrappers/markdown.
4. Validate parseability before returning.

## Output Contract
- Valid JSON object only.

## Guardrails
- No markdown fences.
- No free-text preamble/postamble.
