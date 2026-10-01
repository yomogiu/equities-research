"""Deterministic, source-bound inputs for the private mixed-model benchmark.

Original documents stay in place. Persisted document entries are bounded previews;
``source_slices`` reads complete requested spans, and ``transcript_view`` supplies
all transcript characters together with unchanged speaker/exchange annotations.
No model calls and no issuer-specific selection rules are used here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from research import earnings_experiment as base
from research import financial_evidence as financial

VERSION = 'earnings-compact-evidence-v1'
CHUNK_CHARACTERS = 2400
PREVIEW_CHARACTERS = 500
PRIORITY_CONCEPT = re.compile(
    r'revenue|grossprofit|grossmargin|operatingincome|operatingmargin|netincome|'
    r'cashflow|operatingactivities|propertyplant|capitalexpenditure|earningspershare', re.I)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False)


def _sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _text(path):
    # Preserve CRLF: all offsets refer to decoded, unchanged UTF-8 bytes.
    return Path(path).read_bytes().decode('utf-8')


def _save(path, value):
    content = _canonical(value) + '\n'
    if path.exists() and path.read_bytes() != content.encode('utf-8'):
        raise ValueError('Refusing to overwrite immutable evidence: ' + str(path))
    path.write_bytes(content.encode('utf-8'))


def _span(text, start, end):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        raise ValueError('Invalid Unicode character source offsets')
    return text[start:end]


def _unique_source(sources, document_id, sha256):
    found = [s for s in sources if s.get('document_id') == document_id and s['sha256'] == sha256]
    if len(found) != 1:
        raise ValueError('Missing or ambiguous frozen source binding')
    return found[0]


def _verify_index(index, text):
    if index.get('source', {}).get('text_sha256') != _sha_text(text):
        raise ValueError('Transcript index source hash mismatch')
    if index.get('offset_unit') != 'unicode_character':
        raise ValueError('Unsupported transcript offset unit')
    ids = set()
    for group in ('sections', 'turns', 'exchanges'):
        for item in index[group]:
            if not item.get('id') or item['id'] in ids:
                raise ValueError('Duplicate or missing transcript ID')
            ids.add(item['id'])
            if group != 'exchanges':
                _span(text, item['start'], item['end'])
        if group != 'exchanges':
            ordered = sorted(index[group], key=lambda row: row['start'])
            if any(a['end'] > b['start'] for a, b in zip(ordered, ordered[1:])):
                raise ValueError('Overlapping transcript annotations')
    turns = {t['id']: t for t in index['turns']}
    for exchange in index['exchanges']:
        if not exchange.get('turn_ids') or any(i not in turns for i in exchange['turn_ids']):
            raise ValueError('Exchange has unknown or missing turn IDs')
        if len(set(exchange['turn_ids'])) != len(exchange['turn_ids']):
            raise ValueError('Duplicate exchange turn IDs')


def prepare(case_path, output_dir):
    """Validate frozen inputs and write an immutable compact bundle; return manifest.

    ``files`` maps logical names to absolute artifact paths; ``file_sha256`` binds
    each file. Financial records retain complete contexts, units and support.
    financial_view prioritizes mapped/financial concepts, explicitly lists every
    omitted/unmapped ID and retains extraction gaps. Selection is not validation.
    """
    case_path = Path(case_path).resolve()
    case = base.read(case_path)
    base.validate_case(case)
    output = Path(output_dir).resolve()
    sources = sorted(case['sources'], key=lambda s: (s.get('document_id', ''),
                      s.get('representation', ''), s['path']))
    protected = {Path(s['path']).resolve() for s in sources + case.get('artifacts', [])}
    protected.add(case_path)
    names = ('financial', 'financial_view', 'documents', 'transcript_index')
    files = {name: str(output / (name + '.json')) for name in names}
    if any(Path(p).resolve() in protected for p in [*files.values(), output / 'manifest.json']):
        raise ValueError('Evidence output would overwrite an original input')

    artifact = base.read(case['financial_path'])
    source = artifact['source']
    raw_source = _unique_source(sources, source['document_id'], source['raw_sha256'])
    if source.get('text_sha256'):
        _unique_source(sources, source['document_id'], source['text_sha256'])
    financial.validate_artifact(artifact, {source['document_id']: source})
    index = base.read(case['transcript_index_path'])
    transcript_text = _text(case['transcript_path'])
    _verify_index(index, transcript_text)
    transcript_source = _unique_source(sources, index['source']['document_id'], _sha_text(transcript_text))
    if Path(transcript_source['path']).resolve() != Path(case['transcript_path']).resolve():
        raise ValueError('Transcript path and index source differ')

    texts = {}
    def source_text(item):
        key = item['path']
        if key not in texts:
            texts[key] = _text(key)
        return texts[key]

    contexts, units = {}, {}
    observations = []
    ordered = sorted(artifact['observations'], key=lambda o: (
        o['source_document_id'], o['support']['start'], o['support']['end'], o['observation_id']))
    for ordinal, obs in enumerate(ordered, 1):
        support = obs['support']
        if support.get('offset_unit') not in ('unicode_codepoint', 'unicode_character'):
            raise ValueError('Unsupported financial offset unit')
        support_source = raw_source if obs['method'] == 'inline_xbrl' else _unique_source(
            sources, obs['source_document_id'], support['text_sha256'])
        raw = source_text(support_source)
        snippet = _span(raw, support['start'], support['end'])
        if obs['method'] == 'inline_xbrl' and _sha_text(snippet) != support['raw_span_sha256']:
            raise ValueError('Financial support source span hash mismatch')
        if obs['method'] == 'manual_proposal' and snippet != support['quote']:
            raise ValueError('Financial proposed quote differs from source')
        row = support.get('table_row')
        if row and _sha_text(_span(raw, row['start'], row['end'])) != row['raw_span_sha256']:
            raise ValueError('Financial table row source span hash mismatch')
        context_key, unit_key = _canonical(obs['context']), _canonical(obs['unit'])
        if context_key not in contexts:
            contexts[context_key] = 'C%03d' % (len(contexts) + 1)
        if unit_key not in units:
            units[unit_key] = 'U%03d' % (len(units) + 1)
        record = {k: v for k, v in obs.items() if k not in ('context', 'unit')}
        record.update(id='F%03d' % ordinal, context_id=contexts[context_key],
                      unit_id=units[unit_key], source_path=support_source['path'],
                      source_sha256=support_source['sha256'])
        observations.append(record)
    facts = {'schema_version': VERSION, 'offset_unit': 'unicode_character',
             'source': source, 'contexts': {v: json.loads(k) for k, v in contexts.items()},
             'units': {v: json.loads(k) for k, v in units.items()},
             'observations': observations, 'gaps': artifact.get('gaps', [])}
    selected = [o for o in observations if o.get('canonical_metric') or PRIORITY_CONCEPT.search(o['concept'])]
    selected_ids = {o['id'] for o in selected}
    omitted = [o['id'] for o in observations if o['id'] not in selected_ids]
    unmapped = [o['id'] for o in observations if not o.get('canonical_metric')]
    # No lengthy raw tag/table repetition in the preparer's one-shot view.
    columns = ['id', 'concept', 'canonical_metric', 'value', 'context_id', 'unit_id', 'status', 'nil', 'decimals']
    view = {'schema_version': VERSION, 'selection_rule': 'canonical_metric or concept regex: ' + PRIORITY_CONCEPT.pattern,
            'selection_is_review': False, 'columns': columns,
            'rows': [[o.get(k) for k in columns] for o in selected],
            'contexts': {k: v for k, v in facts['contexts'].items() if k in {o['context_id'] for o in selected}},
            'units': facts['units'], 'total_observations': len(observations),
            'selected_count': len(selected), 'omitted_count': len(omitted), 'omitted_ids': omitted,
            'unmapped_count': len(unmapped), 'unmapped_ids': unmapped,
            'omitted_concepts': {}, 'gaps': facts['gaps'],
            'notice': 'All omitted observations remain available by F ID. Proposed status, nils and gaps are unresolved evidence, not approved facts.'}
    for obs in observations:
        if obs['id'] in selected_ids:
            continue
        view['omitted_concepts'].setdefault(obs['concept'], []).append(obs['id'])

    documents = []
    excluded = []
    for item in sources:
        if item.get('representation') != 'text' or item['kind'] == 'transcript':
            excluded.append({'path': item['path'], 'reason': 'full transcript available separately' if item['kind'] == 'transcript'
                             else 'original representation; frozen reference retained'})
            continue
        text = source_text(item)
        start = 0
        while start < len(text):
            end = min(start + CHUNK_CHARACTERS, len(text))
            if end < len(text):
                boundary = text.rfind('\n', start + CHUNK_CHARACTERS // 2, end)
                if boundary > start:
                    end = boundary + 1
            preview_end = min(start + PREVIEW_CHARACTERS, end)
            documents.append({'id': 'D%03d' % (len(documents) + 1),
                              'document_id': item['document_id'], 'kind': item['kind'],
                              'path': item['path'], 'sha256': item['sha256'],
                              'start': start, 'end': end, 'span_sha256': _sha_text(text[start:end]),
                              'preview': text[start:preview_end], 'preview_end': preview_end,
                              'preview_truncated': preview_end < end})
            start = end
    docs = {'schema_version': VERSION, 'offset_unit': 'unicode_character',
            'chunks': documents, 'excluded_representations': excluded,
            'notice': 'Previews truncate. Retrieve full D spans before relying on context. All text characters in indexed non-transcript representations are covered.'}
    payloads = {'financial': facts, 'financial_view': view, 'documents': docs, 'transcript_index': index}
    # Recheck before writing; do not silently accept a source changed during preparation.
    base.validate_case(case)
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        _save(Path(files[name]), payload)
    manifest = {'schema_version': VERSION, 'case_path': str(case_path), 'case_sha256': base.sha(case_path),
                'case_digest': base.digest(case), 'sources': sources,
                'files': files, 'file_sha256': {k: base.sha(p) for k, p in files.items()},
                'transcript_path': str(Path(case['transcript_path']).resolve()),
                'transcript_sha256': _sha_text(transcript_text), 'scope_notes': case.get('scope_notes', []),
                'counts': {'financial': len(observations), 'financial_selected': len(selected),
                           'financial_omitted': len(omitted), 'financial_unmapped': len(unmapped),
                           'document_chunks': len(documents), 'transcript_characters': len(transcript_text),
                           'exchanges': len(index['exchanges'])}}
    _save(output / 'manifest.json', manifest)
    return manifest


def load_bundle(manifest_or_path):
    """Load the bundle and verify every frozen input and generated file hash."""
    manifest = dict(manifest_or_path) if isinstance(manifest_or_path, dict) else base.read(manifest_or_path)
    if manifest.get('schema_version') != VERSION:
        raise ValueError('Unsupported compact evidence version')
    if base.sha(manifest['case_path']) != manifest['case_sha256']:
        raise ValueError('Frozen case changed')
    case = base.read(manifest['case_path'])
    base.validate_case(case)
    if base.digest(case) != manifest['case_digest']:
        raise ValueError('Case digest mismatch')
    if sorted(case['sources'], key=_canonical) != sorted(manifest['sources'], key=_canonical):
        raise ValueError('Bundle source bindings differ from case')
    if Path(manifest['transcript_path']).resolve() != Path(case['transcript_path']).resolve():
        raise ValueError('Bundle transcript path differs from case')
    result = {'manifest': manifest}
    for name, path in manifest['files'].items():
        if base.sha(path) != manifest['file_sha256'][name]:
            raise ValueError('Compact evidence file changed: ' + name)
        result[name] = base.read(path)
    return result


def transcript_view(manifest_or_path):
    """Return full source text plus original speaker/exchange IDs in one read."""
    bundle = load_bundle(manifest_or_path)
    manifest = bundle['manifest']
    text = _text(manifest['transcript_path'])
    if _sha_text(text) != manifest['transcript_sha256']:
        raise ValueError('Transcript changed')
    _verify_index(bundle['transcript_index'], text)
    return {'text': text, 'index': bundle['transcript_index'],
            'path': manifest['transcript_path'], 'sha256': manifest['transcript_sha256'],
            'notice': 'Complete source text, including all Q&A and unassigned spans. Annotations retain their original review status.'}


def _scopes(bundle):
    manifest = bundle['manifest']
    scopes = {}
    for obs in bundle['financial']['observations']:
        scopes[obs['id']] = [{'path': obs['source_path'], 'sha256': obs['source_sha256'],
            'document_id': obs['source_document_id'], 'start': obs['support']['start'], 'end': obs['support']['end']}]
    for chunk in bundle['documents']['chunks']:
        scopes[chunk['id']] = [{k: chunk[k] for k in ('path', 'sha256', 'document_id', 'start', 'end')}]
    index = bundle['transcript_index']
    turns = {t['id']: t for t in index['turns']}
    def span(item):
        return {'path': manifest['transcript_path'], 'sha256': manifest['transcript_sha256'],
                'document_id': index['source']['document_id'], 'start': item['start'], 'end': item['end']}
    for item in index['sections'] + index['turns']:
        scopes[item['id']] = [span(item)]
    for exchange in index['exchanges']:
        scopes[exchange['id']] = [span(turns[i]) for i in exchange['turn_ids']]
    return scopes


def source_slices(manifest_or_path, ids):
    """Return exact complete source spans in requested ID order; reject unknown IDs.

    F entries include complete financial context and the original table row when
    available. Exchange entries contain each original turn separately; quotes
    cannot bridge speakers or gaps. D entries expand their truncated previews.
    """
    if not isinstance(ids, (list, tuple)) or any(not isinstance(i, str) for i in ids):
        raise ValueError('Source IDs must be a list of strings')
    bundle = load_bundle(manifest_or_path)
    scopes = _scopes(bundle)
    facts = {o['id']: o for o in bundle['financial']['observations']}
    result, cache = [], {}
    def materialize(scope):
        path = scope['path']
        if path not in cache:
            raw = Path(path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != scope['sha256']:
                raise ValueError('Source changed')
            cache[path] = raw.decode('utf-8')
        text = _span(cache[path], scope['start'], scope['end'])
        return {**scope, 'text': text, 'span_sha256': _sha_text(text), 'offset_unit': 'unicode_character'}
    for identifier in ids:
        if identifier not in scopes:
            raise ValueError('Unknown source ID: ' + identifier)
        entry = {'id': identifier, 'spans': [materialize(s) for s in scopes[identifier]]}
        if identifier in facts:
            obs = facts[identifier]
            entry['observation'] = {**obs, 'context': bundle['financial']['contexts'][obs['context_id']],
                                    'unit': bundle['financial']['units'][obs['unit_id']]}
            row = obs['support'].get('table_row')
            if row:
                entry['table_row'] = materialize({**scopes[identifier][0], 'start': row['start'], 'end': row['end']})
        result.append(entry)
    return result


def resolve_quote(manifest_or_path, scope_id, text, *, start=None):
    """Resolve one exact nonempty quotation within F/D/turn/exchange scope.

    Repeated text is ambiguous unless an explicit original Unicode start offset
    disambiguates it. Matching never normalizes whitespace or crosses turns.
    """
    if not isinstance(text, str) or not text:
        raise ValueError('Nonempty exact quote required')
    if start is not None and (type(start) is not int or start < 0):
        raise ValueError('Quote start must be an integer Unicode offset')
    entry = source_slices(manifest_or_path, [scope_id])[0]
    matches = []
    for span in entry['spans']:
        cursor = 0
        while True:
            found = span['text'].find(text, cursor)
            if found < 0:
                break
            absolute = span['start'] + found
            if start is None or absolute == start:
                matches.append({**{k: span[k] for k in ('path', 'sha256', 'document_id')},
                                'scope_id': scope_id, 'start': absolute, 'end': absolute + len(text),
                                'text': text, 'offset_unit': 'unicode_character'})
            cursor = found + 1
    if not matches:
        raise ValueError('Quote differs from source or lies outside scope')
    if len(matches) != 1:
        raise ValueError('Ambiguous quote: supply a source start offset or narrower scope')
    return matches[0]


def validate_quote(manifest_or_path, quote):
    """Validate persisted quote provenance, offsets and exact source text."""
    if not isinstance(quote, dict):
        raise ValueError('Quote object required')
    if any(k not in quote for k in ('scope_id', 'text', 'start', 'end', 'path', 'sha256', 'document_id', 'offset_unit')):
        raise ValueError('Incomplete quote provenance')
    if type(quote['end']) is not int:
        raise ValueError('Quote end must be an integer Unicode offset')
    resolved = resolve_quote(manifest_or_path, quote['scope_id'], quote['text'], start=quote['start'])
    if any(quote[k] != value for k, value in resolved.items()):
        raise ValueError('Quote provenance or offsets differ from source')
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_path')
    parser.add_argument('output_dir')
    args = parser.parse_args()
    manifest = prepare(args.case_path, args.output_dir)
    print(json.dumps({'manifest': str(Path(args.output_dir).resolve() / 'manifest.json'),
                      'counts': manifest['counts']}, sort_keys=True))


if __name__ == '__main__':
    main()
