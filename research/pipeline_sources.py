"""Prepare the full tracked collection universe without guessing identity or ownership.

Only explicitly configured sources, reviewed overrides, and candidate pages on
already approved exact hosts become retrieval inputs. Saved document association
is discovery evidence, not proof of source ownership or quarter qualification.
"""
import copy
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .collect import identity, validate_registry
from .contracts import require, watchlist
from .fetch import FetchError, check_url, save_json

VERIFIED_IDENTITIES = {'verified_sec_directory', 'verified_listing',
                       'verified_exchange', 'verified_regulator', 'verified_non_us_listing'}


def _read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _safe_url(value):
    if not isinstance(value, str):
        return False
    try:
        host = urlsplit(value).hostname
        check_url(value, {host}, resolve=False)
        return True
    except (FetchError, ValueError):
        return False


def _valid_host(host):
    return isinstance(host, str) and _safe_url('https://' + host + '/') and urlsplit('https://' + host).netloc == host


def _identity_reason(row):
    if row.get('monitoring_eligible') is not True or row.get('identity_status') not in VERIFIED_IDENTITIES:
        return 'current_listing_identity_requires_review'
    if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('issuer_id', 'symbol', 'issuer', 'exchange')):
        return 'incomplete_verified_identity'
    if row['exchange'].upper() in {'UNRESOLVED', 'UNKNOWN', 'PENDING'}:
        return 'exchange_requires_review'
    if row.get('regulator_id'):
        cik = str(row['regulator_id'])
        if not re.fullmatch(r'\d{1,10}', cik) or int(cik) == 0:
            return 'invalid_regulator_identity'
        if row['issuer_id'] != 'sec:' + cik.zfill(10):
            return 'conflicting_stable_regulator_identity'
    elif row['identity_status'] == 'verified_sec_directory':
        return 'missing_regulator_identity'
    return None


