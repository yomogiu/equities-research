"""Explicit new edition for an observed, empty correction-proposer server error."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from . import earnings_mixed_runner as r, earnings_role_import as imp
from . import earnings_provider_recovery as provider

VERSION = 'correction-proposer-server-error-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


ORIGINAL = '''
import json,sys
from pathlib import Path
from research import earnings_corrections as c
root=Path(sys.argv[1]);p,b,k,w=c.load(root);state=c.base.read(root/'initial.json')
kwargs={'financial_context_version':p['financial_context_version']} if p.get('financial_context_version') else {}
text=c.prompt('propose',state,b,k,w,**kwargs)
print(json.dumps({'initial':state,'prompt':text}))
'''


def original(seed):
    seed = Path(seed).resolve()
    require(not any(x.is_symlink() for x in seed.rglob('*')), 'Correction seed symlinks forbidden')
    p = r.read(seed/'protocol.json')
    require(p['version']=='deterministic-corrections-v1' and not p.get('imported_proposal')
            and not p.get('new_experiment') and not any(p.get(k) for k in
            ('correction_provider_recovery','evidence_resume','review_context_policy','regression_findings','passage_resolution')),
            'Only an original unapplied correction proposal is supported')
    require(not (seed/'result.json').exists(), 'Terminal correction result cannot be retried')
    require(type(p['max_rounds']) is int and type(p['prior_rounds']) is int
            and p['max_rounds']>=1 and 0<=p['prior_rounds'] and p['max_rounds']+p['prior_rounds']<=2,
            'Original correction round accounting is invalid')
    require(type(p['inherited_tokens']) is int and p['inherited_tokens']>=0, 'Original usage invalid')
    for rec in p['code']+p.get('source_code',[]):
        require(r.sha(rec['path'])==rec['sha256'], 'Original code changed')
    code=Path(next(rec['path'] for rec in p['code'] if rec['path'].endswith('/earnings_corrections.py'))).parent.parent
    require([str(x.relative_to(seed)) for x in seed.rglob('request.json')]==['rounds/0/propose/request.json'],
            'Only one failed first proposer request is supported')
    result=subprocess.run([sys.executable,'-B','-c',ORIGINAL,str(seed)],cwd=code,
                          env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},
                          check=True,capture_output=True,text=True)
    exported=json.loads(result.stdout);job=seed/'rounds/0/propose'
    receipt=provider.inspect_failure(job,code,error_code='server_error')
    q=r.read(job/'request.json')
    from .earnings_corrections import MODEL
    require((q.get('model'),q.get('effort'))==tuple(p['model'])==MODEL,
            'Failed proposer model or effort differs from frozen correction settings')
    require(q['bindings']=={'protocol_sha256':r.sha(seed/'protocol.json'),
                           'snapshot_sha256':r.digest(exported['initial']),'round':0,'role':'propose'},
            'Failed proposal snapshot binding differs')
    require(exported['prompt']==(job/'prompt.txt').read_text(), 'Original proposer prompt does not reproduce')
    return p,code,exported,receipt


def expected(seed, authorization, code_records):
    old,code,exported,receipt=original(seed)
    require(isinstance(authorization,dict) and set(authorization)=={'version','enabled','source_protocol_sha256','token_policy','authorized_by','reason'}
            and authorization['version']==VERSION and authorization['enabled'] is True
            and authorization['source_protocol_sha256']==r.sha(seed/'protocol.json')
            and authorization['token_policy'] in ('preserve','uncapped')
            and all(isinstance(authorization[x],str) and authorization[x].strip() for x in ('authorized_by','reason')),
            'Explicit exact failed-attempt authority required')
    protocol=copy.deepcopy(old);protocol['code']=code_records
    protocol['source_code']=old.get('source_code',[])+old['code']
    protocol['source_bindings']={**old['source_bindings'],**{str(seed/name):digest for name,digest in imp.inventory(seed).items()}}
    protocol['max_tokens']=None if authorization['token_policy']=='uncapped' else old['max_tokens']
    protocol['correction_provider_recovery']={'version':VERSION,'seed':str(seed),
        'authorization':authorization,'failed_receipt':receipt,'failed_attempt':1,'new_attempt':2,
        'usage_uncertainty':'Recorded zero-token provider failure is not proof of zero provider computation or billing.',
        'original_protocol_sha256':r.sha(seed/'protocol.json')}
    return protocol,exported


def initialize(seed, output, authorization):
    seed,output=Path(seed).resolve(),Path(output).resolve()
    require(not output.exists() and output!=seed and not output.is_relative_to(seed)
            and not output.is_relative_to(Path(__file__).resolve().parents[1]), 'New private sibling edition required')
    code=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol,exported=expected(seed,authorization,code)
    output.mkdir(parents=True);r.save(output/'protocol.json',protocol);r.save(output/'initial.json',exported['initial'])
    return {'status':'pending','prior_rounds':protocol['prior_rounds'],'remaining_rounds':protocol['max_rounds'],
            'inherited_tokens':protocol['inherited_tokens'],'failed_attempt_retained':True}


def validate(protocol, initial):
    ref=protocol['correction_provider_recovery'];seed=Path(ref['seed'])
    wanted,exported=expected(seed,ref['authorization'],protocol['code'])
    require(protocol==wanted and initial==exported['initial'], 'Correction failure edition accounting or source differs')


def proposer_prompt(protocol, round_no):
    ref=protocol.get('correction_provider_recovery')
    if not ref or round_no!=0:
        return None
    return (Path(ref['seed'])/'rounds/0/propose/prompt.txt').read_text()
