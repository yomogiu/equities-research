"""Replay independently reviewed attribution changes into a new bundle only.

This changes source indexing, never the source, original speaker identities or a
model response. Report/coverage acceptance is a separate reviewed artifact.
"""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from research import earnings_experiment as base
from research import earnings_qa_grounding as qa

VERSION = 'reviewed-source-attribution-overlay-v1'
DISPOSITION = 'non_substantive_courtesy_routing_or_closing'


def apply(bundle, catalog, proposal_path, review_path):
    proposal_path, review_path = Path(proposal_path), Path(review_path)
    proposal, review = base.read(proposal_path), base.read(review_path)
    if review.get('proposal') != {'path': str(proposal_path), 'sha256': base.sha(proposal_path)}:
        raise ValueError('Attribution review is not bound to proposal')
    if review.get('decision') != 'pass_for_new_attribution_sidecar' or not review.get('reviewer'):
        raise ValueError('Independent attribution review required')
    source = review['source']; source_path = Path(source['path'])
    if base.sha(source_path) != source['sha256']:
        raise ValueError('Attribution source changed')
    original = bundle['transcript_index']; text = source_path.read_text(encoding='utf-8')
    if (original['source']['document_id'] != source['document_id'] or
            original['source']['text_sha256'] != source['sha256']):
        raise ValueError('Attribution source differs from frozen index')
    derived = copy.deepcopy(bundle); index = derived['transcript_index']
    turns = {t['id']: t for t in index['turns']}; exchanges = {e['id']: e for e in index['exchanges']}
    proposals = {r['exchange_id']: r for r in proposal['rows']}
    decisions = review['decisions']; seen = set(); changes = []
    for decision in decisions:
        eid = decision['exchange_id']
        if eid in seen or eid not in exchanges or eid not in proposals or decision.get('decision') != 'pass':
            raise ValueError('Unknown, duplicate or unapproved attribution exchange')
        seen.add(eid); exchange = exchanges[eid]; spans = decision['source_spans']
        if {s['turn_id'] for s in spans} != set(exchange['turn_ids']) or len(spans) != len(exchange['turn_ids']):
            raise ValueError('Attribution review must cover every original member')
        for span in spans:
            turn = turns[span['turn_id']]; chunk = text[span['start']:span['end']]
            if ((span['start'],span['end']) != (turn['start'],turn['end']) or chunk != span['text'] or
                    hashlib.sha256(chunk.encode()).hexdigest() != span['span_sha256']):
                raise ValueError('Attribution evidence span mismatch')
        approved_changes = decision.get('proposed_reviewed_turn_changes', {})
        if approved_changes != proposals[eid].get('proposed_reviewed_turn_changes', {}):
            raise ValueError('Attribution turn changes differ from reviewed proposal')
        for tid, fields in approved_changes.items():
            if tid not in exchange['turn_ids'] or set(fields) - {'role','indexed_dialogue_function'}:
                raise ValueError('Unapproved attribution change target')
            if fields.get('role') not in ('management','analyst','unknown') or fields.get('indexed_dialogue_function') not in qa.KNOWN_FUNCTIONS:
                raise ValueError('Invalid reviewed attribution function')
            turns[tid].update(fields)
            turns[tid]['attribution_review_sha256'] = base.sha(review_path)
        groups = decision.get('approved_question_answer_membership', [])
        if groups:
            questions = [t for g in groups for t in g['question_turn_ids']]
            answers = [t for g in groups for t in g['answer_turn_ids']]
            residual = decision.get('non_question_turns', [])
            if (not questions or not answers or len(set(questions + answers + residual)) != len(questions + answers + residual)
                    or set(questions + answers + residual) != set(exchange['turn_ids'])):
                raise ValueError('Reviewed membership must account for original turns exactly once')
            if any(qa._function(turns[t]) not in qa.QUESTION_FUNCTIONS for t in questions) or any(qa._function(turns[t]) not in qa.ANSWER_FUNCTIONS for t in answers):
                raise ValueError('Reviewed membership conflicts with source dialogue function')
            exchange.update(question_turn_ids=questions, answer_turn_ids=answers,
                            reviewed_question_answer_groups=copy.deepcopy(groups), reviewed_non_question_turn_ids=residual,
                            boundary_review='independently_reviewed_source_attribution')
        elif decision.get('approved_disposition') != DISPOSITION:
            raise ValueError('Review lacks explicit membership or non-substantive disposition')
        changes.append(copy.deepcopy(decision))
    grounding = qa.build(derived, catalog, version=qa.HEADER_VERSION)
    grounded = {e['exchange_id']: e for e in grounding['exchanges']}
    for decision in changes:
        e = grounded[decision['exchange_id']]
        e['attribution_review_sha256'] = base.sha(review_path)
        e['pre_overlay_flags'] = e['flags'][:]
        if decision.get('approved_disposition') == DISPOSITION:
            e['reviewed_disposition'] = DISPOSITION
            e['mechanical_disposition'] = 'courtesy_only'
        else:
            e['reviewed_question_answer_groups'] = copy.deepcopy(decision['approved_question_answer_membership'])
            e['reviewed_non_question_turn_ids'] = copy.deepcopy(decision.get('non_question_turns', []))
            # Only reviewed source-bound interruption/identity ambiguity is
            # discharged. Invalid links/shared turns/out-of-Q&A stay blockers.
            e['flags'] = [f for f in e['flags'] if f not in {'unknown_speaker_role','interrupted_response_boundary','courtesy_only_question_turn','no_indexed_question','no_indexed_management_response','conflicting_role_membership'}]
    derived['qa_grounding'] = grounding
    receipt = dict(version=VERSION, proposal={'path':str(proposal_path),'sha256':base.sha(proposal_path)},
                   review={'path':str(review_path),'sha256':base.sha(review_path)},source=source,
                   original_index_sha256=base.digest(original),derived_index_sha256=base.digest(index),
                   grounding_sha256=base.digest(grounding),changes=changes,
                   boundary='Source attribution only. Coverage prose and report need separate independent review.')
    return derived, receipt


def normalize_non_substantive(out, bundle, receipt):
    """Discard no business content: only explicit reviewed complete dispositions."""
    if receipt.get('grounding_sha256') != base.digest(bundle['qa_grounding']):
        raise ValueError('Attribution grounding binding changed')
    derived = copy.deepcopy(out); allowed = {r['exchange_id'] for r in receipt['changes'] if r.get('approved_disposition') == DISPOSITION}
    changes=[]
    for row in derived['exchange_coverage']:
        if row['exchange_id'] not in allowed:
            continue
        before=base.digest(row)
        row.update(question='Courtesy, routing or closing only.',answer='No business answer required.',
                   consequence='No analytical claim.',question_passage_ids=[],answer_passage_ids=[],
                   continuation_exchange_ids=[],grounding_status='courtesy_only',
                   grounding_notes='Independent source attribution review approved the complete non-substantive group.')
        changes.append(dict(exchange_id=row['exchange_id'],before_sha256=before,after_sha256=base.digest(row)))
    return derived, changes
