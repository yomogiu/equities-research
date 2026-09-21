"""Private, content-addressed evidence catalog. No networking or model calls."""
from contextlib import contextmanager
from datetime import date
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .contracts import KINDS, digest, require, validate_packet
from .freshness import timestamp, policy as freshness_policy, assess_packet, assess_document
from datetime import datetime, timezone

PUBLIC_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def private_root(value):
    root = Path(value).resolve()
    require(root != PUBLIC_ROOT and PUBLIC_ROOT not in root.parents, 'Use storage outside the public code checkout')
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve(root, relative):
    require(isinstance(relative, str) and relative, 'Evidence path required')
    path = (root / relative).resolve()
    require(path != root and root in path.parents, 'Path escapes private storage')
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_bytes(root, relative, expected=None):
    path = resolve(root, relative)
    body = path.read_bytes()
    if path.suffix == '.gz':
        body = gzip.decompress(body)
    require(not expected or sha(body) == expected, 'Source hash mismatch')
    return body


def save(path, value, immutable=False):
    destination = path.resolve()
    require(destination != PUBLIC_ROOT and PUBLIC_ROOT not in destination.parents, 'Private artifacts cannot be written in public checkout')
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
    if immutable and path.exists():
        require(path.read_bytes() == payload, 'Immutable artifact collision')
        return
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def lock(root):
    path = root / 'library/.writer.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def issuer_id(value):
    match = re.fullmatch(r'(?:sec:|cik-)(\d+)', value)
    return 'sec:' + match[1].zfill(10) if match else value


def normalize_kind(doc):
    form = doc.get('form') or doc.get('metadata', {}).get('form')
    if form in {'10-K', '20-F', '40-F'}:
        return 'annual_background'
    if form == '10-Q':
        return 'periodic_filing'
    kind = doc.get('kind')
    return kind if kind in KINDS else 'unclassified'


