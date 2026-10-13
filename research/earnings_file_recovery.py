"""Replay a known local pre-provider budget stop; never retry an unknown launch."""
from pathlib import Path
from . import earnings_mixed_runner as base

VERSION='authenticated-file-preparation-recovery-v1'


def failed_usage(job):
    import json
    job=Path(job).resolve();q=base.read(job/'request.json');execution=base.read(job/'execution.json')
    if execution['status']!='execution_failed' or execution['exit_code']!=1 or execution['request_sha256']!=base.digest(q):raise ValueError('Known failed execution required')
    paths=list((job/'sessions').glob('*.jsonl'))
    if len(paths)!=1:raise ValueError('One recorded attempt required')
    events=[json.loads(x) for x in paths[0].read_text().splitlines() if x.strip()]
    messages=[x['message'] for x in events if x.get('type')=='message']
    if not messages or messages[-1].get('role')!='assistant' or messages[-1].get('stopReason')!='error' or messages[-1].get('errorMessage')!='role_budget':raise ValueError('Only proven local budget stop is recoverable')
    if messages[-1].get('usage',{}).get('totalTokens')!=0:raise ValueError('Failed pre-provider turn must have zero usage')
    calls={};results=set();tokens=0;turns=0
    for m in messages:
        if m.get('role')=='assistant' and m is not messages[-1]:
            if m.get('stopReason')!='toolUse' or m.get('model')!=q['model'] or m.get('provider')!=q['provider']:raise ValueError('Incomplete or changed provider attempt')
            u=m['usage'];keys=('input','output','cacheRead','cacheWrite')
            if any(type(u.get(k)) is not int or u[k]<0 for k in (*keys,'totalTokens')) or sum(u[k] for k in keys)!=u['totalTokens']:raise ValueError('Complete measured usage required')
            tokens+=u['totalTokens'];turns+=1
            for b in m['content']:
                if b['type']=='toolCall':
                    if b['name']!='ipython' or b['id'] in calls:raise ValueError('Bounded distinct tools required')
                    calls[b['id']]=b
        elif m.get('role')=='toolResult':
            if m.get('toolName')!='ipython' or m['toolCallId'] not in calls or m['toolCallId'] in results:raise ValueError('Tool result mismatch')
            results.add(m['toolCallId'])
    if set(calls)!=results or len(base.read(job/'wire.json'))!=turns or tokens>q['max_tokens']:raise ValueError('Closed attempt with complete wire/usage required')
    return tokens


def verify(path):
    path=Path(path).resolve();v=base.read(path)
    if v.get('version')!=VERSION or v.get('new_experiment') is not False or v.get('original_max_tokens')!=1200000 or v.get('prior_correction_rounds')!=0:raise ValueError('Recovery cannot reset lifecycle budget or correction rounds')
    for name,h in v['source_sha256'].items():
        p=Path(name)
        if p.is_symlink() or base.sha(p)!=h:raise ValueError('Recovery ancestor changed')
    old=base.read(v['source_request']);spec=old['spec']
    if old['run_id']!=base.digest(spec)[:24] or v['source_request_sha256']!=base.digest(old):raise ValueError('Recovery ancestor identity changed')
    if v['kind']=='local_budget_stop':
        job=Path(v['failed_job']);jobs=list(job.parent.iterdir())
        if len(jobs)!=1 or job.name!='financial' or (job/'output.json').exists():raise ValueError('Only closed first-role preparation can recover')
        tokens=failed_usage(job)
    elif v['kind']=='reviewed_sidecar_compatibility':
        state=base.read(Path(v['source_request']).parent/'state.json')
        if state.get('status')!='needs_attention' or state.get('reason')!='Generated coverage implementation changed':raise ValueError('Exact sidecar preparation hold required')
        if list(Path(v['source_request']).parent.glob('**/jobs/**/request.json')):raise ValueError('Sidecar hold must precede model execution')
        tokens=0
    else:raise ValueError('Unknown recovery kind')
    if v['inherited_tokens']!=tokens or not 0<=tokens<1200000:raise ValueError('Inherited usage differs')
    return v