def prepare(root, persist=True):
    """Return universe, approved registry and exhaustive coverage; make no requests.

    ``collector_issuer_id`` explicitly maps the collector's storage identity to
    the tracked stable issuer ID. A reviewed foreign listing can be activated
    with an approved issuer source; unresolved listings remain blocked even if
    an investor-relations page was found for the company.
    """
    root = Path(root).resolve()
    public_root = Path(__file__).resolve().parents[1]
    require(root != public_root and public_root not in root.parents,
            'Pipeline data must remain outside the public checkout')
    companies = _read(root / 'inputs/watchlist.catalog.json', {})['companies']
    require(isinstance(companies, list) and companies, 'Tracked companies required')
    require(all(isinstance(r.get('issuer_id'), str) and r['issuer_id'] for r in companies),
            'Stable tracked issuer identities required')
    require(len({r['issuer_id'] for r in companies}) == len(companies), 'Duplicate tracked issuer identities')
    configured = _read(root / 'inputs/source-registry.json', {'schema_version': 1, 'issuers': {}})
    require(configured.get('schema_version') == 1, 'Unknown configured source registry version')
    calendar = _read(root / 'inputs/calendar-sources.json', {}).get('issuers', {})
    overrides = _read(root / 'inputs/calendar-source-overrides.json', {}).get('issuers', {})
    library = _read(root / 'library/catalog.json', {}).get('documents', {})
    observed = {}
    for doc in library.values():
        for source in doc.get('sources', []):
            for field in ('source_url', 'discovery_url'):
                if _safe_url(source.get(field)):
                    observed.setdefault(doc['issuer_id'], set()).add(source[field])
    symbols = Counter(r.get('symbol') for r in companies if not _identity_reason(r))
    universe, entries, coverage = [], {}, []
    for company in companies:
        iid, symbol = company['issuer_id'], company.get('symbol')
        row = {k: company[k] for k in ('symbol', 'issuer', 'exchange') if k in company}
        if company.get('regulator_id'):
            row['regulator_id'] = str(company['regulator_id']).zfill(10)
        reason = _identity_reason(company)
        if not reason and symbols[symbol] > 1:
            reason = 'duplicate_symbol_requires_collector_identity_review'
        candidate_pages = calendar.get(iid, {}).get('pages', [])
        candidates = set(observed.get(iid, set()))
        candidates.update(s['url'] for s in candidate_pages if _safe_url(s.get('url')))
        approved = {'pages': [], 'documents': [], 'allowed_hosts': []}
        source_issues = []
        original = configured.get('issuers', {}).get(symbol)
        # A symbol alone is not enough to adopt an old registry after a ticker reuse.
        if original:
            matches = ((row.get('regulator_id') and str(original.get('cik', '')).zfill(10) == row['regulator_id'])
                       or (not row.get('regulator_id') and original.get('issuer_id') == iid))
            if matches:
                approved = copy.deepcopy(original)
            else:
                source_issues.append('configured_source_identity_mismatch')
        for field in ('pages', 'documents'):
            accepted = []
            for source in approved.get(field, []):
                if _safe_url(source.get('url')):
                    accepted.append(source)
                else:
                    source_issues.append('invalid_configured_source_url')
            approved[field] = accepted
        hosts = {h.lower() for h in approved.get('allowed_hosts', []) if _valid_host(h)}
        hosts.update(urlsplit(s['url']).hostname for field in ('pages', 'documents') for s in approved[field])
        for source in overrides.get(iid, {}).get('pages', []):
            if source.get('issuer_verified') is True and _safe_url(source.get('url')):
                if source['url'] not in {s['url'] for s in approved['pages']}:
                    approved['pages'].append(copy.deepcopy(source))
                hosts.add(urlsplit(source['url']).hostname)
            elif _safe_url(source.get('url')):
                candidates.add(source['url'])
        for source in candidate_pages:
            url = source.get('url')
            if (_safe_url(url) and urlsplit(url).hostname in hosts
                    and url not in {s['url'] for s in approved['pages']}):
                approved['pages'].append({'url': url, 'format': source.get('format', 'html'),
                                          'approval_basis': 'exact_preapproved_issuer_host'})
        approved['allowed_hosts'] = sorted(hosts)
        if row.get('regulator_id'):
            approved['cik'] = row['regulator_id']
        if not reason and not row.get('regulator_id') and not (approved['pages'] or approved['documents']):
            reason = 'verified_listing_needs_approved_source'
        enabled = reason is None
        if enabled:
            universe.append(row)
            entries[symbol] = approved
        configured_urls = {s['url'] for field in ('pages', 'documents') for s in approved[field]}
        coverage.append({'issuer_id': iid, 'symbol': symbol, 'issuer': company.get('issuer'),
                         'identity_status': company.get('identity_status'),
                         'collector_issuer_id': identity(row) if enabled else None,
                         'status': 'ready' if enabled else 'blocked',
                         'reason': reason or ('approved_issuer_sources_and_sec' if row.get('regulator_id') and configured_urls
                                              else 'sec_only' if row.get('regulator_id') else 'approved_issuer_sources'),
                         'approved_pages': len(approved['pages']) if enabled else 0,
                         'approved_documents': len(approved['documents']) if enabled else 0,
                         'source_issues': sorted(set(source_issues)),
                         'candidate_sources': sorted(candidates - configured_urls if enabled else candidates),
                         'candidate_status': 'requires_source_ownership_review'})
    if universe:
        watchlist(universe)
    registry = {'schema_version': 1, 'issuers': entries}
    validate_registry(registry, universe)
    result = {'universe': universe, 'registry': registry, 'coverage': coverage}
    if persist:
        save_json(root / 'pipeline/collection-watchlist.json', universe)
        save_json(root / 'pipeline/source-registry.json', registry)
        save_json(root / 'pipeline/source-coverage.json', {'schema_version': 1, 'companies': coverage,
                  'summary': {'tracked': len(companies), 'ready': len(universe), 'blocked': len(companies) - len(universe)}})
    return result
