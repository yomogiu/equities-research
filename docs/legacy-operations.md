# Handoffs and acceptance

### Explicit current-event preparation

`earnings_event_preparation.prepare` is a separate opt-in source route for a
qualified current earnings release and full transcript when the quarterly
periodic filing is unavailable. Ordinary `earnings_report_flow.prepare` still
requires its original full current-period periodic filing. The event route
requires an independently reviewed, hash-bound SEC 8-K companion that links the
exact qualified release, with original issuer/form/listing/period evidence and a
fresh matching HTTP observation. Its release financial cells must have the
existing distinct-author/reviewer profile authorization. It discovers neither
profiles nor evidence and never launches a model or creates report eligibility.

The case retains the release as a release and the companion as a current report;
it never relabels an older periodic filing. Original raw/text evidence, profile
and source reviews, observations and the explicit selection are frozen inputs.
Source/profile approval does not establish report acceptance. The coordinator
must separately authenticate the reservation, complete source qualification,
account for every preparation/report session under the original allowance and
retain fresh independent full report review and exact private completion proof.

Use private storage with a stable namespace, for example:

```text
watchlist.json
calendar/<as-of>/calendar.json + calendar.md
queue/<issuer-period>.json
packets/<issuer-period>/<packet-id>.json
runs/<run-id>/<role>/result.json
reports/<issuer-period>/<packet-id>/<revision>/report.json + report.md
receipts/<run-id>.json
```

These are logical paths in a private service, not files to add to this repository.
Each cloud task must restore the relevant inputs and write back its results through
that service. Restoring a local copy alone does not establish durable persistence.
The CLI accepts private paths and refuses to render a report inside this checkout.

Record run ID, task/session identity when exposed, stage, source cutoff, artifact
locations/hashes, review status, superseded report, and next retry time. Use the
storage service's conditional writes or a single-writer queue to prevent two tasks
from publishing competing accepted versions. The workspace implements local file locks, fenced leases and fast-forward Git claim
publication before dispatch. Use one coordinator; this is not a general distributed
queue or exactly-once execution engine. See [workspace.md](workspace.md).

Acceptance needs all three: an agent's substantive rubric review, exact-source/schema
validation, and verified private persistence. A stopped task, a successful CLI exit,
or a polished report is not sufficient. Codex has no use of Anthropic's outcome API
here; the Codex coordinator follows the rubric and explicit repair procedure.

Every material quote keeps its document ID, verbatim text, speaker, and locator.
Every metric keeps its original passage, period, currency, unit/scale, and basis.
Interpretations distinguish company claims, facts, and inference, with counterevidence
and uncertainty. Review criteria assess evidence quality, not optimism or agreement.

Maintain a finite run capacity and bounded revisions. Codex subscription limits are
shared with other use. On interruption, preserve receipts and resume incomplete work;
do not recreate already accepted packets or assume an unlimited unattended budget.

Live research starts only after a reviewed watchlist, public-source network access,
private storage, and an actual cloud task invocation have been verified. The fake
example is for tests only and must never be queried as a real company.


## Batched report repair

The initial independent audit lists every material defect in one correction batch,
including repeated claims across financial context, retrieval summaries and prose.
Corrections are hash-bound field patches; financial observations and selected
quotations remain fixed. Claim groups enumerate every matching occurrence and require
an explicit repair or a reason to retain it. This check does not infer semantic
similarity; the author and reviewer must choose the complete aliases and affected fields.

Subsequent reviews receive the complete rendered report, exact field changes, pending
findings and original passages cited by the complete report, with source hashes and
character offsets. Supplying all direct report citations up front avoids a second
lookup for unchanged claims. Review prompts are bounded at 350,000 characters.
Repeated source spans share one source block. The original full-source audit stays
in the immutable history. A reviewer can request exact source IDs once; that evidence
expansion consumes measured tokens but no correction round. Insufficient evidence,
failed provenance, an uncertain launch or an exhausted budget cannot become acceptance.

The reviewer approves the exact staged candidate. Python applies the approved patch
and renders the result; no author rewrites follow acceptance. Optional
`format.layout` (`compact-financial-v1`) folds compatible ratio rows into monetary
rows and moves secondary tables into expandable detail while retaining every original
value and citation. Independent signal review and private persistence remain required.
Historical pinned runs replay with their original code. Explicit v2 remediation
editions may descend from a conclusively stopped correction or remediation run; they
preserve the entire prior history and cannot retry an unchanged candidate or fork a
second descendant from the same source.

Correction application retains exact idempotent instructions for independent review.
A citation-only change may preserve the sentence while updating its support. Actual
before/after values determine whether a field changed; an author label cannot mark
a changed field as unchanged. Claim groups can reference exact existing metadata
paths for paraphrases or display fields without a literal phrase match. All literal
matches still need a proposed operation or an explicit disposition. Unknown paths,
stale hashes, altered observations and unadjudicated repeated claims remain errors.
This never grants acceptance: the reviewer receives each retained instruction, every
actual delta and the original findings, and must approve the exact report.

### Scoped transcript currentness

A changed market quote on a recognized transcript page can be checked separately
from the archived call. The scoped-currentness verifier requires exact complete
speaker blocks, fiscal metadata and all extracted text outside one structurally
identified market widget. It archives the new raw page and extracted text, binds
the actual HTTP observation and original qualification, and retains every original
source hash and evidence offset. New packets state the scoped freshness basis;
materialization replays the proof and rejects conflicting newer observations.
This never asserts that changed full-page text or bytes are identical.

Repair review metadata uses a lossless columnar passage index to avoid repeated
field names. Original evidence and Unicode offsets remain available in full.
Explicit formatting remediation may correct table captions and period labels with
source citations, while preserving numeric values, units, periods and group identity.


