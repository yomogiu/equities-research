# Sequential earnings reports

## Single-author path for new jobs

The `single_author` code binding replaces separate financial selection and table-first authoring with **Sources → combined author → independent review → publication**. Extraction is deterministic. One author session reads one fixed packet and returns source fact selections plus the full structured write-up. Code validates the selections, computes tables, and renders the candidate. The author receives every extracted observation, complete original filing/release bodies and the complete call. Overlapping source chunks are represented by offsets into one copy of each document; redundant SEC machine prefixes are identified explicitly. There is no retrieval loop or prior-review coaching in the initial author input.

A fresh reviewer receives the exact candidate, every original document body and call, the selected definitions, and deterministic numerical verification. It evaluates the same eight criteria and five expected questions. The dictionary fact inventory is not reprinted to the reviewer because original financial statements and the computed tables are already supplied. Each session has one evidence read and one final output. Acceptance still requires a passing exact-candidate independent review; a failed review stops without automatically launching another full report run. Schedule state is separate.

A newly authorized architecture comparison must retain its stopped baseline and cumulative accounting. The private adapter stores it under the original job, uses identical source bytes and a separate explicit test allowance, and reports both incremental and combined costs. It cannot reset or silently replay an existing comparison.

The procedures below also document compatibility for previously pinned jobs.

The active report path is **Sources → financial tables → analysis → review → publication**.
`research.earnings_sequential` owns one `job.json` per company and period.
`research.earnings_sequential_stages` supplies the five concrete handlers.
The private runtime supplies source qualification and verified private publication.

The active path uses shared modules with no legacy-controller dependency:

| Module | Responsibility |
| --- | --- |
| `earnings_runtime_common` | Immutable file/hash operations, exact model selection and installed runtime discovery |
| `earnings_source_case` | Existing source-case serialization and frozen-input validation |
| `earnings_source_preparation` | Deterministic evidence derivation after caller-owned source qualification |
| `earnings_markdown_render` | Report rendering and escaping without historical report builders |
| `earnings_file_context` / `earnings_file_runner` | Source inspection and authenticated model execution |

Archived workflows re-export shared helpers for compatibility. Their controllers and
result validators are not imported by the sequential path. The legacy result preflight
is isolated in `earnings_legacy_result_validation`; sequential schemas and acceptance
remain owned by the stage controller. Existing artifact serialization, hashes and source
qualification rules remain unchanged. Dependency tests forbid retired imports while
executing source preparation and a complete corrected-report cycle.

1. **Sources:** freeze qualified issuer/period evidence, original filing and complete
   call, writing standard, source hashes and observation cutoff. Historical reports
   explicitly identify their fixed source snapshot. Missing or ambiguous evidence blocks.
2. **Financial tables:** compile source-grounded periods, units, GAAP/adjusted basis,
   core metrics and available QoQ/YoY comparisons in code. Missing inputs remain gaps;
   no model invents comparatives or performs arithmetic.
3. **Analysis:** one signed-in author session interprets the tables and original call,
   with cited demand, profits, cash, outlook, earnings multiples and material Q&A.
4. **Review:** a fresh session examines the exact candidate and original evidence,
   all eight review criteria and five expected questions. Revisions return to analysis
   in the same job, at most twice. Prose findings use targeted section corrections.
   Table findings automatically archive the old tables and return to financial tables;
   original sources and cumulative costs stay fixed. Changed tables expand correction scope to the affected sections and require
   fresh independent review of the full candidate before publication.
5. **Publication:** render only the exact accepted candidate. The private publisher
   persists artifacts and verifies remote bytes before recording successful publication.

Before either model stage, code replays the inline-XBRL extraction, financial
configuration, calculations and table rendering against frozen source hashes. The
model receives the tables once, a compact verification record, and explicit gaps.
This verifies numerical reproducibility, not the completeness or accounting meaning
of the report. Original disclosures remain available; qualitative claims still need
original-source inspection and independent review.

Initial analysis and independent review default to `gpt-6.1-sol` with medium
reasoning. Verified corrections default to `gpt-6-luna` with max reasoning, including
sections affected by verified table repairs. Per-job `models`
overrides use the distinct `analysis`, `review` and `correction` keys.

An exact, unambiguous reviewer-requested sentence deletion is applied in code when
all affected components can be repaired solely by deletion. It adds no claims or
citations, uses zero model tokens, records an explicit deterministic execution kind
without a synthetic model session, and still requires a fresh full-report review.
Other corrections use Luna Max. A narrative-only correction replaces exactly the
sections identified by the prior review. Code preserves every other component, verifies the prior reviewed candidate,
and saves hashes of the before/after components. The correction author receives the
flagged sections and their original evidence. The fresh reviewer receives the entire
revised candidate, prior review, verified changes and original evidence for changed
claims and findings. Every replacement citation, including a reused financial ID,
requires original-source inspection. The reviewer still assesses all eight criteria
and all five questions; previous passes do not automatically carry forward. The full
call is read on the initial pass and remains available during corrections. Changed
financial tables expand the replacement scope to the affected financial sections.
The prior candidate is reconstructed with its archived tables; new tables are verified
against original sources. The fresh reviewer sees the full candidate, both change
proofs and original support, including newly parsed comparative disclosures.
Invalid proof or changed frozen
sources blocks execution. No model call or new budget is hidden in these checks.

