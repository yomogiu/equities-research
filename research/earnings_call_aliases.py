"""Short exact citation addresses, derived from the frozen call index."""
from copy import deepcopy


def aliases(bundle):
    index=bundle.get('transcript_index',{})
    return {**{'CALL'+str(i):v['id'] for i,v in enumerate(index.get('turns',[]),1)},
            **{'QA'+str(i):v['id'] for i,v in enumerate(index.get('exchanges',[]),1)}}


def project(payload,bundle):
    reverse={value:key for key,value in aliases(bundle).items()}
    def visit(value):
        if isinstance(value,str):return reverse.get(value,value)
        if isinstance(value,list):return [visit(v) for v in value]
        if isinstance(value,dict):return {k:visit(v) for k,v in value.items()}
        return value
    return visit(deepcopy(payload))
