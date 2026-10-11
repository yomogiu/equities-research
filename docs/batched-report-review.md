# Batched report corrections

`research.earnings_batch_review` is an opt-in coordinator for new report editions.
It reviews a complete draft report and draft signals together, then accepts at
most two atomic correction batches. It does not run preparers or rewrite prose.
Existing protocols and their receipts retain their original rules.

## Review and preservation

The baseline review sees all source passages, financial context, the rendered
report and signals. The reviewer returns every finding in one response. A
correction plan names exact units, old value hashes and replacement values.
Python validates and applies the complete plan before the next review call.

Each later call covers outstanding findings, all changes, affected dependencies,
the rendered candidate and complete cited source scopes. Source text is selected
by code, including question and answer turns together. Unchanged accepted units
retain their original review receipt hashes. They are not sent back for approval.
The reviewer can reopen one only with a specific source-supported contradiction.

Dependencies are deliberately conservative: financial, retrieval or financial
presentation changes reopen dependent analysis; a finding change reopens its
signals and next tests. A signal-only change leaves report acceptance intact.
Acceptance is reconstructed from authenticated requests and outputs on every
advance; the saved acceptance JSON is an audit snapshot, not independent proof.
A report renders as accepted only when every unit is accepted.

## Private input and commands

Create a private JSON manifest containing `source_protocol`, `state` (the existing
`artifacts` and `format` object), and `signals` (existing signal schema bound to
that exact report). Draft signals are supplied with the draft report so they can
be reviewed together. This entry point does not run the legacy separate signal
review loop. The source protocol must identify the frozen evidence manifest and
writing standard; include known author session IDs in `excluded_session_ids`.

```
python3 -m research.earnings_batch_review init PRIVATE_MANIFEST PRIVATE_OUTPUT --authorize 'New batch-review edition'
python3 -m research.earnings_batch_review advance PRIVATE_OUTPUT
python3 -m research.earnings_batch_review advance PRIVATE_OUTPUT --execute
python3 -m research.earnings_batch_review submit PRIVATE_OUTPUT PRIVATE_PLAN
python3 -m research.earnings_batch_review verify PRIVATE_OUTPUT
```

Only `advance --execute` can invoke a reviewer; it makes at most one call. A
partially written request blocks retry until execution is reconciled. `verify`
is read-only. No schedule, production pin or existing report is changed by these
commands. The source/code bindings are immutable after initialization.

A plan has `before_sha256` (the entire unit registry digest) and `changes`.
Each change contains `unit_id`, `before_sha256` (that unit's value digest), `value`
and `reason`. Unit membership and dependencies cannot be changed by a plan.

## Deployment boundary

This is a new opt-in review path, not an automatic migration of stopped jobs.
Do not initialize old corrections as a fresh baseline to reset their rounds or
reuse historical acceptance without its original verifier. Such migrations need
an explicit adapter preserving original usage, remaining rounds and receipts.
The current production cohort and automation remain paused. No live efficiency
claim follows from the synthetic tests; measure actual calls and recorded usage
when an authorized new edition is selected for rollout.

## Production routing

New queue requests select `review_policy: batched-report-review-v1` and freeze
`batch_review` in the passage protocol. `earnings_report_flow.advance` then routes
to `earnings_batched_flow`: financial context, retrieval, analysis, draft signals,
one combined baseline review, and (when necessary) at most two proposal/review
batches. Every invocation starts at most one model call. Completed preparers are
replayed without regeneration. Corrections are proposed together and applied by
code; malformed proposals stop with their authenticated outputs retained.

The private completion verifier replays this pinned route and checks its exact
HTML and complete artifact inventory before counting a report. Legacy requests
continue through their original report and signal verifier. Changing the default
pin or policy does not migrate stopped work or restart paused schedules.

## Mechanical preflight for new editions

The explicitly selected `mechanical-report-review-v2` policy compiles financial
row labels, dimensions and citations from the existing deterministic display
registry before drafting signals. Decimal scaling, units and filed dates remain
source-derived. It does not invent accounting basis or repair ambiguous IDs,
attribution, omissions or prose. Original authenticated artifacts remain intact.
A private `mechanical-preflight.json` records candidate, format, catalog and
source-bundle hashes plus structural diagnostics. Replay checks the same result.

Select this policy only when freezing a new authorized request:

```
python3 -m research.earnings_passage_pipeline freeze PRIVATE_CASE PRIVATE_OUTPUT PRIVATE_WRITING --deterministic-corrections --batch-review --mechanical-preflight
```

Advance through `earnings_report_flow.advance`, as for the existing combined
review controller. This option alone launches no models and changes no schedules.
Private queue policy/default-pin and completion-verifier rollout is separate.
Existing frozen editions retain their original policy, receipts and round limits.

Independent review still assesses all substantive criteria against original
sources and the rendered candidate. A passing decision may use an empty
`passage_ids` list: its signed reviewer receipt certifies source support, and
acceptance records the unit's actual source references separately. This avoids
another model call merely to repeat IDs for already accepted units. Revisions
and reopened claims still require nonempty exact passage IDs. No rejection is
converted into acceptance by code. Review asks for all material defects together;
optional wording preferences do not block acceptance.

Correction review retains complete cited source scopes and both sides of relevant
Q&A, but omits unrelated Q&A index rows. Moving an unchanged accounting note
before/after its table reopens only format review. Changes to labels, citations,
basis text, folds, hidden rows or summaries still invalidate dependent claims and
signals. Two correction batches remain the maximum. No live token-saving claim
is established by synthetic lifecycle tests.

## Model assignments for new freezes

Financial selection, transcript retrieval and report analysis use GPT-6 Luna at
max effort. The combined path's signal author uses GPT-6.1 Sol at low effort,
explicitly frozen as `signal_author_model`. Independent combined review and
correction proposals continue using GPT-6.1 Sol at medium effort. Legacy separate
signal author/reviewer editions retain their existing medium assignment.
Existing frozen checkouts, protocols and authenticated jobs are not migrated.
