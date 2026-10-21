"""Resolve a dangling paragraph address only from one exact indexed turn.

No prefix or textual similarity matching. Coverage must still be replayed by the
original verifier; this function only proposes an explicit successor's addresses.
"""
import copy

def repair(value,catalog,index):
    out=copy.deepcopy(value);known={p['passage_id'] for p in catalog['passages']}
    exchanges={e['id']:e for e in index['exchanges']};mapping={};audit=[]
    for row in out['exchange_coverage']:
        e=exchanges[row['exchange_id']]
        for field,turn_field in [('question_passage_ids','question_turn_ids'),('answer_passage_ids','answer_turn_ids')]:
            for i,address in enumerate(row.get(field,[])):
                if address in known:continue
                ids={p['passage_id'] for p in catalog['passages'] if p['scope_id'] in e[turn_field]}
                if len(ids)!=1 or len(row[field])!=1:
                    raise ValueError('Exactly one indexed original paragraph required')
                target=next(iter(ids))
                if address in mapping and mapping[address]!=target:
                    raise ValueError('Ambiguous original address relation')
                mapping[address]=target;row[field][i]=target
                audit.append({'exchange_id':e['id'],'field':field,'before':address,'after':target,'original_turn_ids':e[turn_field]})
    if not mapping:raise ValueError('No structurally resolvable address defect')
    for quote in out.get('quotes',[]):
        if quote.get('passage_id') in mapping:
            if set(quote)!={'passage_id'}:raise ValueError('Quote prose cannot be reinterpreted')
            quote['passage_id']=mapping[quote['passage_id']]
    # No unknown address outside the explicitly resolved typed fields may remain.
    def scan(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k=='passage_id' and x not in known:raise ValueError('Unresolved quote address')
                if k.endswith('passage_ids') and any(a not in known for a in x):raise ValueError('Unresolved evidence address')
                scan(x)
        elif isinstance(v,list):
            for x in v:scan(x)
    scan(out)
    return out,audit
