# Selected bounded report pipeline

`research.earnings_passage_pipeline` is the selected entry point for new,
user-authorized report runs. Version `luna6-sol-presentation-v4` uses financial
preparation on `gpt-5.6-luna` / `xhigh`, retrieval on `gpt-6-luna` / `max`, and
analysis plus a fresh independent reviewer on `gpt-6.1-sol` / `medium`.

The two preparation sessions run concurrently. Analysis then receives their
artifacts and the complete transcript. A fresh reviewer receives original
sources and the exact candidate report. At most two correction rounds are
permitted. Quotes are selected by passage ID; code copies text, offsets and
hashes. Financial values are rendered from the selected source observations.
New frozen runs also enable the [reviewed signal strip](report-signals.md) by
default after acceptance. `freeze --no-signals` opts out. Existing frozen runs
retain their recorded setting; this default does not activate scheduled analysis.

## Execute a bounded run

Install Python 3.11+, Node and Prime Agent with the existing Codex subscription
sign-in. Source packets and outputs belong in private storage outside this public
checkout. Keep the code checkout pinned and unchanged for each frozen run.
The writing standard must be supplied explicitly. Case manifests must pass
`earnings_experiment.validate_case`; retain issuer, fiscal-period and source
qualification uncertainty. This runner consumes an existing frozen packet;
it does not collect missing documents or authorize investment activity.

Set `REPORT_CASE`, `REPORT_OUTPUT` and `REPORT_WRITING` to the authorized private
case manifest, a new private run directory and the report writing standard.

```sh
python3 -m research.earnings_mixed_runner --probe --model gpt-6-luna
python3 -m research.earnings_passage_pipeline freeze "$REPORT_CASE" "$REPORT_OUTPUT" "$REPORT_WRITING" --repair-loop
python3 -m research.earnings_passage_pipeline run "$REPORT_OUTPUT"
python3 -m research.earnings_passage_pipeline verify "$REPORT_OUTPUT"
```

The probe checks registration/sign-in without a model call. The runner verifies
exact requested model and effort, distinct role sessions, original evidence,
quote offsets, dependencies, review bindings and completed output receipts.
Never remove a launch receipt to force a retry. A launched but incomplete job
requires inspection and explicit recovery; it is not safe to launch again.

## Acceptance and repair

The CLI follows a configured repair continuation for both `run` and `verify`.
The original seed remains immutable; the continuation owns the revised report.
Only `result.json` with `status: accepted`, confirmed by `verify`, establishes
passing review of the exact artifacts. Report-file existence does not establish
acceptance. `blocked` results retain draft reports and unresolved findings.

- Invalid passage IDs receive a bounded candidate window; code permits edits
  only to failed selections. No suitable window or an explicit worker refusal
  produces a source-selection handoff.
- Wrong fact selection, missing material context and evidence interpretation
  return to the responsible author within the correction budget.
- Without `--repair-loop`, renderer findings stop model retries and persist
  `repair-handoff.json`, bound to the protocol, artifacts and review. With the
  flag, the reviewer-owned continuation below executes supported presentation
  repairs and returns the exact candidate to independent review.

Current limitations include financial label/GAAP presentation defects and
interrupted/corrected transcript-turn interpretation. Report synthesis can omit
material facts already present in the preparer output. Independent review remains
required; efficiency measurements do not establish report quality. Fixes need a
new version and a fresh review, while original benchmark runs remain immutable.

This merge selects the bounded report implementation. Connecting it to the
private scheduled coordinator, changing its workflow pin, and enabling recurring
investment analysis are separate deployment steps. No recurring gate or private
configuration is changed by this entry point.

[Financial display and repair details](financial-rendering-experiment.md)

## Reviewer-owned automatic repair loop

New runs can stop after their first substantive review and automatically dispatch
repair/rebuttal workers instead of treating every review request as correct:

```sh
python3 -m research.earnings_passage_pipeline freeze "$REPORT_CASE" "$REPORT_OUTPUT" "$REPORT_WRITING" --repair-loop
python3 -m research.earnings_passage_pipeline run "$REPORT_OUTPUT"
```

