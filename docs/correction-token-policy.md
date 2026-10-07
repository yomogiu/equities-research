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
