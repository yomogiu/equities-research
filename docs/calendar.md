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

The window includes 90 future days and 14 prior days. The provider covers future
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

The private `calendar.yml` workflow can run manually or daily at 07:00
America/New_York. Two UTC triggers with an Eastern-hour guard handle daylight saving;
GitHub schedules are best effort and can be delayed. The private
`ENABLE_EARNINGS_CALENDAR` variable gates recurrence. This is a GitHub Actions
deterministic job, not a scheduled Codex model session. Investment-analysis and
two-hour document-collection gates remain separate.

Use the shared private-writer concurrency group, persist even partial results, and
verify the remote commit. Inspect counts and source failures: workflow success does
not mean every company has a confirmed upcoming date. Public code must contain no
real watchlist, source registry or research outputs.
