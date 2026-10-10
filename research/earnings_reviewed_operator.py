"""Authenticated disposition of an entire source-bound administrative turn."""
import copy
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_role_import as imp

def apply(binding, grounding, bundle, catalog):
    reservation=r.read(binding['reservation'])
    if r.sha(binding['reservation'])!=binding['reservation_sha256']:raise ValueError('Operator reservation changed')
    value=imp.authenticate(binding['review']);job=Path(binding['review']['job']);request=r.read(job/'request.json')
    if request['bindings']!=reservation['bindings'] or r.sha(job/'prompt.txt')!=reservation['prompt_sha256']:raise ValueError('Operator review request changed')
    if [request['model'],request['effort']]!=['gpt-6.1-sol','medium']:raise ValueError('Operator reviewer settings changed')
    target=reservation['bindings']['target_turn_id']
    if r.digest(bundle['transcript_index'])!=reservation['bindings']['transcript_index_sha256']:raise ValueError('Operator index changed')
    if r.sha(binding['catalog_path'])!=reservation['bindings']['catalog_sha256'] or r.read(binding['catalog_path'])!=catalog:raise ValueError('Operator catalog changed')
    result=copy.deepcopy(grounding);turn=next((x for x in result['unassigned_qa_turns'] if x['id']==target),None)
    if not turn or turn['role']!='operator' or turn['indexed_dialogue_function']!='moderator':raise ValueError('Only indexed unassigned operator turns are eligible')
    decision=value['content'];expected={'turn_id','classification','passage_ids','reason'}
    if set(decision)!=expected or decision['turn_id']!=target or decision['classification']!='administrative_routing_only' or not decision['reason'].strip():raise ValueError('Administrative acceptance required')
    ids=turn['passage_ids']
    if decision['passage_ids']!=ids or reservation['target_passage_ids']!=ids:raise ValueError('Complete original turn evidence required')
    original=next(x for x in bundle['transcript_index']['turns'] if x['id']==target)
    rows=sorted((x for x in catalog['passages'] if x['scope_id']==target),key=lambda x:x['start'])
    from .earnings_qa_grounding import _complete
    if not _complete(original,rows):raise ValueError('Complete original span required')
    turn['mechanical_disposition']='moderator_routing_only'
    return result,value
