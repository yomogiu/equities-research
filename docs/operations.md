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
Every call consumes the same cumulative job allowance, including failed work. An uncertain
paid execution stops for reconciliation rather than silently retrying. Deterministic,
idempotent stages may safely resume after interruption. One process owns the job lock.

The private runtime CLI is `python3 scripts/run_reports.py tick`. It advances one eligible
company through up to five stages. The scheduler invokes this command and reports its
result; it does not choose repairs, change budgets or edit execution state. `status` is
read-only. `initialize` creates untouched jobs once from the static authorized batch.
An operator may explicitly resume a proven closed model failure after fixing its cause.
The same journal retains the failed attempt, all charged tokens and the code-change reason;
this is bounded to two operator resumes. The scheduler never performs this action.
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
