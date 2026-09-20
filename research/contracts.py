"""Public document contracts. No network, portfolio state, or investment decisions."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from urllib.parse import urlsplit

KINDS = {'release', 'transcript', 'periodic_filing', 'annual_background', 'presentation'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def public_url(value):
    u = urlsplit(value or '')
    require(u.scheme == 'https' and u.hostname and not u.username and not u.password,
            'Source must be an HTTPS URL without credentials')


def watchlist(value):
    require(isinstance(value, list) and value, 'Nonempty watchlist required')
    for row in value:
        require(set(row) <= {'symbol', 'issuer', 'exchange', 'ir_url', 'regulator_id'},
                'Watchlist contains unapproved fields; do not upload portfolio context')
        require(all(isinstance(row.get(k), str) and row[k].strip()
                    for k in ('symbol', 'issuer', 'exchange')), 'Issuer identity required')
        require(row['exchange'] != 'UNRESOLVED', 'Resolve issuer exchange before activation')
        if row.get('ir_url'):
            public_url(row['ir_url'])
    require(len({r['symbol'] for r in value}) == len(value), 'Duplicate watchlist symbols')
    return value


def validate_calendar(value, universe):
    allowed = {r['symbol'] for r in watchlist(universe)}
    coverage = value['coverage']
    require(len(coverage) == len(allowed) and {r['symbol'] for r in coverage} == allowed,
            'Calendar must account for every issuer exactly once')
    for row in coverage:
        require(row['status'] in {'checked', 'unavailable', 'not_applicable'}, 'Bad coverage status')
        if row.get('source_url'):
            public_url(row['source_url'])
        require(row['status'] != 'checked' or row.get('source_url'), 'Checked requires source')
    seen = set()
    for event in value['events']:
        require(event['symbol'] in allowed, 'Calendar expanded beyond the watchlist')
        require(event['period'] and event['issuer'], 'Fiscal period and issuer required')
        date.fromisoformat(event['report_date'])
        require(event['date_status'] in {'confirmed', 'estimated'}, 'Bad date status')
        require(event['filing_kind'] in {'10-Q', '10-K', '20-F', '6-K', 'other'}, 'Bad filing kind')
        public_url(event['source_url'])
        if event.get('call_at'):
            require(datetime.fromisoformat(event['call_at'].replace('Z', '+00:00')).tzinfo,
                    'Call time needs a timezone')
        key = event_id(event)
        require(key not in seen, 'Duplicate issuer/period')
        seen.add(key)
    require(isinstance(value['report_markdown'], str), 'Calendar report required')
    return value


def event_id(event):
    return digest([event['symbol'], event['period']])[:24]


def validate_packet(value, previous=None):
    statuses = {'available', 'pending', 'not_published', 'access_blocked', 'not_applicable'}
    require(set(value['availability']) == KINDS, 'Document availability must cover all kinds')
    require(set(value['availability'].values()) <= statuses, 'Bad document status')
    seen = set()
    for doc in value['documents']:
        require(doc['kind'] in KINDS, 'Bad document kind')
        require(doc['completeness'] in {'full', 'partial'}, 'Completeness required')
        require(doc['publisher_type'] in {'issuer', 'regulator', 'third_party'}, 'Publisher required')
        require(isinstance(doc['text'], str) and len(doc['text'].strip()) >= 100,
                'Document text missing or implausibly short')
        public_url(doc['source_url'])
        require(doc['period'] and doc['title'], 'Document identity required')
        if doc.get('published_at'):
            timestamp = datetime.fromisoformat(doc['published_at'].replace('Z', '+00:00'))
            require(timestamp.tzinfo is not None, 'Publication timezone required')
            require(timestamp <= datetime.now(timezone.utc), 'Future publication timestamp')
        doc['document_id'] = digest([doc['source_url'], doc['text']])
        require(doc['document_id'] not in seen, 'Duplicate document')
        seen.add(doc['document_id'])
    # Prior versions remain available even if a corrected document was found.
    for doc in (previous or {}).get('documents', []):
        if doc['document_id'] not in seen:
            value['documents'].append(doc)
            seen.add(doc['document_id'])
    for kind, status in value['availability'].items():
        require(status != 'available' or any(d['kind'] == kind for d in value['documents']),
                'Available status requires a retrieved document')
    return value


def packet_id(packet):
    fields = ('document_id', 'kind', 'period', 'published_at', 'completeness', 'publisher_type')
    documents = sorted(({k: d.get(k) for k in fields} for d in packet['documents']),
                       key=lambda d: d['document_id'])
    return digest({'documents': documents,
                   'availability': packet['availability']})


def validate_extraction(value, packet):
    texts = {d['document_id']: d['text'] for d in packet['documents']}
    for quote in value['quotes']:
        require(quote['document_id'] in texts, 'Unknown quotation source')
        require(quote['text'] and quote['text'] in texts[quote['document_id']], 'Quote not verbatim')
        require(quote['speaker'] and quote['locator'], 'Quote attribution required')
    for row in value['data']:
        require(row['document_id'] in texts, 'Unknown data source')
        require(row['source_text'] and row['source_text'] in texts[row['document_id']],
                'Data support is not an exact source passage')
        require(all(row.get(k) for k in ('metric', 'unit', 'period', 'basis', 'locator', 'currency')),
                'Data lost its units, period, basis, or provenance')
        require(row['value'] is None or type(row['value']) in (int, float), 'Invalid numeric value')
        require(row['value'] is None or math.isfinite(row['value']), 'Non-finite numeric value')
        require(row['basis'] in {'GAAP', 'non-GAAP', 'operating_metric', 'guidance'}, 'Invalid basis')
    require(isinstance(value['gaps'], list), 'Gaps required')
    require(isinstance(value['report_markdown'], str) and value['report_markdown'].strip(), 'Report required')
    return value


def validate_commentary(value, packet):
    ids = {d['document_id'] for d in packet['documents']}
    for row in value['commentary']:
        require(row['classification'] in {'company_claim', 'fact', 'inference'}, 'Claim type required')
        require(row['document_ids'] and set(row['document_ids']) <= ids, 'Unsupported commentary')
        require(row['locators'] and row['claim'], 'Commentary locations required')
    for key in ('contradictions', 'questions', 'framework_coverage', 'report_markdown'):
        require(key in value, f'Missing {key}')
    return value


def validate_review(value, packet=None):
    require(value['verdict'] in {'pass', 'revise', 'blocked'}, 'Bad review verdict')
    require(isinstance(value['findings'], list), 'Review findings required')
    for row in value['findings']:
        require(row['target'] in {'extractor', 'commentator'}, 'Review target invalid')
        require(row['severity'] in {'material', 'minor'}, 'Review severity invalid')
        require(row['claim'] and row['evidence'] and row['required_change'], 'Unsubstantiated review')
        if packet is not None:
            require(set(row['document_ids']) <= {d['document_id'] for d in packet['documents']},
                    'Unknown review source')
    require(value['verdict'] != 'pass' or not any(r['severity'] == 'material' for r in value['findings']),
            'Cannot pass unresolved material findings')
    return value


def due(event, now):
    days = (now.date() - date.fromisoformat(event['report_date'])).days
    return -1 <= days <= 60
