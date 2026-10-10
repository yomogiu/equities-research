"""Reuse two authenticated preparers after a versioned mechanical grounding fix."""
import copy
import os
from pathlib import Path
import subprocess
import sys
from . import earnings_mixed_runner as r, earnings_role_import as imp


def require(value, message):
    if not value:
        raise ValueError(message)


REPLAY = '''import sys,json
from pathlib import Path
from research import earnings_passage_pipeline as p, earnings_mixed_runner as r
root=Path(sys.argv[1]);protocol,bundle,catalog=p.load(root);artifacts={}
for role in ('financial','retrieval'):
 job=root/'batch-jobs'/role;request=r.read(job/'request.json');result=r.verify_job(job)
 assert request['bindings']=={'protocol_sha256':r.sha(root/'protocol.json'),'role':role,'dependencies_sha256':r.digest(artifacts)}
 assert (request['model'],request['effort'])==p.MODELS[role]
 assert (job/'prompt.txt').read_text()==p.prompt(role,bundle,Path(protocol['writing_standard']).read_text(),artifacts,[],catalog)
 artifacts[role]=result['content']
print(json.dumps({'verified':True}))
'''


def original(seed):
    seed=Path(seed);old=r.read(seed/'protocol.json')
    require(old.get('batch_review')=='batched-report-review-v1' and old.get('qa_grounding')=='source-bound-qa-membership-v2', 'Original v2 batch required')
    require(old.get('max_correction_rounds')==2 and not any('recovery' in k for k in old), 'Original untouched budget required')
    require(not (seed/'batch-review').exists() and not (seed/'result.json').exists(), 'Reviewed work cannot restart')
    require({p.name for p in (seed/'batch-jobs').iterdir()}=={'financial','retrieval'}, 'Exactly two completed preparers required; no later launch allowed')
    code=Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    replay=subprocess.run([sys.executable,'-c',REPLAY,str(seed)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    require(replay.returncode==0,'Original preparation replay failed: '+replay.stderr[-1200:])
    return old,code


def initialize(seed, output, authorization):
    from . import earnings_passage_pipeline as pipe
    seed,output=Path(seed).resolve(),Path(output).resolve()
    require(authorization.strip() and not output.exists(),'New authorized continuation required')
    old,code=original(seed)
    refs={role:imp.reference(seed/'batch-jobs'/role,code) for role in ('financial','retrieval')}
    protocol=copy.deepcopy(old)
    protocol['code']=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol['grounding_recovery']={'seed':str(seed),'protocol_sha256':r.sha(seed/'protocol.json'),'authorization':authorization,'responses':refs,'prior_correction_rounds':0}
    bundle=pipe.evidence.load_bundle(old['evidence_manifest']);catalog=r.read(seed/'passages.json')
    grounding=pipe.grounding.build(bundle,catalog,pipe.grounding.NAMED_GREETING_VERSION)
    output.mkdir(parents=True)
    (output/'passages.json').write_bytes((seed/'passages.json').read_bytes())
    r.save(output/'qa-grounding.json',grounding)
    protocol.update(qa_grounding=pipe.grounding.NAMED_GREETING_VERSION,qa_grounding_path=str(output/'qa-grounding.json'),qa_grounding_sha256=r.sha(output/'qa-grounding.json'))
    r.save(output/'protocol.json',protocol)
    p,b,c=pipe.load(output);validate(p,b,c)
    return protocol


def validate(protocol,bundle,catalog):
    from . import earnings_passage_pipeline as pipe
    recovery=protocol['grounding_recovery'];seed=Path(recovery['seed']);old,code=original(seed)
    require(recovery.get('authorization','').strip() and recovery['prior_correction_rounds']==0,'Recovery authorization/budget differs')
    require(r.sha(seed/'protocol.json')==recovery['protocol_sha256'],'Seed protocol changed')
    ignored={'code','grounding_recovery','qa_grounding','qa_grounding_path','qa_grounding_sha256'}
    require({k:v for k,v in protocol.items() if k not in ignored}=={k:v for k,v in old.items() if k not in ignored},'Recovery changed original settings or evidence')
    require(protocol['qa_grounding']==pipe.grounding.NAMED_GREETING_VERSION,'Recovery requires new grounding version')
    require(set(recovery['responses'])=={'financial','retrieval'},'Both original preparers required')
    results={}
    for role,ref in recovery['responses'].items():
        require(ref['job']==str(seed/'batch-jobs'/role) and ref['code']==str(code),'Original role mapping changed')
        value=imp.authenticate(ref)
        results[role]={'content':value['content'],'receipt':{'session':value['session'],'usage_is_inherited':True}}
        out=value['content']
        if role=='retrieval':out,_=pipe.grounding.normalize_courtesy(out,bundle,catalog)
        pipe.validate(role,out,bundle,catalog)
    require(len({v['receipt']['session']['id'] for v in results.values()})==2,'Distinct preparer sessions required')
    return results
