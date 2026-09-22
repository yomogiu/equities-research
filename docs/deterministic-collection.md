# Deterministic collection

`python3 -m research.collect` downloads from configured regulator and issuer sources
without invoking a model, search engine, browser agent, or paid data API. Run it on
an ordinary machine or a private GitHub Actions runner. Codex is needed later for
interpretation, independent extraction, commentary, and review.

## Private inputs

Keep the watchlist, source registry, and output directory in the private data repo.
Start with a reviewed subset rather than the entire research candidate universe.
The registry maps watchlist symbols to CIKs, issuer pages, approved document hosts,
and optional known document URLs. See `examples/source-registry.fake.json`.
Configure document CDN hosts explicitly; redirects cannot silently add new hosts.
HTML, RSS/Atom and iCalendar feeds are supported. JavaScript-only pages and unknown
source layouts produce gaps instead of a browser/LLM fallback.

```sh
python3 -m research.collect \
  --watchlist /private/data/inputs/watchlist.user.json \
  --registry /private/data/inputs/source-registry.json \
  --output /private/data/collection --mode plan
# Change plan to collect for documents or calendar for dates only.
```

Python 3.11+ uses the standard library. Install Poppler's `pdftotext` for PDFs;
missing extraction tools and scanned PDFs produce explicit gaps. Set SEC_USER_AGENT
to an honest application name and contact email through private runner settings.
No SEC API key is required. Without that contact, SEC downloads are skipped and
recorded as `sec_contact_required`; issuer downloads can still run.

## Sources and limits

SEC submissions identify current 8-K earnings disclosures (Item 2.02), 6-Ks, and
annual/quarterly filings including 20-F/40-F. Up to four recent/baseline filings are
selected by default. EX-99 exhibits remain candidates until their contents and
period are checked. This is recent monitoring, not exhaustive EDGAR backfill.
An annual report supplies background; it does not stand in for a quarterly filing.

IR adapters follow a bounded set of labeled release, transcript and presentation
links, plus one event-page hop. Prepared remarks remain distinct from full calls.
Transcript length, Q&A and speaker checks are only triage; completeness and fiscal
period remain unverified until reviewed. Calendar dates come from explicit JSON-LD,
iCalendar or unambiguous earnings table rows. An opt-in `dated_lines` adapter
also handles a standalone date immediately followed by an earnings title. Publication dates are never treated
as earnings dates. Other layouts need a targeted adapter or gap investigation.

Defaults cap each run at 160 requests, 64 MiB downloaded, 16 MiB per document,
six discovery links per issuer, and four requests/second with one bounded retry.
Blocked hosts stop further attempts in that run. There is no paywall bypass.
Coverage gaps and budget exhaustion must remain visible; a successful process exit
alone does not establish complete collection. `latest-run.json` reports collected,
partial, or blocked status. It never declares an accepted research packet.

## Durable outputs and handoff

- `objects/`: content-addressed raw documents and extracted text; PDF page markers
  and HTML table cell separators retain useful citation context.
- `documents/`: immutable source manifests with hashes, retrieval time, publisher,
  filing metadata, and extraction/completeness status.
- `document-index.json` and `analysis-queue.json`: changed documents only enter the
  queue once; unchanged extracted text (including markup-only changes) does not
  trigger another model analysis.
- `calendar-candidates.json`: source-supported dates and observed date revisions.
- `source-gaps.json`, `latest-run.json`, `runs/`: source failures and run receipts.
- `http-cache.json`: ETag/Last-Modified cache, persisted across cloud runs.

Use one writer (workflow concurrency and a local process lock). Keep all these
outputs private. Reconcile issuer, fiscal period, full-call coverage, and applicable
filings into the existing packet contract before analysis. Agents should open local
text/manifests first and investigate only listed gaps. Never treat a downloaded
landing page as a completed document packet. Retention and long-term object-storage
migration are needed before collecting a large historical corpus in Git.

## Private GitHub Actions

Install the runner workflow in the private data repository, where its built-in
GITHUB_TOKEN can commit collection files to that same repository. Pin the public
code in `workflow.json`; keep issuer source configuration private. No Codex session,
ChatGPT authentication cache, model API key, or personal access token belongs in
the workflow. This downloader does not use the Codex subscription.

Manual cloud collection and recurring scheduling are separate states. Verify a
bounded manual run, remote files, and repeat-run deduplication before enabling a
recurring trigger. Keep research analysis disabled until its separate agent
scheduler and writeback have been verified. A private Actions run proves only the
downloader's execution and persistence, not that Codex analysis runs unattended.

References: [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[SEC developer access](https://www.sec.gov/about/developer-resources),
[GitHub workflow token](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).

## Whole-universe pipeline

`python3 -m research.pipeline --root /private/data --mode collect --limit 25`
replaces the pilot's fixed universe with resumable batches. `--mode plan` prepares
source coverage and the due queue without downloading; `--mode reconcile` rebuilds
the catalog and published-period tracker without downloading. Private
`config.json.earnings_pipeline.enabled` gates collection independently of investment
analysis. All tracked companies stay in coverage; only verified, unambiguous issuer
identities enter collection. Approved issuer sources are reused; other SEC-verified
companies use SEC submissions while their issuer-source candidates await review.
Observed calendar URLs do not automatically authorize source ownership.

The initial baseline visits every eligible issuer. Subsequently, confirmed or
estimated calendar dates trigger discovery from day -1 through day 7 every two
hours, then incomplete packets daily through day 60. Calendar estimates never assign
accepted fiscal periods. Outside those windows, weekly discovery catches missed or
rescheduled releases. Each run recomputes dates from calendar/latest.json, instead
of trusting an old collection-candidates file. At least one third of batch capacity
is available for the unfinished baseline. Three failed issuer attempts back off for
one week and retain a repair handoff. Budget-exhausted/unvisited names are deferred,
not counted as completed baseline work. A baseline attempt does not mean a complete
packet. Repeated unchanged text does not add another analysis item.

The runner uses one writer and a shared HTTP cache, capped at 240 requests and
192 MiB per batch. Pipeline state is in pipeline/state.json, due work in
pipeline/collection-queue.json, and per-run receipts under pipeline/runs/. Interrupted
work can safely retry immutable objects and checkpointed manifests. The private
workflow persists partial results before reporting failures.

After collection, research.published_quarters records the latest observed fiscal
period in published/latest.json and queues exact evidence in published/review-queue.json.
Original SEC inline-XBRL fiscal facts and explicit actual-results clauses can suggest
a period; dates alone cannot. Conflicting dates, annual-versus-quarterly ambiguity,
missing language/completeness and unresolved identities stay in review. Fiscal years
follow each issuer, never a month-to-quarter conversion. `discovery_complete: false`
means this is the latest observed evidence, not proof every public source was found.

A separate bounded private Codex PR handoff reviews original evidence and writes
qualifications. Reconciliation assembles immutable packets from accepted qualifications,
with freshness and missing-document states. Agent invocation acknowledgment is not
qualification completion; the private main-branch evidence is authoritative. This
pipeline does not automatically run investment analysis or treat unreviewed period
candidates as accepted earnings packets.
