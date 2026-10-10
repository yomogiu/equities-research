"""Adopt an authenticated exact-prompt review after proven pre-model failure.

No model calls, old-file writes, budget resets, or inferred review acceptance.
The original pinned validator adjudicates the original candidate and new receipt.
"""
import json, os, subprocess, sys
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_remediation as rem, earnings_signals as signals
VERSION='completed-review-recovery-v1'
def require(v,m):
    if not v:raise ValueError(m)

PROGRAM=r'''
import json,sys
from pathlib import Path
from research import earnings_mixed_runner as r
seed=Path(sys.argv[1]);job=Path(sys.argv[2]);p=r.read(seed/'protocol.json');response=r.verify_job(job);review=response['content'];tokens=response['receipt']['session']['usage']['totalTokens'];sid=response['receipt']['session']['id']
if p['version']=='signal-label-repair-v1':
 from research import earnings_signal_label_repair as m
 p,state,pack,b,k,w=m.load(seed);text=m.signals.prompt('review',state,b,k,w,pack)
 failed=seed/'jobs/review'
 bindings={'protocol_sha256':r.sha(seed/'protocol.json'),'signals_sha256':r.digest(pack),'report_sha256':m.signals.report_digest(state),'role':'signal_label_review','review_attempt':2}
 if not m.signals.validate_review(review,pack,state,b,k):raise ValueError('Signals did not pass')
 report_seed=r.read(Path(p['seed'])/'protocol.json')['seed'];kind='signals';history={'historical_signal_tokens':p['historical_signal_tokens']}
else:
 from research import earnings_remediation as m
 p,b,k,w=m.load(seed)
 if p['max_review_attempts']!=1:raise ValueError('Only single outstanding review supported')
 folder=seed/'attempts/0';state=r.read(seed/'initial.json');plan=r.read(folder/'plan.json');candidate=m.apply(state,plan,b,k)
 if r.read(folder/'before.json')!=state or r.read(folder/'candidate.json')!=candidate or (folder/'candidate.html').read_text()!=m.corrections.rendered(candidate,b,k):raise ValueError('Candidate changed')
 text=m.prompt(state,plan,candidate,b,k,w,review_context_policy=p.get('review_context_policy'))
 bindings={'protocol_sha256':r.sha(seed/'protocol.json'),'authorization_sha256':p['authorization_sha256'],'attempt':0,'role':'review','before_sha256':r.digest(state),'candidate_sha256':r.digest(candidate),'plan_sha256':r.digest(plan)}
 bindings.update(review_context_version=m.corrections.review_loop.VERSION,evidence_expansion=0,evidence_requests_sha256=r.digest([]),extra_scope_ids_sha256=r.digest([]),prior_review_output_sha256=None)
 failed=folder/'review'
 if p['max_tokens'] is not None and tokens>p['max_tokens']:raise ValueError('Original budget exceeded')
 state,status=m.corrections.adjudicate(state,candidate,plan,review,b,k)
 if status!='accepted':raise ValueError('Original adjudication did not accept')
 pack=None;report_seed=str(seed);kind='report';history=p['history']
if sid in p['excluded_session_ids']:raise ValueError('Reviewer is not independent')
q=r.read(failed/'request.json')
if q['bindings']!=bindings or [q['model'],q['effort']]!=p['model'] or (failed/'prompt.txt').read_text()!=text or (job/'prompt.txt').read_text()!=text:raise ValueError('Exact original review differs')
print(json.dumps({'state':state,'signals':pack,'source_protocol':p['source_protocol'],'report_seed':report_seed,'kind':kind,'history':history,'tokens':tokens,'session_id':sid,'excluded_session_ids':sorted(set(p['excluded_session_ids']+[sid])),'source_usage_uncertainty':p.get('source_usage_uncertainty'),'failed_job':str(failed)}))
'''

