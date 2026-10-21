"""Plan an explicit successor's removal of unresolvable, ID-only quote rows.

Never edits source output, invents a replacement ID or accepts a report. The
caller must authenticate the original job, replay coverage and independently
review the successor under the original lifecycle accounting.
"""
import copy
import json

def prune(value, catalog):
    out=copy.deepcopy(value)
    valid={p['passage_id'] for p in catalog['passages']}
    quotes=out.get('quotes')
    if not isinstance(quotes,list):
        raise ValueError('Quote list required')
    removed=[];kept=[]
    remainder=copy.deepcopy(out);remainder.pop('quotes')
    for i,row in enumerate(quotes):
        if row.get('passage_id') in valid:
            kept.append(row);continue
        if set(row)!={'passage_id'} or not isinstance(row['passage_id'],str):
            raise ValueError('Only unresolved ID-only quote rows supported')
        if row['passage_id'] in json.dumps(remainder):
            raise ValueError('Unknown ID also supports another claim')
        removed.append({'index':i,'original_row':copy.deepcopy(row)})
    if not removed:
        raise ValueError('No orphan quote rows')
    if not 4<=len(kept)<=18 or len({x['passage_id'] for x in kept})!=len(kept):
        raise ValueError('Remaining exact quote selection violates original bounds')
    out['quotes']=kept
    return out,removed
