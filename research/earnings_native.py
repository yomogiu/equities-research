"""Native subscription Codex counterpart of the frozen Prime earnings experiment.

prepare freezes private inputs, comparison provenance, code, binary and settings.
run preserves the original prompts and shared two-round correction graph. No API
credentials are read or copied; each role is one fresh, read-only Codex session.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from . import earnings_experiment as base
from . import financial_evidence, transcript_evidence

VERSION = 'earnings-native-v1'
MODEL = 'gpt-5.6-sol'
EFFORT = 'max'
TIMEOUT = 900
# Reuse the frozen evidence and prompt implementations without modifying globals.
read, save, sha, digest = base.read, base.save, base.sha, base.digest
inside, validate_case, validate_content = base.inside, base.validate_case, base.validate_content
role_prompt, parse_response = base.role_prompt, base.parse_response


def code_hashes():
    return {name: sha(module.__file__) for name, module in
            [('experiment', base), ('financial', financial_evidence),
             ('transcript', transcript_evidence)]} | {'native': sha(__file__)}


def command(codex, job):
    return [str(codex), 'exec', '--ignore-user-config', '-m', MODEL,
            '-c', 'model_reasoning_effort="'+EFFORT+'"',
            '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
            '--enable', 'skip_host_skill_discovery', '--disable', 'plugins',
            '--disable', 'apps', '--disable', 'browser_use', '--disable', 'computer_use',
            '-s', 'read-only', '--json', '-o', str(job/'final.txt'), '-C', str(job), '-']


def prepare(case_path, prime_run, run, codex):
    case_path=Path(case_path).resolve(); prime_run=Path(prime_run).resolve()
    run=Path(run).resolve(); codex=Path(codex).resolve()
    case=read(case_path); validate_case(case)
    if run == prime_run or run.is_relative_to(prime_run) or prime_run.is_relative_to(run):
        raise ValueError('Native and Prime runs must be separate')
    if read(prime_run/'case.json') != case:
        raise ValueError('Comparison case differs from frozen Prime run')
    if (run/'config.json').exists():
        config=verify_config(run)
        if (config['case_path'],config['prime_run'],config['codex']) != (str(case_path),str(prime_run),str(codex)):
            raise ValueError('Existing configuration differs')
        return config
    if run.exists() and any(run.iterdir()):
        raise ValueError('Prepare requires an empty native directory')
    # Version probing is local only: no role or provider is launched by prepare.
    version=subprocess.run([str(codex),'--version'],capture_output=True,text=True,check=True,timeout=30).stdout.strip()
    if not version: raise ValueError('CLI version required')
    prime_files={str(p.relative_to(prime_run)):sha(p) for p in prime_run.rglob('*') if p.is_file() and p.suffix!='.dill'}
    config={'version':VERSION,'case_path':str(case_path),'case_sha256':digest(case),
            'case_file_sha256':sha(case_path),'prime_run':str(prime_run),'prime_files':prime_files,
            'code_sha256':code_hashes(),'codex':str(codex),'codex_sha256':sha(codex),
            'codex_version':version,'model':MODEL,'reasoning_effort':EFFORT,'timeout_seconds':TIMEOUT,
            'command_template':command(codex,Path('{job}'))}
    save(run/'case.json',case); save(run/'config.json',config)
    return verify_config(run)


def verify_config(run):
    run=Path(run).resolve(); config=read(inside(run,'config.json'))
    case=read(inside(run,'case.json')); validate_case(case)
    if config.get('version')!=VERSION or config.get('model')!=MODEL or config.get('reasoning_effort')!=EFFORT or config.get('timeout_seconds')!=TIMEOUT:
        raise ValueError('Unsupported frozen native configuration')
    if config.get('code_sha256')!=code_hashes(): raise ValueError('Frozen code changed')
    if config['case_sha256']!=digest(case) or sha(config['case_path'])!=config['case_file_sha256'] or read(config['case_path'])!=case:
        raise ValueError('Frozen comparison case changed')
    if sha(config['codex'])!=config['codex_sha256'] or config['command_template']!=command(config['codex'],Path('{job}')):
        raise ValueError('Frozen Codex binary or arguments changed')
    prime=Path(config['prime_run'])
    if not config['prime_files'] or any(sha(inside(prime,p))!=h for p,h in config['prime_files'].items()):
        raise ValueError('Frozen Prime comparison artifacts changed')
    if read(prime/'case.json')!=case: raise ValueError('Prime comparison case changed')
    return config


def capture_rollout(job, session_root=None):
    job=Path(job)
    events=[json.loads(line) for line in (job/'events.jsonl').read_text().splitlines() if line.strip()]
    heads=[e for e in events if e.get('type')=='thread.started']
    if len(heads)!=1 or not heads[0].get('thread_id'): raise ValueError('Native thread identity missing')
    sid=heads[0]['thread_id']
    # Only inspect the one file named for this captured thread; never other roles.
    if any(c not in '0123456789abcdef-' for c in sid.lower()): raise ValueError('Unexpected native thread ID format')
    root=Path(session_root) if session_root else Path.home()/'.codex'/'sessions'
    matches=list(root.rglob('*'+sid+'.jsonl'))
    if len(matches)!=1: raise ValueError('Exactly one matching native rollout required')
    source=matches[0]; target=job/'session.jsonl'
    data=source.read_bytes()
    if target.exists() and target.read_bytes()!=data: raise ValueError('Existing native rollout differs')
    target.write_bytes(data)


def rollout_receipt(job, sid, final):
    events=[json.loads(line) for line in (job/'session.jsonl').read_text().splitlines() if line.strip()]
    heads=[e['payload'] for e in events if e.get('type')=='session_meta']
    contexts=[e['payload'] for e in events if e.get('type')=='turn_context']
    if len(heads)!=1 or heads[0].get('id')!=sid or not heads[0].get('cli_version') or heads[0].get('model_provider')!='openai':
        raise ValueError('Native rollout session identity/provider missing')
    if not contexts or any(c.get('model')!=MODEL or c.get('effort')!=EFFORT or c.get('sandbox_policy',{}).get('type')!='read-only' for c in contexts):
        raise ValueError('Native observed model/effort/sandbox differs')
    messages=[e['payload'] for e in events if e.get('type')=='response_item' and e.get('payload',{}).get('type')=='message']
    users=[m for m in messages if m.get('role')=='user']
    def text(message):
        return ''.join(c.get('text','') for c in message.get('content',[]) if c.get('type') in {'input_text','output_text','text'})
    # CLI may emit an environment-context user message before the actual request.
    prompt=(job/'prompt.txt').read_text()
    if not users or text(users[-1])!=prompt or any(not text(m).startswith('<environment_context>') for m in users[:-1]):
        raise ValueError('Native rollout user prompt differs')
    assistants=[m for m in messages if m.get('role')=='assistant']
    if not assistants or assistants[-1].get('phase')!='final_answer' or final not in {text(assistants[-1]),text(assistants[-1])+'\n'}:
        raise ValueError('Native rollout final response differs')
    return {'session_sha256':sha(job/'session.jsonl'),'cli_version':heads[0]['cli_version'],
            'model_provider':heads[0]['model_provider'],'model':MODEL,'reasoning_effort':EFFORT,
            'sandbox_policy':contexts[-1]['sandbox_policy'],
            'approval_policy':contexts[-1].get('approval_policy')}


def session_receipt(job):
    job=Path(job)
    events=[json.loads(line) for line in (job/'events.jsonl').read_text().splitlines() if line.strip()]
    heads=[e for e in events if e.get('type')=='thread.started']
    starts=[e for e in events if e.get('type')=='turn.started']
    ends=[e for e in events if e.get('type')=='turn.completed']
    if len(heads)!=1 or not isinstance(heads[0].get('thread_id'),str) or not heads[0]['thread_id']:
        raise ValueError('Exactly one native thread identity required')
    if len(starts)!=1 or len(ends)!=1 or events[-1]!=ends[0]:
        raise ValueError('Exactly one completed native turn required')
    if events.index(heads[0])>events.index(starts[0]) or any(e.get('type') in {'error','turn.failed'} for e in events):
        raise ValueError('Native event stream reports an error')
    usage=ends[0].get('usage')
    if not isinstance(usage,dict) or not {'input_tokens','cached_input_tokens','output_tokens'}<=set(usage) or any(type(v) is not int or v<0 for v in usage.values()):
        raise ValueError('Actual native token usage required')
    messages=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    final=(job/'final.txt').read_text()
    # Codex output-last-message adds a single trailing LF; preserve all other bytes.
    if not messages or not isinstance(messages[-1].get('text'),str) or final not in {messages[-1]['text'], messages[-1]['text']+'\n'}:
        raise ValueError('Native final message differs from captured final output')
    return {'id':heads[0]['thread_id'],'events_sha256':sha(job/'events.jsonl'),
            'final_sha256':sha(job/'final.txt'),'usage':usage,
            **rollout_receipt(job,heads[0]['thread_id'],final)}


def verify_job(job, role, case, dependencies):
    job=Path(job).resolve(); run=job.parent; config=verify_config(run)
    for name in ('request.json','output.json','execution.json','prompt.txt','events.jsonl','final.txt','stderr.txt','dependencies.json','launch.json','session-receipt.json','session.jsonl'):
        inside(job,job/name)
    for path in dependencies.values(): inside(run,path)
    request=read(job/'request.json'); output=read(job/'output.json'); execution=read(job/'execution.json')
    revision=request.get('revision')
    if type(revision) is not int or not 0<=revision<=2 or job.name!=f'{role}-r{revision}':
        raise ValueError('Invalid role revision')
    expected_prompt=base.role_prompt(role,config['case_path'],case,dependencies,revision)
    if (job/'prompt.txt').read_text()!=expected_prompt or request.get('prompt_sha256')!=sha(job/'prompt.txt'):
        raise ValueError('Native prompt differs from frozen role prompt')
    if request.get('version')!=VERSION or request.get('role')!=role or request.get('case_sha256')!=digest(case) or output.get('request_sha256')!=digest(request):
        raise ValueError('Native role/request binding mismatch')
    if request.get('dependencies')!={k:sha(v) for k,v in dependencies.items()} or read(job/'dependencies.json')!={k:str(v) for k,v in dependencies.items()}:
        raise ValueError('Native role dependencies changed')
    argv=command(config['codex'],job)
    if request.get('config_sha256')!=sha(run/'config.json') or request.get('argv')!=argv or request.get('argv_sha256')!=digest(argv):
        raise ValueError('Native command/configuration changed')
    launch=read(job/'launch.json')
    if launch.get('request_sha256')!=digest(request) or launch.get('argv_sha256')!=digest(argv) or launch.get('status')!='launched':
        raise ValueError('Native launch receipt changed')
    if execution.get('status')!='returned' or execution.get('exit_code')!=0 or execution.get('request_sha256')!=digest(request):
        raise ValueError('Native execution not completed')
    elapsed=execution.get('elapsed_seconds')
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0:
        raise ValueError('Actual elapsed time required')
    for name in ('events.jsonl','final.txt','stderr.txt'):
        if execution.get('files',{}).get(name)!=sha(job/name): raise ValueError('Native runtime capture changed')
    receipt=session_receipt(job)
    if receipt['cli_version']!=config['codex_version'].split()[-1]: raise ValueError('Native observed CLI version differs')
    if read(job/'session-receipt.json')!=receipt: raise ValueError('Native session receipt changed')
    if parse_response((job/'final.txt').read_text())!=output['content']: raise ValueError('Native output differs from runtime response')
    validate_content(role,output['content'],case,dependencies)
    return receipt['id']


def run_role(run, role, revision, case_path, case, dependencies):
    run=Path(run).resolve(); config=verify_config(run); validate_case(case); case_path=Path(case_path).resolve()
    if str(Path(case_path).resolve())!=config['case_path'] or digest(case)!=config['case_sha256']:
        raise ValueError('Role case differs from prepared case')
    job=run/f'{role}-r{revision}'; job.mkdir(parents=True,exist_ok=True)
    dep_hashes={k:sha(v) for k,v in dependencies.items()}
    prompt=base.role_prompt(role,case_path,case,dependencies,revision); argv=command(config['codex'],job)
    request={'version':VERSION,'role':role,'revision':revision,'case_sha256':digest(case),
             'dependencies':dep_hashes,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
             'config_sha256':sha(run/'config.json'),'argv':argv,'argv_sha256':digest(argv)}
    save(job/'request.json',request); save(job/'dependencies.json',{k:str(v) for k,v in dependencies.items()})
    if (job/'output.json').exists():
        verify_job(job,role,case,dependencies); return job/'output.json'
    if (job/'launch.json').exists(): raise ValueError('Existing native launch must be reconciled before retry')
    if (job/'prompt.txt').exists() and (job/'prompt.txt').read_text()!=prompt: raise ValueError('Existing prompt differs')
    (job/'prompt.txt').write_text(prompt)
    launch={'status':'launched','started_at':time.time(),'request_sha256':digest(request),'argv_sha256':digest(argv)}
    # Exclusive creation also prevents concurrent duplicate launches.
    with (job/'launch.json').open('x') as file: json.dump(launch,file,indent=2)
    start=time.monotonic()
    with (job/'events.jsonl').open('w') as out, (job/'stderr.txt').open('w') as err:
        try:
            result=subprocess.run(argv,input=prompt,text=True,stdout=out,stderr=err,cwd=job,timeout=TIMEOUT)
        except (subprocess.TimeoutExpired,OSError) as error:
            save(job/'execution.json',{'status':'launch_uncertain','elapsed_seconds':time.monotonic()-start,
                                      'request_sha256':digest(request),'error_type':type(error).__name__})
            raise ValueError('Native launch uncertain; reconcile retained evidence before any retry') from error
    execution={'status':'returned','exit_code':result.returncode,'elapsed_seconds':time.monotonic()-start,
               'request_sha256':digest(request),'files':{name:sha(job/name) for name in
                ('events.jsonl','stderr.txt','final.txt') if (job/name).exists()}}
    # Save real process outcome before parsing or validation, including nonzero exit.
    save(job/'execution.json',execution)
    if result.returncode: raise ValueError('Native role failed; inspect retained stderr')
    capture_rollout(job)
    receipt=session_receipt(job); save(job/'session-receipt.json',receipt)
    content=parse_response((job/'final.txt').read_text())
    verify_config(run); validate_case(case)
    if any(sha(dependencies[k])!=v for k,v in dep_hashes.items()): raise ValueError('Dependency changed during execution')
    validate_content(role,content,case,dependencies)
    save(job/'output.json',{'request_sha256':digest(request),'content':content})
    verify_job(job,role,case,dependencies)
    return job/'output.json'


def execute(run):
    run=Path(run).resolve(); config=verify_config(run); case_path=config["case_path"]
    case_path=Path(case_path).resolve();run=Path(run).resolve();case=read(case_path)
    validate_case(case);run.mkdir(parents=True,exist_ok=True)
    save(run/'case.json',case)
    revision=0; authors={}; correction={}; next_roles=['extractor','commentator']
    while True:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={r:pool.submit(run_role,run,r,revision,case_path,case,correction) for r in next_roles}
            authors.update({r:f.result() for r,f in futures.items()})
        review=run_role(run,'reviewer',revision,case_path,case,authors)
        rv=read(review)['content']
        if rv['verdict']!='pass':
            if rv['verdict']=='blocked' or revision>=2:return save(run/'blocked.json',{'stage':'substantive','review':str(review),'revisions':revision})
            revision+=1;next_roles=sorted({f['target'] for f in rv['findings'] if f['target'] in authors})
            if not next_roles:raise ValueError('No author targeted for substantive revision')
            correction={'prior_review':review};continue
        while True:
            editor_deps={**authors,'substantive_review':review,**correction}
            editor=run_role(run,'editor',revision,case_path,case,editor_deps)
            report=run/f'report-r{revision}.md'
            body=read(editor)['content']['report_markdown'].strip()+'\n'
            if report.exists() and report.read_text()!=body:raise ValueError('Report overwrite refused')
            report.write_text(body)
            final=run_role(run,'final_reviewer',revision,case_path,case,{**authors,'substantive_review':review,'report':report})
            fv=read(final)['content']
            if fv['verdict']=='pass':
                validate_case(case)
                artifacts={str(p.relative_to(run)):sha(p) for p in [*authors.values(),review,editor,report,final]}
                roles={r:str(p.parent.relative_to(run)) for r,p in {**authors,'reviewer':review,'editor':editor,'final_reviewer':final}.items()}
                acceptance={'version':VERSION,'status':'accepted_local','case_sha256':digest(case),'report':str(report.relative_to(run)),'report_sha256':sha(report),'artifacts':artifacts,'roles':roles,'revisions':revision,'remote_persistence':'pending','runtime':'native-codex','config_sha256':sha(run/'config.json')}
                verify_acceptance(run, acceptance)
                save(run/'accepted.json',acceptance)
                return
            if fv['verdict']=='blocked' or revision>=2:return save(run/'blocked.json',{'stage':'final','review':str(final),'revisions':revision})
            revision+=1;correction={'prior_review':final}
            next_roles=sorted({f['target'] for f in fv['findings'] if f['target'] in authors})
            if next_roles:break


def verify_history(run, acceptance):
    """Replay the unchanged executor graph, including superseded review receipts."""
    case=read(run/'case.json'); authors={}; correction={}; revision=0
    next_roles=['extractor','commentator']; sessions=[]; visited=set()
    def job(role, rev, deps):
        path=run/f'{role}-r{rev}'
        sessions.append(verify_job(path,role,case,deps)); visited.add(path.name)
        return path/'output.json'
    while True:
        for role in next_roles: authors[role]=job(role,revision,correction)
        review=job('reviewer',revision,authors); rv=read(review)['content']
        if rv['verdict']!='pass':
            if rv['verdict']=='blocked' or revision>=2: raise ValueError('History ended without substantive acceptance')
            revision+=1
            next_roles=sorted({f['target'] for f in rv['findings'] if f['target'] in authors})
            if not next_roles: raise ValueError('No author targeted for substantive revision')
            correction={'prior_review':review}; continue
        while True:
            editor=job('editor',revision,{**authors,'substantive_review':review,**correction})
            report=run/f'report-r{revision}.md'
            if read(editor)['content']['report_markdown'].strip()+'\n'!=report.read_text():
                raise ValueError('Historical composed report changed')
            final=job('final_reviewer',revision,{**authors,'substantive_review':review,'report':report})
            fv=read(final)['content']
            if fv['verdict']=='pass':
                roles={r:str(p.parent.relative_to(run)) for r,p in
                       {**authors,'reviewer':review,'editor':editor,'final_reviewer':final}.items()}
                if acceptance['roles']!=roles or acceptance['revisions']!=revision or acceptance['report']!=report.name:
                    raise ValueError('Accepted graph differs from execution history')
                if len(set(sessions))!=len(sessions): raise ValueError('Independent role sessions required throughout history')
                if {p.parent.name for p in run.glob('*/request.json')}!=visited:
                    raise ValueError('Unaccounted role requests in native run')
                return
            if fv['verdict']=='blocked' or revision>=2: raise ValueError('History ended without final acceptance')
            revision+=1; correction={'prior_review':final}
            next_roles=sorted({f['target'] for f in fv['findings'] if f['target'] in authors})
            if next_roles: break


def verify_acceptance(run, a):
    run=Path(run).resolve(); verify_config(run)
    inside(run, run/'case.json')
    case=read(run/'case.json');validate_case(case)
    if a.get('version') != VERSION or a.get('status') != 'accepted_local' or a.get('runtime') != 'native-codex':
        raise ValueError('Unsupported acceptance receipt')
    if a.get('config_sha256') != sha(run/'config.json'): raise ValueError('Acceptance configuration changed')
    if type(a.get('revisions')) is not int or not 0<=a['revisions']<=2:
        raise ValueError('Correction budget exceeded')
    roles=a.get('roles',{})
    if set(roles)!={'extractor','commentator','reviewer','editor','final_reviewer'}:
        raise ValueError('All five accepted roles required')
    if any(Path(p).is_absolute() for p in [a['report'], *roles.values(), *a['artifacts']]):
        raise ValueError('Accepted paths must be relative to run')
    for path in [a['report'], *roles.values(), *a['artifacts']]: inside(run, path)
    if a['case_sha256']!=digest(case) or any(sha(inside(run,p))!=v for p,v in a['artifacts'].items()):
        raise ValueError('Accepted evidence/output changed')
    report = inside(run, a['report'])
    if sha(report)!=a['report_sha256']:raise ValueError('Report changed')
    required={a['report']} | {str(Path(p)/'output.json') for p in roles.values()}
    if set(a['artifacts'])!=required:raise ValueError('Exact accepted artifact set required')
    jobs = {role:inside(run, path) for role,path in roles.items()}
    sessions=[]
    revisions={}
    dependencies={}
    for role,job in jobs.items():
        if job.parent != run: raise ValueError('Role directory must be directly inside run')
        request=read(job/'request.json')
        revisions[role]=request.get('revision')
        dep_paths=read(job/'dependencies.json')
        dependencies[role]={k:inside(run,v) for k,v in dep_paths.items()}
        sessions.append(verify_job(job,role,case,dep_paths))
    if len(set(sessions))!=len(sessions):raise ValueError('Independent role sessions required')
    if any(r > a['revisions'] for r in revisions.values()) or revisions['editor']!=a['revisions'] or revisions['final_reviewer']!=a['revisions']:
        raise ValueError('Accepted revisions do not match correction budget')
    expected_authors={role:jobs[role]/'output.json' for role in ('extractor','commentator')}
    if dependencies['reviewer'] != expected_authors:
        raise ValueError('Substantive review not bound to accepted authors')
    expected_editor={**expected_authors,'substantive_review':jobs['reviewer']/'output.json'}
    actual_editor=dict(dependencies['editor'])
    correction=actual_editor.pop('prior_review',None)
    if actual_editor != expected_editor:
        raise ValueError('Editor not bound to accepted authors and review')
    if correction is not None:
        correction_request=read(correction.parent/'request.json')
        if correction.name!='output.json' or correction_request.get('role') not in {'reviewer','final_reviewer'} or correction_request.get('revision',3)>=revisions['editor']:
            raise ValueError('Invalid prior correction review')
    for role in ('extractor','commentator'):
        author_deps=dependencies[role]
        if set(author_deps)-{'prior_review'}:
            raise ValueError('Author saw another author output directly')
        if 'prior_review' in author_deps:
            req=read(author_deps['prior_review'].parent/'request.json')
            if req.get('role') not in {'reviewer','final_reviewer'} or req.get('revision',3)>=revisions[role]:
                raise ValueError('Invalid author correction dependency')
    rv=read(jobs['reviewer']/'output.json')['content']
    fv=read(jobs['final_reviewer']/'output.json')['content']
    if rv['verdict']!='pass' or fv['verdict']!='pass':raise ValueError('Both reviews must pass')
    expected_final={**expected_editor,'report':report}
    if dependencies['final_reviewer']!=expected_final:
        raise ValueError('Final review not bound to accepted sources/outputs')
    if read(jobs['editor']/'output.json')['content']['report_markdown'].strip()+'\n' != report.read_text():
        raise ValueError('Composed report changed')
    verify_history(run,a)
    return {'status':'verified_local','report':str(report),'revisions':a['revisions']}



def verify(run):
    run=Path(run).resolve()
    return verify_acceptance(run,read(inside(run,'accepted.json')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--case',required=True)
    prep.add_argument('--prime-run',required=True); prep.add_argument('--output',required=True)
    prep.add_argument('--codex',required=True)
    for name in ('run','verify'):
        sub.add_parser(name).add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        prepare(args.case,args.prime_run,args.output,args.codex)
        print('Native configuration prepared; no role launched.')
    elif args.command=='run': execute(args.output)
    else: print(json.dumps(verify(args.output),indent=2))


if __name__=='__main__': main()
