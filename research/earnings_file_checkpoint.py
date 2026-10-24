"""Data-only role checkpoints; fresh contexts resume only proven closed attempts."""
from pathlib import Path
import json
from . import earnings_mixed_runner as base, earnings_file_context as context

VERSION='file-role-checkpoint-v1'
MAX_RESUMES=2


def save(job,draft,pending):
    job=Path(job).resolve();q=base.read(job/'request.json')
    if not isinstance(draft,dict) or len(json.dumps(draft,allow_nan=False).encode())>12000:raise ValueError('Checkpoint draft must be an object of at most 12KB')
    if not isinstance(pending,list) or not pending or any(not isinstance(x,str) or not x.strip() or len(x)>500 for x in pending) or len(pending)>16:raise ValueError('Explicit bounded pending work required')
    entries=context.audit(q['context_index'],job/'retrieval.jsonl')
    value={'version':VERSION,'job':str(job),'request_sha256':base.sha(job/'request.json'),
           'context_sha256':q['context_sha256'],'bindings':q['bindings'],
           'retrieval_count':len(entries),'retrieval_sha256':base.digest(entries),
           'draft':draft,'pending':pending,'status':'unreviewed_partial_work'}
    directory=job/'checkpoints';directory.mkdir(exist_ok=True)
    existing=sorted(directory.glob('*.json'))
    if existing:
        last=base.read(existing[-1])
        if last['draft']==draft and last['pending']==pending and last['retrieval_sha256']==value['retrieval_sha256']:return {'checkpoint':str(existing[-1]),'sha256':base.sha(existing[-1])}
    path=directory/f'{len(existing)+1:04d}.json';context.write(path,value)
    return {'checkpoint':str(path),'sha256':base.sha(path)}


def validate(path):
    path=Path(path).resolve();v=base.read(path);job=Path(v['job']);q=base.read(job/'request.json')
    if path.parent!=job/'checkpoints' or v['version']!=VERSION or v['status']!='unreviewed_partial_work':raise ValueError('Exact data checkpoint required')
    if v['request_sha256']!=base.sha(job/'request.json') or v['context_sha256']!=q['context_sha256'] or v['bindings']!=q['bindings']:raise ValueError('Checkpoint dependencies changed')
    context.Evidence(q['context_index'],job/'retrieval.jsonl')
    entries=context.audit(q['context_index'],job/'retrieval.jsonl',count=v['retrieval_count'])
    if len(entries)!=v['retrieval_count'] or base.digest(entries)!=v['retrieval_sha256']:raise ValueError('Checkpoint source progress changed')
    return v


def closed(job):
    """Reject timeout, unknown provider failures, open calls and altered code."""
    from . import earnings_file_recovery as recovery, earnings_file_runner as runner
    job=Path(job);q=base.read(job/'request.json');failure=base.read(job/'runtime-failure.json')
    if failure.get('code') not in ('role_budget','checkpoint_yield'):raise ValueError('Unknown failure cannot resume')
    runner.verify_request(job,q)
    tokens=recovery.failed_usage(job,allowed_codes=('role_budget','checkpoint_yield'))
    events=[json.loads(x) for x in next((job/'sessions').rglob('*.jsonl')).read_text().splitlines() if x.strip()]
    heads=[x for x in events if x.get('type')=='session']
    if len(heads)!=1 or heads[0].get('parentSession') or Path(heads[0].get('cwd','')).resolve()!=job.resolve():raise ValueError('Fresh failed session required')
    if any(x.get('type') in ('compaction','branch_summary') for x in events):raise ValueError('Unexpected failed context mutation')
    runner.verify_wire(q,base.read(job/'wire.json'),[x['message'] for x in events if x.get('type')=='message'])
    messages=[x['message'] for x in events if x.get('type')=='message']
    if base._text(messages[0])!=(job/'prompt.md').read_text() or sum(m.get('role')=='user' for m in messages)!=1:raise ValueError('Failed instruction binding changed')
    if (job/'resume.json').exists():
        ancestor=Path(base.read(job/'resume.json')['failed_job'])
        prior=[json.loads(x) for x in next((ancestor/'sessions').rglob('*.jsonl')).read_text().splitlines() if x.strip()]
        if heads[0]['id'] in {x.get('id') for x in prior if x.get('type')=='session'}:raise ValueError('Resume must use a fresh session')
    runner.verify_delivery(job,messages)
    context.audit(q['context_index'],job/'retrieval.jsonl')
    return tokens