Only analysis and review invoke models. There are no retrieval-model stages, separate
signal-author stages, successor jobs, repair queues or agent-to-agent handoffs in this path.
The standard successful pass has two model sessions; revisions add an author and reviewer.
Each session may make several provider requests as it reads evidence, so repeated input
counts toward actual usage. A smaller packet is not a measured token-saving guarantee.
Each role plans its own required evidence reads. Whole-role token forecasts are advisory;
admission checks minimum context feasibility and the runtime enforces actual usage.
Every call consumes the same cumulative job allowance, including failed work. An uncertain
paid execution stops for reconciliation rather than silently retrying. Deterministic,
idempotent stages may safely resume after interruption. One process owns the job lock.

The private runtime CLI is `python3 scripts/run_reports.py tick`. It advances one eligible
company through up to five stages. The scheduler invokes this command and reports its
result; it does not choose repairs, change budgets or edit execution state. `status` is
read-only. `initialize` creates untouched jobs once from the static authorized batch.
An operator may explicitly resume a proven closed model failure or a safely replayable,
zero-token deterministic failure after fixing its cause.
The same journal retains the failed attempt, all charged tokens and the code-change reason;
actual model restarts are bounded to two. A recorded zero-token `not_started` model
attempt with no session or execution directory, or a zero-token replay-safe deterministic
attempt, can be repaired explicitly without consuming that limit. Classification comes
from the referenced attempt outcome, including for older resume records; the operator's
reason cannot change it. All repair records remain in the same journal. The scheduler
never performs this technical resume action. A conclusively completed independent
review with financial-table findings instead enters the automatic table repair path.
The normal tick can adopt an older blocked table review after exact-candidate, source,
usage and revision checks; uncertain sessions, exhausted jobs and final-review allowances
are excluded. The transition and each stage are persisted before further work.

Automatic table repair currently applies a small deterministic rule set: source-bound
SEC interim accounting-basis qualification; exact-concept duplicate consolidation;
compatible additive-quarter derivation (never EPS/share subtraction); and selection of
a revenue denominator only when one identity reconciles with reported gross profit plus
cost across every shared period. Distinct revenue definitions remain separate rows.
Every interpretation remains subject to fresh independent review. It does not invent
missing observations, retrieve new sources, change code or accept arbitrary model mappings.

Identical repaired table text stops before another author call. Repeated identical
review findings also stop; a failed or unsupported repair stays blocked and the next
tick selects another eligible company. At most two revision rounds share the original
token allowance. Manual `rebuild-tables` remains available for diagnosed code fixes;
neither path bypasses review or grants additional budget.
An explicitly human-approved final-review allowance may fund one fresh review of the
exact existing candidate. The core records the approval and original allowance, binds
all retained artifacts, and prevents further model retries or corrections. Only a
passing review permits zero-token publication. The scheduler cannot grant allowances.
Global universe analysis remains separately gated. Collection and calendar workflows
are unchanged.

Historical report artifacts, code and receipts remain available for audit. They are
not inputs to the new controller's execution decisions. The one-time migration inventory
retains completed reports and unfinished accounting records; it never resets an old
job's costs. See [historical operations](legacy-operations.md) only when inspecting an
old pinned run. Those instructions do not govern new sequential reports.

Use the signed-in subscription and configured private storage. Never put real evidence,
reports, watchlists, session receipts or authentication in this public repository.
Passing tests establishes code behavior, not live model execution or remote publication.


### Presentation-only corrections

A completed review that passes all seven substantive criteria and flags only a
supported repeated debt caveat can take one deterministic presentation repair.
The rule removes two known generated notices only when the complete debt/lease
limitation remains in the cash commentary. It preserves every financial row,
source, citation and narrative byte. A separate candidate and deletion proof
retain the previously reviewed report. The next stage is independent review,
without another source, table or author run. All eight criteria and five expected
questions remain mandatory; the review and publication bind the new candidate.

This pass has a separate one-repair bound and uses the existing cumulative token
budget, including after the two substantive revision rounds. Unsupported changes,
uncertain executions, another editorial failure or insufficient budget stop. Normal
execution never expands the budget. An explicit user request to correct and review
an already blocked report may be recorded through `repair_editorial`; an optional
bounded review allowance is recorded alongside all previous usage. Publication
still requires acceptance. Scheduling is controlled independently.


### Broad financial extraction and model selection

New sequential jobs insert one accountable `financial_selection` stage between
source preparation and deterministic financial tables. The compact inventory
retains every raw observation, with shared dictionaries for concepts, labels,
periods, entities, units and dimensions. Original statement/note excerpts accompany
it; discovery previews cannot establish source inspection. The selector retrieves
additional original evidence through the signed-in evidence reader.

The saved mapping selects only existing fact IDs and supplies source-cited metric,
basis and perimeter interpretations. Code rejects fabricated fields, unknown or
unqualified facts, mixed classes/segments/units, conflicting values and uncovered
core metrics. Share classes remain separate. Gross purchase capex defines the
code-calculated FCF convention; debt/lease definitions remain explicit. Raw facts
are never rewritten. Model semantic interpretation is not deterministic evidence;
the independent reviewer still challenges it against original sources.

Table compilation and review reproduce the exact hash-bound mapping. All selection
usage is charged to the same job. Selection cannot declare replay safety; a failed
call stops with its receipts. New runs enable this path at code binding. An existing
zero-token blocked table pass may enter it through the explicit
`enable_financial_selection` migration, preserving evidence, costs and revision
limits. Automation does not grant extra budgets or operator recovery actions.

A completed, charged selection rejected by a repaired validator can use
`adopt_financial_selection` with the authenticated `verified_result` recovery.
This revalidates the original response, source-inspection receipts and frozen
inputs without another model call. Original costs and failed attempts remain
recorded; recovery grants neither report acceptance nor additional budget.
