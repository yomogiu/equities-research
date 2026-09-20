# Earnings calendar — daily at 07:00 America/New_York

Read AGENTS.md, docs/operations.md, roles/calendar.md, and roles/rubric.md.
The task's private inputs must supply a reviewed issuer watchlist and a durable
private workspace. If either is unavailable, report the missing input once and
do not substitute public GitHub storage or guess which companies the user owns.

Reconcile the next 45 days and prior 14 days of earnings events. Prefer issuer IR
confirmation. Record fiscal period, report date, call time/timezone, confirmation
status, and source. Every watchlist issuer needs an explicit coverage status.
Resolve ambiguity by research; record unknowns where public sources cannot resolve it.

Produce the JSON contract in roles/calendar.md and a concise Markdown report.
Validate with `python3 -m research.cli calendar --input CALENDAR --watchlist WATCHLIST`.
Use roles/rubric.md to check completeness and repair sourced errors before saving.
Update the private event queue keyed by stable issuer and fiscal period. Preserve
date revisions and old events needed for late filings. Do not overwrite prior reports.
Persist the artifact and queue receipt to the private service, then verify read-back.

The collection task consumes that queue automatically. Report meaningful date
changes, new near-term events, or failures; stay quiet on unchanged results.
Do not send email or other external messages.
