"""Verify one bounded same-session resume after an authentic native r2 timeout.

The original timeout remains a failure receipt. This adapter never launches a
resume. It authenticates the retained resumed execution, fully validates its final
content, and composes both historical schema adapters without adding a revision.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
from . import earnings_experiment as base
from . import earnings_native as native
from . import earnings_native_recovery as initial
from . import earnings_native_revision_recovery as revision

VERSION='earnings-native-timeout-recovery-v1'
JOB='commentator-r2'
RECEIPT='timeout-recovery.json'
ORIGINALS=('request.json','dependencies.json','prompt.txt','launch.json','execution.json','events.jsonl','stderr.txt','session.jsonl')
RECOVERY_FILES=('request.json','launch.json','prompt.txt','inactive-before-resume.json','events.jsonl','stderr.txt','final.txt','execution.json','session.jsonl','cap-policy.json','cap-observation.json')


def entries(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def message_text(message):
    return ''.join(x.get('text','') for x in message.get('content',[]) if x.get('type') in {'input_text','output_text','text'})


def task_users(events):
    users=[e['payload'] for e in events if e.get('type')=='response_item' and e.get('payload',{}).get('type')=='message' and e['payload'].get('role')=='user']
    return [message_text(m) for m in users if not message_text(m).startswith('<environment_context>')]


def cumulative_usage(events):
    tokens=[e['payload'].get('info',{}).get('total_token_usage') for e in events
            if e.get('type')=='event_msg' and e.get('payload',{}).get('type')=='token_count' and e['payload'].get('info')]
    if not tokens or not isinstance(tokens[-1],dict):raise ValueError('Observed cumulative rollout token usage required')
    value=tokens[-1]
    if not {'input_tokens','cached_input_tokens','output_tokens','total_tokens'}<=set(value) or any(type(v) is not int or v<0 for v in value.values()):
        raise ValueError('Invalid cumulative rollout token usage')
    return value


def verify_rollout(job,sid,config):
    recovery=job/'recovery';before_bytes=(job/'session.jsonl').read_bytes();after_bytes=(recovery/'session.jsonl').read_bytes()
    if after_bytes==before_bytes or not after_bytes.startswith(before_bytes):raise ValueError('Resumed rollout must append to the unchanged original snapshot')
    before=entries(job/'session.jsonl');after=entries(recovery/'session.jsonl')
    if task_users(before)!=[(job/'prompt.txt').read_text()] or task_users(after)!=[(job/'prompt.txt').read_text(),(recovery/'prompt.txt').read_text()]:
        raise ValueError('Exactly original task plus one actual continuation required')
    heads=[e['payload'] for e in after if e.get('type')=='session_meta']
    if not heads or any(h.get('id')!=sid or h.get('model_provider')!='openai' or h.get('cli_version')!=config['codex_version'].split()[-1] for h in heads):
        raise ValueError('Resumed session identity/provider/CLI version differs')
    contexts=[e['payload'] for e in after if e.get('type')=='turn_context']
    appended_contexts=[e for e in after[len(before):] if e.get('type')=='turn_context']
    if not contexts or not appended_contexts or any(c.get('model')!=native.MODEL or c.get('effort')!=native.EFFORT or c.get('sandbox_policy',{}).get('type')!='read-only' for c in contexts):
        raise ValueError('Observed resumed model/effort/sandbox differs')
    assistants=[e['payload'] for e in after if e.get('type')=='response_item' and e.get('payload',{}).get('type')=='message' and e['payload'].get('role')=='assistant']
    final=(recovery/'final.txt').read_text()
    if not assistants or assistants[-1].get('phase')!='final_answer' or final not in {message_text(assistants[-1]),message_text(assistants[-1])+'\n'}:
        raise ValueError('Resumed final output differs from completed assistant message')
    before_usage=cumulative_usage(before);after_usage=cumulative_usage(after)
    if set(before_usage)!=set(after_usage) or any(after_usage[k]<v for k,v in before_usage.items()):raise ValueError('Cumulative token usage regressed or changed schema')
    return {'model':native.MODEL,'reasoning_effort':native.EFFORT,'model_provider':'openai',
            'cli_version':heads[-1]['cli_version'],'sandbox_policy':contexts[-1]['sandbox_policy'],
            'approval_policy':contexts[-1].get('approval_policy'),
            'usage':{'scope':'cumulative same-session rollout; do not add resume CLI usage to these totals',
                     'before_resume_cumulative':before_usage,'after_resume_cumulative':after_usage,
                     'resume_increment':{k:after_usage[k]-v for k,v in before_usage.items()}}}


def inspect(run):
    run=Path(run).resolve();config=native.verify_config(run);revision.policy(run);revision.revision_review(run)
    job=base.inside(run,JOB);recovery=base.inside(job,'recovery');case=base.read(run/'case.json')
    for name in ORIGINALS:base.inside(job,name)
    for name in RECOVERY_FILES:base.inside(recovery,name)
    request=base.read(job/'request.json');launch=base.read(job/'launch.json');execution=base.read(job/'execution.json')
    deps={'prior_review':str(run/'reviewer-r1'/'output.json')}
    expected_prompt=base.role_prompt('commentator',config['case_path'],case,deps,2)
    argv=native.command(config['codex'],job)
    if (request.get('version')!=native.VERSION or request.get('role')!='commentator' or request.get('revision')!=2
            or request.get('case_sha256')!=base.digest(case) or request.get('config_sha256')!=base.sha(run/'config.json')
            or request.get('dependencies')!={k:base.sha(v) for k,v in deps.items()} or base.read(job/'dependencies.json')!=deps
            or (job/'prompt.txt').read_text()!=expected_prompt or request.get('prompt_sha256')!=base.sha(job/'prompt.txt')
            or request.get('argv')!=argv or request.get('argv_sha256')!=base.digest(argv)):
        raise ValueError('Original r2 request, prompt, configuration or dependencies changed')
    if launch.get('status')!='launched' or launch.get('request_sha256')!=base.digest(request) or launch.get('argv_sha256')!=base.digest(argv) or not finite(launch.get('started_at')):
        raise ValueError('Original native launch binding changed')
    if (execution.get('status')!='launch_uncertain' or execution.get('error_type')!='TimeoutExpired'
            or 'exit_code' in execution or execution.get('request_sha256')!=base.digest(request)
            or not finite(execution.get('elapsed_seconds')) or execution['elapsed_seconds']<native.TIMEOUT):
        raise ValueError('Original real timeout receipt must remain unchanged')
    original_events=entries(job/'events.jsonl');heads=[e for e in original_events if e.get('type')=='thread.started']
    if len(heads)!=1 or not heads[0].get('thread_id') or any(e.get('type')=='turn.completed' for e in original_events):
        raise ValueError('Original attempt must have one thread and no completed turn')
    sid=heads[0]['thread_id'];req=base.read(recovery/'request.json');start=base.read(recovery/'launch.json');result=base.read(recovery/'execution.json')
    resume_argv=list(argv[:-1]);resume_argv[resume_argv.index('-o')+1]=str(recovery/'final.txt')
    resume_argv+=['resume','--json','-o',str(recovery/'final.txt'),sid,'-']
    original_files={name:base.sha(job/name) for name in ORIGINALS}
    if (req.get('session_id')!=sid or req.get('model')!=native.MODEL or req.get('reasoning_effort')!=native.EFFORT
            or req.get('argv')!=resume_argv or req.get('timeout_seconds')!=native.TIMEOUT
            or req.get('prompt_sha256')!=base.sha(recovery/'prompt.txt') or not (recovery/'prompt.txt').read_text().strip()
            or req.get('original_request_sha256')!=base.sha(job/'request.json')
            or req.get('original_session_sha256')!=base.sha(job/'session.jsonl') or req.get('original_files')!=original_files):
        raise ValueError('Bounded same-session resume request changed')
    if start.get('request_sha256')!=base.digest(req) or start.get('argv_sha256')!=base.digest(resume_argv) or not finite(start.get('started_at')):
        raise ValueError('Resume launch binding changed')
    inactive=base.read(recovery/'inactive-before-resume.json')
    if (inactive.get('session_id')!=sid or inactive.get('matching_original_role_pids')!=[] or not finite(inactive.get('checked_at'))
            or not launch['started_at']+execution['elapsed_seconds']<=inactive['checked_at']<=start['started_at']):
        raise ValueError('Post-timeout inactive original-process observation required')
    if (result.get('status')!='returned' or result.get('exit_code')!=0 or result.get('request_sha256')!=base.digest(req)
            or not finite(result.get('elapsed_seconds')) or not 0<=result['elapsed_seconds']<=605
            or not finite(result.get('completed_at')) or result['completed_at']<start['started_at']):
        raise ValueError('Actual successful bounded resume execution required')
    cap=base.read(recovery/'cap-policy.json'); observation=base.read(recovery/'cap-observation.json')
    if (cap.get('effective_timeout_seconds')!=600 or cap.get('original_requested_timeout_seconds')!=900
            or cap.get('request_sha256')!=base.digest(req) or cap.get('deadline')!=start['started_at']+600
            or not finite(cap.get('recorded_at')) or not start['started_at']<=cap['recorded_at']<=cap['deadline']
            or not cap.get('reason') or result['completed_at']>cap['deadline']+5):
        raise ValueError('Explicit effective 600-second resume cap required')
    if (observation.get('effective_timeout_seconds')!=600 or observation.get('execution_receipt_present') is not True
            or observation.get('terminated_exact_resume_pids')!=[] or observation.get('cap_policy_sha256')!=base.sha(recovery/'cap-policy.json')
            or not finite(observation.get('checked_at')) or observation['checked_at']<result['completed_at']):
        raise ValueError('Successful post-completion cap observation required')
    for name in ('events.jsonl','stderr.txt','final.txt'):
        if result.get('files',{}).get(name)!=base.sha(recovery/name):raise ValueError('Resume execution capture changed')
    events=entries(recovery/'events.jsonl');rheads=[e for e in events if e.get('type')=='thread.started'];starts=[e for e in events if e.get('type')=='turn.started'];ends=[e for e in events if e.get('type')=='turn.completed']
    if len(rheads)!=1 or rheads[0].get('thread_id')!=sid or len(starts)!=1 or len(ends)!=1 or events[-1]!=ends[0] or any(e.get('type') in {'error','turn.failed'} for e in events):
        raise ValueError('Exactly one successful resume turn on the original thread required')
    usage=ends[0].get('usage')
    if not isinstance(usage,dict) or not {'input_tokens','cached_input_tokens','output_tokens'}<=set(usage) or any(type(v) is not int or v<0 for v in usage.values()):raise ValueError('Observed resume CLI token usage required')
    messages=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    final=(recovery/'final.txt').read_text()
    if not messages or final not in {messages[-1].get('text'),str(messages[-1].get('text'))+'\n'}:raise ValueError('Resume event final differs from captured output')
    observed=verify_rollout(job,sid,config)
    if any(observed['usage']['after_resume_cumulative'].get(k)!=v for k,v in usage.items()):raise ValueError('Resume CLI usage must match observed cumulative rollout counters')
    observed['usage']['resume_cli_turn_completed']=usage
    content=base.parse_response(final);base.validate_content('commentator',content,case,deps)
    receipt={'version':VERSION,'job':JOB,'status':'same_session_resume_verified','session_id':sid,
             'adapter_sha256':base.sha(__file__),'native_sha256':base.sha(native.__file__),
             'initial_adapter_sha256':base.sha(initial.__file__),'revision_adapter_sha256':base.sha(revision.__file__),
             'initial_receipt_sha256':base.sha(run/initial.RECEIPT),'revision_receipt_sha256':base.sha(run/revision.RECEIPT),
             'config_sha256':base.sha(run/'config.json'),'case_sha256':base.digest(case),
             'originals':original_files,'recovery_files':{n:base.sha(recovery/n) for n in RECOVERY_FILES},
             'content_sha256':base.digest(content),'maximum_resumes':1,'resume_timeout_seconds':600,'original_requested_timeout_seconds':900,
             'shared_correction_rounds':2,'revision':2,'observed':observed,
             'intervention':'Original resume request retained at 900 seconds, explicitly capped at 600 by a recorded watchdog policy. One bounded continuation of the original timed-out r2 session; original failure retained, no new quality revision and no content-validation exception.'}
    return receipt,content


def common_session_receipt(receipt):
    observed=receipt['observed'];usage=observed['usage']
    return {k:v for k,v in observed.items() if k!='usage'} | {
            'id':receipt['session_id'],'path':'recovery/session.jsonl',
            'session_sha256':receipt['recovery_files']['session.jsonl'],
            'usage':usage['resume_cli_turn_completed'],
            'usage_scope':'Cumulative same-session after resume, counted once; unreported timeout partial tokens remain possible.',
            'before_resume_cumulative':usage['before_resume_cumulative'],
            'after_resume_cumulative':usage['after_resume_cumulative'],
            'resume_increment':usage['resume_increment'],
            'resume_cli_usage':usage['resume_cli_turn_completed'],
            'resume_cli_usage_scope':'Raw turn.completed counters retained separately; never added to cumulative totals.'}


def prepare(run):
    run=Path(run).resolve()
    if (run/RECEIPT).exists():return policy(run)
    if (run/'accepted.json').exists():raise ValueError('Cannot add recovery to an accepted run')
    receipt,content=inspect(run);job=run/JOB
    base.save(job/'recovery'/'session-receipt.json',receipt['observed']|{'id':receipt['session_id']})
    base.save(job/'session-receipt.json',common_session_receipt(receipt))
    base.save(job/'output.json',{'request_sha256':base.digest(base.read(job/'request.json')),'content':content})
    base.save(run/RECEIPT,receipt)
    return policy(run)


def policy(run):
    run=Path(run).resolve();saved=base.read(base.inside(run,RECEIPT));receipt,content=inspect(run)
    if saved!=receipt:raise ValueError('Frozen timeout recovery receipt changed')
    if base.read(run/JOB/'recovery'/'session-receipt.json')!=receipt['observed']|{'id':receipt['session_id']}:raise ValueError('Timeout recovery session receipt changed')
    if base.read(run/JOB/'session-receipt.json')!=common_session_receipt(receipt):raise ValueError('Recovered common session receipt changed')
    expected={'request_sha256':base.digest(base.read(run/JOB/'request.json')),'content':content}
    if base.read(run/JOB/'output.json')!=expected:raise ValueError('Recovered output differs from actual resumed final')
    return receipt


@contextmanager
def adapter(run,creating_acceptance=False):
    run=Path(run).resolve();policy(run)
    with revision.adapter(run,creating_acceptance=creating_acceptance):
        original_verify=native.verify_job;original_acceptance=native.verify_acceptance
        def verify_job(job,role,case,deps):
            if Path(job).resolve()!=run/JOB:return original_verify(job,role,case,deps)
            receipt=policy(run)
            if role!='commentator' or base.digest(case)!=receipt['case_sha256'] or {k:str(v) for k,v in deps.items()}!={'prior_review':str(run/'reviewer-r1'/'output.json')}:
                raise ValueError('Timeout recovery role, case or dependencies differ')
            return receipt['session_id']
        def acceptance(target,value):
            if Path(target).resolve()!=run:raise ValueError('Timeout recovery cannot verify another run')
            policy(run)
            if value.get('roles',{}).get('commentator')!=JOB or value.get('revisions')!=2:raise ValueError('Timeout recovery cannot reset the correction budget')
            binding=base.sha(run/RECEIPT)
            if creating_acceptance and 'timeout_recovery_sha256' not in value:value['timeout_recovery_sha256']=binding
            if value.get('timeout_recovery_sha256')!=binding:raise ValueError('Acceptance lacks timeout recovery binding')
            return original_acceptance(target,value)
        native.verify_job=verify_job;native.verify_acceptance=acceptance
        try:yield
        finally:native.verify_job=original_verify;native.verify_acceptance=original_acceptance


def execute(run):
    with adapter(run,creating_acceptance=True):native.execute(run)


def verify(run):
    with adapter(run):return native.verify(run)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','run','verify']);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.output);print('Existing bounded resume verified; no role launched.')
    elif args.command=='run':execute(args.output)
    else:print(json.dumps(verify(args.output),indent=2))


if __name__=='__main__':main()
