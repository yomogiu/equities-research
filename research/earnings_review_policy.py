"""Explicit source-preserving larger-context editions; no truncation or round reset."""
from pathlib import Path
from . import earnings_experiment as b
VERSION = 'complete-review-context-500k-v1'
LIMITS = {'context_characters':500000,'prompt_characters':550000}


def read(path, seed, exported):
    if not path or not str(path).strip(): raise ValueError('Explicit context authorization required')
    path=Path(path).resolve();seed=Path(seed).resolve();v=b.read(path)
    expected={'version':VERSION,'seed':str(seed),'seed_protocol_sha256':b.sha(seed/'protocol.json'),
              'model':['gpt-6.1-sol','medium'],'limits':LIMITS,'preserve_source_bytes':True,'preserve_rounds':True,
              'prior_rounds':exported['used_rounds'],'inherited_tokens':exported['spent_tokens'],'token_ceiling':None}
    if set(v)!=set(expected)|{'authorization','token_authorization'} or any(not isinstance(v.get(k),str) or not v[k].strip() for k in ('authorization','token_authorization')):
        raise ValueError('Context authorization schema differs')
    if any(v[k]!=x for k,x in expected.items()):raise ValueError('Context authorization source/accounting differs')
    return {'path':str(path),'sha256':b.sha(path),'version':VERSION,**LIMITS}


def validate_limits(policy):
    if policy is None:return
    if policy.get('version')!=VERSION or any(policy.get(k)!=v for k,v in LIMITS.items()):
        raise ValueError('Unknown review context policy')
