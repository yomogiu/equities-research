"""Opt-in mechanical Q&A membership gate; never a semantic source review.

Exchange and turn IDs are joined explicitly. Original Unicode offsets and source
hashes bind membership. Provisional roles, boundaries and followups stay provisional;
a successful check establishes only that selections belong to the indexed scopes.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
from research import earnings_experiment as base

VERSION = 'source-bound-qa-membership-v1'
HEADER_VERSION = 'source-bound-qa-membership-v2'
NAMED_GREETING_VERSION = 'source-bound-qa-membership-v3'
COURTESY_ROUTING_VERSION = 'source-bound-qa-membership-v4'
NAMED_THANKS_VERSION = 'source-bound-qa-membership-v5'
HEADER_VERSIONS = {HEADER_VERSION, NAMED_GREETING_VERSION, COURTESY_ROUTING_VERSION, NAMED_THANKS_VERSION}
SUPPORTED_VERSIONS = {VERSION, *HEADER_VERSIONS}
NOTICE = ('Membership validation checks source offsets and indexed speaker roles, not '
          'whether a question was understood, answered, relevant or summarized correctly. '
          'All provisional annotations and unresolved boundaries require substantive review.')
QUESTION_FUNCTIONS = {'questioner_turn', 'submitted_question', 'live_question', 'submitted_question_topic_transition'}
ANSWER_FUNCTIONS = {'issuer_response_candidate', 'answer_to_submitted_topic', 'answer_to_submitted_question', 'issuer_answer'}
KNOWN_FUNCTIONS = QUESTION_FUNCTIONS | ANSWER_FUNCTIONS | {'moderator', 'issuer_handoff'}
FIELDS = ('question_passage_ids', 'answer_passage_ids', 'continuation_exchange_ids',
          'grounding_status', 'grounding_notes')
GREETING = re.compile(r'(?:(?:hi|hello|hey|thanks|thank you|good (?:morning|afternoon|evening))'
                      r'(?: (?:everyone|all|very much|so much|for taking (?:my|the) question))?'
                      r'[\s,.!?;:]*)+', re.I)


def _header_body(turn, rows, version=HEADER_VERSION):
    """Strip an exact speaker header and known-role title, never infer a role."""
    raw = ''.join(p['text'] for p in rows).strip()
    body = re.sub(r'^' + re.escape(turn['speaker']) + r'\s*[:\n]\s*', '', raw).strip()
    lines = body.splitlines()
    patterns = {'analyst': r'Analyst, [^\n]+',
                'management': r'(?:President and CEO|EVP and CFO|VP of Investor Relations|SVP of Global Sales), [^\n]+'}
    if version == NAMED_THANKS_VERSION:patterns['analyst']=r'(?:Analyst|Managing Director), [^\n]+'
    pattern = patterns.get(turn['role'])
    if (raw.splitlines()[0] == turn['speaker'] and len(lines) >= 2
            and pattern and re.fullmatch(pattern, lines[0])):
        body = '\n'.join(lines[1:]).strip()
    return body


def _body(turn, rows):
    body = ''.join(p['text'] for p in rows).strip()
    return re.sub(r'^' + re.escape(turn['speaker']) + r'\s*[:\n]\s*', '', body).strip()


def _greeting(turn, rows, version=VERSION, peers=()):
    body = _header_body(turn, rows, version) if version in HEADER_VERSIONS else _body(turn, rows)
    # This deliberately recognizes only complete, simple courtesy turns. Other
    # short statements remain evidence; a greeting followed by a question is not
    # discarded. The source text itself is never removed or rewritten.
    if version == NAMED_THANKS_VERSION and _complete(turn,rows) and body == 'Great.':return True
    if version in {NAMED_GREETING_VERSION, COURTESY_ROUTING_VERSION, NAMED_THANKS_VERSION} and turn['role'] in {'analyst', 'management'}:
        # Only another named participant in this exchange can be addressed.
        # Require complete contiguous source coverage before excluding a turn.
        cursor = turn['start']
        complete = bool(rows)
        for row in rows:
            complete = complete and row['start'] == cursor and len(row['text']) == row['end'] - row['start']
            cursor = row['end']
        complete = complete and cursor == turn['end']
        for peer in peers:
            name = peer.get('speaker', '').strip()
            if (not complete or peer['id'] == turn['id'] or peer['role'] not in {'analyst', 'management'}
                    or len(name.split()) < 2):
                continue
            for address in (name, name.split()[0]):
                if version == NAMED_THANKS_VERSION and re.fullmatch(r'(?:Makes sense\. )?Thanks,?\s+'+re.escape(address)+r'[.!]?',body,re.I):
                    return True
                if re.fullmatch(r'(?:Hi|Hello|Hey|Good morning|Good afternoon|Good evening),?\s+'
                                + re.escape(address) + r'[.!]?', body, re.I):
                    return True
    if version in {COURTESY_ROUTING_VERSION, NAMED_THANKS_VERSION} and _complete(turn,rows) and body in {'Thank you. Thanks for the questions.', 'Got it. That makes a lot of sense. Thank you.', 'Perfect. Thank you.'}:
        return True
    return bool(body and (GREETING.fullmatch(body) or version in HEADER_VERSIONS and re.fullmatch(
        r'(?:Great|Okay|Got it|I appreciate that)\. (?:Thank you\.|That[’\']s helpful\. Thank you\.)', body)))


def _complete(turn, rows):
    cursor=turn['start']
    for row in rows:
        if row['start']!=cursor or len(row['text'])!=row['end']-row['start']:return False
        cursor=row['end']
    return bool(rows) and cursor==turn['end']


def _routing(turn, rows, targets, version=HEADER_VERSION):
    if _function(turn) != 'moderator' or turn['role'] != 'operator':
        return False
    body = _header_body(turn, rows, version)
    normalize = lambda text: re.sub(r'\s+', '', text)
    for name, firm in targets:
        if version in {COURTESY_ROUTING_VERSION, NAMED_THANKS_VERSION} and _complete(turn,rows) and normalize(body)==normalize(f'The next question comes from {name} with {firm}. Please go ahead.'):
            return True
        for prefix in ('', 'Thank you for your question. '):
            for ordinal in ('next', 'final'):
                for opened in ('open', 'now open'):
                    exact = (f'{prefix}Your {ordinal} question comes from the line of '
                             f'{name} from {firm}. Your line is {opened}. Please go ahead.')
                    if normalize(body) == normalize(exact):
                        return True
    return False


def _function(turn):
    return turn.get('indexed_dialogue_function') or {'analyst': 'questioner_turn',
        'management': 'issuer_response_candidate', 'operator': 'moderator'}.get(turn['role'], 'unresolved')


def build(bundle, catalog, version=VERSION):
    if version not in SUPPORTED_VERSIONS:
        raise ValueError("Unsupported Q&A grounding version")
    index = bundle['transcript_index']
    source = index['source']
    turns = {t['id']: t for t in index['turns']}
    exchanges = {e['id']: e for e in index['exchanges']}
    if len(turns) != len(index['turns']) or len(exchanges) != len(index['exchanges']):
        raise ValueError('Q&A grounding needs unique explicit scope IDs')
    by_turn = {tid: [] for tid in turns}
    for p in catalog['passages']:
        if p['scope_id'] not in turns:
            continue
        turn = turns[p['scope_id']]
        if (p['document_id'] != source['document_id'] or p['sha256'] != source['text_sha256']
                or not turn['start'] <= p['start'] < p['end'] <= turn['end']):
            raise ValueError('Q&A passage lies outside its exact source-bound turn')
        by_turn[p['scope_id']].append(p)
    for rows in by_turn.values():
        rows.sort(key=lambda p: (p['start'], p['end'], p['passage_id']))
    targets = []
    if version in HEADER_VERSIONS:
        for tid, turn in turns.items():
            raw = ''.join(p['text'] for p in by_turn[tid]).strip().splitlines()
            if turn['role'] == 'analyst' and len(raw) >= 2 and raw[0] == turn['speaker'] and raw[1].startswith('Analyst, '):
                targets.append((turn['speaker'], raw[1][len('Analyst, '):]))
    membership = {tid: [] for tid in turns}
    for eid, exchange in exchanges.items():
        if not exchange.get('turn_ids') or len(set(exchange['turn_ids'])) != len(exchange['turn_ids']):
            raise ValueError('Q&A exchange has missing or duplicate members')
        for tid in exchange['turn_ids']:
            if tid not in turns:
                raise ValueError('Q&A exchange contains an unknown explicit turn ID')
            membership[tid].append(eid)
    declared = index.get('coverage', {}).get('unassigned_qa_turn_ids', [])
    if (not isinstance(declared, list) or any(not isinstance(tid, str) or tid not in turns for tid in declared)
            or len(set(declared)) != len(declared)):
        raise ValueError('Q&A unassigned coverage has unknown or duplicate turn IDs')
    unassigned_ids = {tid for tid, turn in turns.items() if turn.get('section_kind') == 'qa' and not membership[tid]}
    if set(declared) != unassigned_ids:
        raise ValueError('Q&A unassigned coverage differs from actual turn membership')
    unassigned = []
    for tid in sorted(unassigned_ids, key=lambda t: (turns[t]['start'], t)):
        turn, rows = turns[tid], by_turn[tid]
        courtesy = _greeting(turn, rows, version)
        # Only exact full-turn routing phrases by indexed moderators qualify.
        # This does not discard an unidentified substantive question/response.
        routing = _function(turn) == 'moderator' and bool(re.fullmatch(
            r'(?:we now turn to questions|we will now begin the question[- ]and[- ]answer session|'
            r'please go ahead|your line is open)[.!]?', _body(turn, rows), re.I))
        record = {k: turn.get(k) for k in ('id', 'start', 'end', 'speaker', 'role',
                     'role_review', 'participant_function', 'dialogue_function', 'indexed_dialogue_function')}
        record.update(passage_ids=[p['passage_id'] for p in rows if p['text'].strip()],
                      passage_offsets=[{k: p[k] for k in ('passage_id', 'start', 'end', 'span_sha256')} for p in rows if p['text'].strip()],
                      mechanical_disposition='courtesy_only' if courtesy else 'moderator_routing_only' if routing else 'unresolved')
        unassigned.append(record)
    result = []
    for eid, exchange in exchanges.items():
        tids = sorted(exchange['turn_ids'], key=lambda tid: (turns[tid]['start'], tid))
        records, flags = [], []
        for tid in tids:
            turn, rows = turns[tid], by_turn[tid]
            greeting = _greeting(turn, rows, version, [turns[t] for t in tids])
            record = {k: turn.get(k) for k in ('id', 'start', 'end', 'speaker', 'role', 'section_id', 'section_kind',
                         'role_review', 'participant_function', 'dialogue_function', 'indexed_dialogue_function')}
            record.update(passage_ids=[p['passage_id'] for p in rows if p['text'].strip()],
                          passage_offsets=[{k: p[k] for k in ('passage_id', 'start', 'end', 'span_sha256')} for p in rows if p['text'].strip()],
                          courtesy_only=greeting)
            if version in HEADER_VERSIONS:
                record['routing_only'] = _routing(turn, rows, targets, version)
            records.append(record)
            if len(membership[tid]) != 1:
                flags.append('shared_turn_membership')
            if turn['role'] == 'unknown' and _function(turn) not in KNOWN_FUNCTIONS:
                flags.append('unknown_speaker_role')
            if turn.get('section_kind') != 'qa':
                flags.append('turn_outside_qa_section')
            if greeting and tid in exchange.get('question_turn_ids', []):
                flags.append('courtesy_only_question_turn')
        if not exchange.get('question_turn_ids'):
            flags.append('no_indexed_question')
        if not exchange.get('answer_turn_ids'):
            flags.append('no_indexed_management_response')
        for field, functions in (('question_turn_ids', QUESTION_FUNCTIONS), ('answer_turn_ids', ANSWER_FUNCTIONS)):
            if any(tid not in tids or _function(turns[tid]) not in functions for tid in exchange.get(field, [])):
                flags.append('conflicting_role_membership')
        followup = exchange.get('followup_of')
        if followup and (followup not in exchanges or followup == eid
                        or min(turns[t]['start'] for t in exchanges[followup]['turn_ids']) >= turns[tids[0]]['start']):
            flags.append('invalid_followup_link')
        # An operator/unknown turn between the question and an answer is retained
        # as a possible interruption, never silently promoted to an answer.
        answer_starts = [turns[t]['start'] for t in exchange.get('answer_turn_ids', []) if t in turns]
        if answer_starts and any(_function(turns[t]) in ('moderator', 'unresolved')
                                 and turns[tids[0]]['start'] < turns[t]['start'] < max(answer_starts)
                                 for t in tids):
            flags.append('interrupted_response_boundary')
        identity = {'source': source, 'turns': [{k: r[k] for k in ('start', 'end', 'speaker', 'role', 'participant_function', 'dialogue_function', 'indexed_dialogue_function')} for r in records]}
        result.append({'exchange_id': eid, 'canonical_exchange_id': 'QG' + base.digest(identity)[:20],
                       'turns': records, 'question_turn_ids': sorted(exchange.get('question_turn_ids', [])),
                       'answer_turn_ids': sorted(exchange.get('answer_turn_ids', [])),
                       'followup_of': followup, 'boundary_review': exchange.get('boundary_review', index.get('boundary_review', 'provisional')),
                       'flags': sorted(set(flags)),
                       'mechanical_disposition': 'courtesy_only' if all(r['courtesy_only'] or version in HEADER_VERSIONS and r.get('routing_only') for r in records) else None})
    result.sort(key=lambda e: (e['turns'][0]['start'], e['exchange_id']))
    for e in result:
        e['allowed_continuation_exchange_ids'] = sorted(x['exchange_id'] for x in result
            if x['followup_of'] == e['exchange_id'] and 'invalid_followup_link' not in x['flags'])
    return {'version': version, 'source': copy.deepcopy(source), 'offset_unit': 'unicode_character',
            'annotation_status': index.get('boundary_review', 'provisional'),
            'uncertainty': copy.deepcopy(index.get('uncertainty', [])),
            'unassigned_qa_turn_ids': [t['id'] for t in unassigned],
            'unassigned_qa_turns': unassigned,
            'exchanges': result, 'notice': NOTICE}


def validate_retrieval(out, bundle, catalog):
    grounding = bundle.get('qa_grounding')
    if grounding is None:
        return
    if grounding.get('version') not in SUPPORTED_VERSIONS:
        raise ValueError('Unsupported Q&A grounding version')
    exchanges = {e['exchange_id']: e for e in grounding['exchanges']}
    rows = out.get('exchange_coverage')
    if (not isinstance(rows, list) or len(rows) != len(exchanges)
            or any(not isinstance(row, dict) for row in rows)
            or {row.get('exchange_id') for row in rows} != set(exchanges)):
        raise ValueError('Grounded coverage needs each exact exchange ID once')
    pids = {p['passage_id']: p for p in catalog['passages']}
    for row in rows:
        eid = row['exchange_id']; e = exchanges[eid]
        if any(k not in row for k in FIELDS):
            raise ValueError('Q&A grounding fields missing for ' + eid)
        for field in FIELDS[:3]:
            value = row[field]
            if (not isinstance(value, list) or any(not isinstance(v, str) for v in value)
                    or len(set(value)) != len(value)):
                raise ValueError('Q&A grounding requires unique ID lists: ' + field)
        continuations = row['continuation_exchange_ids']
        if not set(continuations) <= set(e['allowed_continuation_exchange_ids']):
            raise ValueError('Q&A continuation must use an explicit indexed followup link: ' + eid)
        groups = {'question_passage_ids': [e], 'answer_passage_ids': [e] + [exchanges[x] for x in continuations]}
        for field, contexts in groups.items():
            turn_field = 'question_turn_ids' if field == 'question_passage_ids' else 'answer_turn_ids'
            allowed = {pid for context in contexts for turn in context['turns']
                       if turn['id'] in context[turn_field] and not turn['courtesy_only']
                       for pid in turn['passage_ids']}
            for pid in row[field]:
                if pid not in pids or pid not in allowed or not pids[pid]['text'].strip():
                    raise ValueError('Q&A supporting passage is outside the indexed ' + field + ': ' + eid)
        status = row['grounding_status']
        if status not in ('bound', 'unresolved', 'courtesy_only') or not isinstance(row['grounding_notes'], str) or not row['grounding_notes'].strip():
            raise ValueError('Q&A grounding needs explicit status and review notes: ' + eid)
        if status == 'courtesy_only':
            if e['mechanical_disposition'] != 'courtesy_only' or any(row[k] for k in FIELDS[:3]):
                raise ValueError('Courtesy disposition requires only exact courtesy turns and no analytical support: ' + eid)
        # Provisional annotations alone do not discard evidence. Concrete missing
        # roles or ambiguous membership are carried as unresolved to the analyst.
        must_flag = bool(e['flags']) or any(exchanges[x]['flags'] for x in continuations)
        if status == 'bound' and (must_flag or not row['question_passage_ids'] or not row['answer_passage_ids']):
            raise ValueError('Q&A ambiguous/missing support must remain unresolved: ' + eid)
        for linked in continuations:
            linked_pids = {pid for t in exchanges[linked]['turns'] if t['id'] in exchanges[linked]['answer_turn_ids'] for pid in t['passage_ids']}
            if not linked_pids.intersection(row['answer_passage_ids']):
                raise ValueError('Unused Q&A continuation link: ' + eid)


def prompt_contract(role, bundle):
    index = bundle.get('qa_grounding')
    if index is None or role not in ('retrieval', 'analysis', 'review'):
        return ''
    text = '\n\nSOURCE-BOUND Q&A MEMBERSHIP GATE\n' + NOTICE + '\n'
    if role == 'retrieval':
        text += ('For every exchange_coverage row add question_passage_ids and answer_passage_ids '
                 '(exact catalogue IDs), continuation_exchange_ids (normally []), grounding_status '
                 '(bound|unresolved|courtesy_only), and grounding_notes. Join by exact exchange_id and turn IDs; '
                 'never map array positions. Question support must belong to this exchange’s indexed '
                 'question turns. Answer support must belong to its answer turns, or an explicitly '
                 'named allowed_continuation_exchange_id. Adjacent exchanges are not interchangeable. '
                 'Do not cite courtesy-only turns as questions or answers. Missing support or structural '
                 'flags require unresolved and an explanation. Preserve provisional attribution; '
                 'Use courtesy_only only for the index’s exact courtesy-only disposition, with all support lists empty. '
                 'bound means membership only. Select enough passages to support each paraphrase, '
                 'including conditions and deferrals. Code copies text/offsets; do not retype them.\n')
    else:
        text += ('Treat unresolved rows as evidence gaps requiring original-source review; never infer '
                 'a management answer from a coverage paraphrase alone. Provisional roles and '
                 'followup links require semantic verification. Independently compare selected '
                 'question/answer passages with the full turns before using their claims.\n')
    return text + json.dumps(index, ensure_ascii=False, sort_keys=True)


def attach(root, protocol, bundle, catalog):
    """Verify opt-in immutable sidecar and recompute it from original source scopes."""
    if 'qa_grounding' not in protocol:
        return
    if protocol['qa_grounding'] not in SUPPORTED_VERSIONS:
        raise ValueError('Q&A grounding policy differs')
    path = Path(protocol['qa_grounding_path'])
    if root is not None and path.resolve() != (Path(root) / 'qa-grounding.json').resolve():
        raise ValueError('Q&A grounding sidecar path differs')
    if base.sha(path) != protocol['qa_grounding_sha256']:
        raise ValueError('Q&A grounding sidecar changed')
    computed = build(bundle, catalog, version=protocol['qa_grounding'])
    binding=protocol.get('grounding_recovery',{}).get('operator_review')
    if binding:
        from .earnings_reviewed_operator import apply
        computed,_=apply(binding,computed,bundle,catalog)
        bundle['operator_review_binding']=binding
    if computed != base.read(path):
        raise ValueError('Q&A grounding differs from original indexed sources')
    bundle['qa_grounding'] = computed


def require_analysis_ready(out, bundle, catalog):
    """A membership failure or unresolved boundary cannot enter report analysis."""
    validate_retrieval(out, bundle, catalog)
    if bundle.get('qa_grounding') is not None:
        unassigned = [t['id'] for t in bundle['qa_grounding']['unassigned_qa_turns']
                      if t['mechanical_disposition'] == 'unresolved']
        if unassigned:
            raise ValueError('Substantive unassigned Q&A turns require source-index repair before analysis: '
                             + ', '.join(unassigned))
        unresolved = [row['exchange_id'] for row in out['exchange_coverage']
                      if row['grounding_status'] not in ('bound', 'courtesy_only')]
        if unresolved:
            raise ValueError('Q&A grounding unresolved; repair source attribution before analysis: '
                             + ', '.join(unresolved))


def normalize_courtesy(out, bundle, catalog):
    """New-edition derivative only: exact versioned courtesy scopes, no source mutation.

    The full original response remains a separate artifact. This receipt binds
    each replaced row and source offsets; substantive and uncertain rows survive.
    """
    grounding = bundle.get('qa_grounding', {})
    if grounding.get('version') not in HEADER_VERSIONS:
        raise ValueError('Courtesy normalization requires explicit header-aware grounding')
    replayed=build(bundle,catalog,version=grounding['version'])
    if bundle.get('operator_review_binding'):
        from .earnings_reviewed_operator import apply
        replayed,_=apply(bundle['operator_review_binding'],replayed,bundle,catalog)
    if grounding != replayed:
        raise ValueError('Courtesy normalization requires replayable grounding')
    derived = copy.deepcopy(out)
    exchanges = {e['exchange_id']: e for e in grounding['exchanges']}
    rows = derived.get('exchange_coverage')
    if not isinstance(rows, list) or len({r.get('exchange_id') for r in rows}) != len(rows):
        raise ValueError('Courtesy normalization requires unique coverage rows')
    receipt = []
    for row in rows:
        e = exchanges.get(row.get('exchange_id'))
        if e is None:
            raise ValueError('Unknown exchange in courtesy normalization')
        if e['mechanical_disposition'] != 'courtesy_only':
            continue
        before = copy.deepcopy(row)
        row.update(question_passage_ids=[], answer_passage_ids=[], continuation_exchange_ids=[],
                   grounding_status='courtesy_only',
                   grounding_notes='Exact source turns contain courtesy only after mechanical speaker/title header removal; no analytical support.')
        # Coverage prose varies by pipeline generation. Only existing paraphrase
        # fields are replaced; unrelated fields and schemas remain intact.
        for key in ('question', 'answer', 'question_summary', 'answer_summary', 'consequence'):
            if key in row:
                row[key] = 'Courtesy only.'
        receipt.append({'exchange_id': e['exchange_id'], 'before_sha256': base.digest(before),
                        'after_sha256': base.digest(row), 'source': copy.deepcopy(grounding['source']),
                        'turns': copy.deepcopy(e['turns']), 'reason': 'exact_header_aware_courtesy_only'})
    return derived, receipt