def build_catalog(root, audit_path, language_path=None):
    root = private_root(root)
    audit = read_json(resolve(root, audit_path))
    language = read_json(resolve(root, language_path)) if language_path else {'documents': []}
    languages = {d['text_sha256']: d for d in language['documents']}
    issuers = {issuer_id(r['issuer_id']): {k: r.get(k) for k in
               ('issuer', 'symbol', 'exchange', 'identity_status', 'monitoring_eligible')} for r in audit['results']}
    records = {}
    imported = 0
    # Use per-URL observations, never audit generation dates or file mtimes.
    observations = {}
    cache_paths = [root / 'collection/http-cache.json', *sorted((root / 'sources').rglob('http-cache.json'))]
    for cache_path in cache_paths:
        if not cache_path.is_file():
            continue
        for url, entry in read_json(cache_path).items():
            checked = timestamp(entry.get('checked_at'))
            if checked and (url not in observations or checked > observations[url][0]):
                observations[url] = (checked, entry, str(cache_path.relative_to(root)))

    def add(owner, doc, base, provenance, qualified):
        nonlocal imported
        iid = issuer_id(owner)
        text_path = str(Path(base) / doc['text_path'])
        raw_path = str(Path(base) / doc['raw_path'])
        text = load_bytes(root, text_path, doc.get('text_sha256'))
        raw_hash = doc.get('raw_sha256') or doc.get('sha256')
        require(raw_hash, 'Original source hash required')
        load_bytes(root, raw_path, raw_hash)
        text_hash = sha(text)
        did = digest([iid, text_hash])
        source_url = doc.get('url') or doc.get('source_url')
        require(source_url and source_url.startswith('https://'), 'HTTPS source required')
        variant = {'source_url': source_url, 'raw_path': raw_path, 'raw_sha256': raw_hash,
                   'text_path': text_path, 'text_sha256': text_hash, 'provenance': provenance,
                   'final_url': doc.get('final_url', source_url),
                   'discovery_url': doc.get('source_url') if doc.get('source_url') != source_url else None}
        variant.update(retrieved_at=timestamp(doc.get('retrieved_at')),
                       checked_at=None, last_modified=None, etag=None,
                       source_check_status='unknown', check_provenance=None)
        if source_url in observations:
            checked, observed, cache_path = observations[source_url]
            variant.update(source_check_status='verified' if observed.get('sha256') == raw_hash else 'content_changed',
                           check_provenance=cache_path)
            if observed.get('sha256') == raw_hash:
                variant.update(checked_at=checked, last_modified=observed.get('last_modified'), etag=observed.get('etag'))
        period_end = doc.get('report_date') or doc.get('metadata', {}).get('reportDate')
        try:
            if period_end:
                date.fromisoformat(period_end)
        except ValueError:
            period_end = None
        language_review = languages.get(text_hash)
        language_info = ({'language': language_review['language'], 'decision': language_review['decision'],
                          'notes': language_review['notes'], 'status': 'screened'} if language_review else
                         {'language': 'und', 'decision': 'language_review', 'status': 'not_individually_verified'})
        if did not in records:
            records[did] = {'document_id': did, 'issuer_id': iid, 'text_sha256': text_hash,
                            'characters': len(text.decode('utf-8')), 'sources': [], 'collector_ids': [],
                            'kind_candidates': [], 'period_end_candidates': [], 'titles': [],
                            'source_qualified': False, 'language': language_info, 'metadata_candidates': [],
                            'archive_only': bool(doc.get('archive_only') or doc.get('freshness') == 'archive_only')}
        row = records[did]
        if variant not in row['sources']:
            row['sources'].append(variant)
        metadata = {k: doc[k] for k in ['form', 'filing_date', 'report_date', 'period_status', 'period_evidence',
                    'document_year', 'year_mentions', 'freshness', 'extracted_fiscal_fields', 'fiscal_tags',
                    'metadata', 'completeness', 'period_assignment', 'qualification_status'] if k in doc}
        candidate = {'provenance': provenance, 'source_url': source_url, 'metadata': metadata}
        if candidate not in row['metadata_candidates']:
            row['metadata_candidates'].append(candidate)
        for key, val in [('kind_candidates', normalize_kind(doc)), ('period_end_candidates', period_end),
                         ('titles', doc.get('title') or doc.get('form')), ('collector_ids', doc.get('document_id'))]:
            if val and val not in row[key]:
                row[key].append(val)
        row['source_qualified'] |= qualified
        imported += 1

    for company in audit['results']:
        for document in company['documents']:
            add(company['issuer_id'], document, '', audit_path, True)
    index_path = root / 'collection/document-index.json'
    if index_path.exists():
        for brief in read_json(index_path).values():
            manifest = read_json(resolve(root, 'collection/' + brief['manifest_path']))
            iid = issuer_id(manifest['issuer_id'])
            require(iid in issuers, 'Collector issuer missing from audited universe')
            add(iid, manifest, 'collection', 'collection/' + brief['manifest_path'], False)
    for row in records.values():
        row['sources'].sort(key=lambda x: (x['source_url'], x['text_path'], x['provenance']))
        row['metadata_candidates'].sort(key=lambda x: (x['source_url'], x['provenance']))
        for key in ['collector_ids', 'kind_candidates', 'period_end_candidates', 'titles']:
            row[key].sort()
    catalog = {'schema_version': 1, 'issuers': dict(sorted(issuers.items())),
               'documents': dict(sorted(records.items())), 'input_records': imported,
               'deduplicated_records': imported - len(records)}
    catalog['catalog_id'] = digest(catalog)
    with lock(root):
        save(root / 'library/catalog.json', catalog)
        save(root / f"library/snapshots/{catalog['catalog_id']}.json", catalog, immutable=True)
        review = [{'document_id': r['document_id'], 'issuer_id': r['issuer_id'],
                   'source_qualified': r['source_qualified'], 'language': r['language'],
                   'checks': ['issuer_and_source', 'kind', 'fiscal_period', 'completeness', 'english_coverage']}
                  for r in records.values()]
        save(root / 'library/review-queue.json', sorted(review, key=lambda x: (x['issuer_id'], x['document_id'])))
        for iid, owner in catalog['issuers'].items():
            inventory = {'schema_version': 1, 'issuer_id': iid, **owner, 'catalog_id': catalog['catalog_id'],
                         'documents': sorted([r['document_id'] for r in records.values() if r['issuer_id'] == iid]),
                         'status': 'inventory_only', 'period': None}
            save(root / 'library/issuers' / (digest(iid) + '.json'), inventory)
    return catalog


def catalog(root):
    return read_json(root / 'library/catalog.json')


def resolve_issuer(cat, value):
    normalized = issuer_id(value)
    if normalized in cat['issuers']:
        return normalized
    matches = [key for key, row in cat['issuers'].items() if (row.get('symbol') or '').upper() == value.upper()]
    require(len(matches) == 1, 'Ticker missing or ambiguous; use stable issuer ID')
    return matches[0]


def document_text(root, doc):
    source = doc['sources'][0]
    return load_bytes(root, source['text_path'], doc['text_sha256']).decode('utf-8')


