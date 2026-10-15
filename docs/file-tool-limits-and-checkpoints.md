# File-backed tool delivery and checkpoint recovery

New frozen file-pipeline runs enforce an 8,192-byte aggregate limit on each
model-facing IPython result (content plus delivery metadata). The runtime hook
runs before the result enters the session. It removes duplicated tool details.
Oversized text is saved intact under the private job's `tool-output/`, with a
hash-bound locator in `delivery.jsonl`. Use `ctx.output(id, start, limit=768)` to
read it in bounded pages. A second pre-provider guard rejects oversized results
that bypass the hook. Unsupported non-text content cannot satisfy coverage.

Source API reads in an oversized result earn no coverage until every overflow
page has itself been delivered. Partial pages, unresolved recursive overflows,
and search previews do not establish full inspection. Original source and
candidate hashes, independent review, and the two correction rounds still apply.

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
