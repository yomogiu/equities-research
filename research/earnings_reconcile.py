"""Reconcile an already completed role journal after its headless CLI timed out.

No model is called. Original failure receipts and stdout remain untouched. This
adapter verifies journal completion honestly, without asserting CLI exit zero.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from . import earnings_experiment as base
from . import earnings_recovery as recovery

VERSION = 'earnings-journal-reconciliation-v1'
FILES = ('request.json','dependencies.json','prompt.txt','launch.json','execution.json','stdout.txt','stderr.txt')


def inspect(job, case, dependencies, inactive_path):
    job=Path(job).resolve(); run=job.parent; base.validate_case(case)
    request=base.read(job/'request.json'); launch=base.read(job/'launch.json'); execution=base.read(job/'execution.json')
    role=request.get('role'); revision=request.get('revision')
    if role not in {'extractor','commentator','reviewer','editor','final_reviewer'} or type(revision) is not int or not 0<=revision<=2 or job.name!=f'{role}-r{revision}':
        raise ValueError('Explicit valid role revision required')
    if request.get('case_sha256')!=base.digest(case) or launch.get('request_sha256')!=base.digest(request):
        raise ValueError('Case or launch request binding differs')
    if execution.get('status')!='launch_uncertain' or 'exit_code' in execution or (job/'stdout.txt').read_bytes():
        raise ValueError('Only uncertain empty-stdout CLI execution can be reconciled')
    for path in dependencies.values():base.inside(run,path)
    if request.get('dependencies')!={k:base.sha(v) for k,v in dependencies.items()} or request.get('prompt_sha256')!=base.sha(job/'prompt.txt'):
        raise ValueError('Original dependencies or prompt changed')
    paths=list((job/'sessions').rglob('*.jsonl'))
    if len(paths)!=1:raise ValueError('Exactly one original role session required')
    path=base.inside(job,paths[0]); events=recovery.entries(path)
    heads=[e for e in events if e.get('type')=='session'];msgs=recovery.messages(events)
    users=[m for m in msgs if m.get('role')=='user']
    if len(heads)!=1 or not heads[0].get('id') or len(users)!=1 or base.message_text(users[0])!=(job/'prompt.txt').read_text():
        raise ValueError('Original single-user session identity and prompt required')
    if not msgs or msgs[-1].get('role')!='assistant' or msgs[-1].get('stopReason')!='stop':
        raise ValueError('Journal lacks terminal completed assistant response')
    final=msgs[-1]
    final_event=[e for e in events if e.get('type')=='message'][-1]
    try:
        completed=datetime.fromisoformat(final_event['timestamp'].replace('Z','+00:00')).timestamp()
    except (KeyError,ValueError,TypeError,AttributeError):
        raise ValueError('Outer journal event completion timestamp required') from None
    timeout_at=launch['started_at']+execution['elapsed_seconds']
    if final.get('provider')!='openai-codex':raise ValueError('Approved subscription provider required')
    inactive_path=base.inside(job,inactive_path);inactive=base.read(inactive_path)
    if inactive.get('command')!=['prime-agent','list','--json'] or inactive.get('exit_code')!=0 or inactive.get('observed_at',0)<launch['started_at']+execution['elapsed_seconds']:
        raise ValueError('Post-timeout successful runtime observation required')
    if not launch['started_at']<=completed<=inactive['observed_at']:
        raise ValueError('Journal completion must precede the inactive runtime observation')
    list_path=base.inside(job,inactive.get('stdout_path','runtime-list.json'))
    if base.sha(list_path)!=inactive['stdout_sha256'] or base.read(list_path)!={'sessions':[]}:
        raise ValueError('Runtime must have no active sessions at reconciliation')
    text=base.message_text(final);content=base.parse_response(text)
    base.validate_content(role,content,case,dependencies)
    return {'session_id':heads[0]['id'],'session_path':str(path.relative_to(job)),
            'session_sha256':base.sha(path),'completed_at':completed,
            'cli_timeout_at':timeout_at,'late_completion_after_timeout':completed>timeout_at,
            'completion_delay_after_timeout_seconds':max(0.0,completed-timeout_at),
            'completion_timestamp_source':'outer_final_message_event',
            'provider':final['provider'],'model':final.get('model'),
            'inactive_path':str(inactive_path.relative_to(job)), 'inactive_sha256':base.sha(inactive_path),
            'list_path':str(list_path.relative_to(job)),'list_sha256':base.sha(list_path)},text,content


def reconcile(run, job_name, inactive_path):
    run=Path(run).resolve();job=base.inside(run,job_name)
    if job.parent!=run:raise ValueError('Role must be directly under run')
    if (job/'reconciliation.json').exists() or (job/'output.json').exists():
        raise ValueError('Existing reconciliation or output requires verification, not replacement')
    case=base.read(run/'case.json');deps=base.read(job/'dependencies.json')
    receipt,text,content=inspect(job,case,deps,inactive_path)
    # Retain the exact existing final message, independently of normalized output.json.
    (job/'journal-final.txt').write_text(text)
    record={'version':VERSION,'status':'journal_reconciled','job':job.name,
            'case_sha256':base.digest(case),'request_sha256':base.digest(base.read(job/'request.json')),
            'module_sha256':base.sha(__file__),'base_module_sha256':base.sha(base.__file__),
            'recovery_module_sha256':base.sha(recovery.__file__),
            'originals':{n:base.sha(job/n) for n in FILES},'journal_final_sha256':base.sha(job/'journal-final.txt'),
            'evidence':receipt,'original_cli_status':'launch_uncertain','original_cli_exit_code':None,
            'new_model_calls':0}
    base.save(job/'reconciliation.json',record)
    base.save(job/'output.json',{'request_sha256':record['request_sha256'],'content':content})
    verify_job(job,base.read(job/'request.json')['role'],case,deps)


def verify_job(job,role,case,dependencies):
    job=Path(job).resolve();record=base.read(job/'reconciliation.json')
    if record.get('version')!=VERSION or record.get('status')!='journal_reconciled' or record.get('job')!=job.name or record.get('original_cli_status')!='launch_uncertain' or record.get('original_cli_exit_code') is not None or record.get('new_model_calls')!=0:
        raise ValueError('Honest journal reconciliation receipt required')
    if record.get('module_sha256')!=base.sha(__file__) or record.get('base_module_sha256')!=base.sha(base.__file__) or record.get('recovery_module_sha256')!=base.sha(recovery.__file__) or record.get('case_sha256')!=base.digest(case):
        raise ValueError('Reconciliation code or case changed')
    if set(record['originals'])!=set(FILES) or any(base.sha(base.inside(job,n))!=h for n,h in record['originals'].items()):
        raise ValueError('Original uncertain attempt changed')
    request=base.read(job/'request.json');output=base.read(job/'output.json')
    if request['role']!=role or record['request_sha256']!=base.digest(request) or output['request_sha256']!=base.digest(request):
        raise ValueError('Reconciled request binding differs')
    evidence,text,content=inspect(job,case,dependencies,record['evidence']['inactive_path'])
    if evidence!=record['evidence'] or base.sha(job/'journal-final.txt')!=record['journal_final_sha256'] or (job/'journal-final.txt').read_text()!=text or output['content']!=content:
        raise ValueError('Reconciled terminal output or evidence changed')
    return evidence['session_id']


@contextmanager
def adapter(run):
    run=Path(run).resolve()
    with recovery.adapter(run):
        original=base.verify_job
        def scoped(job,role,case,dependencies):
            job=Path(job).resolve()
            if job.parent==run and (job/'reconciliation.json').exists():
                return verify_job(job,role,case,dependencies)
            return original(job,role,case,dependencies)
        base.verify_job=scoped
        try:yield
        finally:base.verify_job=original


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['reconcile','continue','verify'])
    p.add_argument('--output',required=True);p.add_argument('--job');p.add_argument('--inactive');p.add_argument('--case')
    a=p.parse_args()
    if a.command=='reconcile':
        if not a.job or not a.inactive:p.error('reconcile requires --job and --inactive')
        reconcile(a.output,a.job,a.inactive)
    else:
        with adapter(a.output):
            if a.command=='verify':print(json.dumps(base.verify(a.output),indent=2))
            else:
                if not a.case:p.error('continue requires original --case')
                base.execute(a.case,a.output)


if __name__=='__main__':main()
