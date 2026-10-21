# Bounded wrapper reliability

This patch preserves model selections, token caps, tool allowances, two-resume
limits, correction limits, source coverage and independent review requirements.
It does not authorize retries of uncertain provider execution.

Fresh launches create an empty retrieval audit before validating resume lineage
or starting a worker. This makes restore-only work explicit without synthesizing
source reads. Existing attempts and their logs are never repaired in place.

Pre-submit validation returns all unknown Q&A exchange IDs and the exact allowed
IDs together. It never guesses bindings, edits a draft or grants acceptance.
The existing reserved validation call is sufficient; no extra call is allocated.

Workers append sanitized fetch lifecycle events to transport-lifecycle.jsonl.
Events record only sequence, phase, allowlisted failure codes and conservative
execution certainty. Header receipt is not stream completion or a completed
model turn. Response objects and bodies pass through untouched. Instrumentation
failure cannot trigger a retry or replace the original error. Provider error or
aborted turns are classified under model_request, not output_validation.
Parent-enforced timeouts have an explicit worker_timeout execution receipt.

## Activation

Use a compatible code-pin transition at a company boundary after checking worker
and coordinator locks. Never change the checkout of an active frozen request.
Existing failed attempts require the established authenticated successor flow,
with consumed usage carried forward; they do not automatically inherit this fix.
Transport-uncertain holds remain blocked pending execution reconciliation.

Before broad activation, verify a bounded successor with inherited evidence and
a draft with corrected exchange references. Compare tokens, validation failures,
completion receipts and independently reviewed output under the original caps.
Synthetic tests do not establish live throughput or authorize clearing holds.