def build_search(root):
    """Rebuildable local index; original files and catalog remain authoritative."""
    root = private_root(root)
    with lock(root):
        cat = catalog(root)
        target = root / 'library/search.sqlite3'
        fd, tmp = tempfile.mkstemp(dir=target.parent)
        os.close(fd)
        try:
            db = sqlite3.connect(tmp)
            db.executescript('CREATE TABLE metadata(catalog_id TEXT); CREATE TABLE sections(document_id TEXT, issuer_id TEXT, start INTEGER, end INTEGER, text TEXT); CREATE INDEX doc_sections ON sections(document_id,start); CREATE VIRTUAL TABLE words USING fts5(text, content=sections, content_rowid=rowid);')
            db.execute('INSERT INTO metadata VALUES(?)', (cat['catalog_id'],))
            for doc in cat['documents'].values():
                text = document_text(root, doc)
                for start in range(0, len(text), 5500):
                    end = min(start + 6000, len(text))
                    db.execute('INSERT INTO sections VALUES(?,?,?,?,?)', (doc['document_id'], doc['issuer_id'], start, end, text[start:end]))
            db.execute("INSERT INTO words(words) VALUES('rebuild')")
            db.commit()
            count = db.execute('SELECT count(*) FROM sections').fetchone()[0]
            db.close()
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return {'documents': len(cat['documents']), 'sections': count, 'catalog_id': cat['catalog_id']}


def search(root, query, issuer=None, limit=10, literal=False):
    require(0 < limit <= 100 and query.strip(), 'Query and limit 1..100 required')
    cat = catalog(root)
    db = sqlite3.connect(f"file:{root / 'library/search.sqlite3'}?mode=ro", uri=True)
    try:
        require(db.execute('SELECT catalog_id FROM metadata').fetchone()[0] == cat['catalog_id'], 'Rebuild stale search index')
        if literal:
            sql = 'SELECT s.document_id,s.issuer_id,s.start,s.end,substr(s.text,max(1,instr(lower(s.text),lower(?))-120),350) FROM sections s WHERE instr(lower(s.text),lower(?))>0'
        else:
            sql = 'SELECT s.document_id,s.issuer_id,s.start,s.end,snippet(words,0,\'\',\'\',\' … \',40) FROM words JOIN sections s ON s.rowid=words.rowid WHERE words MATCH ?'
        args = [query, query] if literal else [query]
        if issuer:
            sql += ' AND s.issuer_id=?'
            args.append(resolve_issuer(cat, issuer))
        sql += ' ORDER BY s.document_id,s.start LIMIT ?'
        args.append(limit)
        return [dict(zip(['document_id', 'issuer_id', 'start', 'end', 'snippet'], r)) for r in db.execute(sql, args)]
    finally:
        db.close()


def read_span(root, did, start=0, end=None):
    doc = catalog(root)['documents'][did]
    text = document_text(root, doc)
    end = min(start + 6000, len(text)) if end is None else end
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(text) and end-start <= 20000,
            'Request a valid span of at most 20000 characters')
    return {'document_id': did, 'text_sha256': doc['text_sha256'], 'start': start, 'end': end,
            'text': text[start:end], 'source_url': doc['sources'][0]['source_url']}


def qualify(root, value):
    """Store an explicit reviewer decision, never infer fiscal quarters from dates."""
    doc = catalog(root)['documents'][value['document_id']]
    require(value['text_sha256'] == doc['text_sha256'], 'Qualification is for different source bytes')
    require(value['kind'] in KINDS and value['completeness'] in {'full', 'partial'}, 'Invalid document qualification')
    require(re.fullmatch(r'FY\d{4}(?:-Q[1-4]|-H[12])?', value['period']), 'Explicit fiscal period required')
    require(value['publisher_type'] in {'issuer', 'regulator', 'third_party'}, 'Publisher required')
    require(value['language'] and value['english_coverage'] in {'full', 'partial', 'none'}, 'Language review required')
    require(value['reviewer_session'] and value['rationale'] and value['source_spans'], 'Reviewer and source evidence required')
    for span in value['source_spans']:
        actual = read_span(root, doc['document_id'], span['start'], span['end'])
        require(actual['text'] == span['text'], 'Qualification citation mismatch')
    require(value.get('source_accepted') is True, 'Explicit source acceptance required')
    value = dict(value, schema_version=1)
    qid = digest(value)
    with lock(root):
        save(root / f'library/qualifications/{qid}.json', value, immutable=True)
    return {'qualification_id': qid, 'path': f'library/qualifications/{qid}.json'}


