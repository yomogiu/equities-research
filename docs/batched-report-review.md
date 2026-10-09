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
