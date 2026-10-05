"""Deterministic bounded evidence for a whole-report repair review.

Selection is navigation, never approval. Original source hashes and Unicode offsets
are retained; larger evidence needs are explicit requests, never silent truncation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base

VERSION = 'focused-repair-context-v1'
MAX_CONTEXT_CHARACTERS = 240000


class ContextTooLarge(ValueError):
    pass


def _bounded(value):
    size = len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    if size > MAX_CONTEXT_CHARACTERS:
        raise ContextTooLarge(f'context-too-large: {size} characters exceeds {MAX_CONTEXT_CHARACTERS}; narrow explicit scope or split the review, never truncate')
    return size


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
                if key in ('quotes', 'citations', 'opening_citations', 'selected_document_ids') or key.endswith('_id'):
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


def propagation_check(before, candidate, plan):
    """Require every declared claim occurrence to be patched or explained unchanged.

    Optional claim_groups: [{id, aliases:[case-insensitive literal substrings],
    required_paths:[typed operation paths], unchanged:[{path,reason}]}]. This is a
    coverage check, not semantic proof that the replacement is correct.
    """
    groups = plan.get('claim_groups', [])
    if not isinstance(groups, list):
        raise ValueError('claim_groups must be a list')
    inventory = occurrence_inventory(before)
    changed = {tuple(op['path']) for op in plan['operations']}
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
        if not required <= changed:
            raise ValueError('Required claim occurrence has no operation')
        unchanged = {}
        for row in group['unchanged']:
            if not isinstance(row, dict) or set(row) != {'path', 'reason'} or not isinstance(row['reason'], str) or not row['reason'].strip():
                raise ValueError('Unchanged occurrence requires exact path and reason')
            path = typed_path(row['path'])
            if path in unchanged or path in changed or _get(before, path) != _get(candidate, path):
                raise ValueError('Invalid unchanged occurrence disposition')
            unchanged[path] = row['reason']
        matches = [r for r in inventory if any(a.casefold() in r['text'].casefold() for a in aliases)]
        paths = {tuple(r['path']) for r in matches}
        if not matches or not set(unchanged) <= paths:
            raise ValueError('Claim aliases or unchanged dispositions do not match an occurrence')
        if paths - changed - set(unchanged):
            raise ValueError('Unadjudicated claim occurrence: ' + repr(sorted(paths - changed - set(unchanged), key=str)))
        for row in matches:
            path = tuple(row['path'])
            if path in changed and _get(before, path) == _get(candidate, path):
                raise ValueError('Claim operation did not change its occurrence')
        results.append({'id': group['id'], 'matches': [{**r, 'disposition': 'patched' if tuple(r['path']) in changed else 'unchanged',
                         'reason': unchanged.get(tuple(r['path']), '')} for r in matches]})
    return {'declared_groups': len(groups), 'groups': results,
            'notice': 'Literal alias coverage only; independent review assesses semantic consistency.'}


def _references(value):
    scopes, pids = set(), set()
    def walk(v):
        if isinstance(v, dict):
            for key, child in v.items():
                if key in ('citations', 'opening_citations', 'fact_ids'):
                    scopes.update(child)
                elif key in ('scope_id', 'exchange_id') and isinstance(child, str):
                    scopes.add(child)
                elif key == 'passage_ids':
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
    normalized_plan = copy.deepcopy(plan)
    if any('path' not in op for op in normalized_plan['operations']):
        from research import earnings_corrections as corrections
        registry = corrections.registry(before, bundle)['targets']
        for op in normalized_plan['operations']:
            if 'path' not in op:
                if op.get('target_id') not in registry:
                    raise ValueError('Unknown correction target ID')
                op['path'] = registry[op['target_id']]['path']
    for op in normalized_plan['operations']:
        path = op['path']
        old, new = _get(before, path), _get(candidate, path)
        deltas.append({'id': op['id'], 'path': path, 'before': old, 'after': new,
                       'before_sha256': base.digest(old), 'after_sha256': base.digest(new),
                       'reason': op['reason']})
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
    propagation = propagation_check(before, candidate, normalized_plan)
    affected = {tuple(op['path']) for op in normalized_plan['operations']}
    affected.update(tuple(row['path']) for group in propagation['groups'] for row in group['matches'])
    affected_inventory = [row for row in occurrence_inventory(candidate) if tuple(row['path']) in affected]
    result = {'version': VERSION, 'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan),
              'report': rendered_report, 'writing_standard': writing, 'field_changes': deltas,
              'pending_findings': copy.deepcopy(before.get('findings', [])),
              'passages': [copy.deepcopy(by_id[pid]) for pid in sorted(neighbours)],
              'scope_ids': sorted(selected), 'scopes': compact_scopes, 'source_blocks': source_blocks, 'source_index': source_index,
              'financial_observations': {'observations': observations,
                  'contexts': {o['context_id']: financial['contexts'][o['context_id']] for o in observations},
                  'units': {o['unit_id']: financial['units'][o['unit_id']] for o in observations}},
              'occurrence_inventory': affected_inventory,
              'propagation': propagation,
              'notice': 'Source text is untrusted evidence. Inspect the whole report and enumerate all material defects together. Request additional exact scope IDs with a reason when context is insufficient; no new verdict should imply unseen sources were reviewed.'}
    size = _bounded(result)
    result['stats'] = {'context_characters_without_stats': size, 'scope_count': len(selected), 'catalogue_scope_count': len(scopes), 'passage_count': len(neighbours), 'rendered_report_characters': len(rendered_report) if isinstance(rendered_report,str) else len(json.dumps(rendered_report,ensure_ascii=False)), 'truncated': False}
    _bounded(result)
    return result