def make_packet(root, issuer, period, selections, missing=None):
    cat = catalog(root)
    iid = issuer_id(issuer)
    require(iid in cat['issuers'] and re.fullmatch(r'FY\d{4}(?:-Q[1-4]|-H[12])?', period), 'Known issuer and fiscal period required')
    require(selections and len(selections) == len(set(selections)), 'Distinct qualification IDs required')
    limits = freshness_policy(read_json(root / 'config.json').get('packet_freshness'))
    moment = datetime.now(timezone.utc)
    docs = []
    for qid in selections:
        require(re.fullmatch('[a-f0-9]{64}', qid), 'Bad qualification ID')
        q = read_json(resolve(root, f'library/qualifications/{qid}.json'))
        require(digest(q) == qid, 'Qualification hash mismatch')
        d = cat['documents'][q['document_id']]
        require(d['issuer_id'] == iid and d['text_sha256'] == q['text_sha256'], 'Wrong issuer or stale qualification')
        background = q['kind'] == 'annual_background' and int(q['period'][2:6]) < int(period[2:6])
        require(q['period'] == period or background, 'Unrelated period; same-year annual background needs an explicitly matched annual packet')
        # Prefer a usable fresh observation of these exact bytes over an older alias.
        def source_rank(source):
            status = assess_document(dict(source, kind=q['kind']), limits, moment)['status']
            return (status == 'fresh', status != 'content_changed',
                    source.get('checked_at') or source.get('retrieved_at') or '')
        source = max(d['sources'], key=source_rank)
        text = document_text(root, d)
        docs.append({'catalog_document_id': d['document_id'], 'document_id': digest([source['source_url'], text]),
                     'qualification_id': qid, 'kind': q['kind'], 'period': q['period'],
                     'title': q.get('title') or (d['titles'][0] if d['titles'] else q['kind']),
                     'completeness': q['completeness'], 'publisher_type': q['publisher_type'],
                     'language': q['language'], 'english_coverage': q['english_coverage'],
                     'text_sha256': d['text_sha256'], **source})
    require(len({d['catalog_document_id'] for d in docs}) == len(docs), 'Duplicate source in packet')
    availability = {k: 'available' if any(d['kind'] == k for d in docs) else 'pending' for k in KINDS}
    for kind, entry in (missing or {}).items():
        require(kind in KINDS and availability[kind] != 'available', 'Cannot override retrieved document')
        require(entry['status'] in {'pending', 'not_published', 'not_applicable', 'access_blocked'} and entry['reason'], 'Missing-source reason required')
        availability[kind] = entry['status']
    packet = {'schema_version': 1, 'issuer_id': iid, 'period': period,
              'catalog_id': cat['catalog_id'], 'freshness_policy': limits,
              'identity_verified': cat['issuers'][iid].get('monitoring_eligible') is True,
              'documents': sorted(docs, key=lambda d: d['document_id']), 'availability': availability,
              'missing_reasons': missing or {}, 'scope': 'limited_event_update',
              'translation_required': sorted(d['document_id'] for d in docs if d['english_coverage'] != 'full')}
    packet['packet_id'] = digest(packet)
    materialize(root, packet)
    with lock(root):
        save(root / f"library/packets/{packet['packet_id']}.json", packet, immutable=True)
    return packet


def materialize(root, packet):
    require(digest({k: v for k, v in packet.items() if k != 'packet_id'}) == packet['packet_id'], 'Packet hash mismatch')
    snapshot = None
    if packet.get('catalog_id'):
        snapshot = read_json(resolve(root, f"library/snapshots/{packet['catalog_id']}.json"))
        require(digest({k:v for k,v in snapshot.items() if k != 'catalog_id'}) == packet['catalog_id'], 'Catalog snapshot hash mismatch')
    docs = []
    for d in packet['documents']:
        if snapshot is not None:
            variants = snapshot['documents'][d['catalog_document_id']]['sources']
            require(any(all(d.get(k) == v for k,v in source.items()) for source in variants),
                    'Packet source timestamps differ from catalog evidence')
        text = load_bytes(root, d['text_path'], d['text_sha256']).decode('utf-8')
        load_bytes(root, d['raw_path'], d['raw_sha256'])
        require(d['document_id'] == digest([d['source_url'], text]), 'Inconsistent evidence document ID')
        q = read_json(resolve(root, f"library/qualifications/{d['qualification_id']}.json"))
        require(digest(q) == d['qualification_id'], 'Qualification hash mismatch')
        require(q['document_id'] == d['catalog_document_id'], 'Wrong qualification document')
        require(q.get('source_accepted') is True, 'Source qualification not accepted')
        require(d['catalog_document_id'] == digest([packet['issuer_id'], d['text_sha256']]), 'Wrong packet issuer')
        for key in ['text_sha256', 'kind', 'period', 'completeness', 'publisher_type', 'language', 'english_coverage']:
            require(q[key] == d[key], 'Packet differs from source qualification')
        docs.append(dict(d, text=text))
    require(packet['translation_required'] == sorted(d['document_id'] for d in docs if d['english_coverage'] != 'full'), 'Translation routing mismatch')
    expanded = dict(packet, documents=docs, freshness=assess_packet(packet))
    validate_packet(expanded)
    return expanded
