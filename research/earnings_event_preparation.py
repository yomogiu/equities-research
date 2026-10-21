"""Explicit reviewed release/current-report preparation, without periodic relabeling.

This route discovers no evidence, approves no mappings and launches no model. The
caller must reserve a qualified current release/call packet, an independently
reviewed SEC current-report companion, and reviewed release financial cells.
Ordinary preparation retains its full current-period periodic-filing requirement.
"""
from datetime import date, datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlsplit

from . import earnings_report_flow as flow, library, freshness
from . import financial_html_tables as tables
from .source_parse import extract, page

VERSION = 'reviewed-current-event-preparation-v1'
SELECTION_FIELDS = ('version', 'enabled', 'packet_id', 'issuer_id', 'period',
                    'release_document_id', 'current_report_path', 'current_report_sha256',
                    'review_path', 'review_sha256', 'author_id', 'reviewer_id',
                    'period_end', 'period_evidence', 'observation_path', 'observation_sha256')
REVIEW_FIELDS = ('version', 'packet_id', 'issuer_id', 'release_document_id',
                 'current_report_sha256', 'author_id', 'reviewer_id', 'period_end',
                 'period_evidence', 'observation_path', 'observation_sha256', 'verdict')


def require(value, message):
    if not value:
        raise ValueError(message)


def _bound(root, path, digest):
    target = library.resolve(root, path)
    require(not target.is_symlink(), 'Event source cannot be a symlink')
    return library.load_bytes(root, path, digest)


def authenticate(root, packet, selection):
    """Replay only the caller's exact independent source selection and receipt."""
    root = Path(root).resolve()
    tables.fields(selection, SELECTION_FIELDS, 'event selection')
    require(selection['version'] == VERSION and selection['enabled'] is True,
            'Explicit current-event selection required')
    for key in ('packet_id', 'issuer_id', 'period'):
        require(selection[key] == packet[key], 'Event selection differs from packet')
    author, reviewer = selection['author_id'], selection['reviewer_id']
    require(all(isinstance(x, str) and x.strip() for x in (author, reviewer)) and author != reviewer,
            'Distinct event source author and reviewer required')
    releases = [d for d in packet['documents'] if d['kind'] == 'release'
                and d['period'] == packet['period'] and d['completeness'] == 'full']
    calls = [d for d in packet['documents'] if d['kind'] == 'transcript'
             and d['period'] == packet['period'] and d['completeness'] == 'full']
    require(len(releases) == len(calls) == 1, 'One full current release and transcript required')
    release, call = releases[0], calls[0]
    require(release['document_id'] == selection['release_document_id'], 'Different selected release')
    review = tables._json(_bound(root, selection['review_path'], selection['review_sha256']))
    tables.fields(review, REVIEW_FIELDS, 'event source review')
    require(review['verdict'] == 'pass_event_sources_only', 'Independent event source review pending')
    for key in REVIEW_FIELDS:
        if key != 'verdict':
            require(review[key] == selection[key], 'Event source review binding differs')
    manifest = tables._json(_bound(root, selection['current_report_path'], selection['current_report_sha256']))
    require(manifest.get('kind') == 'current_report' and manifest.get('symbol') and
            manifest.get('metadata', {}).get('form') == '8-K', 'Actual SEC current report required')
    cik = re.fullmatch(r'sec:(\d{10})', packet['issuer_id'])
    require(cik is not None and manifest.get('issuer_id') in
            (packet['issuer_id'], 'cik-' + cik[1]), 'Current report issuer mismatch')
    url = urlsplit(manifest['source_url'])
    require(url.scheme == 'https' and url.hostname == 'www.sec.gov' and not url.query
            and not url.fragment and not url.username and not url.password
            and re.fullmatch(r'/Archives/edgar/data/' + str(int(cik[1])) +
                             r'/\d{18}/[^/]+\.html?', url.path), 'Exact issuer SEC archive URL required')
    raw = _bound(root, manifest['raw_path'], manifest['raw_sha256'])
    text = _bound(root, manifest['text_path'], manifest['text_sha256']).decode('utf-8')
    observations = tables._json(_bound(root, selection['observation_path'], selection['observation_sha256']))
    observed = observations.get(manifest['source_url'], {})
    require(observed.get('sha256') == manifest['raw_sha256'] and
            observed.get('final_url') == manifest['source_url'], 'Current-report HTTP observation differs')
    config = library.read_json(root/'config.json')
    limits = freshness.policy(config.get('packet_freshness'))
    observed_source = {'source_url': manifest['source_url'], 'kind': 'release',
                       'checked_at': observed.get('checked_at')}
    require(freshness.assess_document(observed_source, limits, datetime.now(timezone.utc))['status'] == 'fresh',
            'Current-report source freshness revalidation required')
    actual, fiscal, status = extract(raw, 'text/html', manifest['source_url'])
    require(status == 'extracted' and actual == text and fiscal == manifest['fiscal_tags'],
            'Current-report extraction differs from archived source')
    require(fiscal.get('DocumentType') == '8-K' and fiscal.get('TradingSymbol') == manifest['symbol'],
            'SEC form and listing source evidence required')
    issuer = library.catalog(root)['issuers'].get(packet['issuer_id'], {})
    require(isinstance(issuer.get('issuer'), str) and
            fiscal.get('EntityRegistrantName') == issuer['issuer'],
            'Current report registrant differs from qualified issuer')
    links = page(raw, manifest['source_url']).links
    require(any(x['url'] == release['source_url'] for x in links),
            'Current report must link exact qualified earnings exhibit')
    end = date.fromisoformat(selection['period_end'])
    filed = date.fromisoformat(manifest['metadata']['filingDate'])
    require(0 <= (filed - end).days <= 90, 'Current report date outside selected earnings event')
    evidence = selection['period_evidence']
    tables.fields(evidence, ('start', 'end', 'text'), 'event period evidence')
    a, b = evidence['start'], evidence['end']
    require(type(a) is int and type(b) is int and 0 <= a < b <= len(text)
            and text[a:b] == evidence['text'], 'Exact current-report period span required')
    normalized = re.sub(r'\s+', ' ', evidence['text'])
    expected = end.strftime('%B') + ' ' + str(end.day) + ', ' + str(end.year)
    require(expected in normalized, 'Period evidence does not identify selected period end')
    return release, call, manifest


