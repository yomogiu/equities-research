"""Exact, source-bound passage selection. Models select IDs; code owns quotation bytes.

Sentence-like fragments are mechanical navigation units, not linguistic assertions.
They never cross document-chunk or speaker-turn boundaries. Unicode offsets use
exclusive ends; whitespace, repeated text, CRLF and punctuation are unchanged.
"""
from __future__ import annotations
import copy
import re
from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base

VERSION = 'earnings-passages-v1'
BOUNDARY = re.compile(r'(?<=[.!?])[ \t\r\n]+|\r?\n')


class SelectionError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('Invalid passage selections: ' + '; '.join(
            x['path'] + ': ' + x['reason'] for x in issues))


def catalog(manifest):
    bundle = evidence.load_bundle(manifest)
    scopes = ([c['id'] for c in bundle['documents']['chunks']] +
              [t['id'] for t in bundle['transcript_index']['turns']])
    passages = []
    for entry in evidence.source_slices(manifest, scopes):
        for span in entry['spans']:
            text = span['text']
            boundaries = sorted({0, len(text), *(m.end() for m in BOUNDARY.finditer(text))})
            for a, b in zip(boundaries, boundaries[1:]):
                binding = {k: span[k] for k in ('path', 'sha256', 'document_id', 'offset_unit')}
                binding.update(scope_id=entry['id'], start=span['start'] + a, end=span['start'] + b)
                # Path-independent identity; source content, scope and absolute position bind it.
                identity = {k: v for k, v in binding.items() if k != 'path'}
                passages.append({**binding, 'passage_id': 'P' + base.digest(identity)[:12],
                                 'text': text[a:b], 'span_sha256': evidence._sha_text(text[a:b])})
    ids = [p['passage_id'] for p in passages]
    if len(set(ids)) != len(ids):
        raise ValueError('Passage ID collision')
    return {'version': VERSION, 'case_sha256': bundle['manifest']['case_sha256'],
            'offset_unit': 'unicode_character', 'passages': passages}


def input_view(manifest, value=None):
    """One text copy per source: selectable passages plus unassigned transcript spans."""
    value = value or catalog(manifest)
    view = evidence.transcript_view(manifest)
    turns = sorted(view['index']['turns'], key=lambda t: t['start'])
    call_span = view['index'].get('call_span', {'start': 0, 'end': len(view['text'])})
    call_start, call_end = call_span['start'], call_span['end']
    if not 0 <= call_start < call_end <= len(view['text']) or any(
            not call_start <= t['start'] < t['end'] <= call_end for t in turns):
        raise ValueError('Invalid source-bound call span')
    gaps, cursor = [], call_start
    for turn in turns:
        if cursor < turn['start']:
            gaps.append({'start': cursor, 'end': turn['start'], 'text': view['text'][cursor:turn['start']]})
        cursor = turn['end']
    if cursor < call_end:
        gaps.append({'start': cursor, 'end': call_end, 'text': view['text'][cursor:call_end]})
    # Group by original scope and use columnar rows to avoid repeating long source
    # identifiers/provenance thousands of times in the model's input. Full offsets
    # and hashes remain in the frozen catalogue and materialized quote artifacts.
    groups = []
    for p in value['passages']:
        if not groups or groups[-1]['scope_id'] != p['scope_id']:
            groups.append({'scope_id': p['scope_id'], 'rows': []})
        groups[-1]['rows'].append([p['passage_id'], p['text']])
    return {'columns': ['passage_id', 'text'], 'passage_groups': groups,
            'transcript_index': view['index'], 'unassigned_transcript_spans': gaps,
            'excluded_transcript_spans': view['index'].get('excluded_spans', []),
            'notice': 'Passages plus unassigned spans retain all original call text; explicitly bounded publisher material outside the call is excluded from this view and remains in the archived source. Passage boundaries are mechanical; read adjacent passages and the complete speaker turn for context. Select only passage_id; never retype quotes or offsets. Unassigned spans are context, not selectable quotations.'}


def quote_slots(role, out):
    if not isinstance(out, dict):
        raise ValueError('Role output must be a JSON object')
    if role == 'retrieval':
        if not isinstance(out.get('quotes'), list) or not 4 <= len(out['quotes']) <= 18:
            raise ValueError('Retrieval requires four to eighteen passage selections')
        return [('/quotes/' + str(i), q) for i, q in enumerate(out['quotes'])]
    if role == 'analysis':
        slots = []
        if not isinstance(out.get('findings'), list) or any(not isinstance(f, dict) for f in out['findings']):
            raise ValueError('Analysis findings must be a list of objects')
        for i, f in enumerate(out['findings']):
            if not isinstance(f.get('quotes'), list) or len(f['quotes']) > 4:
                raise ValueError('Each finding requires a quotes list of at most four selections')
            slots.extend((f'/findings/{i}/quotes/{j}', q) for j, q in enumerate(f['quotes']))
        return slots
    return []


