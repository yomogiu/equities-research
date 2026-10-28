"""Bounded event attachments, selected by document evidence rather than labels."""
import re
from urllib.parse import urlsplit, urlunsplit
from .source_parse import page
from .fetch import FetchError

MAX_CANDIDATES = 8


def candidates(body, event_url):
    origin = urlsplit(event_url)
    found = {}
    for link in page(body, event_url).links:
        u = urlsplit(link['url'])
        # Only exact provider filing routes attached to this verified event.
        # Navigation, other events, arbitrary URLs and label text confer no trust.
        if (u.scheme, u.netloc) != (origin.scheme, origin.netloc):continue
        if not re.fullmatch(r'/filings/[^/]+/\d+/?', u.path):continue
        url = urlunsplit((u.scheme, u.netloc, u.path.rstrip('/')+'/', '', ''))
        row = found.setdefault(url, {'landing_url':url, 'labels':[]})
        if link['title'] not in row['labels']:row['labels'].append(link['title'])
    if not found:raise ValueError('Selected event has no attributable filing links')
    if len(found)>MAX_CANDIDATES:raise ValueError('Event attachment candidate limit exceeded')
    return list(found.values())


def binding(body, landing):
    """Read only the exact filing-ID record; do not execute embedded scripts."""
    identifier = urlsplit(landing).path.strip('/').split('/')[-1]
    if not identifier.isdigit():raise ValueError('Unrecognized provider filing identifier')
    matches = set()
    for obj in re.findall(r'\{[^{}]{0,4000}\}', body.decode('utf-8')):
        if not re.search(r'(?:\{|,)\s*"?id"?\s*:\s*"?'+re.escape(identifier)+r'"?\s*[,}]', obj):continue
        kind = re.search(r'(?:\{|,)\s*"?type"?\s*:\s*"([^"\n]+)"', obj)
        url = re.search(r'(?:\{|,)\s*"?fileUrl"?\s*:\s*"([^"\n]+)"', obj)
        if kind and url:matches.add((kind[1], url[1].replace('\\u002F','/').replace('\\/','/')))
    if len(matches)!=1:raise ValueError('Exact financial-document download binding unavailable')
    kind, url = matches.pop()
    return {'attachment_kind':kind, 'pdf_url':url, 'filing_id':identifier}


def select(body, event_url, fetch, inspect, decisions):
    """Try a finite set; metadata orders candidates, content qualifies them.

    inspect must perform PDF, coverage and deterministic contradiction checks.
    Ambiguous identity/period is resolved once, after selection, by the caller.
    """
    rows = candidates(body, event_url)
    available = []
    for row in rows:
        decisions.append(row)
        try:
            landing, http = fetch(row['landing_url'], 'report_landing')
            row.update(binding(landing, row['landing_url']), landing_sha256=http['sha256'])
            available.append(row)
        except (ValueError, FetchError) as exc:
            row.update(status='rejected', reason=str(exc))
    # Labels never affect eligibility. Prefer statement-bearing document types;
    # unknown/new types remain candidates, subject to identical content checks.
    rank = {'quarterly_report':0, 'annual_report':0, 'report':0, 'earnings_release':1}
    for row in sorted(available, key=lambda r:rank.get(r['attachment_kind'],2)):
        try:
            value = inspect(row)
        except (ValueError, FetchError) as exc:
            row.update(status='rejected', reason=str(exc));continue
        row['status']='selected'
        for other in available:
            if 'status' not in other:other['status']='not_needed'
        return row, value
    raise ValueError('No qualifying event financial document: '+'; '.join(r.get('reason','unavailable') for r in rows))
