"""Fresh Prime/IPython sessions with Markdown prompts and immutable tool receipts."""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
import sys
from . import earnings_mixed_runner as old, earnings_file_context as context

VERSION='file-prime-role-v1'
HELPER=Path(__file__).with_name('earnings_file_prime.mjs')
DELIVERY=HELPER.with_name('earnings_file_delivery.mjs')
USAGE=('input','output','cacheRead','cacheWrite','totalTokens')


def work_plan(role,index):
    """Reserve evidence, metadata and pre-submit validation, bounded at 8."""
    if role not in ('financial','retrieval','analysis','signal_author','review','correction'):return None
    reader=context.Evidence(index,Path(index).parent/'unused-plan.jsonl',_replay=True)
    # Handoff packets already include the complete metadata; do not reserve a
    # duplicate metadata read at the expense of final result validation.
    plan={'metadata_allowance':0 if role in ('analysis','signal_author','review','correction') else 1,
          'validation_checks':1}
    if role=='financial':return {**plan,'work_tool_limit':4}
    if role in ('retrieval','analysis','review','correction'):
        start=0;pages=0
        while True:
            meta=json.loads(reader._call_batch(start,48000).splitlines()[2]);pages+=1
            if pages>8:raise ValueError('Required call coverage exceeds bounded work plan')
            if meta['next_start'] is None:break
            start=meta['next_start']
        plan['call_pages']=pages
    if role in ('analysis','signal_author','review','correction'):
        plan['handoff_pages']=(len(reader._handoff_body())+58999)//59000
    if role in ('analysis','review','correction'):
        plan['support_pages']=(len(reader._support_body()[0])+58999)//59000
    if role in ('retrieval','review'):plan['filing_checks']=1
    if role=='signal_author':plan['selected_source_checks']=2
    total=sum(plan.values())
    if total>8:raise ValueError('Required evidence pages exceed eight-call bounded work plan')
    return {**plan,'work_tool_limit':total}


def parse(text):
    # Markdown envelope keeps machine-verifiable metadata separate from prose.
    import re
    matches=re.findall(r'^```json\s*\n(.*?)\n```\s*$',text,re.M|re.S)
    if len(matches)!=1:raise ValueError('Exactly one JSON metadata block required in Markdown result')
    value=json.loads(matches[0])
    if not isinstance(value,dict):raise ValueError('Structured role metadata must be an object')
    return value


def receipt(job,request):
    paths=list((job/'sessions').rglob('*.jsonl'))
    if len(paths)!=1:raise ValueError('Exactly one fresh session required')
    journal=old._inside(job,paths[0].relative_to(job));events=[json.loads(x) for x in journal.read_text().splitlines() if x.strip()]
    heads=[e for e in events if e.get('type')=='session']
    if len(heads)!=1 or heads[0].get('parentSession') or Path(heads[0].get('cwd','')).resolve()!=job or not heads[0].get('id'):raise ValueError('Fresh session binding required')
    models=[e for e in events if e.get('type')=='model_change'];thoughts=[e for e in events if e.get('type')=='thinking_level_change']
    if not models or any(e.get('provider')!=old.PROVIDER or e.get('modelId')!=request['model'] for e in models):raise ValueError('Exact model required')
    if not thoughts or any(e.get('thinkingLevel')!=request['effort'] for e in thoughts):raise ValueError('Exact effort required')
    if any(e.get('type') in ('compaction','branch_summary') for e in events):raise ValueError('Unexpected context mutation')
    messages=[e['message'] for e in events if e.get('type')=='message']
    users=[m for m in messages if m.get('role')=='user']
    if len(users)!=1 or messages[0]!=users[0] or old._text(users[0])!=(job/'prompt.md').read_text():raise ValueError('Exact sole instruction prompt required')
    final=messages[-1]
    if final.get('role')!='assistant' or final.get('stopReason')!='stop' or old._text(final)!=(job/'response.md').read_text():raise ValueError('Incomplete or changed final response')
    calls={};results=set();usage={k:0 for k in USAGE};turns=0
    for m in messages[1:]:
        if m.get('role')=='assistant':
            turns+=1
            if m.get('model')!=request['model'] or m.get('provider')!=old.PROVIDER or m.get('api')!='openai-codex-responses':raise ValueError('Assistant identity changed')
            u=m.get('usage',{})
            if any(type(u.get(k)) is not int or u[k]<0 for k in USAGE) or u['totalTokens']!=sum(u[k] for k in USAGE[:-1]):raise ValueError('Measured usage for every model turn required')
            for k in USAGE:usage[k]+=u[k]
            for block in m.get('content',[]):
                if block.get('type')=='toolCall':
                    if block.get('name')!='ipython' or block.get('id') in calls:raise ValueError('Only distinct IPython calls allowed')
                    calls[block['id']]=block
        elif m.get('role')=='toolResult':
            if m.get('toolName')!='ipython' or m.get('toolCallId') not in calls or m['toolCallId'] in results:raise ValueError('Tool result binding differs')
            results.add(m['toolCallId'])
        else:raise ValueError('Unexpected session message')
    verify_delivery(job,messages)
    if set(calls)!=results or not calls or len(calls)>request['max_tool_calls']:raise ValueError('Complete bounded IPython interaction required')
    if usage['totalTokens']>request['max_tokens']:raise ValueError('Job token cap exceeded')
    return {'id':heads[0]['id'],'path':str(journal.relative_to(job)),'sha256':old.sha(journal),'model':request['model'],
        'effort':request['effort'],'provider':old.PROVIDER,'usage':usage,'model_turns':turns,'tool_calls':len(calls)}


