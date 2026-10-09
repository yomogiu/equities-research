"""One explicitly authorized distinct review after a proven local interruption.

Unknown historical usage remains unknown. No author, expansion or correction retry.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import fcntl
from . import earnings_mixed_runner as runner, earnings_role_import as imports
from . import earnings_corrections as corrections, earnings_remediation as remediation
from . import earnings_report_repair as repair

VERSION = 'interrupted-report-review-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


EXPORT = """
import json,sys
from pathlib import Path
from research import earnings_corrections as c
root=Path(sys.argv[1]);p,b,k,w=c.load(root);v=c.replay(root,p,b,k,w)
if v['status']!='launch_uncertain' or v.get('role')!='review' or v.get('round')!=0:
 raise ValueError('Only a first-round interrupted report review is supported')
print(json.dumps({'before':v['state'],'plan':c.base.read(root/'rounds/0/plan.json'),
 'candidate':c.base.read(root/'rounds/0/candidate.json'),'prompt':v['prompt'],
 'bindings':v['bindings'],'known_tokens':v['tokens']}))
"""


def no_live_process(job):
    # Inspect process identity, not reused PID numbers. Never signal a process here.
    rows=subprocess.check_output(['ps','-axo','pid,command'],text=True)
    require(not any(str(job) in line and 'earnings_mixed_prime.mjs' in line for line in rows.splitlines()),
            'Original review helper is still running')


def original(seed, proof, check_process=True):
    seed=Path(seed).resolve(); job=seed/'rounds/0/review'
    require(not any(x.is_symlink() for x in seed.rglob('*')), 'Seed symlinks forbidden')
    old=runner.read(seed/'protocol.json')
    require(old['version']=='deterministic-corrections-v1' and old.get('max_tokens') is None
            and not any(old.get(k) for k in ('new_experiment','imported_proposal','evidence_resume',
                       'review_context_policy','regression_findings','passage_resolution','correction_provider_recovery')),
            'Only original uncapped correction review is supported; unknown usage cannot satisfy a finite cap')
    require(type(old['prior_rounds']) is int and type(old['max_rounds']) is int
            and 0<=old['prior_rounds']<2 and old['max_rounds']>=1
            and old['prior_rounds']+old['max_rounds']<=2, 'Original round accounting invalid')
    require(sorted(str(x.relative_to(seed)) for x in seed.rglob('request.json'))==
            ['rounds/0/propose/request.json','rounds/0/review/request.json'], 'Exactly one author and one interrupted review required')
    require(not (seed/'result.json').exists() and not (seed/'rounds/0/decision.json').exists(), 'Terminal report cannot be retried')
    for name in ('execution.json','output.json','runtime-finish.json','runtime-failure.json','stdout.txt','wire.json'):
        require(not (job/name).exists(), 'Completed or failed review must use its own authenticated disposition')
    require(not list((job/'sessions').rglob('*.jsonl')), 'Existing journal must be reconciled instead of discarded')
    for record in old['code']+old.get('source_code',[]):
        require(runner.sha(record['path'])==record['sha256'], 'Original verifier changed')
    code=Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_corrections.py'))).parent.parent
    result=subprocess.run([sys.executable,'-c',EXPORT,str(seed)],cwd=code,
        env={**os.environ,'PYTHONPATH':str(code),'PYTHONDONTWRITEBYTECODE':'1'},check=True,capture_output=True,text=True)
    exported=json.loads(result.stdout);q=runner.read(job/'request.json');launch=runner.read(job/'launch.json');start=runner.read(job/'runtime-start.json')
    require(q['job_path']==str(job) and q['bindings']==exported['bindings']
            and [q['model'],q['effort']]==old['model']==list(corrections.MODEL)
            and q['prompt_sha256']==runner.sha(job/'prompt.txt')
            and (job/'prompt.txt').read_text()==exported['prompt'], 'Original exact review request does not reproduce')
    require(q['runner_sha256']==runner.sha(code/'research/earnings_mixed_runner.py')
            and q['helper_sha256']==runner.sha(code/'research/earnings_mixed_prime.mjs'), 'Original launch code differs')
    require(launch['request_sha256']==runner.digest(q) and launch['id']==start['launch_id']
            and start['model']==q['model'] and start['effort']==q['effort']
            and start['provider']==q['provider']==runner.PROVIDER and start['oauth'] is True
            and isinstance(start['session_id'],str) and start['session_id'], 'Original runtime identity differs')
    expected={'job':str(job),'request_sha256':runner.sha(job/'request.json'),'launch_sha256':runner.sha(job/'launch.json'),
              'session_id':start['session_id'],'candidate_sha256':runner.digest(exported['candidate']),
              'prompt_sha256':runner.sha(job/'prompt.txt')}
    require(isinstance(proof,dict) and set(proof)==set(expected)|{'pause_record','pause_sha256','partial_inventory','partial_inventory_sha256','model_pid','observed_stopped_at','attested_by'}
            and all(proof[k]==v for k,v in expected.items()), 'Termination proof must bind exact interrupted review')
    for key in ('observed_stopped_at','attested_by'):
        require(isinstance(proof[key],str) and proof[key].strip(), 'Explicit host-stop attestation required')
    require(runner.sha(proof['pause_record'])==proof['pause_sha256']
            and runner.sha(proof['partial_inventory'])==proof['partial_inventory_sha256'], 'Pause evidence changed')
    pause=runner.read(proof['pause_record']);inventory=runner.read(proof['partial_inventory'])
    require(pause.get('paused') is True and type(proof['model_pid']) is int
            and proof['model_pid'] in pause['processes']['terminated_pids'], 'Model termination not recorded')
    recorded=Path(inventory['job'])
    require((recorded==job if recorded.is_absolute() else str(job).endswith('/'+str(recorded)))
            and any((Path(proof['pause_record']).parent/name).resolve()==job for name in pause['interrupted_jobs'])
            and inventory['files']==imports.inventory(job),
            'Interrupted bytes differ from original stop inventory')
    if check_process:no_live_process(job)
    return old,exported,start['session_id']


def claim_path(seed):
    return seed.parent/('.interrupted-review-'+runner.sha(seed/'rounds/0/review/request.json')+'.json')


def expected(seed, output, authorization, proof, code, check_process=True):
    old,exported,sid=original(seed,proof,check_process=check_process)
    require(isinstance(authorization,dict) and set(authorization)=={'version','enabled','seed_protocol_sha256','output_path','authorized_by','reason','unknown_usage_authorization'}
            and authorization['version']==VERSION and authorization['enabled'] is True
            and authorization['seed_protocol_sha256']==runner.sha(seed/'protocol.json')
            and authorization['output_path']==str(output)
            and all(isinstance(authorization[k],str) and authorization[k].strip() for k in ('authorized_by','reason','unknown_usage_authorization')),
            'Explicit distinct review and unknown-usage authority required')
    bound={**old['source_bindings'],**{str(seed/k):v for k,v in imports.inventory(seed).items()},
           proof['pause_record']:proof['pause_sha256'],proof['partial_inventory']:proof['partial_inventory_sha256']}
    sessions={sid};known={}
    for name in bound:
        if Path(name).name=='execution.json':
            session=runner.read(name).get('session',{}).get('id')
            if session:
                sessions.add(session); usage=runner.read(name)['session']['usage']['totalTokens']
                require(type(usage) is int and usage>=0 and (session not in known or known[session]==usage), 'Historical usage differs')
                known[session]=usage
    protocol={'version':VERSION,'seed':str(seed),'authorization':authorization,'termination_proof':proof,'code':code,
              'source_code':old['code']+old.get('source_code',[]),'source_protocol':old['source_protocol'],'source_bindings':bound,
              'model':old['model'],'max_tokens':None,'max_prompt_chars':min(old.get('max_prompt_chars',350000),350000),
              'before_sha256':runner.digest(exported['before']),'candidate_sha256':runner.digest(exported['candidate']),
              'plan_sha256':runner.digest(exported['plan']),'prompt_sha256':runner.sha(seed/'rounds/0/review/prompt.txt'),
              'excluded_session_ids':sorted(sessions),'review_attempt':2,'max_review_attempts':2,
              'correction_round':old['prior_rounds']+1,'remaining_correction_rounds':0,
              'known_prior_tokens':sum(known.values()),'known_correction_tokens':old.get('inherited_tokens',0)+exported['known_tokens'],
              'unknown_prior_usage':{'session_id':sid,'total_tokens':None,'status':'unknown_interrupted_request'},
              'total_tokens':None}
    return protocol,exported


def initialize(seed, output, authorization, proof):
    seed=Path(seed).resolve();output=Path(output).resolve()
    require(not output.exists() and output!=seed and not output.is_relative_to(seed)
            and not output.is_relative_to(Path(__file__).resolve().parents[1]), 'New private sibling review required')
    code=[{'path':str(p),'sha256':runner.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol,exported=expected(seed,output,authorization,proof,code)
    claim={'version':VERSION,'output':str(output),'source_request_sha256':runner.sha(seed/'rounds/0/review/request.json')}
    path=claim_path(seed)
    if path.exists():require(runner.read(path)==claim,'A distinct review successor is already reserved')
    else:runner.save(path,claim)
    output.mkdir(parents=True);runner.save(output/'protocol.json',protocol)
    for name in ('before','candidate','plan'):runner.save(output/(name+'.json'),exported[name])
    (output/'prompt.txt').write_text(exported['prompt'])
    return {'status':'pending','review_attempt':2,'remaining_correction_rounds':0,'total_tokens':None}


def load(root):
    root=Path(root).resolve();p=runner.read(root/'protocol.json');seed=Path(p['seed'])
    for rec in p['code']:
        require(runner.sha(rec['path'])==rec['sha256'] and runner.sha(Path(__file__).parent/Path(rec['path']).name)==rec['sha256'],'Successor code changed')
    expected_p,exported=expected(seed,root,p['authorization'],p['termination_proof'],p['code'],check_process=False)
    require(p==expected_p and runner.read(claim_path(seed))=={'version':VERSION,'output':str(root),'source_request_sha256':runner.sha(seed/'rounds/0/review/request.json')}, 'Successor accounting or reservation changed')
    for name in ('before','candidate','plan'):require(runner.read(root/(name+'.json'))==exported[name],'Staged review bytes changed')
    require((root/'prompt.txt').read_text()==exported['prompt'],'Original review prompt changed')
    bundle,catalog=remediation._source_bundle(p['source_protocol'])
    return p,exported,bundle,catalog


def advance(output, execute=False):
    root=Path(output).resolve()
    with (root/'.coordinator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        p,e,b,k=load(root);job=root/'review'
        bindings={'protocol_sha256':runner.sha(root/'protocol.json'),'role':'interrupted_report_review','review_attempt':2,
                  'candidate_sha256':p['candidate_sha256'],'plan_sha256':p['plan_sha256'],
                  'interrupted_session_id':p['unknown_prior_usage']['session_id']}
        text=e['prompt']
        if not (job/'output.json').exists():
            uncertain=job.exists() and any(job.iterdir())
            if uncertain:return {'status':'execution_uncertain','total_tokens':None,'unknown_prior_usage':p['unknown_prior_usage']}
            if len(text)>p['max_prompt_chars']:return {'status':'prompt_too_large','total_tokens':None}
            if not execute:return {'status':'pending','review_attempt':2,'total_tokens':None}
            no_live_process(Path(p['seed'])/'rounds/0/review')
            runner.run_role(job,text,*p['model'],bindings,timeout=1200)
        result=runner.verify_job(job);request=runner.read(job/'request.json')
        require(request['bindings']==bindings and [request['model'],request['effort']]==p['model']
                and (job/'prompt.txt').read_text()==text, 'Successor review request differs')
        require(result['receipt']['session']['id'] not in p['excluded_session_ids'], 'Distinct independent review session required')
        if result['content'].get('verdict')=='needs_evidence':
            return {'status':'blocked','reason':'Distinct review needs more evidence; no further review attempt authorized',
                    'measured_new_tokens':result['receipt']['session']['usage']['totalTokens'],'total_tokens':None,
                    'unknown_prior_usage':p['unknown_prior_usage']}
        after,status=corrections.adjudicate(e['before'],e['candidate'],e['plan'],result['content'],b,k)
        summary={'status':'accepted' if status=='accepted' else 'blocked','review_attempt':2,'correction_round':p['correction_round'],
                 'remaining_correction_rounds':0,'known_prior_tokens':p['known_prior_tokens'],
                 'measured_new_tokens':result['receipt']['session']['usage']['totalTokens'],'total_tokens':None,
                 'unknown_prior_usage':p['unknown_prior_usage']}
        if summary['status']=='accepted':
            repair.render(root/'report.html',{**after,'status':'accepted'},b,k)
            repair.write(root/'result.json',{**summary,'state':after,'html_sha256':runner.sha(root/'report.html')})
        elif (root/'result.json').exists():raise ValueError('Accepted result does not reproduce')
        return summary


def verify(output):
    return advance(output,execute=False)
