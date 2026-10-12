"""Apply authenticated complete-turn non-Q&A decisions; retain all source text.

Only explicit reviewed courtesy/routing/closing classifications are supported.
Substantive or uncertain decisions stop; no source is deleted or reworded.
"""
import copy
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_role_import as imp


def require(ok, message):
    if not ok: raise ValueError(message)


def apply(binding, grounding, bundle, catalog):
    from .earnings_qa_grounding import _complete
    reservation=r.read(binding['reservation'])
    require(r.sha(binding['reservation'])==binding['reservation_sha256'],'Attribution reservation changed')
    value=imp.authenticate(binding['review']);job=Path(binding['review']['job']);request=r.read(job/'request.json')
    require(request['bindings']==reservation['bindings'] and r.sha(job/'prompt.txt')==reservation['prompt_sha256'],'Attribution review request changed')
    require([request['model'],request['effort']]==['gpt-6.1-sol','medium'],'Independent attribution settings changed')
    expected=reservation['bindings']
    require(r.digest(bundle['transcript_index'])==expected['index_sha256'],'Attribution source index changed')
    require(r.sha(binding['catalog_path'])==expected['catalog_sha256'] and r.read(binding['catalog_path'])==catalog,'Attribution catalog changed')
    require(r.sha(binding['retrieval_output'])==expected['retrieval_sha256'],'Original retrieval changed')
    require(value['session']['id']!=reservation['prior_session'],'Attribution reviewer reused author session')
    verdict=value['content']
    if binding.get('review_field') is not None:
        require(binding['review_field']=='non_qa' and set(verdict)=={'boundary','non_qa'},'Exact combined non-Q&A response required')
        verdict=verdict['non_qa']
    require(set(verdict)=={'exchanges'} and isinstance(verdict['exchanges'],list),'Exact attribution response required')
    extended=expected.get('scope')=='complete-source-disposition-v2'
    decisions=verdict['exchanges'];ids=[d.get('exchange_id') for d in decisions]
    require(len(ids)==len(set(ids)) and set(ids)==set(expected['exchange_ids']),'Every reserved exchange required exactly once')
    result=copy.deepcopy(grounding);groups={e['exchange_id']:e for e in result['exchanges']}
    originals={e['id']:e for e in bundle['transcript_index']['exchanges']};turns={t['id']:t for t in bundle['transcript_index']['turns']}
    for decision in decisions:
        continuing=extended and decision.get('disposition')=='answer_continuation'
        fields={'exchange_id','disposition','turns','question_turn_ids','answer_turn_ids','reason'} | ({'continued_from'} if continuing else set())
        require(set(decision)==fields,'Exact exchange disposition fields required')
        eid=decision['exchange_id'];require(eid in groups and eid in originals,'Unknown reviewed exchange')
        if continuing:
            original=originals[eid];parent=decision['continued_from']
            require(parent==original.get('followup_of') and parent in originals,'Explicit original continuation parent required')
            require(not decision['question_turn_ids'] and decision['answer_turn_ids']==original['answer_turn_ids'] and decision['answer_turn_ids'],'Continued management answer must retain original membership')
            require(groups[eid]['flags']==['courtesy_only_question_turn'] and originals[parent]['question_turn_ids'],'Only courtesy acknowledgment before explicit continued answer is supported')
            require({turns[t]['speaker'] for t in original['question_turn_ids']}=={turns[t]['speaker'] for t in originals[parent]['question_turn_ids']} and all(turns[t]['role']=='analyst' for t in originals[parent]['question_turn_ids']),'Continuation requires the same original analyst')
            require(max(turns[t]['end'] for t in originals[parent]['turn_ids'])<=min(turns[t]['start'] for t in original['turn_ids']),'Continuation scopes must be ordered and disjoint')
        else:
            require(decision['disposition'] in ('courtesy_and_routing_only','boundary_repair_required') and not decision['question_turn_ids'] and not decision['answer_turn_ids'],'Substantive or uncertain attribution cannot be normalized')
        require(isinstance(decision['reason'],str) and decision['reason'].strip(),'Specific boundary reason required')
        rows=decision['turns'];require(isinstance(rows,list) and len(rows)==len(originals[eid]['turn_ids']) and len({t.get('turn_id') for t in rows})==len(rows) and {t.get('turn_id') for t in rows}==set(originals[eid]['turn_ids']),'Complete exchange turn membership required')
        classes=[]
        for row in rows:
            require(set(row)=={'turn_id','classification','passage_ids','reason'},'Exact turn disposition fields required')
            tid=row['turn_id'];original=turns[tid]
            passages=sorted((p for p in catalog['passages'] if p['scope_id']==tid),key=lambda p:p['start'])
            require(_complete(original,passages) and row['passage_ids']==[p['passage_id'] for p in passages if p['text'].strip()],'Complete exact original turn passages required')
            classification=row['classification'];require(classification in ('courtesy','operator_routing','management_closing') or extended and classification in ('analyst_acknowledgment','management_answer_continuation'),'Unknown/substantive turn cannot be normalized')
            require(isinstance(row['reason'],str) and row['reason'].strip(),'Turn evidence reason required')
            if classification=='operator_routing':require(original['role']=='operator','Routing requires indexed operator')
            if classification=='management_closing':require(original['role']=='management','Closing requires indexed management')
            if classification=='analyst_acknowledgment':require(original['role']=='analyst' and not continuing,'Acknowledgment requires indexed analyst outside a continued answer')
            if classification=='management_answer_continuation':require(continuing and tid in decision['answer_turn_ids'] and original['role']=='management','Continued answer requires original management answer')
            if continuing:
                if tid in originals[eid]['question_turn_ids']:
                    from .earnings_qa_grounding import _greeting
                    require(classification=='courtesy' and original['role']=='analyst' and _greeting(original,passages,grounding['version']),'Continued answer requires exact full analyst courtesy')
                else:require(classification=='management_answer_continuation' and tid in decision['answer_turn_ids'],'No intervening or unaccounted continuation turn')
            classes.append(classification)
        require(('management_closing' in classes)==(decision['disposition']=='boundary_repair_required'),'Closing must remain explicitly distinct from courtesy')
        group=groups[eid]
        if continuing:
            group.update(question_turn_ids=[],answer_turn_ids=copy.deepcopy(decision['answer_turn_ids']),flags=[],
                         mechanical_disposition='reviewed_answer_continuation',reviewed_continued_from=decision['continued_from'],
                         reviewed_turn_dispositions=copy.deepcopy(rows),review_reason=decision['reason'])
            continue
        group.update(question_turn_ids=[],answer_turn_ids=[],mechanical_disposition='reviewed_non_qa',
                     boundary_review='authenticated_complete_turn_review',reviewed_non_question_turn_ids=list(originals[eid]['turn_ids']),
                     reviewed_turn_dispositions=copy.deepcopy(rows),review_reason=decision['reason'])
    return result,value