def request(job,prompt,model,effort,bindings,index,max_tokens,max_tool_calls,timeout,*,yield_checkpoint=False,resume=None,execution_plan=None):
    old._validate_selection(model,effort)
    if not prompt.strip() or type(max_tokens) is not int or not 1<=max_tokens<=1200000 or type(max_tool_calls) is not int or not 1<=max_tool_calls<=64 or timeout<=0:raise ValueError('Explicit bounded role settings required')
    index=Path(index).resolve();context.Evidence(index,job/'retrieval.jsonl')
    plan=work_plan(bindings.get('role'),index) if max_tool_calls>1 else None
    # The worker already reserves the registered full model output maximum
    # before EVERY turn. A second fixed reserve can close evidence tools while
    # ample output budget remains, producing an inevitably unreviewable draft.
    policy={**plan,'work_tool_limit':min(plan['work_tool_limit'],max_tool_calls-1),'automatic_checkpoints':True,'finalization_margin_tokens':0} if plan else None
    if execution_plan is not None:
        if (not isinstance(execution_plan,dict) or set(execution_plan)!={'work_tool_limit','finalization_margin_tokens','preflight_sha256'}
            or type(execution_plan['work_tool_limit']) is not int or not 1<=execution_plan['work_tool_limit']<=min(8,max_tool_calls-1)
            or type(execution_plan['finalization_margin_tokens']) is not int or not 0<=execution_plan['finalization_margin_tokens']<=65536
            or not __import__('re').fullmatch('[0-9a-f]{64}',str(execution_plan['preflight_sha256']))):
            raise ValueError('Explicit bounded preflighted execution plan required')
        policy={**(plan or {}),**execution_plan,'automatic_checkpoints':True}

    return {'execution_policy':policy,'checkpoint_python':sys.executable,'version':VERSION,'job_path':str(job),'model':model,'effort':effort,'provider':old.PROVIDER,'bindings':bindings,
        'context_index':str(index),'context_sha256':old.sha(index),'max_tokens':max_tokens,'max_tool_calls':max_tool_calls,
        'timeout_seconds':timeout,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'helper_sha256':old.sha(HELPER),'runner_sha256':old.sha(__file__),
        'delivery_sha256':old.sha(DELIVERY),'checkpoint_api_sha256':old.sha(Path(__file__).with_name('earnings_file_checkpoint.py')),'max_tool_response_bytes':None,'yield_checkpoint':yield_checkpoint,'resume':resume,'context_api_sha256':old.sha(context.__file__),'code_root':str(Path(__file__).resolve().parent.parent),'tool_names':['ipython']}


