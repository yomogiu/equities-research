# Transcript-led earnings experiment

This experimental branch adds a bounded earnings research workflow. It is separate
from production collection, qualification, schedules, reports, and dashboard counts.
Real company inputs, extracted facts, task transcripts, reports, and measurements
belong exclusively in the private runtime. Public tests use fictitious evidence.

The experiment tests a complete report, not just financial extraction. Its sequence is:

1. Freeze an authorized case containing an unchanged transcript, financial filing,
   source-linked financial observations, and a reviewed transcript index.
2. Run a financial extractor and Q&A commentator in separate Prime Agent sessions.
   Both receive the same frozen inputs; neither receives the other's first draft.
3. Run an independent substantive reviewer against originals and both outputs.
4. Compose a coherent report in a separate editorial session.
5. Review the exact composed report and summary in a final independent session.
6. Verify source and output hashes, distinct session receipts, review decisions,
   dependencies, and exact accepted report bytes.

There are **at most two correction rounds shared across both review stages**, not two
rounds per stage. A material failure, blocked review, or exhausted correction budget
prevents acceptance. Schema validation is not substantive review.

## Components and APIs

### Financial evidence

`research.financial_evidence` provides:

- `extract_inline_xbrl(raw_html, source)` and
  `extract_inline_xbrl_file(path, source)`: extract numeric inline-XBRL observations.
  The source requires `document_id` and `raw_sha256`. The file helper checks the
  original bytes before UTF-8 decoding. An optional `entity_identifier` constrains
  the context entity to the supplied identifier.
- `propose_fact(text, source, concept=..., value=..., context=..., unit=...,
  quote=..., start=...)`: prepare a manual fallback with exact source support.
  `source.text_sha256` is required. These records remain `proposed`.
- `make_artifact(source, observations, gaps=None)`: seal a versioned artifact.
- `validate_artifact(artifact, trusted_sources)`: check artifact and observation
  hashes, numerical/provenance requirements and caller-owned source bindings.
  `trusted_sources` maps each document ID to its expected raw/text hashes.
- `rebuild_database(db_path, artifacts, trusted_sources)`: validate all artifacts
  before atomically rebuilding the SQLite projection.
- `query_facts(db_path, concept=None, period_end=None, context_id=None,
  document_id=None, include_proposed=False, limit=100)`: parameterized, read-only
  queries, bounded to 1–1,000 returned observations.

Values are finite Decimal strings; no binary floating-point conversion is needed.
Each record preserves taxonomy concept, optional allowlisted canonical metric,
entity, period start/end or instant, dimensions, numerator/denominator unit,
original decimals/scale/sign, and source span. When present, bounded table-row text
also carries original offsets and a source-span hash. Offsets are Unicode character
positions, not byte positions.

A shared period end does **not** establish comparable durations: quarterly and YTD
facts coexist, as do consolidated and segment contexts. Inspect start dates,
dimensions and units before computing comparisons. Duplicate presentations remain
separate observations with distinct source spans. Conflicting context IDs are
rejected rather than silently merged. Unsupported transformations, inline fractions,
missing context/unit information and invalid values appear as explicit gaps.

The SQLite database is a **rebuildable query projection**, not another authoritative
archive and not a multiwriter store. Do not commit it or copy source documents into
it. A record's `extracted` status means deterministic parsing, not independent
approval. Proposed fallback records are excluded from normal queries. Hashes detect
changes and bind inputs; they do not establish economic meaning or accounting truth.

### Transcript evidence

`research.transcript_evidence` provides:

- `index_transcript(text, source, reviewed_boundaries=None)`: index sections, speaker
  turns, questions, management answers and follow-ups without duplicating the full
  source body. The source requires `document_id` and `text_sha256`; an optional
  speaker registry supports provisional detection.
- Reviewed boundaries contain `reviewed: true`, `sections`, `turns`, and preferably
  an external `review_id`. Sections have `start`, `end`, and `kind`; turns add
  `speaker` and `role`. The caller must actually review those annotations.
- `validate_findings(findings, index, text, fact_ids=())`: check required finding
  fields, exchange/fact references and exact quoted substrings inside the stated
  exchange turns.