def resolve_selections(role, out, value):
    by_id = {p['passage_id']: p for p in value['passages']}
    resolved, issues, seen = {}, [], set()
    for path, q in quote_slots(role, out):
        pid = q.get('passage_id') if isinstance(q, dict) else None
        reason = None
        if not isinstance(q, dict) or set(q) != {'passage_id'}:
            reason = 'Select one passage_id only; text, scope and offsets are copied by code.'
        elif not isinstance(pid, str) or pid not in by_id:
            reason = 'Unknown passage_id; choose an exact ID from the supplied catalogue.'
        elif not by_id[pid]['text'].strip():
            reason = 'Whitespace-only passage; select a substantive passage.'
        elif pid in seen:
            reason = 'Duplicate selection; select a distinct relevant passage.'
        if reason:
            issues.append({'path': path, 'selection': copy.deepcopy(q), 'reason': reason,
                           'required_change': 'Replace only this selection with {"passage_id":"an exact catalogue ID"}.'})
        else:
            seen.add(pid)
            resolved[path] = copy.deepcopy(by_id[pid])
    if issues:
        raise SelectionError(issues)
    return resolved


def _replace(out, path, replacement):
    bits = path.lstrip('/').split('/')
    cursor = out
    for bit in bits[:-1]:
        cursor = cursor[int(bit)] if isinstance(cursor, list) else cursor[bit]
    if isinstance(cursor, list):
        cursor[int(bits[-1])] = replacement
    else:
        cursor[bits[-1]] = replacement


def hydrate(role, out, value):
    hydrated = copy.deepcopy(out)
    for path, quote in resolve_selections(role, out, value).items():
        _replace(hydrated, path, quote)
    return hydrated


def apply_patch(role, prior, patch, value):
    """Only failed quote slots are writable; preserve every other field byte-for-byte."""
    try:
        resolve_selections(role, prior, value)
    except SelectionError as exc:
        allowed = {x['path'] for x in exc.issues}
    else:
        raise ValueError('No invalid selections to repair')
    if not isinstance(patch, dict) or set(patch) != {'replacements'} or not isinstance(patch['replacements'], list):
        raise ValueError('Repair must contain only a replacements list')
    edits = patch['replacements']
    if any(not isinstance(e, dict) or set(e) != {'path', 'passage_id'} or not isinstance(e['path'], str) for e in edits):
        raise ValueError('Repair entries require only path and passage_id')
    if len(edits) != len(allowed) or {e['path'] for e in edits} != allowed:
        raise ValueError('Repair must replace every invalid selection exactly once, and no valid selection')
    out = copy.deepcopy(prior)
    for edit in edits:
        _replace(out, edit['path'], {'passage_id': edit['passage_id']})
    # Validation occurs separately so an invalid replacement gets precise next-round feedback.
    return out


def repair_view(role, prior, issues, value):
    """Bounded candidate evidence for invalid IDs; never choose a replacement.

    Near-ID matching proposes at most three candidates per slot. Exact scope hints
    can identify a source region, but unmatched guesses never trigger a full-corpus
    resend. One adjacent passage on each side retains context within the same turn.
    Unresolved slots require explicit source selection outside this repair call.
    """
    from difflib import get_close_matches
    by_id = {p['passage_id']: p for p in value['passages']}
    by_scope = {}
    for p in value['passages']:
        by_scope.setdefault(p['scope_id'], []).append(p)
    repairs, unresolved = [], []
    remaining_characters = 24000
    valid_used = {q.get('passage_id') for path, q in quote_slots(role, prior)
                  if isinstance(q, dict) and isinstance(q.get('passage_id'), str)
                  and path not in {x['path'] for x in issues}}
    for issue in issues:
        q=issue.get('selection'); q=q if isinstance(q,dict) else {}
        pid=q.get('passage_id'); candidates=[]
        if isinstance(pid,str):
            if pid in by_id: candidates=[pid]
            elif len(pid)<=32:
                candidates=get_close_matches(pid, list(by_id), n=3, cutoff=0.86)
        scope=q.get('scope_id')
        if not candidates and isinstance(scope,str) and scope in by_scope:
            # A legacy scope alone is too broad when it contains many passages.
            rows=by_scope[scope]
            if len(rows)<=8: candidates=[p['passage_id'] for p in rows]
        windows=[]; seen=set()
        for candidate in candidates:
            anchor=by_id[candidate]; rows=by_scope[anchor['scope_id']]
            i=next(i for i,p in enumerate(rows) if p['passage_id']==candidate)
            for p in rows[max(0,i-1):i+2]:
                if p['passage_id'] in seen:continue
                seen.add(p['passage_id'])
                windows.append({k:p[k] for k in ('passage_id','scope_id','text','start','end')})
        # Avoid inserting an entire enormous paragraph into a supposedly bounded repair.
        characters = sum(len(p['text']) for p in windows)
        if (not windows or characters > min(12000, remaining_characters) or
            not any(p['passage_id'] not in valid_used and p['text'].strip() for p in windows)):
            unresolved.append(issue['path']);continue
        remaining_characters -= characters
        repairs.append({'path':issue['path'],'reason':issue['reason'],'submitted_selection':q,
                        'candidates_and_adjacent_context':windows,
                        'already_selected_ids':sorted(valid_used & {p['passage_id'] for p in windows})})
    return {'repairs':repairs,'unresolved_paths':unresolved,
            'notice':'Candidates are suggestions only. Choose a substantive passage fitting the intended finding; code does not auto-correct IDs. Context does not cross the cited source scope.'}