The sibling `REPORT_OUTPUT-repair` directory contains the durable continuation.
Source-preparation failures without a complete report and substantive review keep
their original handoff; they do not launch report-repair workers.
An existing blocked passage-pipeline experiment can also be resumed into a new
private directory without altering its original artifacts:

```sh
python3 -m research.earnings_report_repair init "$BLOCKED_RUN" "$REPAIR_OUTPUT"
python3 -m research.earnings_report_repair run "$REPAIR_OUTPUT"
python3 -m research.earnings_report_repair verify "$REPAIR_OUTPUT"
```

`advance` performs one worker job, useful for an external scheduler; `run` advances
until acceptance, a terminal block, a dispatch budget, or an uncertain launch.
Connecting that command to recurring private automation remains a deployment task.

Each author responds to its findings with `repair`, `rebut`, or `unresolved`, citing
original passage IDs and explicitly naming the source speaker and subject. A
fresh reviewer receives original sources, artifacts, the rendered candidate and
those concise responses. It adjudicates every finding as `closed`, `withdrawn`
or `open`. A rebuttal cannot close a finding; only the reviewer can withdraw it.
The reviewer can also withdraw a disproven premise in a compound finding when
the author labeled its response `repair`; the author's label does not overrule
source-backed adjudication. Every withdrawal still requires original evidence.
A pass requires every rubric criterion to pass and every finding to be resolved.
The reviewer can add new source-backed findings, including defects it discovers
in preparer artifacts that did not appear in the report.

The rendered review view contains the report body plus anchor IDs, fragment
targets and missing destinations parsed from the complete HTML. The evidence
appendix is explicitly omitted from the body excerpt because original sources
are supplied separately. Its omission cannot be treated as missing links.

Unchanged extraction and retrieval are reused. Financial/retrieval repairs trigger
an analyst reconciliation; formatting-only repairs do not repeat analysis. The
formatter worker proposes source-backed labels, dimension descriptions and an
accounting-basis note. Code preserves fact IDs, numerical values, units, scaling,
periods and row grouping, escapes all text and regenerates the report. These
presentation repairs are automatic. Arbitrary code patches, new parsers, document
retrieval and unsupported rendering-engine defects are **not** executable worker
outputs; they remain explicit unresolved work. There is no automatic code merge.

The original two-round semantic correction budget is retained across the seed
and continuation. A malformed response gets one schema retry in its current
round, still subject to the dispatch budgets (default 12 jobs and 1.5 million
reported tokens for the continuation). Token use is checked between calls; a
single in-flight call can exceed the remaining token budget. Budgets never
produce acceptance by themselves. Exhausted budgets and unresolved findings are
reported as such.

Missing response passage IDs receive a narrow selection-only retry against at
most 24 source passages per affected response, ranked within its cited sources
and including adjacent context. Code preserves the proposed artifact and response
text. An unsupported selection or failed retry keeps the report blocked; this
mechanical repair does not establish that the source supports the claim.

A file lock prevents concurrent coordinators. Immutable event records bind the
prior state, job output, updated artifacts and adjudication history. Verification
replays authenticated worker outputs, checks exact model/effort and distinct
sessions, source/code hashes, prompts, report bytes and acceptance conditions.
A completed job interrupted before its event was saved is reused. A launched job
without a verified completed output returns `launch_uncertain`; inspecting and
reconciling that execution is required before any retry, rather than guessing it
never ran. Original benchmark directories remain unchanged.

The repair loop automates execution and records disagreement; it does not make
model judgments infallible. Test fixtures exercise mistaken reviewer findings,
withdrawal after rebuttal, formatter preservation, interrupted execution, tamper
rejection and budget exhaustion. Live outcomes belong in private storage.

## Private coordinator connection

The [finite report flow](connected-report-flow.md) supplies the selected pipeline
adapter for private queue execution. It prepares an explicitly authorized qualified
packet, advances one new model call per turn, and requires both deterministic
corrections and independently reviewed signals. The private coordinator owns queue
reservation, separate code pinning, exact remote persistence and dashboard publication.
