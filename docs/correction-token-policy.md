# Correction usage policy

New deterministic correction editions default to `max_tokens: null`: no token
spending cap and no byte-based admission rejection. The CLI may still set an
explicit finite cap with `--max-tokens`.

At most two correction rounds remain available across ordinary continuations.
Removing a token cap does not reset used rounds, previous usage, source bindings,
independent review, prompt-size bounds, or uncertain-execution protection.
Measured authenticated usage is recorded even when uncapped. This setting applies
to correction authors and reviewers; it does not change signal-stage policies.

Frozen runs retain their original code and policy. To unblock a previously capped
run, initialize a new correction continuation with this code, retaining its source,
used rounds and inherited usage. Never edit the old protocol or restart its calls.

## Local token diagnostics

Install the optional `requirements-token-counting.txt` in a separate environment,
then run `python scripts/count_prompt_tokens.py /private/run --encoding o200k_base`.
Directories scan only `prompt.txt`; files count their exact UTF-8 text. Use
`--output /private/new-counts.json` to save a new receipt. Counts and hashes are
returned, never prompt contents. Keep paths and diagnostics private.

Use `--model` when tiktoken recognizes the model. Unknown aliases require an
explicit `--encoding`; that is a disclosed assumption, not a verified model
mapping. Tokenizer data may download on first use; text is encoded locally and
is not sent to a model. No account login/API key is needed. This diagnostic does
not change admission, the uncapped correction policy, or the two-round limit.

Use these counts to compare prompt sizes and compaction. Actual usage receipts
remain authoritative for runtime framing, generated reasoning/output, caching,
and repeated calls. See https://developers.openai.com/api/docs/guides/token-counting.

New role executions write `token-estimate.json` before launch and bind its hash
in `launch.json`. Successful `execution.json` records `token_accounting` alongside
the authenticated session usage, separating estimated prompt tokens, recorded
input including cache, output and total. Replay verifies these bindings without
recounting with a potentially different tokenizer version.

Run the Python worker from an environment with the optional tokenizer requirement
installed for tiktoken counts. Unmapped aliases explicitly assume `o200k_base`.
If the dependency or tokenizer cache is unavailable, a labelled bytes/4 estimate
is recorded. Neither method blocks a call. Failed calls retain their preflight
estimate; missing actual usage remains unavailable, never inferred to be zero.
