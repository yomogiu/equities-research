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
iCalendar or unambiguous earnings table rows. Publication dates are never treated
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
  queue once; unchanged documents do not trigger another model analysis.
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