def prepare(root, packet_id, output, writing, authorization, *, selection,
            reviewed_financial, reviewed_sidecar=None):
    """Prepare the ordinary report case from explicitly reviewed event sources."""
    root, output, writing = Path(root).resolve(), Path(output).resolve(), Path(writing).resolve()
    require(isinstance(authorization, str) and authorization.strip(), 'Explicit report authorization required')
    require(reviewed_financial is not None, 'Independently reviewed release financial cells required')
    packet = flow.validate_packet(root, packet_id)
    release, call, current = authenticate(root, packet, selection)
    # The ordinary adapter verifies distinct financial author/reviewer identities,
    # exact cells, periods, units, basis, context, and all source/artifact hashes.
    extras = [{'document_id': current['document_id'], 'kind': 'filing',
               'original_kind': 'current_report', 'representation': name,
               'path': str(library.resolve(root, current[name + '_path'])),
               'sha256': current[name + '_sha256'], 'url': current['source_url']}
              for name in ('raw', 'text')]
    artifacts = [{'path': str(library.resolve(root, selection[key + '_path'])),
                  'sha256': selection[key + '_sha256']} for key in ('current_report', 'review', 'observation')]
    output.mkdir(parents=True, exist_ok=True)
    selected = output / 'event-source-selection.json'
    flow.base.save(selected, selection)
    artifacts.append({'path': str(selected), 'sha256': flow.base.sha(selected)})
    return flow._prepare_selected(root, packet_id, packet, release, call, output, writing, authorization,
        reviewed_financial=reviewed_financial, reviewed_sidecar=reviewed_sidecar,
        extra_sources=extras, extra_artifacts=artifacts, scope_notes=[
            'Explicit current-event route: financial observations come from reviewed earnings-release cells; '
            'the companion is the actual SEC current report, not a periodic filing. '
            'The current-quarter periodic filing is unavailable. No prior-period filing was relabeled. '
            'Profile/source review is not independent full report acceptance.'])
