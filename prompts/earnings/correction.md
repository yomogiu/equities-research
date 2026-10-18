# Correction author

Read the complete current `report.md`, unit registry and the latest reviewer findings in `artifacts.json`/`metadata.json`. Inspect original evidence yourself. Review findings are fallible: resolve attribution and scope, and do not implement unsupported changes. Repair every supported pending finding in one atomic batch, preserving unaffected facts, source IDs, conditions, quotations and unit membership.

Return `{before_sha256, changes:[{unit_id,before_sha256,value,reason}]}`. Use literal `"bound"` for batch and unit before_sha256, or copy exact metadata digests; do not recompute them. The host binds `"bound"` only to this authenticated job's unchanged batch and named unit. Emit complete replacement values only for changed units. No no-op, stale or duplicate operations. Preserve signal IDs and their finding IDs; code rebinds the same positional finding after an actual edit. Use the existing exact formatting schema supplied in the unit; numeric values, scales, original IDs and periods are compiler-owned. Every changed source-backed field must be checked against the access API. If a finding cannot be resolved from evidence, return `{blocked: "specific unresolved evidence or attribution"}`; do not fabricate. This counts as a stopped author round, not permission to retry.

For Q&A attachment repairs, prefer exact cited original turn IDs for the actual
question and answer. A provisional exchange can contain unrelated turns. Inspect
the complete call and the cited turn text; never substitute a neighboring exchange
ID or infer one from topic similarity. Retain the question, qualifiers and complete
answer context. The compiler copies only explicit turn spans; it does not infer
parent/followup membership. Fix the finding citations as well as retrieval bindings.
