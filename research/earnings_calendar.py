"""Whole-universe earnings calendar, explicit uncertainty, no model execution."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from .contracts import digest, require
from .earnings_dates import DATE_TOKEN, parse_events
from .fetch import Client, FetchError, Redirects, check_url
from .library import lock, private_root, read_json, save
from .source_parse import page

# Public example endpoint documented by the provider; 'demo' is not a user secret.
PROVIDER_URL = 'https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=demo'
USER_AGENT = 'equities-research/0.1 (+https://github.com/yomogiu/equities-research)'
LINK_LABEL = re.compile(r'calendar|events?|to (?:report|announce)|will (?:report|announce)|earnings.call|financial.results|財務日曆|決算発表|財報', re.I)
HOST_LOCKS, HOST_LAST, HOST_GUARD = {}, {}, threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


class CalendarClient(Client):
    """Bounded shared-host requests and gzip source evidence for private Git."""
    def object(self, body, suffix='bin'):
        relative = f'objects/{hashlib.sha256(body).hexdigest()}.{suffix}.gz'
        target = self.root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(body, mtime=0))
        return relative

    def _cached(self, entry):
        if not entry:
            return None
        path = self.root / entry['body_path']
        if not path.exists():
            return None
        try:
            body = gzip.decompress(path.read_bytes())
        except (OSError, EOFError) as exc:
            raise FetchError('cache_integrity_error') from exc
        if hashlib.sha256(body).hexdigest() != entry['sha256']:
            raise FetchError('cache_integrity_error')
        return body

    def _request(self, url, headers):
        host = urlsplit(url).hostname
        with HOST_GUARD:
            mutex = HOST_LOCKS.setdefault(host, threading.Lock())
        with mutex:
            time.sleep(max(0, .35 - (time.monotonic() - HOST_LAST.get(host, 0))))
            HOST_LAST[host] = time.monotonic()
            try:
                with build_opener(Redirects(self.hosts)).open(Request(url, headers=headers), timeout=10) as response:
                    return response.status, dict(response.headers.items()), response.read(self.max_document_bytes + 1), response.url
            except HTTPError as exc:
                return exc.code, dict(exc.headers.items()), b'', url
            except (URLError, TimeoutError, OSError) as exc:
                raise FetchError('network_error') from exc


def words(value):
    ignored = {'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'ltd', 'limited',
               'plc', 'holdings', 'holding', 'group', 'sa', 'nv', 'the', 'technologies', 'technology'}
    return {x for x in re.findall(r'[a-z0-9]+', value.lower()) if len(x) > 1 and x not in ignored}


def provider_events(body, companies, as_of, days=90):
    text = body.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    require({'symbol', 'name', 'reportDate', 'fiscalDateEnding'} <= set(reader.fieldnames or []),
            'Provider did not return an earnings calendar CSV (demo access may be unavailable)')
    by_symbol = {}
    for row in companies:
        if row.get('monitoring_eligible') and row.get('exchange', '').lower() in {'nasdaq', 'nyse', 'nyse american', 'amex'}:
            by_symbol.setdefault(row.get('symbol'), []).append(row)
    events, rows, invalid, dates_seen = [], 0, 0, []
    for item in reader:
        rows += 1
        try:
            dates_seen.append(date.fromisoformat(item['reportDate']))
        except (ValueError, TypeError):
            pass
        matches = by_symbol.get(item['symbol'], [])
        if len(matches) != 1:
            continue
        owner = matches[0]
        try:
            day = date.fromisoformat(item['reportDate'])
            period_end = date.fromisoformat(item['fiscalDateEnding']).isoformat()
        except (ValueError, TypeError):
            invalid += 1
            continue
        if not as_of <= day <= as_of + timedelta(days=days):
            continue
        consistent = bool(words(item['name']) & words(owner['issuer']))
        event = {'issuer_id': owner['issuer_id'], 'symbol': owner.get('symbol'),
                 'title': item['name'] + ' expected earnings', 'event_date': day.isoformat(),
                 'event_type': 'results', 'report_date': day.isoformat(),
                 'call_at': None, 'time_label': item.get('timeOfTheDay') or None,
                 'fiscal_period': None, 'fiscal_period_end': period_end,
                 'date_status': 'estimated' if consistent else 'source_identity_review',
                 'source_kind': 'provider_estimate', 'source_url': PROVIDER_URL,
                 'evidence_excerpt': dict(item), 'provider': 'Alpha Vantage public demo calendar',
                 'limitations': ['Expected date, not issuer confirmation.', 'Public demo availability is not guaranteed.']}
        event['event_id'] = digest([owner['issuer_id'], 'alpha_vantage', period_end])
        events.append(event)
    require(rows > 0, 'Empty provider calendar is unavailable, not proof of no events')
    require(any(as_of <= day <= as_of + timedelta(days=days) for day in dates_seen),
            'Provider calendar is stale or outside the requested window')
    return events, {'provider_rows': rows, 'matched_events': len(events), 'invalid_matched_rows': invalid,
                    'earliest_provider_date': min(dates_seen).isoformat(), 'latest_provider_date': max(dates_seen).isoformat()}


def scan_issuer(owner, entry, root, as_of, days=90):
    iid = owner['issuer_id']
    seeds = entry.get('pages', [])[:3]
    result = {'issuer_id': iid, 'attempts': [], 'events': [], 'requests': 0, 'cache_hits': 0}
    if not seeds:
        result['source_status'] = 'no_issuer_source'
        return result
    hosts = {urlsplit(p['url']).hostname.lower() for p in seeds}
    client_root = root / 'sources' / digest(iid)
    client = CalendarClient(client_root, hosts, USER_AGENT, max_requests=8,
                            max_bytes=16 * 1024 * 1024, max_document_bytes=4 * 1024 * 1024)
    pending, visited, blocked = list(seeds), set(), set()
    while pending and len(visited) < 6:
        source = pending.pop(0)
        url = source['url']
        if url in visited or urlsplit(url).hostname in blocked:
            continue
        visited.add(url)
        try:
            body, receipt = client.get(url, fresh_seconds=3600)
            evidence = {'path': str((client_root / receipt['body_path']).relative_to(root)),
                        'sha256': receipt['sha256'], 'checked_at': receipt['checked_at']}
            events = parse_events(body, receipt['final_url'], source.get('format', 'html'))
            accepted = 0
            for candidate in events:
                try:
                    start = datetime.fromisoformat(candidate['start'].replace('Z', '+00:00'))
                except (ValueError, KeyError, TypeError):
                    continue
                day = start.date()
                if not as_of - timedelta(days=14) <= day <= as_of + timedelta(days=days):
                    continue
                trusted = source.get('issuer_verified') is True
                explicit = candidate.get('date_status', '').startswith('issuer_published') and candidate.get('date_status') != 'issuer_published_tentative'
                status = ('confirmed' if trusted and owner.get('monitoring_eligible') else
                          'issuer_date_identity_review') if explicit else 'date_needs_review'
                title = candidate.get('title', '')
                event_type = 'call' if re.search(r'call|webcast|説明会|法說會|法说会', title, re.I) else 'results' if re.search(r'results|release|report|決算発表|公布|公佈', title, re.I) else 'earnings_event'
                # Preserve fiscal labels but remove explicit event dates from identity.
                key = candidate.get('fiscal_period') or re.sub(r'\s+', ' ', DATE_TOKEN.sub('[date]', title)).strip()
                event = {**candidate, 'issuer_id': iid, 'symbol': owner.get('symbol'),
                         'event_id': digest([iid, receipt['final_url'], key, event_type]),
                         'event_date': day.isoformat(), 'event_type': event_type,
                         'report_date': day.isoformat() if event_type == 'results' else None,
                         'call_at': start.isoformat() if event_type == 'call' and start.tzinfo and 'T' in candidate['start'] else None,
                         'time_label': candidate.get('timezone_label'), 'date_status': status,
                         'source_kind': 'issuer_page', 'source_url': receipt['final_url'],
                         'source_evidence': evidence, 'source_trust': source.get('trust'),
                         'fiscal_period': candidate.get('fiscal_period'), 'fiscal_period_end': None}
                result['events'].append(event)
                accepted += 1
            result['attempts'].append({'url': url, 'status': 'fetched', 'events_in_window': accepted,
                                       'source_evidence': evidence})
            if source.get('format') != 'ics':
                links = sorted(page(body, receipt['final_url']).links,
                               key=lambda link: (0 if re.search(r'calendar|日曆|日历|カレンダー', link['title'], re.I) else
                                                 1 if re.search(r'events?|予定', link['title'], re.I) else 2))
                for link in links:
                    u = urlsplit(link['url'])
                    if (u.scheme == 'https' and u.hostname in hosts and not re.search(r'\.(pdf|zip|xlsx?)(?:\?|$)', link['url'], re.I)
                            and LINK_LABEL.search(link['title']) and link['url'] not in visited
                            and len(pending) + len(visited) < 6):
                        pending.append({'url': link['url'], 'format': 'ics' if '.ics' in u.path else 'html',
                                        'trust': source.get('trust'), 'issuer_verified': source.get('issuer_verified', False)})
        except (FetchError, ValueError, UnicodeError) as exc:
            code = exc.code if isinstance(exc, FetchError) else 'parse_error'
            result['attempts'].append({'url': url, 'status': code})
            if code in {'access_blocked', 'retry_later', 'network_error', 'http_429'}:
                blocked.add(urlsplit(url).hostname)
    result.update(requests=client.requests, cache_hits=client.cache_hits,
                  source_status='checked' if any(a['status'] == 'fetched' for a in result['attempts']) else 'source_unavailable')
    return result


def reconcile(companies, observations, previous, as_of, days=90):
    """Every company gets coverage; stale or uncertain dates cannot authorize analysis."""
    stamp = now()
    grouped = {}
    for event in observations:
        grouped.setdefault(event['event_id'], []).append(event)
    fresh = {}
    for key, group in grouped.items():
        dates = {e['event_date'] for e in group}
        for day in sorted(dates):
            matches = [e for e in group if e['event_date'] == day]
            event = dict(matches[0], last_seen_at=stamp, freshness='current')
            if len(dates) > 1:
                event['event_id'] = digest([key, day])
                event['date_status'] = 'conflict'
            elif any(e['date_status'] != event['date_status'] for e in matches):
                event['date_status'] = 'date_needs_review'
            fresh[event['event_id']] = event
    period_groups = {}
    for event in fresh.values():
        period = event.get('fiscal_period') or event.get('fiscal_period_end')
        if period:
            period_groups.setdefault((event['issuer_id'], period, event.get('event_type')), []).append(event)
    for group in period_groups.values():
        if len({e['event_date'] for e in group}) > 1:
            for event in group:
                event['date_status'] = 'conflict'
    old = {e['event_id']: e for e in previous.get('events', [])}
    changes = []
    for key, event in fresh.items():
        prior = old.get(key)
        if prior and any(prior.get(f) != event.get(f) for f in ['event_date', 'report_date', 'call_at', 'date_status']):
            changes.append({'event_id': key, 'issuer_id': event['issuer_id'], 'change': 'revised',
                            'previous': {f: prior.get(f) for f in ['event_date', 'report_date', 'call_at', 'date_status']},
                            'current': {f: event.get(f) for f in ['event_date', 'report_date', 'call_at', 'date_status']}})
        elif not prior:
            changes.append({'event_id': key, 'issuer_id': event['issuer_id'], 'change': 'new',
                            'event_date': event['event_date']})
    for key, event in old.items():
        day = date.fromisoformat(event['event_date'])
        if key not in fresh and as_of - timedelta(days=14) <= day <= as_of + timedelta(days=days):
            fresh[key] = dict(event, freshness='not_observed_this_run')
            if event.get('freshness') == 'current':
                changes.append({'event_id': key, 'issuer_id': event['issuer_id'], 'change': 'not_observed'})
    return list(sorted(fresh.values(), key=lambda e: (e['event_date'], e['issuer_id'], e['event_id']))), changes


def coverage_rows(companies, events, attempts, as_of, provider_status):
    rows = []
    for owner in companies:
        iid = owner['issuer_id']
        matched = [e for e in events if e['issuer_id'] == iid]
        upcoming = [e for e in matched if e['event_date'] >= as_of.isoformat() and e['freshness'] == 'current']
        check = attempts.get(iid, {'source_status': 'not_checked', 'attempts': []})
        statuses = {e['date_status'] for e in upcoming}
        if not owner.get('monitoring_eligible'):
            status = 'identity_review'
        elif 'conflict' in statuses:
            status = 'conflict'
        elif 'confirmed' in statuses:
            status = 'confirmed'
        elif 'estimated' in statuses:
            status = 'estimated'
        elif upcoming:
            status = 'date_review'
        elif any(e['freshness'] != 'current' and e['event_date'] >= as_of.isoformat() for e in matched):
            status = 'stale'
        elif check['source_status'] == 'checked':
            status = 'no_upcoming_date_found'
        else:
            status = 'source_gap'
        preferred = sorted(upcoming, key=lambda e: (e['date_status'] != 'confirmed', e['event_date']))
        rows.append({'issuer_id': iid, 'issuer': owner['issuer'], 'symbol': owner.get('symbol'),
                     'exchange': owner.get('exchange'), 'identity_status': owner.get('identity_status'),
                     'monitoring_eligible': bool(owner.get('monitoring_eligible')), 'status': status,
                     'next_date': preferred[0]['event_date'] if preferred else None,
                     'next_date_status': preferred[0]['date_status'] if preferred else None,
                     'event_ids': [e['event_id'] for e in matched],
                     'issuer_source_status': check['source_status'], 'source_attempts': check['attempts'],
                     'provider_status': provider_status,
                     'action': 'Resolve issuer/listing identity; do not dispatch analysis.' if not owner.get('monitoring_eligible') else
                               'Verify issuer confirmation and fiscal period before document/analysis routing.'})
    return rows


def render_report(result):
    esc = lambda x: html.escape(str(x if x is not None else '—'))
    rows = []
    by_id = {e['event_id']: e for e in result['events']}
    for row in sorted(result['coverage'], key=lambda r: (r['next_date'] or '9999', r['issuer'].lower())):
        links = []
        for eid in row['event_ids'][:4]:
            e = by_id[eid]
            links.append(f'<a href="{esc(e["source_url"])}">{esc(e["event_date"])} · {esc(e["date_status"])} · {esc(e["freshness"])}</a>')
        rows.append('<tr>' + ''.join(f'<td>{esc(row[k])}</td>' for k in ['issuer', 'symbol', 'exchange', 'status', 'next_date'])
                    + '<td>' + '<br>'.join(links) + '</td></tr>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>Earnings calendar</title><style>body{font:15px system-ui;margin:32px;color:#172331}table{border-collapse:collapse;width:100%}'
            'td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}input{padding:10px;width:340px}a{color:#165fb4}</style>'
            f'<h1>Earnings calendar · {esc(result["as_of"])}</h1><p>{len(result["coverage"])} tracked companies · '
            f'{esc(result["window_start"])} to {esc(result["window_end"])} · America/New_York</p>'
            '<p>Estimated dates are not issuer confirmations. Identity, source, stale-date and fiscal-period gaps remain explicit. No analysis is dispatched.</p>'
            f'<p>{esc(json.dumps(result["counts"], sort_keys=True))}</p>'
            '<p><a href="latest.json">Calendar JSON</a> · <a href="review-queue.json">Review queue</a> · <a href="changes.json">Changes</a></p>'
            '<input id="filter" placeholder="Filter company, ticker, status or date" aria-label="Filter calendar">'
            '<table><thead><tr><th>Company</th><th>Ticker</th><th>Exchange</th><th>Status</th><th>Next date</th><th>Evidence</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table>'
            '<script>document.getElementById("filter").addEventListener("input",function(){const q=this.value.toLowerCase();'
            'document.querySelectorAll("tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></html>')


def run(root, universe_path, registry_path, as_of=None, days=90, workers=8, provider=True):
    root = private_root(root)
    require(1 <= days <= 180 and 1 <= workers <= 12, 'Bounded horizon/workers required')
    companies = read_json(root / universe_path)['companies']
    require(len({r['issuer_id'] for r in companies}) == len(companies), 'Duplicate issuer IDs')
    registry = read_json(root / registry_path)['issuers']
    require(set(registry) == {r['issuer_id'] for r in companies}, 'Registry must account for entire universe')
    as_of = as_of or datetime.now(ZoneInfo('America/New_York')).date()
    base = root / 'calendar'
    base.mkdir(exist_ok=True)
    with lock(base):
        previous = read_json(base / 'latest.json') if (base / 'latest.json').exists() else {}
        stamp = now()
        run_id = stamp.replace(':', '').replace('+', '_')
        events, provider_receipt = [], {'status': 'disabled', 'requests': 0}
        if provider:
            client = CalendarClient(base / 'sources/provider', {'www.alphavantage.co'}, USER_AGENT,
                                    max_requests=2, max_bytes=8 * 1024 * 1024)
            try:
                body, receipt = client.get(PROVIDER_URL, fresh_seconds=3600)
                events, info = provider_events(body, companies, as_of, days)
                provider_receipt = dict(info, status='fetched', public_demo=True,
                                        source_url=PROVIDER_URL, sha256=receipt['sha256'],
                                        body_path='sources/provider/' + receipt['body_path'],
                                        checked_at=receipt['checked_at'], requests=client.requests)
                for event in events:
                    event['source_evidence'] = {'path': provider_receipt['body_path'], 'sha256': receipt['sha256'], 'checked_at': receipt['checked_at']}
            except (FetchError, ValueError, UnicodeError) as exc:
                provider_receipt = {'status': exc.code if isinstance(exc, FetchError) else 'invalid_provider_response',
                                    'source_url': PROVIDER_URL, 'requests': client.requests}
        attempts = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(scan_issuer, owner, registry[owner['issuer_id']], base, as_of, days): owner for owner in companies}
            for future in as_completed(futures):
                owner = futures[future]
                try:
                    receipt = future.result()
                except Exception as exc:
                    receipt = {'issuer_id': owner['issuer_id'], 'events': [], 'attempts': [],
                               'source_status': 'worker_error', 'error_type': type(exc).__name__}
                attempts[owner['issuer_id']] = receipt
                events.extend(receipt['events'])
                save(base / 'checkpoints' / (digest(owner['issuer_id']) + '.json'), dict(receipt, run_id=run_id))
                if len(attempts) % 50 == 0:
                    print(json.dumps({'calendar_companies_checked': len(attempts), 'total': len(companies)}), flush=True)
        events, changes = reconcile(companies, events, previous, as_of, days)
        coverage = coverage_rows(companies, events, attempts, as_of, provider_receipt['status'])
        result = {'schema_version': 1, 'run_id': run_id, 'generated_at': now(), 'as_of': as_of.isoformat(),
                  'window_start': (as_of-timedelta(days=14)).isoformat(), 'window_end': (as_of+timedelta(days=days)).isoformat(),
                  'timezone': 'America/New_York', 'tracked_companies': len(companies),
                  'counts': dict(Counter(row['status'] for row in coverage)),
                  'provider': provider_receipt, 'events': events, 'coverage': coverage,
                  'requests': provider_receipt.get('requests', 0) + sum(r.get('requests', 0) for r in attempts.values()),
                  'worker_errors': sum(r['source_status'] == 'worker_error' for r in attempts.values()),
                  'model_calls': 0, 'analysis_dispatched': False,
                  'limitations': ['Calendar covers every tracked candidate; source and listing gaps are not date confirmations.',
                                  'Provider public demo has no availability guarantee; failures retain prior dates as stale.',
                                  'Unknown fiscal periods require review; dates do not infer a fiscal quarter.']}
        save(base / 'runs' / (run_id + '.json'), result, immutable=True)
        save(base / 'latest.json', result)
        save(base / 'changes.json', {'run_id': run_id, 'changes': changes})
        review = [dict(r, reasons=['identity_or_date_source_gap'] if r['status'] not in {'confirmed','estimated'} else ['confirm_fiscal_period_and_date']) for r in coverage]
        save(base / 'review-queue.json', {'run_id': run_id, 'companies': review})
        eligible = {r['issuer_id'] for r in companies if r.get('monitoring_eligible')}
        due = [e for e in events if e['issuer_id'] in eligible and e['freshness'] == 'current'
               and e['date_status'] == 'confirmed' and e.get('fiscal_period')
               and as_of-timedelta(days=14) <= date.fromisoformat(e['event_date']) <= as_of+timedelta(days=2)]
        save(base / 'collection-candidates.json', {'run_id': run_id, 'events': due, 'dispatch_enabled': False})
        (base / 'index.html').write_text(render_report(result), encoding='utf-8')
        print(json.dumps({k: result[k] for k in ['tracked_companies','counts','requests','worker_errors','model_calls']}), flush=True)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('--universe', default='inputs/watchlist.catalog.json')
    p.add_argument('--registry', default='inputs/calendar-sources.json')
    p.add_argument('--as-of', type=date.fromisoformat)
    p.add_argument('--days', type=int, default=90)
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--no-provider', action='store_true')
    args = p.parse_args()
    result = run(args.root, args.universe, args.registry, args.as_of, args.days, args.workers, not args.no_provider)
    if result['worker_errors']:
        raise SystemExit('Calendar persisted with worker errors; inspect private coverage and checkpoints.')


if __name__ == '__main__':
    main()