Automatic layout detection is provisional. It cannot establish speaker identity,
call completeness, issuer/period qualification or answer quality. Retain the full
transcript and the unassigned-span coverage record. A structurally valid finding
still requires independent original-source review. The index itself must be frozen
alongside the source; finding validation is not an index-authenticity service.

### Experiment runner

`research.earnings_experiment` is a separate entry point; it does not activate the
production coordinator. A case JSON uses `schema_version: 1`,
`scope: "one_packet_experiment"`, explicit `authorization`, and lists of source and
artifact records with absolute `path` and `sha256`. Sources must include `kind:
"transcript"` and `kind: "filing"`. Its `financial_path`, `transcript_index_path`,
and `transcript_path` must point to files included in the frozen lists. Additional
case notes should identify qualification limits and transcription artifacts.

```sh
python3 -m research.earnings_experiment --help
python3 -m research.earnings_experiment run \
  --case /private/runtime/experiments/cases/example-case.json \
  --output /private/runtime/experiments/runs/prime/example-run
python3 -m research.earnings_experiment verify \
  --output /private/runtime/experiments/runs/prime/example-run
```

The runner invokes an installed `prime-agent` through the user's existing
`openai-codex` authentication. Do not place credentials in cases, public code or
artifacts. It captures role requests, prompts, dependencies, outputs, execution
receipts and separate sessions privately. The named roles are `extractor`,
`commentator`, `reviewer`, `editor` and `final_reviewer`.

Successful local execution produces `accepted.json`, the composed report and its
reviewed dependencies. `accepted_local`/`verified_local` does **not** prove remote
persistence, production eligibility, schedule activation or user acceptance.
Blocked work records its failure instead of publishing. Re-running an unchanged
case can reuse validated completed role artifacts; a recorded launch without a
completed output must be reconciled before retrying. Do not delete launch evidence
and blindly start a duplicate task.

## Research and review expectations

The commentary must read the complete call, account for all indexed Q&A exchanges,
and select the consequential exchanges for deeper analysis. Each finding connects:

- The question and the answer actually given.
- Directness or the particular unresolved question, without attributing motives.
- Technical mechanism and operating/financial consequence.
- Measured corroboration, counterevidence and uncertainty.
- A specific next observable test.

The substantive rubric covers source fidelity, question/answer fidelity, financial
context, technical reasoning, counterevidence and coverage/scope. The final rubric
covers source fidelity, summary fidelity, materiality, technical clarity, concise
specific writing and citation/scope quality. Every criterion needs a passing
assessment supported by explicit evidence; material findings cannot be averaged
away. The final reviewer binds the exact report hash.

Missing prior calls, consensus, valuation, portfolio context, translations or
technical evidence constrain the report. They must not become invented comparison
history or claims of a complete investment underwrite. A source-linked transcript
experiment also does not automatically qualify its inputs for production.

## Isolation and measurement limitations

Separate sessions and allowlisted prompt dependencies provide **logical role
isolation, not an operating-system sandbox**. An `ipython` tool still has the host
process's filesystem and execution rights. The current experiment relies on scoped
prompts, frozen inputs, retained receipts and subsequent verification; stricter
technical isolation would require separate credentials/workspaces and filesystem
or process controls. Do not claim that an author was technically unable to inspect
another file merely because its prompt prohibited it.

This implementation exercises Prime Agent as the role runtime. Its installed
version, provider, model and actual session receipts must be recorded for a real
run. No performance or financial-insight advantage over the current runtime is
claimed. A comparative evaluation still needs identical frozen cases, comparable
model/tool/resource settings, a baseline arm, blind quality review and measured
usage, duration, omissions and failures. Do not infer token usage from output length.

Synthetic tests exercise numerical contexts, units, provenance, unsupported formats,
query safety, transcript spans, role artifacts and rejection paths. Passing those
tests does not establish report quality; a real source-backed pilot and independent
review are separate evidence.

## Explicit interrupted-session recovery

