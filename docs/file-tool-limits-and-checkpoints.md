# File-backed tool delivery and checkpoint recovery

New frozen file-pipeline runs have no enforced tool-response byte limit. The
runtime delivers complete text results and still saves hash-bound private
`tool-output/` copies and delivery receipts. Duplicate tool details remain
removed. `max_tool_response_bytes: null` explicitly records the uncapped policy.
Normal source API paging and small-print guidance remain available.

Historical frozen runs retain their original 8,192-byte cap and spill receipts.
Partial pages, unresolved recursive overflows, and search previews do not
establish full inspection. Unsupported non-text content cannot satisfy coverage.
Original source and candidate hashes, independent review, checkpoints, token
budgets and the two correction rounds remain unchanged. Removing the response
cap does not change the registered 128,000-token output reservation used by the
separate token-budget guard.

Call `ctx.checkpoint(draft_dict, pending_list)` after material progress. It saves
an immutable, bounded partial draft plus pending work and exact retrieval-prefix
hashes. Checkpoints contain unreviewed data, not approval or execution authority.
`ctx.restore()` loads a bound checkpoint into a new kernel. All source files stay
outside the prompt. An inventory is paged rather than printing every fact ID.

The caller advances at most one new attempt per invocation. A recorded local
budget stop or deliberate checkpoint yield can resume only after complete tool
pairing, provider usage, delivery receipts and unchanged dependencies are checked.
Timeouts, uncertain launches and unknown provider failures never auto-retry.
Recovery uses fresh sibling jobs (`--resume-1`, `--resume-2`), preserving previous
requests, journals and token spend. It stops after two resumptions, absent a
checkpoint, or without changed draft/pending work. Remaining allowance can only
decrease. Finished roles are replayed, not relaunched. Reviewers can recover
only their own identical candidate context, never an author's inspection credit.

This changes new code pins only. Historical frozen attempts are not migrated or
retrofitted with checkpoints. A checkpoint does not by itself wake a caller;
the existing bounded coordinator must invoke the next advance. Use the optional
`yield_checkpoint=True` runner setting for a controlled recovery pilot, where the
next provider turn stops after a checkpoint has been written.

Separately authorized pilot calls are recorded as source-bound usage debits.
Recovery verifies both the interrupted and completed pilot receipts, adds their
measured usage to inherited spend, and freezes the debit and supporting private
artifacts. Testing never creates a fresh company allowance.

A user may explicitly remove the cumulative cap for one trial. Initialize with
`max_tokens=None` and an immutable `budget_authorization` file binding that issuer,
period, the user's request and the prior measured-usage proof. Prior usage remains
in every cumulative total. The normal default remains 1.2M tokens. Per-role 1.2M
token limits, tool-call limits, checkpoint lineage, source checks, independent
review and two correction rounds remain in effect. Such approval creates a new
frozen trial; it never edits an old request or protocol. A source-bound previous
checkpoint may be supplied as unreviewed preparation data, without inheriting
another context's inspection or approval credit.

Large structured `financial.json` and `transcript-index.json` files load through
`ctx.load_structured(name)` into kernel memory. That returns counts and the kernel
attribute name, not thousands of raw observations/HTML snippets. Project needed
fields from `ctx.financial_data` or `ctx.transcript_index`; inspect cited originals
with the existing fact, scope and table-row methods. This avoids automatic full
extraction dumps without reinstating a tool-response byte cap or hiding evidence.
Complete call pages may be batched within a tool invocation to avoid dozens of
model turns spent walking 768-character transcript fragments.
