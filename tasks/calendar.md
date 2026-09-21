# Earnings calendar — quarterly baseline at 07:00 America/New_York

Read AGENTS.md, docs/operations.md, roles/calendar.md, and roles/rubric.md.
The task's private inputs must supply a reviewed issuer watchlist and a durable
private workspace. If either is unavailable, report the missing input once and
do not substitute public GitHub storage or guess which companies the user owns.

For failure-triggered work, follow tasks/calendar-repair.md and process only the claimed batch.

First read calendar/latest.json, calendar/review-queue.json and calendar/changes.json
from the full-universe deterministic updater. Reuse its fetched sources and provenance.
The old collection/calendar-candidates.json covers only the core pilot and is not
the authoritative whole-universe calendar. See docs/calendar.md for status meanings.
Investigate only missing, conflicting, or stale dates; avoid re-searching every issuer.
Candidates require fiscal-period reconciliation before entering the accepted queue.

Reconcile the next 100 days and prior 14 days of earnings events. Prefer issuer IR
confirmation. Record fiscal period, report date, call time/timezone, confirmation
status, and source. Every watchlist issuer needs an explicit coverage status.
Resolve ambiguity by research; record unknowns where public sources cannot resolve it.

Produce the JSON contract in roles/calendar.md and a concise Markdown report.
Validate with `python3 -m research.cli calendar --input CALENDAR --watchlist WATCHLIST`.
Use roles/rubric.md to check completeness and repair sourced errors before saving.
Update the private event queue keyed by stable issuer and fiscal period. Preserve
date revisions and old events needed for late filings. Do not overwrite prior reports.
Persist the artifact and queue receipt to the private service, then verify read-back.

The deterministic updater emits collection candidates; actual collection dispatch
must be separately connected and enabled. Do not claim this runs automatically from
a candidate file alone. Report meaningful date
changes, new near-term events, or failures; stay quiet on unchanged results.
Do not send email or other external messages.
