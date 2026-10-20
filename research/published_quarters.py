"""Evidence-backed published fiscal periods; private preparation, never model calls.

A catalog is an inventory, not proof that all currently published reports were found.
This tracker records the latest *observed* period and leaves discovery completeness
and ambiguous fiscal labels explicit. It never maps a calendar month to a fiscal Q.
"""
from collections import Counter
from datetime import date, datetime, timezone
import html
import re
from urllib.parse import urlsplit

from . import library
from .contracts import KINDS, digest, require
from .freshness import assess_packet

VERSION = 1
PERIOD = re.compile(r'FY\d{4}(?:-Q[1-4]|-H[12])?\Z')
QUARTERS = {'first': '1', 'second': '2', 'third': '3', 'fourth': '4',
            '1st': '1', '2nd': '2', '3rd': '3', '4th': '4'}
QWORD = r'(?:first|second|third|fourth|1st|2nd|3rd|4th)'
# Requiring FY/fiscal avoids interpreting a calendar quarter as the issuer's fiscal Q.
LABELS = [
    re.compile(r'\bFY\s*(?P<year>20\d{2})\s*[-– ]\s*Q(?P<q>[1-4])\b', re.I),
    re.compile(r'\bQ(?P<q>[1-4])\s+(?:of\s+)?(?:FY\s*|fiscal(?:\s+year)?\s+)(?P<year>20\d{2})\b', re.I),
    re.compile(r'\b(?P<word>' + QWORD + r')\s+quarter\s+(?:of\s+)?(?:FY\s*|fiscal(?:\s+year)?\s+)(?P<year>20\d{2})\b', re.I),
    re.compile(r'\bfiscal\s+(?P<word>' + QWORD + r')\s+quarter(?:\s+of)?\s+(?P<year>20\d{2})\b', re.I),
    re.compile(r'\bfiscal(?:\s+year)?\s+(?P<year>20\d{2})\s+(?P<word>' + QWORD + r')\s+quarter\b', re.I),
]
ACTUAL = re.compile(r'\b(?:financial results|earnings results|quarterly results|results for|earnings call|results conference call|reports?\b.{0,100}\bresults|announces?\b.{0,100}\bresults)\b', re.I)
FUTURE = re.compile(r'\b(?:will|expects? to|plans? to|scheduled|schedule|upcoming|outlook|guidance|forecast|estimates?|preview|anticipates?)\b', re.I)
COMPARATIVE = re.compile(r'\b(?:compared|comparison|versus|prior.year|year.ago)\b', re.I)
DEI_FIELDS = ('DocumentFiscalYearFocus', 'DocumentFiscalPeriodFocus', 'DocumentPeriodEndDate')


