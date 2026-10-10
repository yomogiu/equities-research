"""One source-bound correction of rejected signal fields; accepted signals stay exact."""
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from . import earnings_signals as signals, earnings_mixed_runner as runner
from . import earnings_role_import as imports, earnings_remediation as remediation

VERSION = 'signal-field-repair-v1'


def require(value, message):
    if not value: raise ValueError(message)


EXPORT = '''
import json,sys,os,subprocess
from pathlib import Path
from research import earnings_signals as s
root=Path(sys.argv[1]);p,state,b,k,w=s.load(root);v=s.verify(root)
if v['status']!='blocked':raise ValueError('Only independently blocked signals may be repaired')
source=Path(p['seed']);sp=s.base.read(source/'protocol.json')
code=Path(next(x['path'] for x in sp['code'] if x['path'].endswith('/earnings_passage_pipeline.py'))).parent.parent
accepted=subprocess.run([sys.executable,'-c',s.EXPORT,str(source)],cwd=code,env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},check=True,capture_output=True,text=True)
a=json.loads(accepted.stdout)
if a['state']!=state:raise ValueError('Accepted report state differs')
review=s.verify_job(root/'jobs/review')['content']
print(json.dumps({'state':state,'pack':s.base.read(root/'signals.json'),'review':review,'tokens':v['tokens']}))
'''


def original(seed):
    p=runner.read(seed/'protocol.json')
    require(p['version']==signals.VERSION,'Only original signals may receive a label repair')
    require(not any(x.is_symlink() for x in seed.rglob('*')),'Signal seed symlinks forbidden')
    for item in p['code']+p['source_code']:
        require(runner.sha(item['path'])==item['sha256'],'Original verifier changed')
    code=Path(next(x['path'] for x in p['code'] if x['path'].endswith('/earnings_signals.py'))).parent.parent
    value=subprocess.run([sys.executable,'-c',EXPORT,str(seed)],cwd=code,
        env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},check=True,capture_output=True,text=True)
    return p,json.loads(value.stdout)


def apply(pack, review, plan):
    require(isinstance(plan,dict) and set(plan)=={'signals_sha256','changes'}
            and plan['signals_sha256']==runner.digest(pack),'Plan must bind original signals')
    require(review.get('verdict')=='blocked' and review.get('signals_sha256')==runner.digest(pack),
            'Original blocked review must bind exact signals')
    rejected={x['id'] for x in review['decisions'] if x['approved'] is False}
    changes=plan['changes']
    require(isinstance(changes,list) and 1<=len(changes)<=4,'Bounded signal changes required')
    candidate=copy.deepcopy(pack);seen=set()
    fields={'label','summary','comparison','rationale','citations','passage_ids'}
    for change in changes:
        require(isinstance(change,dict) and set(change)=={'signal_id','before','after','reason'},'Exact field correction required')
        sid=change['signal_id'];require(sid in rejected and sid not in seen,'Only independently rejected signals may change')
        seen.add(sid);row=next(x for x in candidate['signals'] if x['id']==sid)
        before,after=change['before'],change['after']
        require(isinstance(before,dict) and isinstance(after,dict) and before.keys()==after.keys()
                and bool(before) and set(before)<=fields,'Only bounded presentation and source fields may change')
        signals.legacy.check_text(change['reason'],'reason')
        for key,value in before.items():require(row[key]==value,'Field compare-and-swap failed')
        require(before!=after,'No-op repair forbidden')
        for key,value in after.items():
            if key not in ('citations','passage_ids'):signals.legacy.check_text(value,key)
            else:require(isinstance(value,list) and value and all(isinstance(x,str) and x for x in value),'Exact evidence IDs required')
        row.update(copy.deepcopy(after))
        require(len(row['label'])<=60,'Signal label exceeds 60 characters')

    return candidate


def invalid_preflight(seed):
    claim=seed.parent/('.signal-field-repair-'+runner.sha(seed/'protocol.json')+'.json')
    if not claim.exists():return None
    value=runner.read(claim);prior=Path(value['output']).resolve()
    require(value['source_protocol_sha256']==runner.sha(seed/'protocol.json'),'Prior seed differs')
    if (prior/'jobs').exists():return None
    pp=runner.read(prior/'protocol.json')
    if pp.get('version')!=VERSION:return None
    bundle,catalog=remediation._source_bundle(pp['source_protocol'])
    try:signals.validate(runner.read(prior/'signals.json'),runner.read(prior/'state.json'),bundle,catalog)
    except ValueError:
        return claim,prior
    return None


def claim_path(seed):
    original=seed.parent/('.signal-field-repair-'+runner.sha(seed/'protocol.json')+'.json')
    return original.with_suffix('.preflight.json') if invalid_preflight(seed) else original


