"""Deterministic filing/IR collectors. Run with python -m research.collect --help."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from .cli import ROOT, read
from .contracts import require, watchlist
from .fetch import Client, FetchError, check_url, save_json
from .source_parse import EARNINGS, extract, feed_links, kind_for, page, structured_events, transcript_checks, calendar_events

SEC_HOSTS = {'data.sec.gov', 'www.sec.gov'}
ANNUAL = {'10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A'}
QUARTERLY = {'10-Q', '10-Q/A'}
CURRENT = {'8-K', '8-K/A', '6-K', '6-K/A'}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def identity(row):
    return 'cik-' + row['regulator_id'].zfill(10) if row.get('regulator_id') else hashlib.sha256(
        (row['exchange'] + ':' + row['symbol']).encode()).hexdigest()[:16]


def validate_registry(registry, universe):
    require(registry.get('schema_version') == 1, 'Unknown source registry version')
    entries = registry.get('issuers', {})
    require(isinstance(entries, dict), 'Registry issuers must be an object')
    for row in universe:
        entry = entries.get(row['symbol'], {})
        if entry.get('cik'):
            require(str(entry['cik']).zfill(10) == str(row.get('regulator_id', '')).zfill(10),
                    'Registry/watchlist CIK mismatch')
        for source in entry.get('pages', []) + entry.get('documents', []):
            u = urlsplit(source['url'])
            require(u.scheme == 'https' and u.hostname and not u.username and not u.password,
                    'Registry sources require public HTTPS URLs without credentials')
            require(not any(k in u.query.lower() for k in ('token=', 'key=', 'signature=')),
                    'Do not store credential-bearing URLs')
    return registry


def filing_rows(submissions):
    recent = submissions.get('filings', {}).get('recent', {})
    length = len(recent.get('accessionNumber', []))
    return [{key: values[i] for key, values in recent.items() if isinstance(values, list) and i < len(values)}
            for i in range(length)]


def select_filings(submissions, as_of, lookback=21, max_filings=4):
    """Recent earnings filings plus latest annual/quarterly baseline; preserve amendments."""
    rows = sorted(filing_rows(submissions), key=lambda r: (r.get('filingDate', ''),
                  r.get('acceptanceDateTime', ''), r['accessionNumber']), reverse=True)
    cutoff = (as_of - timedelta(days=lookback)).isoformat()
    chosen = []
    baseline = set()
    for row in rows:
        form = row.get('form', '')
        filed = row.get('filingDate', '')
        if not filed or filed > as_of.isoformat():
            continue
        family = 'annual' if form in ANNUAL else 'quarterly' if form in QUARTERLY else None
        if form in CURRENT:
            if filed < cutoff:
                continue
            if form.startswith('8-K') and '2.02' not in row.get('items', ''):
                continue
        elif family:
            if filed < (as_of - timedelta(days=550)).isoformat():
                continue
            # Include both original and amendment within lookback; newest baseline otherwise.
            if family in baseline and filed < cutoff:
                continue
            baseline.add(family)
        else:
            continue
        chosen.append(row)
        if len(chosen) >= max_filings:
            break
    return chosen


class Collector:
    def __init__(self, universe, registry, root, as_of=None, client=None,
                 sec_user_agent=None, mode='collect', max_filings=4, max_links=6):
        self.universe = watchlist(universe)
        self.registry = validate_registry(registry, universe)
        self.root = Path(root).resolve()
        require(self.root != ROOT and ROOT not in self.root.parents,
                'Collection data must remain outside the public checkout')
        self.root.mkdir(parents=True, exist_ok=True)
        self.as_of, self.mode = as_of or date.today(), mode
        self.sec_user_agent = sec_user_agent
        self.max_filings, self.max_links = max_filings, max_links
        hosts = set(SEC_HOSTS)
        for row in universe:
            entry = registry['issuers'].get(row['symbol'], {})
            hosts.update(h.lower() for h in entry.get('allowed_hosts', []))
            hosts.update(urlsplit(s['url']).hostname.lower()
                         for s in entry.get('pages', []) + entry.get('documents', []))
        self.client = client or Client(self.root, hosts,
            'equities-research/0.1 (+https://github.com/yomogiu/equities-research)')
        self.doc_index_path = self.root / 'document-index.json'
        self.doc_index = read(self.doc_index_path) if self.doc_index_path.exists() else {}
        self.event_path = self.root / 'calendar-candidates.json'
        self.events = read(self.event_path) if self.event_path.exists() else {}
        self.queue_path = self.root / 'analysis-queue.json'
        self.queue = read(self.queue_path) if self.queue_path.exists() else {}
        self.new_documents, self.gaps, self.checked = [], [], []
        self.failed_hosts = set()
        self.seen_documents = []
        self.current_events = 0

    def gap(self, row, source, code, kind=None):
        value = {'issuer_id': identity(row), 'symbol': row['symbol'], 'source_url': source,
                 'code': code, 'kind': kind}
        if value not in self.gaps:
            self.gaps.append(value)

    def get(self, row, url, fresh_seconds=900):
        host = urlsplit(url).hostname
        if host in self.failed_hosts:
            raise FetchError('host_backoff')
        entry = self.registry['issuers'].get(row['symbol'], {})
        allowed = SEC_HOSTS | set(entry.get('allowed_hosts', [])) | {urlsplit(s['url']).hostname for s in entry.get('pages', []) + entry.get('documents', [])}
        if host not in allowed:
            raise FetchError('unapproved_issuer_host')
        previous = self.client.user_agent
        if host in SEC_HOSTS:
            if not self.sec_user_agent or '@' not in self.sec_user_agent:
                raise FetchError('sec_contact_required')
            self.client.user_agent = self.sec_user_agent
        try:
            return self.client.get(url, fresh_seconds)
        except FetchError as exc:
            if exc.code in ('access_blocked', 'retry_later', 'http_429'):
                self.failed_hosts.add(host)
            raise
        finally:
            self.client.user_agent = previous

    def fetch_document(self, row, source, kind, title='', metadata=None, body_entry=None):
        try:
            body, entry = body_entry or self.get(row, source, fresh_seconds=86400)
            text, fiscal, status = extract(body, entry['content_type'], source)
            if status != 'extracted' or len(text) < 100:
                self.gap(row, source, status if status != 'extracted' else 'insufficient_text', kind)
                return None
            checks = transcript_checks(text)
            if kind in ('presentation', 'earnings_page') and len(text) < 3000 and 'html' in entry['content_type']:
                self.gap(row, source, 'landing_page_not_document', kind)
                return None
            # Conference pages may contain a transcript, but remarks alone are not a full call.
            if kind == 'earnings_page' and checks['substantial_call_text']:
                kind = 'transcript'
            if kind == 'transcript' and (not checks['substantial_call_text'] or re.search(r'prepared.remark', title + ' ' + source, re.I)):
                kind = 'prepared_remarks' if re.search(r'prepared.remark', title + ' ' + source, re.I) else 'transcript_candidate'
                self.gap(row, source, 'full_transcript_not_verified', 'transcript')
            text_sha = hashlib.sha256(text.encode()).hexdigest()
            document_id = hashlib.sha256((identity(row) + '\n' + kind + '\n' + text_sha).encode()).hexdigest()
            # Preserve existing IDs during upgrades; markup-only changes need no new analysis.
            for known_id, known in self.doc_index.items():
                if (known['issuer_id'] == identity(row) and known['kind'] == kind
                        and Path(known['text_path']).stem == text_sha):
                    document_id = known_id
                    break
            self.seen_documents.append((identity(row), kind))
            if document_id in self.doc_index:
                return self.doc_index[document_id]
            text_path = self.client.object(text.encode(), 'txt')
            document = {'document_id': document_id, 'issuer_id': identity(row), 'symbol': row['symbol'],
                        'issuer': row['issuer'], 'source_url': source, 'final_url': entry['final_url'],
                        'publisher_type': 'regulator' if urlsplit(source).hostname in SEC_HOSTS else 'issuer',
                        'kind': kind, 'title': title, 'retrieved_at': now_iso(),
                        'raw_path': entry['body_path'], 'raw_sha256': entry['sha256'],
                        'text_path': text_path, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                        'parse_status': status, 'characters': len(text), 'fiscal_tags': fiscal,
                        'metadata': metadata or {}, 'completeness': 'unverified',
                        'transcript_checks': checks if kind.startswith('transcript') or kind == 'prepared_remarks' else None,
                        'period_assignment': 'needs_review'}
            manifest = f'documents/{identity(row)}/{document_id}.json'
            save_json(self.root / manifest, document)
            brief = {k: document[k] for k in ('document_id', 'issuer_id', 'symbol', 'kind', 'title',
                                             'source_url', 'raw_sha256', 'text_path', 'retrieved_at')}
            brief['manifest_path'] = manifest
            self.doc_index[document_id] = brief
            self.new_documents.append(brief)
            # Keep uncertainty work separate from substantive analysis. No full-text LLM search.
            self.queue.setdefault(document_id, {'status': 'pending', 'document': brief,
                                               'next_stage': 'period_and_completeness_review'})
            return brief
        except FetchError as exc:
            self.gap(row, source, exc.code, kind)
            return None

    def sec(self, row):
        cik = row.get('regulator_id')
        if not cik:
            self.gap(row, None, 'regulator_adapter_required', 'filing')
            return
        url = f'https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json'
        try:
            body, _ = self.get(row, url)
            data = json.loads(body)
            require(int(data['cik']) == int(cik), 'SEC returned a different issuer')
            selected = select_filings(data, self.as_of, max_filings=self.max_filings)
            for f in selected:
                accession = f['accessionNumber']
                require(bool(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession)), 'Invalid accession')
                document = f['primaryDocument']
                require('/' not in document and '..' not in document, 'Invalid primary document')
                base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
                doc_url = base + quote(document)
                kind = 'annual_background' if f['form'] in ANNUAL else 'periodic_filing' if f['form'] in QUARTERLY else 'current_report'
                self.fetch_document(row, doc_url, kind, f['form'] + ' ' + f.get('reportDate', ''),
                                    {k: f.get(k) for k in ('accessionNumber', 'form', 'filingDate', 'reportDate', 'acceptanceDateTime')})
                if f['form'] in CURRENT:
                    index_url = base + accession + '-index.html'
                    try:
                        index_body, _ = self.get(row, index_url, 86400)
                        p = page(index_body, index_url)
                        for tr in p.rows:
                            if any(re.fullmatch(r'EX-99(?:\.\d+)?', cell) for cell in tr['cells']):
                                for link in tr['links'][:1]:
                                    # An EX-99 exhibit can be something other than earnings.
                                    self.fetch_document(row, link['url'], 'earnings_exhibit_candidate',
                                                        ' '.join(tr['cells'][:4]),
                                                        {'accessionNumber': accession, 'form': f['form'], 'filingDate': f['filingDate']})
                    except FetchError as exc:
                        self.gap(row, index_url, exc.code, 'release')
            if not selected:
                self.gap(row, url, 'no_matching_recent_filings', 'filing')
        except FetchError as exc:
            self.gap(row, url, exc.code, 'filing')
        except (ValueError, KeyError, TypeError):
            self.gap(row, url, 'invalid_submissions_response', 'filing')

    def capture_events(self, row, p, events=None):
        for event in (structured_events(p) if events is None else events):
            self.current_events += 1
            event.update(issuer_id=identity(row), symbol=row['symbol'])
            # Stable identity allows a corrected date to supersede an earlier date.
            key = hashlib.sha256((identity(row) + p.base + event['title']).encode()).hexdigest()
            previous = self.events.get(key)
            if previous and previous.get('start') != event['start']:
                event['previous_starts'] = previous.get('previous_starts', []) + [previous['start']]
            elif previous:
                event['previous_starts'] = previous.get('previous_starts', [])
            self.events[key] = event

    def ir(self, row):
        entry = self.registry['issuers'].get(row['symbol'], {})
        if not entry.get('pages') and not entry.get('documents'):
            self.gap(row, None, 'ir_source_not_configured', 'calendar_and_transcript')
            return
        if self.mode != 'calendar':
            for source in entry.get('documents', []):
                self.fetch_document(row, source['url'], source['kind'], source.get('title', ''),
                                    {k: source[k] for k in ('period', 'published_at') if k in source})
        candidates = []
        seen_pages = set()
        for source in entry.get('pages', []):
            url = source['url']
            try:
                body, http = self.get(row, url)
                p = page(body, http['final_url'])
                seen_pages.add(url)
                events = calendar_events(body, url, source.get('format', 'html'))
                self.capture_events(row, p, events)
                links = feed_links(body, url) if source.get('format') == 'rss' else p.links
                for link in links:
                    kind = kind_for(link['title'], link['url'])
                    if kind and link['url'] not in seen_pages and urlsplit(link['url']).hostname in (set(entry.get('allowed_hosts', [])) | {urlsplit(s['url']).hostname for s in entry.get('pages', []) + entry.get('documents', [])}):
                        # Skip obviously old archive links; unrecognized dates remain candidates.
                        years = re.findall(r'(?<!\d)(20\d{2})(?!\d)', link['title'] + ' ' + link['url'])
                        if years and max(map(int, years)) < self.as_of.year - 1:
                            continue
                        candidates.append({**link, 'kind': kind})
                if not links:
                    self.gap(row, url, 'no_static_links_or_feed_items', 'source_page')
                if not events:
                    self.gap(row, url, 'no_structured_earnings_date', 'calendar')
            except FetchError as exc:
                self.gap(row, url, exc.code, 'source_page')
        # Prioritize explicit transcripts/releases over generic earnings pages.
        priority = {'transcript': 0, 'release': 1, 'presentation': 2, 'annual_background': 3, 'periodic_filing': 3, 'earnings_page': 4}
        unique = {}
        for c in sorted(candidates, key=lambda c: priority[c['kind']]):
            unique.setdefault(c['url'], c)
        if len(unique) > self.max_links:
            self.gap(row, None, 'discovery_link_limit', 'source_page')
        for source in list(unique.values())[:self.max_links]:
            try:
                body, http = self.get(row, source['url'])
                p = page(body, http['final_url'])
                self.capture_events(row, p)
                if self.mode != 'calendar':
                    self.fetch_document(row, source['url'], source['kind'], source['title'],
                                        body_entry=(body, http))
                    # One bounded additional hop for explicit transcript/release links on event pages.
                    if source['kind'] == 'earnings_page':
                        follow = [l for l in p.links if kind_for(l['title'], l['url']) in ('transcript', 'release')
                                  and l['url'] != source['url'] and urlsplit(l['url']).hostname in (set(entry.get('allowed_hosts', [])) | {urlsplit(s['url']).hostname for s in entry.get('pages', []) + entry.get('documents', [])})]
                        for link in follow[:2]:
                            self.fetch_document(row, link['url'], kind_for(link['title'], link['url']), link['title'])
            except FetchError as exc:
                self.gap(row, source['url'], exc.code, source['kind'])
        if self.mode != 'calendar' and (identity(row), 'transcript') not in self.seen_documents:
            self.gap(row, None, 'full_transcript_not_observed_this_run', 'transcript')

    def run(self):
        for row in self.universe:
            self.checked.append(identity(row))
            if self.mode != 'calendar':
                self.sec(row)
            self.ir(row)
        save_json(self.doc_index_path, self.doc_index)
        save_json(self.queue_path, self.queue)
        save_json(self.event_path, self.events)
        save_json(self.root / 'source-gaps.json', {'checked_at': now_iso(), 'gaps': self.gaps})
        receipt = {'run_at': now_iso(), 'mode': self.mode, 'issuers_checked': len(self.checked),
                   'status': 'partial' if self.gaps and (self.seen_documents or self.current_events) else 'blocked' if self.gaps else 'collected',
                   'documents_checked': len(self.seen_documents),
                   'new_documents': len(self.new_documents), 'total_documents': len(self.doc_index),
                   'calendar_candidates': len(self.events), 'gaps': len(self.gaps),
                   'requests': self.client.requests, 'cache_hits': self.client.cache_hits,
                   'bytes_downloaded': self.client.bytes, 'model_calls': 0,
                   'change_ids': [r['document_id'] for r in self.new_documents]}
        save_json(self.root / 'latest-run.json', receipt)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        save_json(self.root / 'runs' / (run_id + '.json'), receipt)
        return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--watchlist', required=True, type=Path)
    p.add_argument('--registry', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['plan', 'collect', 'calendar'], default='plan')
    p.add_argument('--symbols', help='Comma-separated subset; defaults to the supplied watchlist')
    p.add_argument('--limit', type=int, default=25)
    p.add_argument('--max-filings', type=int, default=4)
    p.add_argument('--max-links', type=int, default=6)
    p.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    a = p.parse_args()
    require(1 <= a.limit <= 450 and 1 <= a.max_filings <= 10 and 1 <= a.max_links <= 20,
            'Invalid collection limits')
    universe = watchlist(read(a.watchlist))
    if a.symbols:
        selected = set(a.symbols.split(','))
        require(selected <= {r['symbol'] for r in universe}, 'Unknown requested symbol')
        universe = [r for r in universe if r['symbol'] in selected]
    universe = universe[:a.limit]
    registry = validate_registry(read(a.registry), universe)
    if a.mode == 'plan':
        print(json.dumps({'mode': 'plan', 'issuers': len(universe), 'model_calls': 0,
                          'network_calls': 0, 'configured_ir_issuers': sum(bool(registry['issuers'].get(r['symbol'], {}).get('pages')) for r in universe)}))
        return
    collector = Collector(universe, registry, a.output, a.as_of,
                          sec_user_agent=os.environ.get('SEC_USER_AGENT'), mode=a.mode,
                          max_filings=a.max_filings, max_links=a.max_links)
    with (collector.root / '.collector.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = collector.run()
    # Never expose the watchlist or document text in public console output.
    print(json.dumps({k: v for k, v in receipt.items() if k != 'change_ids'}))


if __name__ == '__main__':
    main()
