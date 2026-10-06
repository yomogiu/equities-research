"""Deterministic bounded evidence for a whole-report repair review.

Selection is navigation, never approval. Original source hashes and Unicode offsets
are retained; larger evidence needs are explicit requests, never silent truncation.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base

VERSION = 'focused-repair-context-v1'
MAX_CONTEXT_CHARACTERS = 330000
COMPACTION_THRESHOLD = 300000
STRING_REFERENCE = 'shared_string_id'


class ContextTooLarge(ValueError):
    pass


def _bounded(value):
    size = len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    if size > MAX_CONTEXT_CHARACTERS:
        raise ContextTooLarge(f'context-too-large: {size} characters exceeds {MAX_CONTEXT_CHARACTERS}; narrow explicit scope or split the review, never truncate')
    return size


def expand_context(value):
    """Decode the optional lossless transport, retaining every original value."""
    if 'lossless_encoding' not in value:
        return copy.deepcopy(value)
    out = copy.deepcopy(value)
    encoding = out.pop('lossless_encoding')
    if (not isinstance(encoding, dict) or set(encoding) != {'version', 'strings', 'tables', 'notice'}
            or encoding['version'] != 'shared-strings-v1'):
        raise ValueError('Invalid lossless context encoding')
    strings = encoding['strings']
    if not isinstance(strings, dict) or any(not isinstance(v, str) for v in strings.values()):
        raise ValueError('Invalid shared context strings')
    def restore(v):
        if isinstance(v, dict):
            if set(v) == {STRING_REFERENCE}:
                key = v[STRING_REFERENCE]
                if not isinstance(key, str) or key not in strings:
                    raise ValueError('Unknown shared context string')
                return strings[key]
            return {k: restore(child) for k, child in v.items()}
        if isinstance(v, list): return [restore(child) for child in v]
        return v
    out = restore(out)
    for path in encoding['tables']:
        parent = out
        for key in path[:-1]: parent = parent[key]
        table = parent[path[-1]]
        columns, rows = table['columns'], table['rows']
        if len(set(columns)) != len(columns) or any(len(row) != len(columns) for row in rows):
            raise ValueError('Invalid lossless context table')
        parent[path[-1]] = [dict(zip(columns, row)) for row in rows]
    return out


def compact_context(value):
    """Intern repeated strings and table metadata; never shorten source/report text.

    The complete rendered report remains directly readable. Other repeated values
    are supplied once, not removed. Exact round-trip equality is checked before
    the existing context and final prompt limits are applied.
    """
    size = lambda v: len(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    if size(value) <= COMPACTION_THRESHOLD:
        return value
    if 'lossless_encoding' in value:
        raise ValueError('Context already has lossless encoding')
    counts = Counter()
    def count(v):
        if isinstance(v, dict):
            if set(v) == {STRING_REFERENCE}:
                raise ValueError('Reserved context string reference')
            for child in v.values(): count(child)
        elif isinstance(v, list):
            for child in v: count(child)
        elif isinstance(v, str): counts[v] += 1
    for key, child in value.items():
        if key != 'report': count(child)
    shared = {s: 'S' + str(i) for i, s in enumerate(sorted(s for s, n in counts.items() if n > 1 and len(s) >= 64))}
    def pack(v):
        if isinstance(v, dict): return {k: pack(child) for k, child in v.items()}
        if isinstance(v, list): return [pack(child) for child in v]
        if isinstance(v, str) and v in shared: return {STRING_REFERENCE: shared[v]}
        return v
    out = {key: copy.deepcopy(child) if key == 'report' else pack(child) for key, child in value.items()}
    tables = []
    for path in (['field_changes'], ['occurrence_inventory'],
                 ['canonical_exchange_index', 'exchanges'], ['canonical_exchange_index', 'turns'],
                 ['financial_observations', 'observations']):
        parent = out
        for key in path[:-1]: parent = parent.get(key, {})
        rows = parent.get(path[-1])
        if (not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows)
                or any(set(row) != set(rows[0]) for row in rows)):
            continue
        table = _passage_table(rows)
        if size(table) < size(rows):
            parent[path[-1]] = table; tables.append(path)
    out['lossless_encoding'] = {
        'version': 'shared-strings-v1', 'strings': {key: s for s, key in shared.items()}, 'tables': tables,
        'notice': 'Lossless encoding: replace every {shared_string_id: ID} object with the exact string in this strings map. At each listed tables path, pair row values with columns to restore record objects. Resolve references before interpreting source text, hashes, offsets or passages. Every original field and character is retained; the complete report is verbatim. This encoding conveys no factual approval.'}
    if expand_context(out) != value:
        raise ValueError('Lossless context round-trip changed content')
    return out if size(out) < size(value) else value


def _get(value, path):
    for part in path:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            return None
    return value


def occurrence_inventory(snapshot):
    """All editable prose leaves, with exact paths and inherited source citations.

    Quote selections, identifiers, and financial observations are deliberately not
    prose occurrences. Nothing is rewritten by this inventory.
    """
    result = []
    roots = [('analysis', None), ('retrieval', None), ('financial', 'context'), ('financial', 'gaps')]
    def visit(value, path, citations=()):
        if isinstance(value, dict):
            own = value.get('citations', citations)
            for key, child in value.items():
                if key in ('quotes', 'citations', 'opening_citations', 'selected_document_ids', 'question_passage_ids', 'answer_passage_ids', 'continuation_exchange_ids', 'grounding_status', 'grounding_notes') or key.endswith('_id'):
                    continue
                visit(child, path + [key], value.get('opening_citations', own) if key == 'opening' else own)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, path + [i], citations)
        elif isinstance(value, str):
            result.append({'path': path, 'text': value, 'sha256': base.digest(value), 'citations': list(citations)})
    for role, section in roots:
        path = ['artifacts', role] + ([section] if section else [])
        visit(_get(snapshot, path), path)
    return result


def addressable_inventory(snapshot, bundle=None):
    """One exact occurrence namespace for authors, staging and independent review.

    Display rows exist even before an override is written. Their absent override
    hashes as None; their source observations remain outside the editable namespace.
    """
    rows = {tuple(row['path']): row for row in occurrence_inventory(snapshot)}
    keys = snapshot.get('format', {}).get('rows', {})
    if bundle is not None:
        from research import earnings_report_repair as repair
        keys = repair.row_catalog(snapshot['artifacts']['financial'], bundle)
    # Citation lists are individually allowlisted metadata in remediation,
    # unlike aggregate report objects, quote selections or numeric observations.
    citation_paths = [['artifacts', 'analysis', 'opening_citations']]
    for role, section in (('financial', 'context'), ('retrieval', 'document_findings'),
                          ('analysis', 'findings'), ('analysis', 'next_tests')):
        citation_paths += [['artifacts', role, section, i, 'citations']
                           for i, row in enumerate(snapshot['artifacts'][role][section]) if 'citations' in row]
    paths = [['format', key] for key in ('basis', 'layout', 'tables')] + citation_paths
    paths += [['format', 'rows', key] for key in keys]
    table_keys = snapshot.get('format', {}).get('tables', {})
    if bundle is not None:
        table_keys = repair.table_catalog(snapshot['artifacts']['financial'], bundle)
    paths += [['format', 'tables', key] for key in table_keys]
    for path in paths:
        value = _get(snapshot, path)
        rows[tuple(path)] = {'path': path, 'text': json.dumps(value, ensure_ascii=False, sort_keys=True),
                            'sha256': base.digest(value),
                            'citations': value.get('citations', []) if isinstance(value, dict) else []}
    return [{**row, 'occurrence_id': 'occ-' + base.digest([row['path'], row['sha256']])[:24]}
            for row in rows.values()]


def resolve_claim_groups(groups, inventory):
    """Resolve author-selected IDs to exact paths; never infer dispositions."""
    if not isinstance(groups, list):
        raise ValueError('claim_groups must be a list')
    by_id = {row['occurrence_id']: row for row in inventory}
    by_path = {tuple(row['path']): row for row in inventory}
    def path(value):
        if not isinstance(value, list) or not value or any(type(v) not in (str, int) or
                (type(v) is int and v < 0) for v in value):
            raise ValueError('Exact typed occurrence path required')
        key = tuple(value)
        if key not in by_path:
            children = [row['occurrence_id'] for p, row in by_path.items() if p[:len(key)] == key]
            raise ValueError('Invalid unchanged or required occurrence: unknown or aggregate occurrence path ' + repr(value) +
                             '; select individual occurrence IDs' + (': ' + ', '.join(children[:8]) if children else ''))
        return list(value)
    def occurrence(value):
        if not isinstance(value, str) or value not in by_id:
            raise ValueError('Unknown or stale occurrence_id: ' + repr(value))
        return list(by_id[value]['path'])
    result = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('Claim group must be an object')
        use_ids = 'required_occurrence_ids' in group
        required_key = 'required_occurrence_ids' if use_ids else 'required_paths'
        if set(group) != {'id', 'aliases', required_key, 'unchanged'}:
            raise ValueError('Claim group requires id, aliases, ' + required_key + ', unchanged')
        aliases = group['aliases']
        if not isinstance(aliases, list) or not aliases or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError('Nonempty literal aliases required for claim group ' + str(group.get('id')))
        if not isinstance(group[required_key], list) or not isinstance(group['unchanged'], list):
            raise ValueError('Required occurrences and unchanged dispositions must be lists')
        resolve = occurrence if use_ids else path
        required = [resolve(v) for v in group[required_key]]
        if len({tuple(p) for p in required}) != len(required):
            raise ValueError('Duplicate required occurrence in claim group')
        unchanged = []
        for row in group['unchanged']:
            ref = 'occurrence_id' if use_ids else 'path'
            if not isinstance(row, dict) or set(row) != {ref, 'reason'} or not isinstance(row['reason'], str) or not row['reason'].strip():
                raise ValueError('Unchanged occurrence requires exact ' + ref + ' and nonempty reason')
            unchanged.append({'path': resolve(row[ref]), 'reason': row['reason']})
        result.append({'id': group['id'], 'aliases': aliases, 'required_paths': required, 'unchanged': unchanged})
    return result


def propagation_check(before, candidate, plan, bundle=None):
    """Check literal coverage and declared dispositions, never semantic approval."""
    inventory = addressable_inventory(before, bundle)
    groups = resolve_claim_groups(plan.get('claim_groups', []), inventory)
    operations = {tuple(op['path']): op for op in plan['operations']}
    changed = {path for path in operations if _get(before, path) != _get(candidate, path)}
    by_path = {tuple(row['path']): row for row in inventory}
    ids, results = set(), []
    for group in groups:
        if not isinstance(group, dict) or set(group) != {'id', 'aliases', 'required_paths', 'unchanged'}:
            raise ValueError('Claim group requires id, aliases, required_paths, unchanged')
        if not isinstance(group['id'], str) or not group['id'].strip() or group['id'] in ids:
            raise ValueError('Unique nonempty claim group ID required')
        ids.add(group['id'])
        aliases = group['aliases']
        if not isinstance(aliases, list) or not aliases or any(not isinstance(a, str) or not a.strip() for a in aliases):
            raise ValueError('Nonempty literal aliases required')
        def typed_path(path):
            if not isinstance(path, list) or not path or any(type(p) not in (str, int) or (type(p) is int and p < 0) for p in path):
                raise ValueError('Exact typed claim path required')
            return tuple(path)
        required = {typed_path(p) for p in group['required_paths']}
        if not required <= set(operations):
            raise ValueError('Required claim occurrence has no operation')
        unchanged = {}
        for row in group['unchanged']:
            if not isinstance(row, dict) or set(row) != {'path', 'reason'} or not isinstance(row['reason'], str) or not row['reason'].strip():
                raise ValueError('Unchanged occurrence requires exact path and reason')
            path = typed_path(row['path'])
            if path in unchanged or path not in by_path or (path not in operations and _get(before, path) != _get(candidate, path)):
                raise ValueError('Invalid unchanged occurrence disposition at ' + repr(row['path']) + ': duplicate, unknown, or changed without an operation')
            unchanged[path] = row['reason']
        literal = [r for r in by_path.values() if any(a.casefold() in r['text'].casefold() for a in aliases)]
        paths = {tuple(r['path']) for r in literal} | required | set(unchanged)
        if not paths:
            raise ValueError('Claim aliases or exact paths do not identify an occurrence')
        if paths - set(operations) - set(unchanged):
            raise ValueError('Unadjudicated claim occurrence: ' + repr(sorted(paths - set(operations) - set(unchanged), key=str)))
        matches = []
        for path in sorted(paths, key=str):
            row = by_path[path]
            matches.append({**row, 'disposition': 'patched' if path in changed else 'unchanged',
                'reason': unchanged.get(path, operations.get(path, {}).get('reason', '')),
                'literal_alias_match': any(a.casefold() in row['text'].casefold() for a in aliases),
                'declared_unchanged': path in unchanged,
                'idempotent_instruction': path in operations and path not in changed})
        results.append({'id': group['id'], 'matches': matches})
    return {'declared_groups': len(groups), 'groups': results,
            'notice': 'Exact paths and literal alias coverage only; actual deltas determine patched versus unchanged. Independent review assesses semantic consistency and all author dispositions.'}


def _references(value):
    scopes, pids = set(), set()
    def walk(v):
        if isinstance(v, dict):
            for key, child in v.items():
                if key in ('citations', 'opening_citations', 'fact_ids'):
                    scopes.update(child)
                elif key in ('scope_id', 'exchange_id') and isinstance(child, str):
                    scopes.add(child)
                elif key in ('passage_ids', 'question_passage_ids', 'answer_passage_ids'):
                    pids.update(child)
                elif key == 'passage_id' and isinstance(child, str):
                    pids.add(child)
                else:
                    walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)
    walk(value)
    return scopes, pids


def _index(bundle, catalog):
    scopes = evidence._scopes(bundle)
    for obs in bundle['financial']['observations']:
        row = obs.get('support', {}).get('table_row')
        if row:
            scopes[obs['id']].append({**scopes[obs['id']][0], 'start': row['start'], 'end': row['end']})
    by_id = {p['passage_id']: p for p in catalog['passages']}
    if len(by_id) != len(catalog['passages']):
        raise ValueError('Duplicate passage ID')
    if catalog.get('case_sha256') != bundle['manifest']['case_sha256']:
        raise ValueError('Passage catalogue case mismatch')
    parents = {}
    for exchange in bundle['transcript_index']['exchanges']:
        for turn_id in exchange['turn_ids']:
            parents.setdefault(turn_id, set()).add(exchange['id'])
    return scopes, by_id, parents


def _materialize(scopes, ids):
    cache, result = {}, []
    for identifier in sorted(ids):
        rows = []
        for scope in scopes[identifier]:
            key = (scope['path'], scope['sha256'])
            if key not in cache:
                raw = Path(scope['path']).read_bytes()
                if evidence._sha_text(raw.decode('utf-8')) != scope['sha256']:
                    raise ValueError('Frozen source changed')
                cache[key] = raw.decode('utf-8')
            text = evidence._span(cache[key], scope['start'], scope['end'])
            rows.append({**scope, 'text': text, 'span_sha256': evidence._sha_text(text), 'offset_unit': 'unicode_character'})
        result.append({'id': identifier, 'spans': rows})
    return result


def _compact_spans(entries):
    """Deduplicate overlapping selected spans without dropping a character.

    Each scope retains its exact boundaries and hash. Shared source blocks merge
    only overlapping or adjacent intervals in the same frozen representation.
    """
    groups = {}
    for entry in entries:
        for span in entry['spans']:
            key = tuple(span[k] for k in ('path', 'sha256', 'document_id'))
            groups.setdefault(key, []).append(span)
    blocks = []
    for key, rows in sorted(groups.items()):
        intervals = []
        for row in sorted(rows, key=lambda r: (r['start'], r['end'])):
            if intervals and row['start'] <= intervals[-1][1]:
                intervals[-1][1] = max(intervals[-1][1], row['end'])
            else:
                intervals.append([row['start'], row['end']])
        text = Path(key[0]).read_bytes().decode('utf-8')
        if evidence._sha_text(text) != key[1]:
            raise ValueError('Frozen source changed')
        for start, end in intervals:
            binding = dict(zip(('path','sha256','document_id'), key))
            body = text[start:end]
            block = {**binding, 'start': start, 'end': end, 'text': body,
                     'span_sha256': evidence._sha_text(body), 'offset_unit': 'unicode_character'}
            blocks.append({'block_id': 'B' + base.digest({k:v for k,v in block.items() if k not in ('path','text')})[:16], **block})
    out = []
    for entry in entries:
        refs = []
        for span in entry['spans']:
            block = next(b for b in blocks if all(b[k] == span[k] for k in ('path','sha256','document_id'))
                         and b['start'] <= span['start'] and b['end'] >= span['end'])
            refs.append({'block_id': block['block_id'], 'start': span['start'], 'end': span['end'], 'span_sha256': span['span_sha256']})
        out.append({'id': entry['id'], 'spans': refs})
    return out, blocks


def _navigation_index(scopes):
    sources = sorted({(s['document_id'],s['sha256']) for spans in scopes.values() for s in spans})
    lookup = {source: i for i, source in enumerate(sources)}
    return {'source_columns': ['document_id','sha256'], 'sources': [list(s) for s in sources],
            'columns': ['scope_id','spans'], 'span_columns': ['source_index','start','end'],
            'rows': [[key, [[lookup[(s['document_id'],s['sha256'])],s['start'],s['end']] for s in values]] for key,values in sorted(scopes.items())]}


def _compact_passages(selected, blocks):
    """Reference already supplied source blocks; reconstruct every passage exactly.

    Passage start/end remain absolute Unicode offsets in the original source.
    The referenced block carries its source path, hash, document and offset unit.
    """
    if len({b['block_id'] for b in blocks}) != len(blocks):
        raise ValueError('Duplicate source block ID')
    for block in blocks:
        if (block['offset_unit'] != 'unicode_character'
                or len(block['text']) != block['end'] - block['start']
                or evidence._sha_text(block['text']) != block['span_sha256']):
            raise ValueError('Source block text or offsets changed')
    result = []
    for passage in selected:
        matches = [b for b in blocks
                   if all(b[k] == passage[k] for k in ('path', 'sha256', 'document_id', 'offset_unit'))
                   and b['start'] <= passage['start'] < passage['end'] <= b['end']]
        if len(matches) != 1:
            raise ValueError('Passage requires one exact source block')
        block = matches[0]
        text = block['text'][passage['start']-block['start']:passage['end']-block['start']]
        if text != passage['text'] or evidence._sha_text(text) != passage['span_sha256']:
            raise ValueError('Passage differs from referenced source block')
        result.append({k: copy.deepcopy(v) for k, v in passage.items()
                       if k not in ('text', 'path', 'sha256', 'document_id', 'offset_unit')}
                      | {'block_id': block['block_id']})
    return result


def _passage_table(rows):
    """Lossless columnar metadata; retain every field without repeated JSON keys."""
    columns = sorted({key for row in rows for key in row})
    if any(set(row) != set(columns) for row in rows):
        raise ValueError('Passage metadata fields differ')
    return {'columns': columns, 'rows': [[row[key] for key in columns] for row in rows]}


def evidence_response(bundle, catalog, requests, already_scope_ids=()):
    """Validate read-more requests and return exact complete scopes once.

    Each request is {scope_id, reason}. Asking for a Q&A turn also returns every
    turn in its parent exchange, preserving the analyst question and full answer.
    """
    scopes, _, parents = _index(bundle, catalog)
    if not isinstance(requests, (list, tuple)) or not requests:
        raise ValueError('Nonempty evidence requests required')
    selected = set()
    for request in requests:
        if not isinstance(request, dict) or set(request) != {'scope_id', 'reason'} or not isinstance(request['reason'], str) or not request['reason'].strip():
            raise ValueError('Evidence request needs exact scope_id and reason')
        identifier = request['scope_id']
        if not isinstance(identifier, str) or identifier not in scopes:
            raise ValueError('Unknown requested source scope')
        selected.add(identifier)
        selected.update(parents.get(identifier, ()))
    if any(s not in scopes for s in already_scope_ids):
        raise ValueError('Unknown previously supplied scope')
    new = selected - set(already_scope_ids)
    result = {'requests': copy.deepcopy(list(requests)), 'scope_ids': sorted(new), 'scopes': _materialize(scopes, new)}
    _bounded(result)
    return result


def canonical_exchange_index(bundle):
    """Verified role membership and boundary annotations shared by both agents."""
    transcript = evidence.transcript_view(bundle['manifest'])
    return {'transcript_sha256': transcript['sha256'],
            'exchanges': copy.deepcopy(transcript['index']['exchanges']),
            'turns': copy.deepcopy(transcript['index']['turns'])}


def build(before, candidate, plan, bundle, catalog, rendered_report, writing, extra_scope_ids=()):
    """Review the entire rendered report with source evidence focused on changes.

    rendered_report must already exclude the generated evidence appendix. It is
    preserved in full. Changed-field citations, pending findings, every report
    quotation, and source-bound financial facts select evidence deterministically.
    """
    if not isinstance(rendered_report, (str, dict)) or not rendered_report:
        raise ValueError('Complete rendered report text required')
    scopes, by_id, parents = _index(bundle, catalog)
    selected, pids = set(extra_scope_ids), set()
    deltas = []
    before_rows = {tuple(r['path']): r for r in occurrence_inventory(before)}
    after_rows = {tuple(r['path']): r for r in occurrence_inventory(candidate)}
    from research import earnings_corrections as corrections
    normalized_plan = corrections.normalize_plan(before, plan, bundle)
    for op in normalized_plan['operations']:
        path = op['path']
        old, new = _get(before, path), _get(candidate, path)
        deltas.append({'id': op['id'], 'path': path, 'before': old, 'after': new,
                       'before_sha256': base.digest(old), 'after_sha256': base.digest(new),
                       'reason': op['reason'], 'parent_operation_id': op.get('parent_operation_id', op['id'])})
        for value in (op, before_rows.get(tuple(path), {}), after_rows.get(tuple(path), {}), old, new,
                      _get(before, path[:-1]) if len(path) > 3 else {},
                      _get(candidate, path[:-1]) if len(path) > 3 else {}):
            a, b = _references(value); selected.update(a); pids.update(b)
    a, b = _references(before.get('findings', [])); selected.update(a); pids.update(b)
    # Full report quotations and selected financial rows are fixed evidence. The
    # rest of unchanged prose stays in the rendered report, avoiding full-source reruns.
    for role in ('analysis', 'retrieval'):
        def quotes(value):
            if isinstance(value, dict):
                if 'passage_id' in value:
                    pids.add(value['passage_id'])
                for child in value.values(): quotes(child)
            elif isinstance(value, list):
                for child in value: quotes(child)
        quotes(candidate['artifacts'][role])
    # The full report is reviewed for coherence. Supply its direct citations
    # initially so unchanged but visible claims do not require a second lookup.
    for value in (candidate['artifacts']['analysis'], candidate['format']):
        a, b = _references(value); selected.update(a); pids.update(b)
    financial = bundle['financial']
    fact_ids, _ = _references(candidate['artifacts']['financial']['rows'])
    if not fact_ids <= set(scopes):
        raise ValueError('Unknown financial observation ID')
    for pid in pids:
        if pid not in by_id:
            raise ValueError('Unknown selected passage ID')
        selected.add(by_id[pid]['scope_id'])
    if any(identifier not in scopes for identifier in selected):
        raise ValueError('Unknown cited source scope')
    for identifier in tuple(selected):
        selected.update(parents.get(identifier, ()))
    # Source scopes cover complete D chunks/turns, and entire parent exchanges.
    # Exact selected passages retain adjacent navigation units in the same scope.
    neighbours = set(pids)
    by_scope = {}
    for p in catalog['passages']:
        by_scope.setdefault(p['scope_id'], []).append(p)
    for rows in by_scope.values():
        rows.sort(key=lambda p: p['start'])
        for i, p in enumerate(rows):
            if p['passage_id'] in pids:
                neighbours.update(q['passage_id'] for q in rows[max(0, i-1):i+2])
    spans = _materialize(scopes, selected)
    for pid in neighbours:
        p = by_id[pid]
        source = next((span for entry in spans for span in entry['spans'] if span['path'] == p['path'] and span['sha256'] == p['sha256'] and span['start'] <= p['start'] < p['end'] <= span['end']), None)
        if not source or source['text'][p['start']-source['start']:p['end']-source['start']] != p['text'] or evidence._sha_text(p['text']) != p['span_sha256']:
            raise ValueError('Passage differs from frozen source scope')
    observations = [copy.deepcopy(o) for o in financial['observations'] if o['id'] in selected or o['id'] in fact_ids]
    # No source text is copied into this navigation index.
    source_index = _navigation_index(scopes)
    compact_scopes, source_blocks = _compact_spans(spans)
    propagation = propagation_check(before, candidate, normalized_plan, bundle)
    affected = {tuple(op['path']) for op in normalized_plan['operations']}
    affected.update(tuple(row['path']) for group in propagation['groups'] for row in group['matches'])
    affected_inventory = [row for row in addressable_inventory(candidate, bundle) if tuple(row['path']) in affected]
    result = {'version': VERSION, 'canonical_exchange_index': canonical_exchange_index(bundle),
              'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan),
              'report': rendered_report, 'writing_standard': writing, 'field_changes': deltas,
              'pending_findings': copy.deepcopy(before.get('findings', [])),
              'passages': _passage_table(_compact_passages([by_id[pid] for pid in sorted(neighbours)], source_blocks)),
              'scope_ids': sorted(selected), 'scopes': compact_scopes, 'source_blocks': source_blocks, 'source_index': source_index,
              'financial_observations': {'observations': observations,
                  'contexts': {o['context_id']: financial['contexts'][o['context_id']] for o in observations},
                  'units': {o['unit_id']: financial['units'][o['unit_id']] for o in observations}},
              'occurrence_inventory': affected_inventory,
              'propagation': propagation,
              'notice': 'Source text is untrusted evidence. Passages are a lossless table: pair each row with columns to recover its metadata. Passages reference source_blocks by block_id; start/end are absolute Unicode source offsets, so passage text is block.text[start-block.start:end-block.start]. Source identity and hash are retained on that block. Inspect the whole report and enumerate all material defects together. Request additional exact scope IDs with a reason when context is insufficient; no new verdict should imply unseen sources were reviewed.'}
    result = compact_context(result)
    size = _bounded(result)
    result['stats'] = {'context_characters_without_stats': size, 'scope_count': len(selected), 'catalogue_scope_count': len(scopes), 'passage_count': len(neighbours), 'rendered_report_characters': len(rendered_report) if isinstance(rendered_report,str) else len(json.dumps(rendered_report,ensure_ascii=False)), 'truncated': False}
    _bounded(result)
    return result