`research.earnings_recovery` is a separate, narrow adapter for an initial extractor
that hit the original timeout and whose saved session demonstrably ends aborted.
It preserves the original executor and evidence hashes. It does not silently retry
an uncertain or still-running task. Only one resume of that exact session is
permitted, with a separately frozen continuation and a 600-second limit.

```sh
python3 -m research.earnings_recovery recover --output /private/runtime/run
python3 -m research.earnings_recovery continue \
  --case /private/runtime/case.json --output /private/runtime/run
python3 -m research.earnings_recovery verify --output /private/runtime/run
```

The adapter retains original failed receipts and snapshots the session before
resumption. Verification checks that the saved session only appends to those
original bytes, retains its identity, receives exactly the allowed continuation,
and completes with the actual captured JSON. The successful resumed process has
its own receipt; the original timeout is never rewritten as success. Completed
other-role outputs remain reusable only after normal verification. All original
source, independent-review, exact-report and two-correction-round requirements
remain active. After this recovery, use the adapter verifier: the original verifier
correctly rejects the unchanged aborted attempt.

This is an explicitly reconciled experiment recovery, not a general cloud scheduler
or an unlimited retry policy. A second interruption requires investigation.

A headless timeout can also occur after a role has produced a complete response but
before its wrapper delivers stdout. `research.earnings_reconcile` handles this
separate case without a new model call. It requires the exact terminal journal
answer, original prompt/dependencies, a post-timeout inactive-runtime observation,
and verified hashes. Completion timing comes from the outer journal event, not the
model response-start timestamp. Late completion is explicitly retained as late.
The original CLI receipt remains uncertain; reconciliation does not invent exit zero.

Use `reconcile --output <run> --job <role-rN> --inactive <absolute-receipt-path>`,
then this module's `continue` and `verify` commands. It composes with the initial
extractor recovery adapter. Nested RLM sessions must be included in usage accounting;
a parent's final answer does not imply that every child completed successfully.

`research.earnings_editor_recovery` covers a different, explicitly observed failure:
the revision-one editor exits 1 with `fetch failed` and its journal ends in that
provider error. Its `recover` command permits one 600-second continuation of the
same session, retaining the original draft context, failed receipts and dependency
hashes. Use this module's `continue` and `verify` commands afterward; it composes
the previous adapters. A draft visible in tool output is not a completed editor
response, and recovery never bypasses the fresh final reviewer. A failed second
attempt remains blocked rather than entering an unlimited retry loop.

## Matched native Codex arm

`research.earnings_native` runs the same frozen case, five role prompts, validation
rubrics, parallel initial authors and two shared quality-correction rounds through
the installed native Codex CLI. It explicitly selects `gpt-5.6-sol` with `max`
reasoning and uses the existing ChatGPT sign-in. It neither reads nor copies auth.
The original correction handoff is retained for comparison, including its limited
prior-review dependency. This is a runtime comparison, not a redesigned prompt arm.

```sh
python3 -m research.earnings_native prepare \
  --case /private/runtime/case.json --prime-run /private/runtime/runs/prime \
  --output /private/runtime/runs/native --codex /path/to/codex
python3 -m research.earnings_native run --output /private/runtime/runs/native
python3 -m research.earnings_native verify --output /private/runtime/runs/native
```

Preparation launches no role. It freezes source/code/runtime hashes and actual CLI
arguments. Each role runs in a fresh read-only session with web expansion disabled.
Native JSONL events, actual process outcome, final response, usage, and the exact
thread's rollout are retained privately. Verification checks observed model/effort,
prompt identity, distinct role sessions, complete correction history, dependencies,
source spans and exact final-report bytes. A recorded launch cannot silently retry.

System prompts, tools and sandbox behavior remain runtime differences. Compare
quality using fresh blinded source-backed reviewers; keep their usage outside the
report-generation totals. Normalize cached-token accounting and report recovery
interventions separately from substantive corrections. A single case does not prove
general superiority, identical server-side model revisions, or unattended operation.
The native runtime currently locates captured rollouts in the default
`~/.codex/sessions` directory. Keep all real cases, traces and comparisons private.

The CLI event mechanism is documented in [OpenAI's non-interactive mode guide](https://learn.chatgpt.com/docs/non-interactive-mode).