def export(seed,job,manifest):
    seed,job,manifest=map(lambda p:Path(p).resolve(),(seed,job,manifest))
    p=r.read(seed/'protocol.json');m=r.read(manifest)
    require(m['version']=='proven-pre-model-host-access-retry-v1','Unsupported recovery authority')
    q=r.read(job/'request.json');bind=q['bindings'];failed=Path(seed/'jobs/review' if p['version']=='signal-label-repair-v1' else seed/'attempts/0/review')
    old=r.read(failed/'request.json')
    rows=[v for v in m['companies'].values() if str(failed).endswith('/'+v['source_job']) and v['request']==old]
    require(len(rows)==1,'Recovery manifest does not reserve this attempt')
    row=rows[0];private=Path(str(failed)[:-len(row['source_job'])])
    for name,h in row['bindings'].items():require(r.sha(private/name)==h,'Original failure binding changed')
    require(r.read(failed/'runtime-failure.json')=={'stage':'auth_storage'},'Not a proven pre-model failure')
    e=r.read(failed/'execution.json');require(e['status']=='returned' and e['exit_code']==1,'Original execution uncertain')
    require(not any((failed/n).exists() for n in ('runtime-start.json','runtime-finish.json','sessions','wire.json','output.json')),'Prior execution may have run')
    require(bind=={'recovery_manifest_sha256':r.sha(manifest),'original_request_sha256':r.sha(failed/'request.json'),'original_bindings':old['bindings'],'attempt':2,'prior_model_calls':0},'Recovery request binding changed')
    require((q['model'],q['effort'],q['timeout_seconds'])==(old['model'],old['effort'],old['timeout_seconds']),'Recovery settings changed')
    code=Path(next(c['path'] for c in p['code'] if c['path'].endswith('/earnings_passage_pipeline.py'))).parent.parent
    for c in p['code']:require(r.sha(c['path'])==c['sha256'],'Original code changed')
    result=subprocess.run([sys.executable,'-c',PROGRAM,str(seed),str(job)],cwd=code,env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def initialize(seed,job,manifest,output):
    root=Path(output).resolve();require(not root.exists() and not root.is_relative_to(Path(__file__).parent.parent),'New private edition required')
    v=export(seed,job,manifest);old=r.read(Path(seed)/'protocol.json')
    bound=dict(old.get('source_bindings',{}))
    for folder in (Path(seed),Path(job)):
        bound.update({str(p.resolve()):r.sha(p) for p in folder.rglob('*') if p.is_file() and not p.name.startswith('.') and p.suffix not in ('.pyc','.lock')})
    bound[str(Path(manifest).resolve())]=r.sha(manifest)
    code=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    p={'version':VERSION,'seed':v['report_seed'],'failed_seed':str(Path(seed).resolve()),'review_job':str(Path(job).resolve()),'recovery_manifest':str(Path(manifest).resolve()),'source_bindings':bound,'code':code,'source_code':old['code'],'source_protocol':v['source_protocol'],'kind':v['kind'],'excluded_session_ids':v['excluded_session_ids'],'source_usage_uncertainty':v['source_usage_uncertainty']}
    root.mkdir(parents=True)
    r.save(root/'protocol.json',p);r.save(root/'state.json',v['state'])
    if v['signals'] is not None:r.save(root/'signals.json',v['signals'])
    return verify(root)


def verify(output):
    root=Path(output).resolve();p=r.read(root/'protocol.json');require(p['version']==VERSION,'Recovery version changed')
    for c in p['code']:require(r.sha(c['path'])==c['sha256'] and r.sha(Path(__file__).parent/Path(c['path']).name)==c['sha256'],'Recovery code changed')
    for name,h in p['source_bindings'].items():require(r.sha(name)==h,'Recovery dependency changed')
    v=export(p['failed_seed'],p['review_job'],p['recovery_manifest'])
    require(v['state']==r.read(root/'state.json') and v['source_protocol']==p['source_protocol'] and v['kind']==p['kind'] and v['report_seed']==p['seed'] and v['excluded_session_ids']==p['excluded_session_ids'] and v['source_usage_uncertainty']==p['source_usage_uncertainty'],'Recovery provenance changed')
    b,k=rem._source_bundle(p['source_protocol']);result={'status':'accepted','tokens':v['tokens'],'history':v['history'],'new_model_calls':0,'review_sha256':r.sha(Path(p['review_job'])/'output.json')}
    if v['source_usage_uncertainty'] is not None:result.update(source_usage_uncertainty=v['source_usage_uncertainty'],total_tokens=None)
    if p['kind']=='signals':
        pack=r.read(root/'signals.json');require(pack==v['signals'],'Signals changed')
        signals.render(root/'report.html',v['state'],pack,r.verify_job(Path(p['review_job']))['content'],b,k)
        result['signals_sha256']=r.digest(pack)
    else:rem.repair.render(root/'report.html',{**v['state'],'status':'accepted'},b,k)
    result.update(state=v['state'],html_sha256=r.sha(root/'report.html'))
    rem.repair.write(root/'result.json',result)
    return {key:val for key,val in result.items() if key!='state'}
