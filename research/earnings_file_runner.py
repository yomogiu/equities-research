"""Fresh Prime/IPython sessions with Markdown prompts and immutable tool receipts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
import sys
from . import earnings_runtime_common as runtime, earnings_file_context as context

VERSION='file-prime-role-v1'
HELPER=Path(__file__).with_name('earnings_file_prime.mjs')
DELIVERY=HELPER.with_name('earnings_file_delivery.mjs')
USAGE=('input','output','cacheRead','cacheWrite','totalTokens')


def work_plan(role,index):
    """Reserve evidence, metadata and pre-submit validation, bounded at 8."""
    if role=='retrieval_reference':
        reader=context.Evidence(index,Path(index).parent/'unused-plan.jsonl',_replay=True);metadata=runtime.read(Path(index).parent/'metadata.json');ids=metadata['source_scope_ids']
        if not 1<=len(ids)<=32:raise ValueError('Bounded original target scopes required')
        plan={'handoff_pages':(len(reader._handoff_body())+58999)//59000,'source_pages':(len(reader._support_body(ids)[0])+58999)//59000,'validation_checks':1}
        if sum(plan.values())>8:raise ValueError('Reference inspection exceeds bounded work plan')
        return {**plan,'work_tool_limit':sum(plan.values())}
    if role not in ('financial','retrieval','analysis','signal_author','review','correction'):return None
    reader=context.Evidence(index,Path(index).parent/'unused-plan.jsonl',_replay=True)
    if (runtime.read(Path(index).parent/'metadata.json').get('context_projection')=='compact-role-handoff-v1'
            and role in ('analysis','review','correction')):
        plan={'role_pages':len(reader.role_batch_plan()),'validation_checks':1}
        if role=='review':plan['filing_checks']=1
        if sum(plan.values())>8:raise ValueError('Required evidence pages exceed eight-call bounded work plan')
        return {**plan,'work_tool_limit':sum(plan.values())}
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


def budget_preflight(role,index,prompt,available_tokens):
    """Forecast repeated context before launch; never replace the wire guard.

    UTF-8 bytes / 3 is a disclosed planning estimate, not a tokenizer or bound.
    Reserve the registered full final output plus a planning allowance for each
    intermediate turn. Both cached and uncached input count on every turn.
    Unknown/adaptive tool output is budgeted at the documented packet limit.
    """
    reader=context.Evidence(index,Path(index).parent/'unused-budget.jsonl',_replay=True)
    plan=work_plan(role,index)
    sizes=[]
    if 'role_pages' in plan:
        sizes=[page['utf8_bytes'] for page in reader.role_batch_plan()]
        if plan.get('filing_checks'):
            sizes.append(max(60000,len(reader._challenge_batch('guidance EBITDA cash debt capital expenditure',4)[0].encode())))
        sizes.append(4096)  # validation result, usually much smaller
    else:
        # Adaptive signals and fallback retrieval still get a pre-launch forecast.
        sizes=[60000]*(plan['work_tool_limit']-1)+[4096]
        if plan.get('handoff_pages'):
            handoff_bytes=len(reader._handoff_body().encode())
            count=plan['handoff_pages']
            sizes[:count]=[(handoff_bytes+count-1)//count]*count
    registered_output_tokens=128000
    intermediate_output_tokens=4096
    envelope_tokens=4096
    prefix=(len(prompt.encode())+2)//3+envelope_tokens
    estimated_inputs=prefix
    for size in sizes:
        prefix+=(size+2)//3+intermediate_output_tokens
        estimated_inputs+=prefix
    required=estimated_inputs+len(sizes)*intermediate_output_tokens+registered_output_tokens
    return {'version':'role-token-planning-v1','status':'ready' if available_tokens>=required else 'insufficient_planned_budget',
            'available_tokens':available_tokens,'planned_tokens':required,'estimated_repeated_input_tokens':estimated_inputs,
            'registered_final_output_reserve':registered_output_tokens,'intermediate_output_allowance':intermediate_output_tokens,
            'wire_envelope_allowance':envelope_tokens,'utf8_bytes_per_estimated_token':3,
            'tool_packet_utf8_bytes':sizes,'planned_model_turns':len(sizes)+1,'work_plan':plan,
            'context_sha256':runtime.sha(index),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'notice':'Planning estimate, not a cost quote or guaranteed upper bound. Actual receipts and the full per-turn output reservation remain authoritative.'}


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
    journal=runtime._inside(job,paths[0].relative_to(job));events=[json.loads(x) for x in journal.read_text().splitlines() if x.strip()]
    heads=[e for e in events if e.get('type')=='session']
    if len(heads)!=1 or heads[0].get('parentSession') or Path(heads[0].get('cwd','')).resolve()!=job or not heads[0].get('id'):raise ValueError('Fresh session binding required')
    models=[e for e in events if e.get('type')=='model_change'];thoughts=[e for e in events if e.get('type')=='thinking_level_change']
    if not models or any(e.get('provider')!=runtime.PROVIDER or e.get('modelId')!=request['model'] for e in models):raise ValueError('Exact model required')
    if not thoughts or any(e.get('thinkingLevel')!=request['effort'] for e in thoughts):raise ValueError('Exact effort required')
    if any(e.get('type') in ('compaction','branch_summary') for e in events):raise ValueError('Unexpected context mutation')
    messages=[e['message'] for e in events if e.get('type')=='message']
    users=[m for m in messages if m.get('role')=='user']
    if len(users)!=1 or messages[0]!=users[0] or runtime._text(users[0])!=(job/'prompt.md').read_text():raise ValueError('Exact sole instruction prompt required')
    final=messages[-1]
    if final.get('role')!='assistant' or final.get('stopReason')!='stop' or runtime._text(final)!=(job/'response.md').read_text():raise ValueError('Incomplete or changed final response')
    calls={};results=set();usage={k:0 for k in USAGE};turns=0
    for m in messages[1:]:
        if m.get('role')=='assistant':
            turns+=1
            if m.get('model')!=request['model'] or m.get('provider')!=runtime.PROVIDER or m.get('api')!='openai-codex-responses':raise ValueError('Assistant identity changed')
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
    if set(calls)!=results or (not calls and not request.get('direct_input')) or (request.get('direct_input') and (calls or turns!=1)) or len(calls)>request['max_tool_calls']:raise ValueError('Complete bounded IPython interaction required')
    if usage['totalTokens']>request['max_tokens']:raise ValueError('Job token cap exceeded')
    return {'id':heads[0]['id'],'path':str(journal.relative_to(job)),'sha256':runtime.sha(journal),'model':request['model'],
        'effort':request['effort'],'provider':runtime.PROVIDER,'usage':usage,'model_turns':turns,'tool_calls':len(calls)}


def request(job,prompt,model,effort,bindings,index,max_tokens,max_tool_calls,timeout,*,yield_checkpoint=False,resume=None,execution_plan=None,direct_input=False):
    runtime._validate_selection(model,effort)
    if not prompt.strip() or type(max_tokens) is not int or not 1<=max_tokens<=1200000 or type(max_tool_calls) is not int or not 1<=max_tool_calls<=64 or timeout<=0:raise ValueError('Explicit bounded role settings required')
    index=Path(index).resolve();context.Evidence(index,job/'retrieval.jsonl')
    if direct_input:
        if yield_checkpoint or resume or execution_plan:raise ValueError('Direct input cannot use retrieval or resume plans')
        _direct_packet(prompt,index,bindings)
    plan=work_plan(bindings.get('role'),index) if max_tool_calls>1 and not direct_input else None
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

    return {'execution_policy':policy,'checkpoint_python':sys.executable,'version':VERSION,'job_path':str(job),'model':model,'effort':effort,'provider':runtime.PROVIDER,'bindings':bindings,
        'context_index':str(index),'context_sha256':runtime.sha(index),'max_tokens':max_tokens,'max_tool_calls':max_tool_calls,
        'timeout_seconds':timeout,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'helper_sha256':runtime.sha(HELPER),'runner_sha256':runtime.sha(__file__),
        'delivery_sha256':runtime.sha(DELIVERY),'checkpoint_api_sha256':runtime.sha(Path(__file__).with_name('earnings_file_checkpoint.py')),'max_tool_response_bytes':None,'yield_checkpoint':yield_checkpoint,'resume':resume,'context_api_sha256':runtime.sha(context.__file__),'code_root':str(Path(__file__).resolve().parent.parent),'tool_names':[] if direct_input else ['ipython'],**({'direct_input':True} if direct_input else {})}


def _direct_packet(prompt,index,bindings):
    if bindings.get('workflow') not in ('single-author-report-v1','single-author-report-v2','simple-report-v1') or bindings.get('role') not in ('single_report_analysis','single_report_review'):
        raise ValueError('Direct input requires the single-report contract')
    reader=context.Evidence(index,Path(index).parent/'unused-direct.jsonl',_replay=True)
    if runtime.read(reader.root/'metadata.json').get('role')!=bindings['role'].removeprefix('single_report_'):raise ValueError('Direct packet role differs')
    if runtime.read(reader.root/'metadata.json').get('single_report_version')!=bindings['workflow']:raise ValueError('Direct packet version differs')
    body=reader._report_packet()
    if not prompt.endswith(body):raise ValueError('Complete fixed packet must be embedded in direct prompt')
    return body


def verify_delivery(job,messages):
    records=context.delivery_records(job)
    results=[m for m in messages if m.get('role')=='toolResult']
    if len(records)!=len(results):raise ValueError('Delivery receipt required for every tool result')
    for r,m in zip(records,results):
        value={k:m[k] for k in ('content','details','isError')}
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        if r['tool_call_id']!=m['toolCallId'] or r['delivered_bytes']!=len(raw) or r['delivered_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('Tool delivery exceeded limit or changed')
    q=runtime.read(job/'request.json')
    if q.get('direct_input'):
        if records or results or context.audit(q['context_index'],job/'retrieval.jsonl'):raise ValueError('Direct role cannot retrieve evidence')
        _direct_packet((job/'prompt.md').read_text(),q['context_index'],q['bindings'])
        return
    if q.get('execution_policy',{} ) and q['execution_policy']['automatic_checkpoints']:
        from . import earnings_file_checkpoint as checkpoint
        saved=runtime.read(job/'automatic-checkpoints.json')
        if len(saved)!=len(records):raise ValueError('Host checkpoint receipt required after every tool result')
        for item,record in zip(saved,records):
            if item['delivery_id']!=record['id']:raise ValueError('Checkpoint delivery identity changed')
            if item['status']=='saved':
                if runtime.sha(item['checkpoint'])!=item['sha256']:raise ValueError('Automatic checkpoint changed')
                progress=checkpoint.validate(item['checkpoint'])
                if Path(progress['job']).resolve()!=Path(job).resolve() or progress['retrieval_count']!=record['retrieval_end']:raise ValueError('Automatic checkpoint does not cover this delivered prefix')
            elif item['status']=='no_evidence_progress':
                if record['retrieval_end']>record['retrieval_start']:raise ValueError('Delivered evidence progress was not checkpointed')
            else:raise ValueError('Unknown checkpoint capture result')
    entries=context.audit(q['context_index'],job/'retrieval.jsonl')
    context.delivered_entries(job,entries)


def verify_request(job,q):
    if q['version']!=VERSION or q['job_path']!=str(job) or q['helper_sha256']!=runtime.sha(HELPER) or q['runner_sha256']!=runtime.sha(__file__) or q['context_api_sha256']!=runtime.sha(context.__file__):raise ValueError('Runner/code binding changed')
    if q.get('delivery_sha256')!=runtime.sha(DELIVERY) or q.get('checkpoint_api_sha256')!=runtime.sha(Path(__file__).with_name('earnings_file_checkpoint.py')) or ('max_tool_response_bytes' not in q or q['max_tool_response_bytes'] is not None):raise ValueError('Delivery/checkpoint code binding changed')
    runtime._validate_selection(q['model'],q['effort'])
    if q['prompt_sha256']!=runtime.sha(job/'prompt.md') or q['context_sha256']!=runtime.sha(q['context_index']) or q['tool_names']!=([] if q.get('direct_input') else ['ipython']):raise ValueError('Instruction/evidence/tool binding changed')
    if q.get('direct_input'):_direct_packet((job/'prompt.md').read_text(),q['context_index'],q['bindings'])
    if q.get('resume') is not None:
        if runtime.read(job/'resume.json')!=q['resume']:raise ValueError('Resume binding changed')
        from . import earnings_file_checkpoint
        earnings_file_checkpoint.restore(job)


def verify_wire(q,wire,messages):
    turns=[m for m in messages if m.get('role')=='assistant' and m.get('stopReason')!='error']
    if len(wire)!=len(turns):raise ValueError('Exact metered wire turns required')
    calls=0;finalizing=False
    for item,m in zip(wire,turns):
        expected={'model':q['model'],'effort':q['effort'],'tools':q['tool_names']}
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
    job=Path(job_path).resolve();q=runtime.read(job/'request.json');verify_request(job,q)
    launch=runtime.read(job/'launch.json');execution=runtime.read(job/'execution.json');output=runtime.read(job/'output.json')
    if launch['request_sha256']!=runtime.digest(q) or execution['request_sha256']!=runtime.digest(q) or execution['launch_sha256']!=runtime.sha(job/'launch.json') or execution['status']!='completed' or execution['exit_code']!=0:raise ValueError('Successful bound execution required')
    names={'runtime-start.json','runtime-finish.json','wire.json','response.md','retrieval.jsonl','delivery.jsonl'}
    if set(execution['artifact_sha256'])!=names or any(runtime.sha(runtime._inside(job,n))!=h for n,h in execution['artifact_sha256'].items()):raise ValueError('Incomplete or changed runtime artifacts')
    r=receipt(job,q)
    if execution['session']!=r:raise ValueError('Session receipt changed')
    start=runtime.read(job/'runtime-start.json');finish=runtime.read(job/'runtime-finish.json');wire=runtime.read(job/'wire.json')
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
    if output!={'request_sha256':runtime.digest(q),'execution_sha256':runtime.sha(job/'execution.json'),'content':content}:raise ValueError('Output changed')
    return {'content':content,'receipt':execution,'output_path':str(job/'output.json')}


def run_role(job_path,prompt,model,effort,bindings,index,*,max_tokens,max_tool_calls=48,timeout=1200,yield_checkpoint=False,resume=None,execution_plan=None,direct_input=False):
    job=Path(job_path).resolve();q=request(job,prompt,model,effort,bindings,index,max_tokens,max_tool_calls,timeout,yield_checkpoint=yield_checkpoint,resume=resume,execution_plan=execution_plan,direct_input=direct_input)
    if (job/'request.json').exists():
        if runtime.read(job/'request.json')!=q:raise ValueError('Immutable role request differs')
        if (job/'output.json').exists():return verify_job(job)
        raise RuntimeError('Incomplete role cannot be launched again')
    if job.exists() and any(job.iterdir()):raise ValueError('Fresh job directory required')
    job.mkdir(parents=True,exist_ok=True);runtime.save(job/'request.json',q);(job/'prompt.md').write_text(prompt)
    # Every fresh attempt owns an explicit empty audit, including restore-only calls.
    (job/'retrieval.jsonl').touch(exist_ok=False)
    if direct_input:(job/'delivery.jsonl').touch(exist_ok=False)
    if resume is not None:
        runtime.save(job/'resume.json',resume)
        verify_request(job,q)
    launch={'id':str(uuid.uuid4()),'request_sha256':runtime.digest(q),'started_at':datetime.now(timezone.utc).isoformat()};runtime.save(job/'launch.json',launch)
    node,sdk=runtime._runtime_paths();started=time.monotonic();process=subprocess.Popen([str(node),str(HELPER),str(sdk),str(job)],cwd=job,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    timed_out=False
    try:code=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        code=process.returncode
    execution={'request_sha256':runtime.digest(q),'launch_sha256':runtime.sha(job/'launch.json'),'exit_code':code,'seconds':round(time.monotonic()-started,3),'status':'execution_failed'}
    if timed_out:
        execution['failure_kind']='worker_timeout'
        execution['execution_certainty']='unknown'
        execution['retry_authorized']=False
    if code!=0:runtime.save(job/'execution.json',execution);raise RuntimeError('Prime/IPython role failed; immutable launch retained, no retry')
    try:
        execution['session']=receipt(job,q);context.audit(index,job/'retrieval.jsonl');content=parse((job/'response.md').read_text())
        execution['artifact_sha256']={n:runtime.sha(job/n) for n in ('runtime-start.json','runtime-finish.json','wire.json','response.md','retrieval.jsonl','delivery.jsonl')};execution['status']='completed'
    except (ValueError,KeyError,OSError):runtime.save(job/'execution.json',execution);raise
    runtime.save(job/'execution.json',execution);runtime.save(job/'output.json',{'request_sha256':runtime.digest(q),'execution_sha256':runtime.sha(job/'execution.json'),'content':content})
    return verify_job(job)
