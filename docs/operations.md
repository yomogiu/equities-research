# Sequential earnings reports

The active report path is **Sources → financial tables → analysis → review → publication**.
`research.earnings_sequential` owns one `job.json` per company and period.
`research.earnings_sequential_stages` supplies the five concrete handlers.
The private runtime supplies source qualification and verified private publication.

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
   in the same job, at most twice. Tables and source hashes remain fixed. A financial
   input/calculation finding blocks for correction rather than inviting a prose override.
5. **Publication:** render only the exact accepted candidate. The private publisher
   persists artifacts and verifies remote bytes before recording successful publication.

Only analysis and review invoke models. There are no retrieval-model stages, separate
signal-author stages, successor jobs, repair queues or agent-to-agent handoffs in this path.
The standard successful pass has two model calls; revisions add an author and reviewer.
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
never performs this action. A proven financial-table defect may instead
be rebuilt explicitly in the same job: original table bytes are archived, source hashes
and cumulative costs are preserved, and a correction round requires fresh analysis and
review. The scheduler cannot bypass that review.
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
