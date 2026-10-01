# Private Luna/Sol earnings benchmark

This isolated historical earnings experiment measures whether two Luna preparation
roles can support a concise Sol report and a fresh, independent Sol review. It does
not collect new sources, change production gates, activate schedules, publish
reports, or establish investment approval. Speed and token-reduction targets are
hypotheses, not measured results.

## Components and exact role settings

| Component | Purpose |
| --- | --- |
| `research.earnings_compact_evidence` | Validate frozen case inputs; assign short financial and document IDs; preserve source offsets, hashes, contexts, units, gaps, and uncertainty. |
| `research.earnings_mixed_runner` | Execute and verify one immutable, authenticated Prime SDK session per role attempt. |
| `research.earnings_mixed_pipeline` | Freeze the protocol, coordinate preparation and review, render the private report, and verify completed results. |
| `research/earnings_mixed_prime.mjs` | Host the installed Prime SDK with exact model/effort selection and no tools. |

| Role | Model | Reasoning effort |
| --- | --- | --- |
| Financial context preparation | `gpt-5.6-luna` | `xhigh` |
| Evidence retrieval and Q&A coverage | `gpt-5.6-luna` | `max` |
| Report analysis | `gpt-6.1-sol` | `medium` |
| Fresh independent review | `gpt-6.1-sol` | `medium` |

The two preparation roles run concurrently. Analysis and review then run
sequentially, each in a separate session. The reviewer receives the complete
transcript, all indexed document text, all financial observations, and the exact
candidate artifacts/report. It does not inherit the authors' conversation.

## Freeze, run, and verify

Use Python 3.11+, an installed Prime Agent SDK/Node runtime, and the existing
subscription sign-in. No API key or exported credentials are needed. Optionally
check registration and sign-in availability without making a model call:

```sh
python3 -m research.earnings_mixed_runner --probe --model gpt-5.6-luna
python3 -m research.earnings_mixed_runner --probe --model gpt-6.1-sol
```

Set `BENCH_CASE`, `BENCH_OUTPUT`, and `BENCH_WRITING` to your authorized case
manifest, a fresh private output directory, and the required writing standard.
Keep every input and output outside the public checkout. The case must satisfy
`earnings_experiment.validate_case`, including frozen source/artifact hashes, and
supply `case_id` and `scope_notes` for the pipeline prompts.

```sh
python3 -m research.earnings_mixed_pipeline freeze "$BENCH_CASE" "$BENCH_OUTPUT" "$BENCH_WRITING"
python3 -m research.earnings_mixed_pipeline run "$BENCH_OUTPUT"
```

Freeze records the evidence manifest, writing standard, exact role settings,
correction limit, and implementation hashes. Do not edit frozen code or inputs
while a run is active. For a completed run, use the read-only verification API:

```sh
python3 - "$BENCH_OUTPUT" <<'PY'
from pathlib import Path
import sys
from research.earnings_mixed_pipeline import verify_result
result = verify_result(Path(sys.argv[1]).resolve())
print(result['status'])
PY
```

Calling `run` on an existing completed result also verifies it. A launched role
without a verified completed output is uncertain and cannot be retried in place;
the runner rejects duplicate launches. Do not remove receipts to force a retry.

## Evidence and correction boundaries

Original source files remain in place. Financial `F` IDs retain original
observation IDs, complete reporting contexts and units, extraction status, and
source support. Document `D` IDs identify exact Unicode-character spans. Persisted
previews explicitly mark truncation; source-slice helpers return complete spans.
The compact financial view explicitly lists omitted and unmapped observations.
The pipeline's financial preparer and reviewer receive **all** observations,
including unmapped concepts. The retrieval role receives all document text and
the complete transcript; the analyst also receives the complete transcript,
including every Q&A exchange and unassigned text.

Source and artifact hashes are checked before preparation and when loading the
bundle. Financial support and table-row spans are verified against originals.
Unknown citation IDs, changed sources, ambiguous quotations, and quotations
outside the cited scope are rejected. Exact quotes preserve whitespace and
punctuation; transcript quotes cannot cross speaker turns. These checks establish
provenance and structure; the independent reviewer assesses meaning and material
omissions.

There are at most two correction rounds after the initial attempt. Findings target
the responsible preparation or analysis role, and a corrected candidate receives
a fresh review. Acceptance requires every review criterion to pass with no
unresolved findings, bound to the final report and artifacts. Remaining defects
produce a blocked result and, when available, a visibly marked draft.

## Runtime and measurement

Each Prime SDK session has one user prompt and one completed assistant response.
Tools, inherited context files, skills, extensions, automatic compaction, provider
retries, and model fallback are disabled. Runtime receipts, the session journal,
and the outgoing request record must agree on model, reasoning effort, and zero
tools. This attests client-side selection and observed response identity; it does
not independently certify server-side model weights.

Use the measured usage in each verified job's session receipt:

- `input`: uncached input tokens.
- `cacheRead` and `cacheWrite`: separately reported cache tokens.
- `output`: reported output tokens.
- `totalTokens`: `input + cacheRead + cacheWrite + output`.

Count every actual role attempt, including corrections. Report cache reads
separately; a decrease in uncached input is not necessarily a decrease in total
context supplied. Do not infer billing, subscription quota consumption, or dollar
savings from these fields. Record any setup probes separately from benchmark
role totals.

Benchmark wall time spans the earliest role launch to the latest role completion,
so concurrent preparation is counted once in elapsed time. It differs from the
sum of individual job durations and from the current coordinator process's timer.

All case manifests, source material, prompts, model outputs, reports, journals,
and receipts stay in private storage. The public repository contains only generic
workflow code, documentation, and fictitious tests. A verified local benchmark is
not a production deployment or a replacement for production acceptance gates.

## Candidate-quarantine follow-up

`research.earnings_quote_candidates.qualify_candidates` is a separate, explicit
policy. It retains only exact verified candidate quotations, records every
rejected candidate, and preserves every nonquote field. It does not normalize or
repair quotations. Unknown source IDs or changed source files remain fatal.
At least four distinct validated spans must survive.

To exercise the analyst and reviewer without paying to regenerate authenticated
preparation, use a **new private directory**:

```sh
python3 -m research.earnings_mixed_continuation "$PRIVATE_RUNTIME/original" "$PRIVATE_RUNTIME/followup"
python3 -m research.earnings_mixed_audit continuation "$PRIVATE_RUNTIME/followup"
python3 -m research.earnings_mixed_audit strict "$PRIVATE_RUNTIME/original"
```

The continuation uses the original first-pass financial/retrieval receipts,
records the quote derivation, and creates fresh analysis and review sessions.
It has zero correction rounds: failed review remains a draft. Its actual
**downstream** latency is measured. Adding inherited preparation latency produces
a **projection**, not a newly observed successful end-to-end run. Count original
failed attempts separately; never erase them from the experiment's total usage.

Use `earnings_mixed_audit` for final verification. It also checks complete ordered
role sets, role-specific models, distinct sessions, actual regenerated prompts,
and receipt-derived timing. This additional verifier is separate so original
frozen code and completed artifacts remain unchanged.