def expected(seed, output, plan, authorization, code):
    old,e=original(seed)

    require(isinstance(authorization,dict) and set(authorization)=={'version','enabled','seed_protocol_sha256','plan_sha256','output_path','authorized_by','reason'}
            and authorization['version']==VERSION and authorization['enabled'] is True
            and authorization['seed_protocol_sha256']==runner.sha(seed/'protocol.json')
            and authorization['plan_sha256']==runner.digest(plan) and authorization['output_path']==str(output),
            'Explicit exact signal-label repair authority required')
    for key in ('authorized_by','reason'):signals.legacy.check_text(authorization[key],key)
    uncertainty=old.get('source_usage_uncertainty')
    require(uncertainty is None or (isinstance(uncertainty,dict) and set(uncertainty)=={'session_id','total_tokens','status'} and isinstance(uncertainty['session_id'],str) and bool(uncertainty['session_id']) and uncertainty['total_tokens'] is None and uncertainty['status']=='unknown_interrupted_request'), 'Invalid source usage uncertainty')
    pack=apply(e['pack'],e['review'],plan)
    bound={**old['source_bindings'],**{str(seed/k):v for k,v in imports.inventory(seed).items()}}
    prior=invalid_preflight(seed)
    if prior:
        claim,folder=prior
        bound[str(claim)]=runner.sha(claim)
        bound.update({str(folder/k):v for k,v in imports.inventory(folder).items()})
    sessions=set(old.get('excluded_session_ids',[]))
    for name in bound:
        if Path(name).name=='execution.json':
            sid=runner.read(name).get('session',{}).get('id')
            if sid:sessions.add(sid)
    protocol={'version':VERSION,'seed':str(seed),'authorization':authorization,'code':code,
              'source_code':old['code']+old.get('source_code',[]),'source_protocol':old['source_protocol'],
              'source_bindings':bound,'state_sha256':runner.digest(e['state']),'signals_sha256':runner.digest(pack),
              'model':list(signals.MODEL),'max_review_attempts':1,'max_prompt_chars':old['max_prompt_chars'],
              'excluded_session_ids':sorted(sessions),'historical_signal_tokens':e['tokens'],
              'original_signal_review_attempts':1,'new_signal_review_attempt':2, 'source_usage_uncertainty':old.get('source_usage_uncertainty')}
    return protocol,e,pack


def initialize(seed, output, plan, authorization):
    seed=Path(seed).resolve();output=Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(seed)
            and not output.is_relative_to(Path(__file__).resolve().parents[1]),'New private sibling edition required')
    code=[{'path':str(f),'sha256':runner.sha(f)} for f in sorted(Path(__file__).parent.glob('earnings_*')) if f.suffix in ('.py','.mjs')]
    p,e,pack=expected(seed,output,plan,authorization,code)
    bundle,catalog=remediation._source_bundle(p['source_protocol'])
    signals.validate(pack,e['state'],bundle,catalog)
    claim={'version':VERSION,'output':str(output),'source_protocol_sha256':runner.sha(seed/'protocol.json')}
    path=claim_path(seed)
    if path.exists():require(runner.read(path)==claim,'A label-repair successor is already reserved')
    else:runner.save(path,claim)
    output.mkdir(parents=True)
    for name,value in [('protocol',p),('state',e['state']),('signals',pack),('plan',plan)]:runner.save(output/(name+'.json'),value)
    return {'status':'pending','role':'review','historical_signal_tokens':e['tokens']}


def load(root):
    root=Path(root).resolve();p=runner.read(root/'protocol.json');seed=Path(p['seed']);plan=runner.read(root/'plan.json')
    for record in p['code']:
        require(runner.sha(record['path'])==record['sha256'] and runner.sha(Path(__file__).parent/Path(record['path']).name)==record['sha256'],'Signal repair verifier changed')
    expected_p,e,pack=expected(seed,root,plan,p['authorization'],p['code'])
    require(p==expected_p and runner.read(root/'state.json')==e['state'] and runner.read(root/'signals.json')==pack,'Signal repair or original report changed')
    require(runner.read(claim_path(seed))=={'version':VERSION,'output':str(root),'source_protocol_sha256':runner.sha(seed/'protocol.json')},'Successor reservation changed')
    bundle,catalog=remediation._source_bundle(p['source_protocol'])
    signals.validate(pack,e['state'],bundle,catalog)
    return p,e['state'],pack,bundle,catalog,Path(p['source_protocol']['writing_standard']).read_text()


def advance(output,execute=True):
    root=Path(output).resolve()
    with (root/'.coordinator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        p,state,pack,b,k,w=load(root);job=root/'jobs/review'
        text=signals.prompt('review',state,b,k,w,pack)
        binding={'protocol_sha256':runner.sha(root/'protocol.json'),'signals_sha256':runner.digest(pack),
                 'report_sha256':signals.report_digest(state),'role':'signal_field_review','review_attempt':2}
        if not (job/'output.json').exists():
            if job.exists() and any(job.iterdir()):return {'status':'execution_uncertain'}
            if len(text)>p['max_prompt_chars']:return {'status':'prompt_too_large'}
            if not execute:return {'status':'pending','role':'review'}
            runner.run_role(job,text,*signals.MODEL,binding,timeout=1200)
        result=runner.verify_job(job);request=runner.read(job/'request.json')
        require(request['bindings']==binding and [request['model'],request['effort']]==p['model']
                and (job/'prompt.txt').read_text()==text,'Fresh signal review binding differs')
        require(result['receipt']['session']['id'] not in p['excluded_session_ids'],'Independent fresh signal review required')
        accepted=signals.validate_review(result['content'],pack,state,b,k)
        tokens=result['receipt']['session']['usage']['totalTokens']
        out={'status':'accepted' if accepted else 'blocked','tokens':tokens,'historical_signal_tokens':p['historical_signal_tokens'],
             'total_signal_tokens':tokens+p['historical_signal_tokens'],'report_sha256':signals.report_digest(state),
             'signals_sha256':runner.digest(pack),'review_sha256':runner.sha(job/'output.json'),'review_attempt':2}
        if p.get('source_usage_uncertainty') is not None:
            out.update(source_usage_uncertainty=p['source_usage_uncertainty'],total_tokens=None)
        if accepted:
            signals.render(root/'report.html',state,pack,result['content'],b,k);out['html_sha256']=runner.sha(root/'report.html')
        signals.repair.write(root/'result.json',out)
        return out


def verify(output):return advance(output,False)
