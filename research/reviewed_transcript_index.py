"""Apply independently reviewed, source-bound transcript annotations in memory.

The caller supplies a trusted, externally reserved authorization; an untrusted
proposal or reviewer output cannot authorize itself. This module neither reads
artifact paths nor writes sources, catalog identity, qualification or eligibility.
Occupation and dialogue function are separate. Application does not certify the
whole generated index, answer quality, source completeness or report readiness.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import transcript_evidence as transcript

VERSION = 'reviewed-transcript-sidecar-v1'
QUESTIONERS = {'investor_questioner', 'private_investor_questioner',
               'external_research_questioner'}
PARTICIPANTS = QUESTIONERS | {'issuer_representative', 'external_investor_relations_host',
                             'submitted_question_moderator', 'unresolved'}
FUNCTIONS = {'submitted_question', 'live_question', 'submitted_question_topic_transition',
             'answer_to_submitted_topic', 'answer_to_submitted_question', 'issuer_answer',
             'live_analyst_transition', 'moderator', 'greeting', 'closing'}


def _sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def _json(raw):
    if not isinstance(raw, bytes):
        raise ValueError('Artifact bytes required for exact digest verification')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    result = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError('JSON object required')
    return result


def _span(text, value):
    span = transcript._span(text, value['start'], value['end'])
    expected = value.get('text', value.get('quote'))
    if expected is not None and expected != span['text']:
        raise ValueError('Evidence span differs from original source')
    if 'text_sha256' in value and value['text_sha256'] != _sha(span['text']):
        raise ValueError('Turn hash differs from original source')
    return span


def _validate_evidence(text, value):
    """Check embedded exact spans including name evidence and quoted handoffs."""
    if isinstance(value, dict):
        if 'start' in value and 'end' in value:
            _span(text, value)
        for child in value.values():
            _validate_evidence(text, child)
    elif isinstance(value, list):
        for child in value:
            _validate_evidence(text, child)


def _receipt(proposal, review, authorization, proposal_hash):
    author, reviewer = authorization.get('author_id'), authorization.get('reviewer_id')
    if not author or not reviewer or author == reviewer:
        raise ValueError('Distinct authorized author and reviewer required')
    if proposal.get('author_session', author) != author:
        raise ValueError('Proposal author differs from authorization')
    if review.get('reviewer_session', review.get('reviewer')) != reviewer:
        raise ValueError('Reviewer differs from authorization')
    if review.get('author', author) != author:
        raise ValueError('Receipt author differs from authorization')
    revised = 'companies' in review
    if revised and review.get('status') != 'pass_sidecar_only':
        raise ValueError('Revised sidecar review has not passed')
    rows = review.get('companies' if revised else 'decisions', [])
    matches = [r for r in rows if r.get('symbol') == proposal.get('symbol')]
    if len(matches) != 1:
        raise ValueError('Exactly one matching review decision required')
    row = matches[0]
    if row.get('artifact_sha256' if revised else 'proposal_sha256') != proposal_hash:
        raise ValueError('Review is for different proposal bytes')
    if row.get('status' if revised else 'verdict') not in {'pass', 'pass_with_holds'}:
        raise ValueError('Sidecar review has not passed')
    for key in ('document_id', 'raw_sha256', 'text_sha256'):
        if key in row and row[key] != authorization[key]:
            raise ValueError('Review source binding mismatch')
    if not revised and row.get('qa_decision') != 'pass':
        raise ValueError('Q&A boundary proposal was not approved')
    if row.get('dialogue_function_decision', 'pass') not in {'pass', 'not_proposed'}:
        raise ValueError('Dialogue functions were not approved')
    decisions = row.get('speaker_decisions', [])
    if len({x['source_speaker'] for x in decisions}) != len(decisions):
        raise ValueError('Duplicate speaker review decision')
    if not revised and {x['source_speaker'] for x in decisions} != {x['source_speaker'] for x in proposal.get('speaker_proposals', [])}:
        raise ValueError('Exact speaker review decisions required')
    return row, {x['source_speaker']: x for x in decisions}


def apply_reviewed_sidecar(text, raw, source, proposal_bytes, review_bytes, authorization):
    """Return a new index; original bytes/inputs are never mutated.

    authorization binds issuer_id, document_id, raw_sha256, text_sha256,
    proposal_sha256, review_sha256, author_id, reviewer_id, proposal_path,
    review_path. Paths are inert private references. Source issuer_names must be
    supplied by the caller's verified catalog, as for the ordinary parser.
    Native source-mapping draft and review formats are accepted. Their original
    exact bytes are preserved in the returned digest bindings. A new or changed
    annotation requires a new authorization and independent receipt.
    """
    if not isinstance(text, str) or not isinstance(raw, bytes):
        raise ValueError('Original Unicode text and raw bytes required')
    for key, actual in [('raw_sha256', _sha(raw)), ('text_sha256', _sha(text))]:
        if source.get(key) != actual or authorization.get(key) != actual:
            raise ValueError('Original source hash mismatch')
    for key in ('issuer_id', 'document_id'):
        if not source.get(key) or source[key] != authorization.get(key):
            raise ValueError('Authorized source identity mismatch')
    for key in ('proposal_path', 'review_path'):
        if not isinstance(authorization.get(key), str) or not authorization[key].strip():
            raise ValueError('Bound artifact reference required')
    for key, raw_artifact in [('proposal_sha256', proposal_bytes), ('review_sha256', review_bytes)]:
        if not isinstance(raw_artifact, bytes) or _sha(raw_artifact) != authorization.get(key):
            raise ValueError('Authorized artifact digest mismatch')
    proposal, review = _json(proposal_bytes), _json(review_bytes)
    nested = proposal.get('source', proposal)
    if proposal.get('issuer_id') != source['issuer_id'] or proposal.get('document_id') != source['document_id']:
        raise ValueError('Proposal issuer/document mismatch')
    for key in ('raw_sha256', 'text_sha256'):
        if nested.get(key) != source[key]:
            raise ValueError('Proposal source hashes mismatch')
    if nested.get('catalog_document_id', source['document_id']) != source['document_id']:
        raise ValueError('Proposal catalog document mismatch')
    row, speaker_reviews = _receipt(proposal, review, authorization, _sha(proposal_bytes))
    _validate_evidence(text, proposal)
    evidence = {e['id']: e for e in proposal.get('evidence', []) if 'id' in e}
    if len(evidence) != len([e for e in proposal.get('evidence', []) if 'id' in e]):
        raise ValueError('Duplicate evidence ID')

    def supporting(value):
        ids = value.get('evidence_ids', []) + ([value['evidence_id']] if 'evidence_id' in value else [])
        if any(eid not in evidence for eid in ids):
            raise ValueError('Unknown supporting evidence ID')
        if not ids and not value.get('evidence'):
            raise ValueError('Source evidence required for annotation')

    result = transcript.index_publisher_transcript(text, source, raw)
    if 'call_span' not in result:
        raise ValueError('Exact publisher call blocks required for this adapter')
    turns = result['turns']
    lookup = {(t['start'], t['end']): t for t in turns}
    if len(lookup) != len(turns):
        raise ValueError('Duplicate source turns')
    for t in turns:
        t['text_sha256'] = _sha(text[t['start']:t['end']])
        t['role_review'] = 'provisional'
        t['participant_function'] = None
        t['dialogue_function'] = None

    def target(value, speaker):
        _span(text, value)
        t = lookup.get((value['start'], value['end']))
        if not t or t['speaker'] != speaker or value.get('speaker', speaker) != speaker:
            raise ValueError('Annotation does not match an original speaker turn')
        return t

    seen = set()
    for item in proposal.get('speaker_proposals', []):
        name, role = item['source_speaker'], item['proposed_role']
        if name in seen or role not in transcript.ROLES:
            raise ValueError('Duplicate speaker or invalid occupation role')
        seen.add(name)
        supporting(item)
        decision = speaker_reviews.get(name)
        if speaker_reviews and (not decision or decision.get('verdict') != 'pass' or
                                decision.get('required_role', decision.get('proposed_role')) != role):
            raise ValueError('Speaker role was not approved')
        function = item.get('participant_function', (decision or {}).get('participant_function'))
        if function is not None and function not in PARTICIPANTS:
            raise ValueError('Unsupported participant function')
        if decision and item.get('participant_function') and decision.get('participant_function') != function:
            raise ValueError('Participant function differs from review')
        if not item.get('turns'):
            raise ValueError('Speaker mapping requires exact turns')
        spans = set()
        for annotated in item['turns']:
            t = target(annotated, name)
            pair = (t['start'], t['end'])
            if pair in spans:
                raise ValueError('Duplicate annotated turn')
            spans.add(pair)
            t.update(role=role, role_review='reviewed_sidecar', participant_function=function)

    annotated_functions = set()
    for item in proposal.get('dialogue_function_proposals', []):
        supporting(item)
        name = item['source_speaker']
        if 'turns' in item:
            function = item.get('participant_function')
            if function not in QUESTIONERS:
                raise ValueError('Unsupported participant-side mapping')
            for annotated in item['turns']:
                t = target(annotated, name)
                key = (t['start'], 'participant')
                if key in annotated_functions:
                    raise ValueError('Duplicate participant function mapping')
                annotated_functions.add(key)
                if t['participant_function'] not in (None, function):
                    raise ValueError('Conflicting participant function')
                if item.get('occupational_role', t['role']) != t['role']:
                    raise ValueError('Dialogue function cannot promote occupation')
                t['participant_function'] = function
        else:
            t = target(item, name)
            function = item.get('dialogue_function')
            if function not in FUNCTIONS or (t['start'], 'dialogue') in annotated_functions:
                raise ValueError('Unsupported or duplicate dialogue function')
            annotated_functions.add((t['start'], 'dialogue'))
            if function.startswith('answer_') or function == 'issuer_answer':
                if t['role'] != 'management' and t['participant_function'] != 'issuer_representative':
                    raise ValueError('Answer function requires supported issuer attribution')
            t['dialogue_function'] = function

    qa = proposal['qa_proposal']
    supporting(qa)
    start = qa.get('proposed_qa_section_start', qa.get('transition_start'))
    end = qa.get('qa_end', result['call_span']['end'])
    transcript._span(text, start, end)
    if not result['call_span']['start'] <= start < end <= result['call_span']['end']:
        raise ValueError('Q&A boundary outside archived call')
    if start not in {t['start'] for t in turns} or end not in {t['end'] for t in turns}:
        raise ValueError('Q&A boundary must preserve exact whole turns')
    first_question = qa.get('first_substantive_question_turn_start')
    if first_question not in {t['start'] for t in turns if start <= t['start'] < end}:
        raise ValueError('First substantive question is not a Q&A turn')
    sections = []
    for a, b, kind in [(result['call_span']['start'], start, 'prepared_remarks'),
                       (start, end, 'qa'), (end, result['call_span']['end'], 'other')]:
        if a < b:
            sections.append({'start': a, 'end': b, 'kind': kind,
                             'id': transcript._id('section', [source['text_sha256'], a, b, kind])})
    result['sections'] = sections
    for t in turns:
        section = next((s for s in sections if s['start'] <= t['start'] and t['end'] <= s['end']), None)
        if section is None:
            raise ValueError('Section boundary splits source turn')
        t.update(section_id=section['id'], section_kind=section['kind'])
        # New identities bind the applied sidecar rather than overwriting old IDs.
        t['id'] = transcript._id('turn', [VERSION, source['text_sha256'], authorization['proposal_sha256'],
                                          t['start'], t['end'], t['speaker'], t['role']])
    _exchanges(result, first_question)
    result['boundary_review'] = 'partially_reviewed'
    result['needs_review'] = True  # Receipt covers annotations, not entire generated coverage.
    result['reviewed_sidecar'] = {
        'schema_version': VERSION,
        'proposal': {'path': authorization['proposal_path'], 'sha256': authorization['proposal_sha256']},
        'review': {'path': authorization['review_path'], 'sha256': authorization['review_sha256']},
        'author_id': authorization['author_id'], 'reviewer_id': authorization['reviewer_id'],
        'source': {k: source[k] for k in ('issuer_id', 'document_id', 'raw_sha256', 'text_sha256')},
        'first_substantive_question_turn_start': first_question,
        'retained_holds': copy.deepcopy(proposal.get('holds', []) + proposal.get('retained_holds', []) + row.get('retained_holds', [])),
        'review_conditions': copy.deepcopy(review.get('conditions', [])),
        'coverage_review': 'required',
        'qualification_and_eligibility': 'not_assessed_or_changed',
    }
    result['uncertainty'] = ['Reviewed annotations applied; generated exchange coverage still requires review.',
                             'Unknown occupation is distinct from unresolved dialogue function.',
                             'Source qualification, identity, freshness and completeness are not assessed here.']
    return result


def _exchanges(index, first_question):
    exchanges, ledger, unresolved, unassigned = [], [], [], []
    current = None
    for t in index['turns']:
        if t['section_kind'] != 'qa':
            current = None
            continue
        explicit = t['dialogue_function']
        participant = t['participant_function']
        if explicit in {'submitted_question', 'live_question', 'submitted_question_topic_transition'}:
            function = explicit
        elif explicit:
            function = explicit
        elif participant in QUESTIONERS or t['role'] == 'analyst':
            function = 'questioner_turn'  # Includes greetings; does not claim each is a question.
        elif t['role'] == 'operator' or participant in {'external_investor_relations_host', 'submitted_question_moderator'}:
            function = 'moderator'
        elif t['role'] == 'management' or participant == 'issuer_representative':
            function = 'issuer_response_candidate' if current else 'issuer_handoff'
        else:
            function = 'unresolved'
        t['indexed_dialogue_function'] = function
        ledger.append({'turn_id': t['id'], 'start': t['start'], 'end': t['end'],
                       'speaker': t['speaker'], 'occupational_role': t['role'],
                       'dialogue_function': function, 'text_sha256': t['text_sha256']})
        question = function in {'questioner_turn', 'submitted_question', 'live_question', 'submitted_question_topic_transition'}
        if question:
            if not (current and not current['answer_turn_ids'] and current['questioner'] == t['speaker']
                    and function == 'questioner_turn'):
                previous = current
                current = {'id': transcript._id('exchange', [VERSION, t['id']]),
                           'questioner': t['speaker'], 'questioner_occupation': t['role'],
                           'question_turn_ids': [], 'answer_turn_ids': [], 'operator_turn_ids': [],
                           'unknown_turn_ids': [], 'turn_ids': [],
                           'followup_of': previous['id'] if previous and previous['questioner'] == t['speaker'] else None,
                           'question_kind': 'submitted_topic' if function == 'submitted_question_topic_transition' else 'questioner_dialogue',
                           'boundary_review': 'partially_reviewed'}
                exchanges.append(current)
            key = 'question_turn_ids'
        elif function in {'answer_to_submitted_topic', 'answer_to_submitted_question', 'issuer_answer', 'issuer_response_candidate'}:
            key = 'answer_turn_ids'
        elif function == 'unresolved':
            unresolved.append(t['id'])
            key = 'unknown_turn_ids'
        else:
            key = 'operator_turn_ids'
        if current:
            current[key].append(t['id'])
            current['turn_ids'].append(t['id'])
        else:
            unassigned.append(t['id'])
    first = next(t for t in index['turns'] if t['start'] == first_question)
    if not any(first['id'] in e['question_turn_ids'] for e in exchanges):
        raise ValueError('Reviewed first substantive question lacks questioner function')
    for e in exchanges:
        e['status'] = 'response_identified' if e['answer_turn_ids'] else 'no_identified_answer'
    index['exchanges'] = exchanges
    index['coverage']['unassigned_qa_turn_ids'] = unassigned
    index['coverage']['qa_turn_ledger'] = ledger
    index['coverage']['unresolved_qa_turn_ids'] = unresolved
    index['coverage']['mapping_blockers'] = (['unresolved_qa_dialogue'] if unresolved else []) + (
        ['no_answered_exchange'] if not any(e['answer_turn_ids'] for e in exchanges) else [])