def select(job):
    """Choose a sibling attempt; old requests and sessions are never rewritten."""
    original=Path(job).resolve();current=original;spent=0;previous=None
    for number in range(MAX_RESUMES+1):
        if not (current/'request.json').exists() or (current/'output.json').exists():return current,spent,previous
        spent+=closed(current)
        checkpoints=sorted((current/'checkpoints').glob('*.json'))
        if not checkpoints or number==MAX_RESUMES:return current,spent,None
        chosen=checkpoints[-1];v=validate(chosen)
        if previous:
            old=validate(previous['checkpoint'])
            if v['draft']==old['draft'] and v['pending']==old['pending'] and v['retrieval_sha256']==old['retrieval_sha256']:return current,spent,None
        record={'checkpoint':str(chosen),'sha256':base.sha(chosen),'failed_job':str(current),
                'failed_usage':closed(current),'number':number+1}
        following=original.with_name(original.name+'--resume-'+str(number+1))
        if following.exists() and base.read(following/'resume.json')!=record:raise ValueError('Immutable resume lineage changed')
        previous=record;current=following
    raise ValueError('Resume bound exceeded')


def restore(job):
    job=Path(job);r=base.read(job/'resume.json')
    if base.sha(r['checkpoint'])!=r['sha256'] or closed(r['failed_job'])!=r['failed_usage']:raise ValueError('Resume ancestor changed')
    v=validate(r['checkpoint']);q=base.read(job/'request.json');old_job=Path(r['failed_job']);old=base.read(old_job/'request.json')
    previous=base.read(old_job/'resume.json')['number'] if (old_job/'resume.json').exists() else 0
    if type(r['number']) is not int or r['number']!=previous+1 or not 1<=r['number']<=MAX_RESUMES or old_job.parent!=job.parent or job==old_job:raise ValueError('Bounded sibling lineage required')
    if q['max_tokens']>old['max_tokens']-r['failed_usage']:raise ValueError('Recovery cannot increase remaining token allowance')
    if q['bindings']!=old['bindings'] or q['context_sha256']!=old['context_sha256'] or q['model']!=old['model'] or q['effort']!=old['effort']:raise ValueError('Cross-role or changed-context resume forbidden')
    return v


def entries(job, count=None):
    """Reuse inspected sources only within the identical role and candidate."""
    job=Path(job);q=base.read(job/'request.json');previous=[]
    if (job/'resume.json').exists():
        v=restore(job);r=base.read(job/'resume.json')
        previous=entries(Path(r['failed_job']),count=v['retrieval_count'])
    current=context.audit(q['context_index'],job/'retrieval.jsonl',count=count)
    return previous+context.delivered_entries(job,current)


def capture(job):
    """Host-owned checkpoint of delivered progress; never invent author prose."""
    job=Path(job).resolve();q=base.read(job/'request.json')
    if not (job/'retrieval.jsonl').exists():
        return {'status':'no_evidence_progress'}
    observed=entries(job)
    if not observed:return {'status':'no_evidence_progress'}
    paths=sorted((job/'checkpoints').glob('*.json'))
    last=validate(paths[-1]) if paths else None
    if last and last['draft'].get('kind')!='source_progress_only':
        draft=last['draft'];pending=last['pending']
    else:
        scopes=context.complete_ranges(observed,'scope','id')
        scopes.update(x for e in observed if e['method'] in ('filing_batch','challenge_batch') for x in e['ids'])
        call_scopes,call_files=context.inspected_call(q['context_index'],observed)
        support_scopes,handoff_files,support_rows=context.inspected_role_batches(q['context_index'],observed)
        scopes.update(call_scopes);scopes.update(support_scopes)
        draft={'kind':'source_progress_only','role':q['bindings'].get('role'),
               'notice':'Delivered source progress only; no authored prose or analytical conclusions are saved.',
               'source_ids':sorted(scopes)[:64],'source_count':len(scopes),
               'event_count':len(observed),'event_sha256':base.digest(observed)}
        pending=['Complete the assigned role using original evidence. Inspect material source text needed for interpretation; the saved progress is not an authored draft or approval.']
    saved=save(job,draft,pending)
    return {'status':'saved',**saved}
