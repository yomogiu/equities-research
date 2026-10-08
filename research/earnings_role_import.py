"""Import completed authenticated responses without claiming an observed process exit."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from . import earnings_mixed_runner as r

VERSION = 'authenticated-response-import-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def inventory(job):
    return {str(p.relative_to(job)): r.sha(p) for p in sorted(job.rglob('*'))
            if p.is_file() and not p.name.endswith('.lock')}


AUTHENTICATE = '''import json,sys
from pathlib import Path
from research import earnings_mixed_runner as r
p=Path(sys.argv[1]);q=r.read(p/'request.json');a=r.read(p/'launch.json')
assert q['job_path']==str(p) and q['runner_sha256']==r.sha(r.__file__) and q['helper_sha256']==r.sha(r.HELPER)
r._validate_selection(q['model'],q['effort'])
assert q['prompt_sha256']==r.sha(p/'prompt.txt') and a['request_sha256']==r.digest(q)
if (p/'execution.json').exists() or (p/'output.json').exists():
 v=r.verify_job(p); print(json.dumps({'content':v['content'],'session':v['receipt']['session'],'original_elapsed_seconds':v['receipt'].get('elapsed_seconds'),'completion_basis':'original_verified_execution'}))
else:
 assert not (p/'runtime-failure.json').exists()
 session=r.session_receipt(p,q)
 start=r.read(p/'runtime-start.json');finish=r.read(p/'runtime-finish.json')
 assert start['launch_id']==a['id']
 for v in (start,finish):
  assert v['session_id']==session['id'] and v['model']==q['model'] and v['effort']==q['effort'] and v['oauth'] is True
 assert r.read(p/'wire.json')==[{'model':q['model'],'effort':q['effort'],'tools':0}]
 if 'token_estimate_sha256' in a:
  est=r.read(p/'token-estimate.json');assert r.sha(p/'token-estimate.json')==a['token_estimate_sha256'] and est['prompt_sha256']==q['prompt_sha256'] and est['model']==q['model'] and est['enforced'] is False
 print(json.dumps({'content':r.parse_response((p/'stdout.txt').read_text()),'session':session,'original_elapsed_seconds':None,'completion_basis':'authenticated_session_and_runtime_finish'}))
'''


def authenticate(reference):
    job, code = Path(reference['job']), Path(reference['code'])
    require(job.is_absolute() and code.is_absolute(), 'Absolute source paths required')
    require(not any(p.is_symlink() for p in job.rglob('*')), 'Source symlinks forbidden')
    require(inventory(job) == reference['files'], 'Imported source changed')
    for name, expected in reference['code_files'].items():
        require(r.sha(code/name) == expected, 'Original verifier changed')
    value = subprocess.run([sys.executable, '-c', AUTHENTICATE, str(job)], cwd=code,
                           env={**os.environ, 'PYTHONPATH': str(code)}, capture_output=True, text=True)
    require(value.returncode == 0, 'Original response authentication failed: '+value.stderr[-1000:])
    return json.loads(value.stdout)


def reference(job, code):
    job, code = Path(job).resolve(), Path(code).resolve()
    require(not (job/'import.json').exists(), 'Chained imports require a separate contract')
    q=r.read(job/'request.json')
    require(q['runner_sha256']==r.sha(code/'research/earnings_mixed_runner.py') and
            q['helper_sha256']==r.sha(code/'research/earnings_mixed_prime.mjs'), 'Source verifier mismatch')
    ref={'job':str(job),'code':str(code),'files':inventory(job),
         'code_files':{str(p.relative_to(code)):r.sha(p) for p in (code/'research').glob('earnings_*') if p.is_file()}}
    authenticate(ref)
    return ref


def create(job, prompt, model, effort, bindings, timeout, ref):
    job=Path(job).resolve();q=r._request(job,prompt,model,effort,bindings,timeout)
    original=r.read(Path(ref['job'])/'request.json');source=authenticate(ref)
    require((Path(ref['job'])/'prompt.txt').read_text()==prompt and
            (original['model'],original['effort'])==(model,effort), 'Imported prompt/model differs')
    if (job/'request.json').exists():
        require(r.read(job/'request.json')==q and r.read(job/'import.json')['source']==ref, 'Import request changed')
        return verify(job)
    job.mkdir(parents=True,exist_ok=True)
    require(not any(job.iterdir()), 'Import directory must be empty')
    r.save(job/'request.json',q);(job/'prompt.txt').write_text(prompt)
    imported={'version':VERSION,'source':ref,'completion_basis':source['completion_basis'],
              'original_elapsed_seconds':source['original_elapsed_seconds'],'process_exit_code_observed':False}
    r.save(job/'import.json',imported)
    execution={'status':'imported_completed_response','exit_code':None,'elapsed_seconds':0,
               'new_model_calls':0,'request_sha256':r.digest(q),'import_sha256':r.sha(job/'import.json'),
               'session':source['session'],'usage_is_inherited':True}
    r.save(job/'execution.json',execution)
    r.save(job/'output.json',{'request_sha256':r.digest(q),'execution_sha256':r.sha(job/'execution.json'),'content':source['content']})
    return verify(job)


def verify(job):
    job=Path(job).resolve();q=r.read(job/'request.json');im=r.read(job/'import.json')
    require(im['version']==VERSION and q['version']==r.VERSION and q['job_path']==str(job), 'Import identity changed')
    require(q['runner_sha256']==r.sha(r.__file__) and q['helper_sha256']==r.sha(r.HELPER), 'Import runner changed')
    require(q['prompt_sha256']==r.sha(job/'prompt.txt'), 'Import prompt changed')
    source=authenticate(im['source']);original=r.read(Path(im['source']['job'])/'request.json')
    require((Path(im['source']['job'])/'prompt.txt').read_bytes()==(job/'prompt.txt').read_bytes() and
            (original['model'],original['effort'])==(q['model'],q['effort']), 'Import differs from authenticated source')
    require(im=={'version':VERSION,'source':im['source'],'completion_basis':source['completion_basis'],
                 'original_elapsed_seconds':source['original_elapsed_seconds'],'process_exit_code_observed':False}, 'Import provenance changed')
    execution={'status':'imported_completed_response','exit_code':None,'elapsed_seconds':0,'new_model_calls':0,
               'request_sha256':r.digest(q),'import_sha256':r.sha(job/'import.json'),'session':source['session'],'usage_is_inherited':True}
    require(r.read(job/'execution.json')==execution, 'Import execution changed')
    expected={'request_sha256':r.digest(q),'execution_sha256':r.sha(job/'execution.json'),'content':source['content']}
    require(r.read(job/'output.json')==expected, 'Import response changed')
    return {'content':source['content'],'receipt':execution,'output_path':str(job/'output.json')}


def initialize(seed, output, authorization, evidence_job=None):
    from . import earnings_passage_pipeline as pipe
    seed,output=Path(seed).resolve(),Path(output).resolve()
    require(authorization.strip() and output!=seed and not output.exists(), 'New authorized recovery directory required')
    old=r.read(seed/'protocol.json');require(old['version'] in (pipe.VERSION,pipe.EFFICIENT_VERSION) and not old.get('response_recovery'), 'Only original passage pipeline can be recovered')
    for rec in old['code']:require(r.sha(rec['path'])==rec['sha256'],'Frozen code changed')
    code=Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    imports={p.parent.name:reference(p.parent,code) for p in sorted((seed/'jobs').glob('*/request.json'))}
    require(imports, 'Saved responses required')
    require(not (seed/'result.json').exists(), 'Terminal pipeline requires another explicit recovery contract')
    # Original prompts, evidence and numbered attempts are replayed unchanged.
    protocol=copy.deepcopy(old)
    protocol['code']=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol['response_recovery']={'authorization':authorization,'seed':str(seed),'protocol_sha256':r.sha(seed/'protocol.json'),'imports':imports}
    if evidence_job:
        require(evidence_job in imports and evidence_job.startswith('retrieval-r') and evidence_job.endswith('-evidence-1'), 'Only an existing retrieval evidence request can be resumed')
        saved=authenticate(imports[evidence_job])['content']
        require(isinstance(saved,dict) and set(saved)=={'needs_evidence'} and saved['needs_evidence'], 'Saved response must request original evidence')
        protocol['response_recovery']['extra_evidence']={'job':evidence_job,'request_sha256':r.digest(saved),'max_additional_expansions':1}
    output.mkdir(parents=True)
    (output/'passages.json').write_bytes((seed/'passages.json').read_bytes())
    if old.get('qa_grounding_path'):
        (output/'qa-grounding.json').write_bytes(Path(old['qa_grounding_path']).read_bytes())
        protocol['qa_grounding_path']=str(output/'qa-grounding.json')
    r.save(output/'protocol.json',protocol)
    pipe.load(output)
    return protocol['response_recovery']


def validate_recovery(recovery):
    """Every saved job must be accounted for before any successor can launch."""
    seed=Path(recovery['seed']);old=r.read(seed/'protocol.json')
    code=Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    jobs={q.parent.name:q.parent for q in (seed/'jobs').glob('*/request.json')}
    failed=recovery.get('provider_retry')
    excluded={'analysis-r0'} if failed else set()
    if failed:
        require(set(jobs)=={'financial-r0','retrieval-r0','analysis-r0'} and
                Path(failed['job'])==jobs['analysis-r0'] and Path(failed['code'])==code,
                'Provider failure must bind original first analysis attempt')
    require(set(recovery['imports'])==set(jobs)-excluded,'All completed seed jobs must be imported')
    for name in set(jobs)-excluded:
        require(recovery['imports'][name]==reference(jobs[name],code),'Imported preparer provenance differs')


def complete_courtesy(out, bundle, catalog):
    """Fill absent exact thank-you exchanges only; no substantive answer synthesis."""
    import re
    value=copy.deepcopy(out);added=[]
    if not isinstance(value.get('exchange_coverage'),list):return value,added
    turns={t['id']:t for t in bundle['transcript_index']['turns']}
    present={x.get('exchange_id') for x in value['exchange_coverage']}
    def courtesy(tid,role):
        t=turns[tid]
        if t['role']!=role:return None
        rows=sorted([p for p in catalog['passages'] if p['scope_id']==tid],key=lambda p:p['start'])
        text=''.join(p['text'] for p in rows).strip();lines=text.splitlines()
        if len(lines)!=3 or lines[0]!=t['speaker'] or lines[-1]!='Thank you.':return None
        pattern=r'Analyst, .+' if role=='analyst' else r'President and CEO, .+'
        if not re.fullmatch(pattern,lines[1]):return None
        selected=[p['passage_id'] for p in rows if p['text'].strip()=='Thank you.']
        return selected if len(selected)==1 else None
    for e in bundle['transcript_index']['exchanges']:
        if e['id'] in present or e.get('unknown_turn_ids') or len(e['question_turn_ids'])!=1 or len(e['answer_turn_ids'])!=1:continue
        question=courtesy(e['question_turn_ids'][0],'analyst');answer=courtesy(e['answer_turn_ids'][0],'management')
        if not question or not answer:continue
        entry={'exchange_id':e['id'],'question':'Thank you.','answer':'Thank you.',
               'consequence':'Courtesy exchange; no substantive question or response.',
               'question_passage_ids':question,'answer_passage_ids':answer,'continuation_exchange_ids':[],
               'grounding_status':'bound','grounding_notes':'Deterministic completion of an omitted courtesy-only exchange from exact original turns; provisional speaker annotations retained.'}
        value['exchange_coverage'].append(entry);added.append(entry)
    return value,added
