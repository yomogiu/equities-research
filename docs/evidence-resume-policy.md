# Resuming a saved review evidence request

A new correction edition may use `--reuse-proposal --resume-evidence` to retain
an authenticated saved `needs_evidence` response. The v2 binding accepts one or
two completed original requests, verifies each using its bound original runner,
and supplies the exact requested source scopes with the unchanged candidate and
plan. An incomplete launch, missing first response, final review verdict, or
unexpected additional lookup fails closed. Original source and job files remain
unchanged. All earlier reviewer sessions are excluded from fresh review.

By default the new edition retains the original token ceiling. An explicitly
authorized token-only policy may remove that ceiling using
`--evidence-token-authorization PRIVATE_JSON`. The policy must contain exactly:

- `version: evidence-token-policy-v1`, `enabled: true`, and
  `scope: token_ceiling_only`.
- The original `source_protocol_sha256` and `prior_max_tokens`.
- `max_tokens: null`, exact `prior_rounds` and `inherited_tokens` from authenticated
  export, and nonempty `authorized_by` and `reason`.

The coordinator must obtain actual user authorization before reserving this
file. A model-provided reason is not authorization. The new protocol freezes its
path and bytes, and replay validates the original accounting again. This option
cannot reset rounds, erase usage, change sources, discard requested evidence,
expand the correction allowance, or approve the report. Two original correction
rounds remain the maximum. Prompt-size limits and independent acceptance remain
in force. Earlier v1 evidence bindings keep their original replay behavior.

Keep policy files and all real sources, prompts, receipts and reports private.