def _day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _dei_date(value):
    """Normalize an explicit inline-XBRL date display, not a fiscal assignment."""
    if _day(value):
        return value
    normalized = ' '.join(value.split())
    # This exact English month-name syntax is unambiguous across locales. Numeric
    # slash dates need their transformation attribute and stay pending for now.
    match = re.fullmatch(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', normalized)
    if not match:
        return None
    for fmt in ('%B %d %Y', '%b %d %Y'):
        try:
            return datetime.strptime(' '.join(match.groups()), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _cutoff(value):
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    result = _day(value)
    require(result is not None, 'as_of must be an ISO date')
    return result


def _span(text, start, end):
    return {'start': start, 'end': end, 'text': text[start:end]}


def _dates(doc):
    """Keep regulator/collector date candidates explicit; never use retrieval dates."""
    ends, publications = set(), set()
    for candidate in doc.get('metadata_candidates', []):
        meta = candidate.get('metadata', {})
        nested = meta.get('metadata') or {}
        for value in (meta.get('report_date'), nested.get('reportDate')):
            if _day(value):
                ends.add(value)
        for value in (meta.get('filing_date'), nested.get('filingDate')):
            if _day(value):
                publications.add(value)
    # More than one candidate is not resolved by selecting a convenient maximum.
    return {'period_end': next(iter(ends)) if len(ends) == 1 else None,
            'published_on': next(iter(publications)) if len(publications) == 1 else None,
            'date_conflict': len(ends) > 1 or len(publications) > 1}


def _headline_candidates(text):
    """Only actual-results header clauses, not whole-body keyword co-occurrence."""
    found = []
    # Titles/first paragraphs are bounded. Sentence boundaries prevent a past result
    # from lending its announcement verb to a later outlook clause.
    for clause in re.finditer(r'[^\n.!?]{1,600}(?:[.!?]|$)', text[:4000]):
        line = clause.group()
        if not ACTUAL.search(line) or FUTURE.search(line) or COMPARATIVE.search(line):
            continue
        labels = []
        for pattern in LABELS:
            for match in pattern.finditer(line):
                number = match.groupdict().get('q') or QUARTERS[match['word'].lower()]
                labels.append('FY' + match['year'] + '-Q' + number)
        if len(set(labels)) == 1:
            found.append({'period': labels[0], 'basis': 'explicit_actual_results_clause',
                          'source_spans': [_span(text, clause.start(), clause.end())]})
    return found


def _dei_facts(raw_text):
    """Match nested inline-XBRL elements without truncating outer fact text."""
    facts = {field: [] for field in DEI_FIELDS}
    stack = []
    for match in re.finditer(r'</?(?:ix:)?nonNumeric\b[^>]*>', raw_text, re.I):
        tag = match.group()
        if tag.startswith('</'):
            if not stack:
                continue
            start, body_start, field = stack.pop()
            if field:
                body = raw_text[body_start:match.start()]
                value = html.unescape(re.sub('<[^>]+>', '', body)).strip()
                facts[field].append((value, _span(raw_text, start, match.end())))
        elif not tag.endswith('/>'):
            name = re.search(r'\bname\s*=\s*["\']dei:([^"\']+)["\']', tag, re.I)
            field = next((f for f in DEI_FIELDS if name and f.lower() == name[1].lower()), None)
            stack.append((match.start(), match.end(), field))
    return facts


def _dei_candidates(root, doc):
    """Read original inline-XBRL facts only from SEC archive bytes for the owner.

    A form/year in a download filename or a stored metadata guess is not sufficient.
    The raw locator stays inspectable even when text extraction drops hidden DEI tags.
    """
    iid = doc['issuer_id']
    if not iid.startswith('sec:'):
        return []
    expected_cik = str(int(iid.split(':')[1]))
    forms = {candidate.get('metadata', {}).get('form') or (candidate.get('metadata', {}).get('metadata') or {}).get('form')
             for candidate in doc.get('metadata_candidates', [])}
    if not forms.intersection({'10-Q', '10-K', '20-F', '40-F'}):
        return []
    results = []
    for source in doc['sources']:
        url = urlsplit(source['source_url'])
        path = re.match(r'/Archives/edgar/data/(\d+)/', url.path, re.I)
        if url.hostname not in {'www.sec.gov', 'sec.gov', 'archives.sec.gov'} or not path or str(int(path[1])) != expected_cik:
            continue
        raw = library.load_bytes(root, source['raw_path'], source['raw_sha256'])
        if raw.startswith(b'%PDF'):
            continue
        raw_text = raw.decode('utf-8', errors='replace')
        facts, spans = {}, []
        original_facts = _dei_facts(raw_text)
        for field in DEI_FIELDS:
            matches = original_facts[field]
            values = {value for value, span in matches}
            if len(values) != 1:
                break
            facts[field] = values.pop()
            spans.append({'field': field, **matches[0][1]})
        if len(facts) != 3:
            continue
        year, focus, displayed_end = (facts[field] for field in DEI_FIELDS)
        end = _dei_date(displayed_end)
        if not re.fullmatch(r'20\d{2}', year) or focus not in {'Q1', 'Q2', 'Q3', 'Q4', 'FY', 'H1', 'H2'} or not _day(end):
            continue
        period = 'FY' + year + (('-' + focus) if focus != 'FY' else '')
        results.append({'period': period, 'period_end': end, 'basis': 'sec_inline_xbrl_dei',
                        'source_spans': [], 'raw_source_spans': spans,
                        'raw_path': source['raw_path'], 'raw_sha256': source['raw_sha256'],
                        'source_url': source['source_url']})
    return results


def _qualifications(root, cat, issuer_ids=None):
    result, errors = {}, []
    for path in sorted((root / 'library/qualifications').glob('*.json')):
        owner = None
        try:
            q = library.read_json(path)
            owner = cat['documents'].get(q.get('document_id'), {}).get('issuer_id')
            if issuer_ids is not None and owner is not None and owner not in issuer_ids:
                continue
            require(digest(q) == path.stem, 'Qualification hash mismatch')
            doc = cat['documents'].get(q['document_id'])
            require(doc and doc['text_sha256'] == q['text_sha256'], 'Qualification has no matching current source')
            require(PERIOD.fullmatch(q['period']) and q['source_accepted'] is True, 'Invalid qualification')
            require(q['kind'] in KINDS and q['completeness'] in {'full', 'partial'}, 'Invalid kind or completeness')
            require(q['publisher_type'] in {'issuer', 'regulator', 'third_party'} and q['language'] and q['english_coverage'] in {'full', 'partial', 'none'}, 'Invalid language or publisher')
            require(q['reviewer_session'] and q['rationale'] and q['source_spans'], 'Qualification needs reviewer evidence')
            text = library.document_text(root, doc)
            for span in q['source_spans']:
                require(type(span['start']) is int and type(span['end']) is int and 0 <= span['start'] < span['end'] <= len(text) and text[span['start']:span['end']] == span['text'], 'Qualification citation mismatch')
            result.setdefault(doc['document_id'], []).append(dict(q, qualification_id=path.stem))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({'qualification_id': path.stem, 'issuer_id': owner,
                           'status': 'qualification_invalid', 'reason': str(exc)})
    return result, errors


def inspect_document(root, doc, qualifications=(), as_of=None):
    """Return exact evidenced period candidates without accepting source/language."""
    cutoff = _cutoff(as_of)
    text = library.document_text(root, doc)  # validates original extracted bytes
    for source in doc['sources']:
        library.load_bytes(root, source['raw_path'], source['raw_sha256'])
    dates = _dates(doc)
    candidates = []
    for q in qualifications:
        candidates.append({'period': q['period'], 'basis': 'reviewed_qualification',
                           'qualification_id': q['qualification_id'], 'kind': q['kind'],
                           'source_spans': q['source_spans']})
    # A reviewed qualification overrides automatic interpretations of the same bytes.
    if not candidates:
        candidates = _dei_candidates(root, doc) or _headline_candidates(text)
    unique = {}
    for evidence in candidates:
        candidate = {'document_id': doc['document_id'], 'text_sha256': doc['text_sha256'],
                     'source_url': doc['sources'][0]['source_url'],
                     'kind_candidates': doc['kind_candidates'], **dates, **evidence}
        future = any(_day(candidate.get(k)) and _day(candidate[k]) > cutoff for k in ('period_end', 'published_on'))
        candidate['status'] = ('future_dated' if future else 'date_conflict' if dates['date_conflict'] else
                               'qualified' if candidate.get('qualification_id') else 'needs_qualification')
        candidate['required_checks'] = [] if candidate['status'] == 'qualified' else [
            'issuer_and_source', 'fiscal_period', 'completeness', 'language_and_english_coverage',
            'publication_cutoff', 'latest_published_source_discovery']
        unique[digest(candidate)] = candidate
    return list(unique.values())


def _latest(candidates):
    """Order reports within one issuer by period end, then publication if needed.

    Fiscal labels alone cannot rank mixed half-year, quarterly and annual reports.
    Missing comparison dates cause review, rather than a guessed fiscal ordering.
    """
    usable = [c for c in candidates if c['status'] in {'qualified', 'needs_qualification'}]
    periods = {c['period'] for c in usable}
    if not usable:
        return None, []
    if len(periods) == 1:
        return next(iter(periods)), usable
    basis = 'period_end' if all(c.get('period_end') for c in usable) else 'published_on'
    if not all(c.get(basis) for c in usable):
        # A reviewed transcript may have an explicit fiscal label without a
        # collector date. Its already-reviewed period can use dated siblings
        # for ordering; do not invent a date on that source or rank FY labels.
        groups = {period: [c for c in usable if c['period'] == period] for period in periods}
        for field in ('period_end',):
            bounds = {}
            for period, group in groups.items():
                dates = [c[field] for c in group if c.get(field)]
                if not dates or any(not c.get(field) and c['status'] != 'qualified' for c in group):
                    break
                bounds[period] = (min(dates), max(dates))
            if len(bounds) != len(groups):
                continue
            newest = [p for p, (start, _) in bounds.items()
                      if all(start > end for other, (_, end) in bounds.items() if other != p)]
            if len(newest) == 1:
                return newest[0], groups[newest[0]]
            # Conflicting/overlapping period-end anchors must not be overruled
            # by a later filing date (for example an amended older report).
            return None, usable
        return None, usable
    last = max(c[basis] for c in usable)
    newest = [c for c in usable if c[basis] == last]
    # An annual label and Q4 may cover the same end: keep the ambiguity explicit.
    if len({c['period'] for c in newest}) != 1:
        return None, usable
    period = newest[0]['period']
    return period, [c for c in usable if c['period'] == period]


def run(root, as_of=None, issuer_ids=None, require_incremental=False):
    """Prepare latest-observed periods and packets in private storage.

    Writes published/latest.json, published/review-queue.json and a small receipt.
    issuer_ids limits source reads and packet rebuilding when a matching baseline
    exists. Unchanged issuer rows retain their original issuer_as_of timestamps.
    No network requests, qualification invention, model calls or execution toggles.
    """
    root = library.private_root(root)
    cutoff = _cutoff(as_of)
    cat = library.catalog(root)
    build_policy = digest(library.read_json(root / 'config.json').get('packet_freshness'))
    requested = None if issuer_ids is None else set(issuer_ids)
    require(requested is None or (requested and requested <= set(cat['issuers'])),
            'Rebuild scope must contain known issuers')
    baseline_result, previous_review = None, []
    rebuild_issuers = set(cat['issuers'])
    # A changed catalog or missing baseline needs a full rebuild. Never retain
    # rows whose source/identity inventory may have changed.
    if requested is not None:
        try:
            baseline = library.read_json(root / 'published/latest.json')
            queue = library.read_json(root / 'published/review-queue.json')
            same_catalog = baseline['catalog_id'] == cat['catalog_id']
            compatible = same_catalog
            if not compatible and require_incremental:
                require(re.fullmatch(r'[a-f0-9]{64}', baseline['catalog_id']) is not None, 'Invalid baseline catalog ID')
                old = library.read_json(root / 'library/snapshots' / (baseline['catalog_id'] + '.json'))
                require(digest({k: v for k, v in old.items() if k != 'catalog_id'}) == baseline['catalog_id'],
                        'Published baseline snapshot hash mismatch')
                def untouched(c):
                    return ({iid: row for iid, row in c['issuers'].items() if iid not in requested},
                            {did: row for did, row in c['documents'].items() if row['issuer_id'] not in requested})
                compatible = untouched(old) == untouched(cat)
            if (baseline['schema_version'] == VERSION
                    and compatible
                    and baseline.get('build_policy') == build_policy
                    and set(baseline['issuers']) == set(cat['issuers'])
                    and isinstance(queue, list)
                    and all(item.get('catalog_id') == baseline['catalog_id'] for item in queue)):
                baseline_result, previous_review, rebuild_issuers = baseline, queue, requested
        except (OSError, ValueError, KeyError, TypeError):
            pass
    require(not require_incremental or baseline_result is not None,
            'Compatible publication baseline required; explicit full reconciliation needed')
    qualifications, review = _qualifications(root, cat, rebuild_issuers)
    by_issuer = {iid: [] for iid in cat['issuers']}
    document_counts = Counter()
    for doc in cat['documents'].values():
        iid = doc['issuer_id']
        if iid not in rebuild_issuers:
            continue
        document_counts[iid] += 1
        try:
            candidates = inspect_document(root, doc, qualifications.get(doc['document_id'], []), cutoff)
        except (ValueError, OSError, UnicodeError) as exc:
            review.append({'issuer_id': iid, 'document_id': doc['document_id'], 'status': 'source_invalid', 'reason': str(exc)})
            continue
        by_issuer[iid].extend(candidates)
        if not candidates:
            review.append({'issuer_id': iid, 'document_id': doc['document_id'], 'status': 'period_unresolved',
                           'reason': 'No reviewed period, SEC DEI facts or unambiguous actual fiscal-results clause.',
                           'required_checks': ['fiscal_period', 'issuer_and_source', 'completeness', 'language_and_english_coverage']})
        for candidate in candidates:
            review.append(dict(candidate, issuer_id=iid))
    rows = {iid: row for iid, row in baseline_result['issuers'].items() if iid not in rebuild_issuers} if baseline_result else {}
    for iid, owner in cat['issuers'].items():
        if iid not in rebuild_issuers:
            continue
        candidates = by_issuer[iid]
        period, selected = _latest(candidates)
        confirmed_period, _ = _latest([c for c in candidates if c['status'] == 'qualified'])
        row = {'issuer_id': iid, 'symbol': owner.get('symbol'), 'issuer': owner.get('issuer'),
               'period': period, 'confirmed_period': confirmed_period, 'document_count': document_counts[iid],
               'status': 'needs_qualification' if period else 'period_unresolved',
               'candidate_documents': selected or candidates, 'qualification_ids': [], 'packet_id': None,
               'freshness': None, 'missing': {}, 'discovery_complete': False,
               'coverage': 'Latest observed in indexed evidence; live-source completeness is not asserted.'}
        if owner.get('monitoring_eligible') is not True:
            row['status'] = 'identity_unresolved'
        elif not document_counts[iid]:
            row['status'] = 'no_documents'
        elif period:
            # Conflicting reviewed decisions for the same document need adjudication.
            q_by_doc = {}
            for candidate in selected:
                if candidate['status'] == 'qualified':
                    q_by_doc.setdefault(candidate['document_id'], []).append(candidate['qualification_id'])
            qids = [ids[0] for ids in q_by_doc.values() if len(set(ids)) == 1]
            if any(len(set(ids)) > 1 for ids in q_by_doc.values()):
                row['status'] = 'qualification_conflict'
            elif qids:
                # An annual filing is background, not an invented Q4. Attach the
                # newest unambiguous reviewed prior fiscal year to event packets.
                if '-Q' in period or '-H' in period:
                    annual = [c for c in candidates if c['status'] == 'qualified'
                              and c.get('kind') == 'annual_background'
                              and re.fullmatch(r'FY\d{4}', c['period'])
                              and int(c['period'][2:]) < int(period[2:6])]
                    if annual:
                        year = max(c['period'] for c in annual)
                        newest = {c['qualification_id'] for c in annual if c['period'] == year}
                        if len(newest) == 1:
                            qids.extend(newest)
                try:
                    present = {q['kind'] for decisions in qualifications.values() for q in decisions
                               if q['qualification_id'] in qids}
                    missing = {kind: {'status': 'pending', 'reason': 'No accepted document of this type for the selected fiscal period.'}
                               for kind in sorted(KINDS - present)}
                    packet = library.make_packet(root, iid, period, sorted(qids), missing)
                    current = library.read_json(root / 'config.json').get('packet_freshness')
                    row.update(status='packet_prepared', qualification_ids=sorted(qids), packet_id=packet['packet_id'],
                               freshness=assess_packet(packet, current), missing=missing,
                               translation_required=packet['translation_required'])
                except (ValueError, KeyError, OSError) as exc:
                    row['status'] = 'packet_blocked'
                    review.append({'issuer_id': iid, 'period': period, 'status': 'packet_blocked', 'reason': str(exc)})
        if row['status'] in {'identity_unresolved', 'no_documents', 'period_unresolved', 'qualification_conflict'}:
            review.append({'issuer_id': iid, 'status': row['status'], 'period': period,
                           'reason': 'Resolve identity/source coverage or period evidence before dispatch.'})
        rows[iid] = row
    # Opaque IDs bind document+period; timing, spans and status changes do not create
    # a different review task. Retain qualified entries for remote completion checks.
    normalized_review = {}
    for item in review:
        doc = cat['documents'].get(item.get('document_id'))
        latest_period = rows.get(item.get('issuer_id'), {}).get('period')
        item = dict(item, catalog_id=cat['catalog_id'],
                    monitoring_eligible=cat['issuers'].get(item.get('issuer_id'), {}).get('monitoring_eligible') is True,
                    is_latest_observed_period=latest_period is not None and item.get('period') == latest_period)
        if doc:
            item.update(text_sha256=doc['text_sha256'], source_variants=doc['sources'])
        item['qualification_ids'] = ([item['qualification_id']] if item.get('qualification_id') else [])
        item['review_id'] = digest([item.get('issuer_id'), item.get('document_id'),
                                    item.get('period'), item.get('qualification_id') if not doc else None,
                                    item.get('status') if not doc else None])
        previous = normalized_review.get(item['review_id'])
        if previous:
            previous['qualification_ids'] = sorted(set(previous['qualification_ids'] + item['qualification_ids']))
        else:
            normalized_review[item['review_id']] = dict(item, catalog_id=cat['catalog_id'])
    for item in previous_review:
        if item.get('issuer_id') is not None and item['issuer_id'] not in rebuild_issuers:
            normalized_review[item['review_id']] = dict(item, catalog_id=cat['catalog_id'])
    review = sorted(normalized_review.values(), key=lambda item: item['review_id'])
    issuer_as_of = {iid: (cutoff.isoformat() if iid in rebuild_issuers else
                         baseline_result.get('issuer_as_of', {}).get(iid, baseline_result['as_of']))
                    for iid in rows}
    result = {'schema_version': VERSION, 'as_of': cutoff.isoformat(), 'catalog_id': cat['catalog_id'],
              'issuers': rows, 'build_policy': build_policy, 'issuer_as_of': issuer_as_of, 'discovery_complete': False,
              'rule': 'Fiscal labels require source evidence; publication/period-end evidence orders reports; calendar and access dates do not assign fiscal quarters.'}
    receipt = {'schema_version': VERSION, 'as_of': cutoff.isoformat(), 'catalog_id': cat['catalog_id'],
               'issuers': len(rows), 'documents': sum(row['document_count'] for row in rows.values()),
               'rebuild_mode': 'incremental' if baseline_result else 'full',
               'rebuilt_issuer_ids': sorted(rebuild_issuers), 'documents_inspected': sum(document_counts.values()),
               'statuses': dict(sorted(Counter(r['status'] for r in rows.values()).items())),
               'packets_prepared': sum(r['packet_id'] is not None for r in rows.values()),
               'review_items': sum(item['status'] != 'qualified' for item in review), 'download_requests': 0, 'model_calls': 0,
               'latest_path': 'published/latest.json', 'review_queue_path': 'published/review-queue.json'}
    with library.lock(root):
        library.save(root / 'published/latest.json', result)
        library.save(root / 'published/review-queue.json', review)
        library.save(root / 'published/receipt.json', receipt)
    return receipt