### Batched call inspection

File-backed roles use `print(ctx.call_batch())` to show the original transcript
once, with compact citation offsets and provisional Q&A annotations. For calls
longer than 48,000 characters, follow `next_start` in the same IPython call when
practical. The overlapping exchange, section, turn and quotation representations
are locators rather than repeated source paragraphs. Coverage projects only to
hash- and offset-equivalent transcript spans after the full call is delivered;
filings and financial rows still require their own evidence reads. Merely loading
a batch into kernel memory does not satisfy inspection. Reviewers inspect their
own fresh-context batch. Historical frozen runs retain their original API.

Measure retrieval changes in one fresh retrieval-only job with an explicit token
budget, tool-call bound and no automatic retries. Record input, output, cache-read,
cache-write, model turns and source coverage, including failed attempts. Do not
advance analysis or restart the batch as part of this measurement.

The IPython runtime independently truncates outputs at 65,536 characters. Call
batches therefore fit within 60,000 characters including compact locator tables,
and expose next_start for any remaining source text. Do not concatenate batches
or other prints beyond that total in one tool result. A delivery-hook setting
does not remove the runtime truncation. Missing exact batch text earns no credit.


### Filing retrieval without exact-query dead ends

Use `print(ctx.filing_batch(query, limit=4))` in a separate tool response from the
call batch. It ranks individual query tokens over the complete D-excerpt inventory,
prefers source-document diversity, omits duplicate and overlapping text, and prints
whole excerpts with their original provenance and exact D IDs. Empty matches trigger
an explicitly marked representative fallback, not a claim that evidence is absent.
If no eligible excerpts exist, record a source-access gap; nonempty document selection
remains required for a completed retrieval. Oversized scopes are counted separately
and remain available through paged access. Selection is not acceptance or exhaustive
filing review. Only complete visible, replay-verified batches gain coverage credit.
`ctx.search` retains its original exact literal semantics for historical replay.


Live role bootstraps use `Evidence.for_job()`, deriving the context and canonical
retrieval log from the runner-owned request in the kernel working directory.
Direct construction in an active role also binds that log and rejects a different
context. Historical offline audit contexts remain replayable. Full lifecycles use
their explicit lifecycle budget; small retrieval-trial ceilings are not inherited
as full-run ceilings. The conservative pre-turn input/output reserve remains in
force; cached input and prior attempts remain counted.


A completed retrieval stopped by the exact `{finding, document_id}` transport
shape can continue through an explicit preparation manifest. The caller replays
the original frozen verifier and coverage, performs only the lossless conversion
to `{text, citations}`, and validates the complete canonical retrieval including
Q&A grounding. A new immutable continuation carries the original token ceiling,
all spent tokens and the retrieval session identity. Authors and reviewers remain
fresh. Original requests, sessions and outputs are never edited; unknown or mixed
schemas are rejected rather than repaired by guesswork.


### Host-enforced progress and final-writing phase

New role requests bind an execution policy: three tool calls for financial,
retrieval, analysis and signal roles; four for reviewers and correction authors.
Batch required evidence within that plan. The host uses Responses `tool_choice=none`
after the allowance, or earlier when another maximum-output reserve no longer fits,
so the next turn writes the result instead of adding another exploration round.
An unexpected tool call in final-writing mode is blocked and cannot pass replay.
This follows the final-request pattern in the official OpenAI agent optimization
example: https://developers.openai.com/cookbook/examples/agent_optimization/optimizing_agents_for_cost_and_quality

After every tool result, the host independently checkpoints the delivered evidence
prefix and records its bound receipt. It preserves authored partial work if supplied;
otherwise it labels the checkpoint source-progress-only, with no invented prose or
acceptance authority. Resume retains all spent tokens, dependencies and the two-resume
limit. Missing, altered or stale checkpoint receipts fail closed. Source-progress
recovery still requires the new model to inspect material text for interpretation.
The lifecycle ceiling and conservative output reserve remain unchanged. These
controls cannot retroactively reconstruct an unsaved draft from a historical run.


Completed author output can likewise continue through a separately bound analysis
manifest when its only issue is source addressing. Exact passage references in
citation lists map to their original parent scopes; the transcript document identity
maps to all its original call sections. Unknown IDs remain errors. Text and quote
selections are unchanged. The original frozen verifier replays the author receipt,
normalizes addressing, and verifies original inspection and all author validation.
The new lifecycle retains both session IDs and the combined inherited usage; it
cannot raise the original ceiling or bypass fresh signal/review work.


### Typed, paged role packets

Use handoff_batch for the whole report, metadata and relevant handoffs. Signal
handoffs contain the finding catalogue rather than a duplicate of the entire state;
review handoffs contain unit values rather than repeating both units and state.
Use call_batch for the complete call and support_batch for all referenced non-call
support. Each role packet is at most 59,000 body characters, with next_start when
more remains. Full delivered ranges, not kernel loads, determine coverage.

Signal authors may instead use source_batch with exact selected scope or passage
IDs after choosing material findings. It prints complete original parent scopes,
original provenance, selected context/unit data and exact passage locators. This
avoids a whole-call reread for a narrow signal selection. Reviewers still inspect
all required original evidence. Support packets deduplicate source blocks and file
identities without changing original text. Missing pages receive no coverage.

The early-finalization margin is 65,536 tokens above the registered maximum-output
reserve, rather than another full maximum output. The hard conservative reserve
and cumulative token accounting remain in force. A continuation may lower its
ceiling to deduct a verified failed sibling's usage; it cannot raise the inherited
ceiling. This preserves lost-attempt charges without rerunning a validated author.
