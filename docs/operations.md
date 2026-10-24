# Sequential earnings reports

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
   original sources and cumulative costs stay fixed. New tables require full analysis
   and fresh independent review before publication.
5. **Publication:** render only the exact accepted candidate. The private publisher
   persists artifacts and verifies remote bytes before recording successful publication.

Before either model stage, code replays the inline-XBRL extraction, financial
configuration, calculations and table rendering against frozen source hashes. The
model receives the tables once, a compact verification record, and explicit gaps.
This verifies numerical reproducibility, not the completeness or accounting meaning
of the report. Original disclosures remain available; qualitative claims still need
original-source inspection and independent review.

Initial analysis and independent review default to `gpt-6.1-sol` with medium
reasoning. Verified narrative corrections default to `gpt-6-luna` with max reasoning;
full reauthoring after table repairs retains the analysis model. Per-job `models`
overrides use the distinct `analysis`, `review` and `correction` keys.

A narrative-only correction replaces exactly the sections identified by the prior
review. Code preserves every other component, verifies the prior reviewed candidate,
and saves hashes of the before/after components. The correction author receives the
flagged sections and their original evidence. The fresh reviewer receives the entire
revised candidate, prior review, verified changes and original evidence for changed
claims and findings. Every replacement citation, including a reused financial ID,
requires original-source inspection. The reviewer still assesses all eight criteria
and all five questions; previous passes do not automatically carry forward. The full
call is read on the initial pass and remains available during corrections. A changed
financial table requires the full author/review path; invalid proof or changed frozen
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