def verify_delivery(job,messages):
    records=context.delivery_records(job)
    results=[m for m in messages if m.get('role')=='toolResult']
    if len(records)!=len(results):raise ValueError('Delivery receipt required for every tool result')
    for r,m in zip(records,results):
        value={k:m[k] for k in ('content','details','isError')}
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        if r['tool_call_id']!=m['toolCallId'] or r['delivered_bytes']!=len(raw) or r['delivered_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('Tool delivery exceeded limit or changed')
    q=old.read(job/'request.json')
    if q.get('execution_policy',{} ) and q['execution_policy']['automatic_checkpoints']:
        from . import earnings_file_checkpoint as checkpoint
        saved=old.read(job/'automatic-checkpoints.json')
        if len(saved)!=len(records):raise ValueError('Host checkpoint receipt required after every tool result')
        for item,record in zip(saved,records):
            if item['delivery_id']!=record['id']:raise ValueError('Checkpoint delivery identity changed')
            if item['status']=='saved':
                if old.sha(item['checkpoint'])!=item['sha256']:raise ValueError('Automatic checkpoint changed')
                progress=checkpoint.validate(item['checkpoint'])
                if Path(progress['job']).resolve()!=Path(job).resolve() or progress['retrieval_count']!=record['retrieval_end']:raise ValueError('Automatic checkpoint does not cover this delivered prefix')
            elif item['status']=='no_evidence_progress':
                if record['retrieval_end']>record['retrieval_start']:raise ValueError('Delivered evidence progress was not checkpointed')
            else:raise ValueError('Unknown checkpoint capture result')
    entries=context.audit(q['context_index'],job/'retrieval.jsonl')
    context.delivered_entries(job,entries)


def verify_request(job,q):
    if q['version']!=VERSION or q['job_path']!=str(job) or q['helper_sha256']!=old.sha(HELPER) or q['runner_sha256']!=old.sha(__file__) or q['context_api_sha256']!=old.sha(context.__file__):raise ValueError('Runner/code binding changed')
    if q.get('delivery_sha256')!=old.sha(DELIVERY) or q.get('checkpoint_api_sha256')!=old.sha(Path(__file__).with_name('earnings_file_checkpoint.py')) or ('max_tool_response_bytes' not in q or q['max_tool_response_bytes'] is not None):raise ValueError('Delivery/checkpoint code binding changed')
    old._validate_selection(q['model'],q['effort'])
    if q['prompt_sha256']!=old.sha(job/'prompt.md') or q['context_sha256']!=old.sha(q['context_index']) or q['tool_names']!=['ipython']:raise ValueError('Instruction/evidence/tool binding changed')
    if q.get('resume') is not None:
        if old.read(job/'resume.json')!=q['resume']:raise ValueError('Resume binding changed')
        from . import earnings_file_checkpoint
        earnings_file_checkpoint.restore(job)


def verify_wire(q,wire,messages):
    turns=[m for m in messages if m.get('role')=='assistant' and m.get('stopReason')!='error']
    if len(wire)!=len(turns):raise ValueError('Exact metered wire turns required')
    calls=0;finalizing=False
    for item,m in zip(wire,turns):
        expected={'model':q['model'],'effort':q['effort'],'tools':['ipython']}
        policy=q.get('execution_policy')
        if policy:
            choice=item.get('tool_choice')
            if choice not in ('auto','none') or (finalizing and choice!='none'):raise ValueError('Monotonic tool phase required')
            if calls>=policy['work_tool_limit'] and choice!='none':raise ValueError('Tool exploration limit exceeded')
            if choice=='none':finalizing=True
            expected['tool_choice']=choice
        if item!=expected:raise ValueError('Provider tool/model transcript changed')
        new=sum(b.get('type')=='toolCall' for b in m.get('content',[]))
        if finalizing and new:raise ValueError('Tool call returned during final-writing phase')
        calls+=new
        if policy and calls>policy['work_tool_limit']:raise ValueError('Requested tool batch exceeds bounded work phase')


def verify_job(job_path):
    job=Path(job_path).resolve();q=old.read(job/'request.json');verify_request(job,q)
    launch=old.read(job/'launch.json');execution=old.read(job/'execution.json');output=old.read(job/'output.json')
    if launch['request_sha256']!=old.digest(q) or execution['request_sha256']!=old.digest(q) or execution['launch_sha256']!=old.sha(job/'launch.json') or execution['status']!='completed' or execution['exit_code']!=0:raise ValueError('Successful bound execution required')
    names={'runtime-start.json','runtime-finish.json','wire.json','response.md','retrieval.jsonl','delivery.jsonl'}
    if set(execution['artifact_sha256'])!=names or any(old.sha(old._inside(job,n))!=h for n,h in execution['artifact_sha256'].items()):raise ValueError('Incomplete or changed runtime artifacts')
    r=receipt(job,q)
    if execution['session']!=r:raise ValueError('Session receipt changed')
    start=old.read(job/'runtime-start.json');finish=old.read(job/'runtime-finish.json');wire=old.read(job/'wire.json')
    if start.get('launch_id')!=launch['id']:raise ValueError('Launch identity changed')
    for value in (start,finish):
        if value.get('session_id')!=r['id'] or value.get('model')!=q['model'] or value.get('effort')!=q['effort'] or value.get('oauth') is not True:raise ValueError('Runtime identity changed')
    if len(wire)!=r['model_turns']:raise ValueError('Provider turn transcript changed')
    events=[json.loads(x) for x in (job/r['path']).read_text().splitlines() if x.strip()]
    verify_wire(q,wire,[x['message'] for x in events if x.get('type')=='message'])
    context.audit(q['context_index'],job/'retrieval.jsonl')
    if q.get('resume'):
        ancestor=Path(q['resume']['failed_job'])
        prior=[json.loads(x) for x in next((ancestor/'sessions').rglob('*.jsonl')).read_text().splitlines() if x.strip()]
        if r['id'] in {x.get('id') for x in prior if x.get('type')=='session'}:raise ValueError('Resume must use a fresh session')
    content=parse((job/'response.md').read_text())
    if output!={'request_sha256':old.digest(q),'execution_sha256':old.sha(job/'execution.json'),'content':content}:raise ValueError('Output changed')
    return {'content':content,'receipt':execution,'output_path':str(job/'output.json')}


def run_role(job_path,prompt,model,effort,bindings,index,*,max_tokens,max_tool_calls=48,timeout=1200,yield_checkpoint=False,resume=None,execution_plan=None):
    job=Path(job_path).resolve();q=request(job,prompt,model,effort,bindings,index,max_tokens,max_tool_calls,timeout,yield_checkpoint=yield_checkpoint,resume=resume,execution_plan=execution_plan)
    if (job/'request.json').exists():
        if old.read(job/'request.json')!=q:raise ValueError('Immutable role request differs')
        if (job/'output.json').exists():return verify_job(job)
        raise RuntimeError('Incomplete role cannot be launched again')
    if job.exists() and any(job.iterdir()):raise ValueError('Fresh job directory required')
    job.mkdir(parents=True,exist_ok=True);old.save(job/'request.json',q);(job/'prompt.md').write_text(prompt)
    if resume is not None:
        old.save(job/'resume.json',resume)
        verify_request(job,q)
    launch={'id':str(uuid.uuid4()),'request_sha256':old.digest(q),'started_at':old.datetime.now(old.timezone.utc).isoformat()};old.save(job/'launch.json',launch)
    node,sdk=old._runtime_paths();started=time.monotonic();process=subprocess.Popen([str(node),str(HELPER),str(sdk),str(job)],cwd=job,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:code=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        code=process.returncode
    execution={'request_sha256':old.digest(q),'launch_sha256':old.sha(job/'launch.json'),'exit_code':code,'seconds':round(time.monotonic()-started,3),'status':'execution_failed'}
    if code!=0:old.save(job/'execution.json',execution);raise RuntimeError('Prime/IPython role failed; immutable launch retained, no retry')
    try:
        execution['session']=receipt(job,q);context.audit(index,job/'retrieval.jsonl');content=parse((job/'response.md').read_text())
        execution['artifact_sha256']={n:old.sha(job/n) for n in ('runtime-start.json','runtime-finish.json','wire.json','response.md','retrieval.jsonl','delivery.jsonl')};execution['status']='completed'
    except (ValueError,KeyError,OSError):old.save(job/'execution.json',execution);raise
    old.save(job/'execution.json',execution);old.save(job/'output.json',{'request_sha256':old.digest(q),'execution_sha256':old.sha(job/'execution.json'),'content':content})
    return verify_job(job)
