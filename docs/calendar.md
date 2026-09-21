# Whole-universe earnings calendar

`python3 -m research.earnings_calendar --root PRIVATE_ROOT` updates the entire private
watchlist catalog, not the core-pilot list. Every stable issuer ID gets coverage,
including unresolved listings and missing dates. No models, translation, investment
analysis or document-download dispatch are invoked by this module.

The private source registry supplies up to three observed pages per issuer. A bounded
crawl follows relevant links on approved hosts, preserves compressed source responses
and hashes, and records failures. Explicit issuer-source qualification is separate
from listing eligibility. Neither is silently promoted by a successful download.

The bulk expected-earnings CSV currently uses Alpha Vantage's documented public demo:
[Earnings Calendar documentation](https://www.alphavantage.co/documentation/#earnings-calendar).
It is a best-effort source, not an authenticated production-service entitlement or
guarantee. Provider dates are estimates, even when they agree with issuer material.
Only unique, eligible US symbol matches with consistent company-name tokens are
associated automatically. International tickers are never matched as US symbols.
A provider error or changed schema becomes an explicit failure, not an empty calendar.

The window includes 100 future days and 14 prior days. The provider covers future
estimates; issuer pages supply explicit dates, including recent events. Coverage
distinguishes confirmed, estimated, identity/source review, no date found, stale and
conflicting observations. A date not found does not establish that no earnings exist.

Event dates, release dates and call timestamps are separate. A time without a verified
offset is not converted to a guessed timestamp. Unknown fiscal years/quarters remain
null. Period ends and article publication dates are not earnings-event dates.

## Private artifacts

- `calendar/latest.json`: every company, observations and source-attempt statuses.
- `calendar/index.html`: searchable company/status/date table with evidence links.
- `calendar/runs/<run-id>.json`: immutable snapshots for historical comparison.
- `calendar/changes.json`: new/revised/no-longer-observed events from the latest run.
- `calendar/review-queue.json`: identity, source and fiscal-period review work.
- `calendar/collection-candidates.json`: fresh, eligible, confirmed events with an
  explicit fiscal period near their event window; dispatch remains separately disabled.
- `calendar/sources/`: conditional HTTP cache and compressed, hashed response objects.
- `calendar/checkpoints/`: issuer outcomes persisted as workers complete.

Failed or disappearing observations retain their original last-seen timestamp and
become stale; they cannot enter collection candidates. Date changes create a change
record. Same-period/type conflicts stay unresolved. Where a source changes its URL
or event label without an explicit period, reconciliation may require manual review.

## Scheduling and acceptance

The private `calendar.yml` workflow runs manually or quarterly on January, April,
July and October 1, at 07:00 America/New_York. Two UTC triggers plus an Eastern-time
check and durable successful-quarter marker handle daylight saving and duplicate runs;
GitHub schedules are best effort and can be delayed. The private
`ENABLE_EARNINGS_CALENDAR` variable gates recurrence. This is a GitHub Actions
deterministic job, not a scheduled Codex model session. Investment-analysis and
two-hour document-collection gates remain separate.

Use the shared private-writer concurrency group, persist even partial results, and
verify the remote commit. Inspect counts and source failures: workflow success does
not mean every company has a confirmed upcoming date. Public code must contain no
real watchlist, source registry or research outputs.

## Retrieval failure hook

After calendar and document retrieval, actual failed attempts create private
`calendar/repair-queue.json` work, including partial runs whose process exits zero.
Normal absence of an announced date, an optional transcript or a verified listing is
not a retrieval failure. Failures are deduplicated by issuer, source, kind and quarter;
repeated checks update evidence rather than multiplying agent tasks. A claim takes at
most five items, expires after a bounded lease, and permits at most three attempts.
Resolution requires evidence; unresolved blocks remain visible. Source text is untrusted.

`research.calendar_repair` exposes enqueue, claim and finish commands. The consumer
follows `tasks/calendar-repair.md`, persists its claim before work, repairs official
source overrides, and runs `scripts/update_calendar.py --issuer STABLE_ID` in the private
workspace. Targeted refresh preserves other issuers and provider evidence, scans only
the affected issuer pages and leaves identity/analysis gates unchanged. Provider-wide
failure is a separate single task, not one task per company.

The hook is a durable handoff, not an authenticated model service. The private config
records automatic dispatch separately. Without a connected consumer, work stays queued.
The documented subscription cloud entry point is a GitHub PR comment addressed to
Codex; merely enabling Actions does not connect a ChatGPT identity for its bot.
See [Codex GitHub integration](https://learn.chatgpt.com/docs/third-party/github).
No API key or cached subscription credential is copied into CI.

Quarterly refresh is economical but can miss announcements made later in the quarter.
The 100-day issuer window spans long quarters; the bulk provider still supplies only
its three-month horizon. `freshness=current` means observed at `last_seen_at`, not
verified today. Before collecting a due event, recompute its date window from the saved
calendar and recheck that issuer; the saved collection-candidates file is only a snapshot
and is not an active scheduler. Failure repair cannot discover a newly announced date
for a company that has neither a saved date nor a retrieval attempt.
