"""Once-only conclusive signal-provider overload continuation, never generic retries."""
import copy
from pathlib import Path
from . import earnings_mixed_runner as r

VERSION='authenticated-terminal-signal-overload-recovery-v1'
ERROR='Codex error: Our servers are currently overloaded. Please try again later.'


def require(value,reason):
    if not value:raise ValueError(reason)


def inspect(seed):
    seed=Path(seed);p=r.read(seed/'protocol.json');job=seed/'batch-jobs/signal_author'
    require('signal_provider_recovery' not in p,'Repeated provider retry forbidden')
    require({x.name for x in (seed/'batch-jobs').iterdir()}=={'signal_author'} and not (seed/'batch-review').exists() and not (seed/'result.json').exists(),'Only failed signal stage allowed')
    require(not any((job/name).exists() for name in ('output.json','stdout.txt','runtime-finish.json')),'Provider completion/output ambiguity')
    request,launch,execution,start,fail,wire=[r.read(job/name) for name in ('request.json','launch.json','execution.json','runtime-start.json','runtime-failure.json','wire.json')]
    require(request.get('version')=='mixed-prime-role-v1' and request.get('provider')=='openai-codex' and start.get('provider')=='openai-codex','Exact configured provider required')
    require(execution['status']=='returned' and execution['exit_code']==1 and fail=={'stage':'output_validation'},'Conclusive terminal output-validation failure required')
    require(execution['request_sha256']==r.digest(request)==launch['request_sha256'] and execution['launch_sha256']==r.sha(job/'launch.json'),'Failed request binding changed')
    require(request['bindings']['role']=='signal_author' and request['bindings']['protocol_sha256']==r.sha(seed/'protocol.json'),'Signal failure protocol differs')
    require([request['model'],request['effort']]==p['signal_author_model']==['gpt-6.1-sol','low'],'Original signal model differs')
    require(start['launch_id']==launch['id'] and start['model']==request['model'] and start['effort']==request['effort'] and start['oauth'] is True,'Failed runtime identity differs')
    require(wire==[{'model':request['model'],'effort':request['effort'],'tools':0}],'Exactly one original provider request required')
    journals=list((job/'sessions').glob('*.jsonl'));require(len(journals)==1,'One failed session required')
    entries=[__import__('json').loads(line) for line in journals[0].read_text().splitlines() if line.strip()]
    headers=[e for e in entries if e.get('type')=='session'];require(len(headers)==1 and headers[0]['id']==start['session_id'] and headers[0]['cwd']==str(job),'Failed session identity differs')
    messages=[e['message'] for e in entries if e.get('type')=='message'];require([m.get('role') for m in messages]==['user','assistant'],'Single terminal exchange required')
    terminal=messages[-1];require(terminal.get('content')==[] and terminal.get('stopReason')=='error' and terminal.get('errorMessage')==ERROR and terminal.get('model')==request['model'] and terminal.get('provider')=='openai-codex','Unknown/nonterminal/nonempty provider failure')
    require(any(d.get('error',{}).get('code')=='server_is_overloaded' for d in terminal.get('diagnostics',[])),'Exact overload diagnostic required')
    usage=terminal['usage'];require(all(usage.get(k)==0 for k in ('input','output','cacheRead','cacheWrite','totalTokens')),'Nonzero or unknown reported usage requires separate adjudication')
    require(r.sha(job/'prompt.txt')==request['prompt_sha256'],'Failed prompt changed')
    estimate=r.read(job/'token-estimate.json');require(estimate['prompt_sha256']==request['prompt_sha256'],'Failed token estimate changed')
    files={str(path):r.sha(path) for path in job.rglob('*') if path.is_file() and not path.name.startswith('.')}
    return {'version':VERSION,'seed':str(seed),'protocol_sha256':r.sha(seed/'protocol.json'),'state_sha256':r.sha(seed.parent/'state.json'),'job':str(job),'input_sha256':files,'session_id':start['session_id'],'model':[request['model'],request['effort']],'prompt_sha256':request['prompt_sha256'],'recorded_total_tokens':0,'usage_is_unknown':True,'failed_request_upper_bound_tokens':272000,'admission_note':'Reported usage is zero, but a failed provider request has uncertain actual usage; reserve the full configured 272,000-token model context, without adding correction rounds.'}


def validate(binding,protocol,bundle,catalog,artifacts):
    from . import earnings_signals as signals, earnings_mechanical_preflight as mechanical
    receipt=inspect(binding['seed']);require({k:v for k,v in binding.items() if k!='authorization'}==receipt and binding.get('authorization','').strip(),'Overload recovery receipt changed')
    source=r.read(Path(binding['seed'])/'protocol.json')
    ignored={'code','signal_provider_recovery','qa_grounding_path','qa_grounding_sha256','excluded_session_ids'}
    require({k:v for k,v in protocol.items() if k not in ignored}=={k:v for k,v in source.items() if k not in ignored},'Overload recovery changed frozen settings')
    state={'artifacts':copy.deepcopy(artifacts),'format':mechanical.formatting(artifacts['financial'],bundle)}
    text=signals.prompt('analysis',state,bundle,catalog,Path(protocol['writing_standard']).read_text()).replace('accepted report','draft report')
    require(Path(binding['job'],'prompt.txt').read_text()==text,'Overload retry must retain exact signal prompt')
    request=r.read(Path(binding['job'])/'request.json');require(request['bindings']['dependencies_sha256']==r.digest(artifacts),'Failed signal dependencies changed')
    return receipt


def initialize(seed,output,authorization):
    from . import earnings_passage_pipeline as pipe,earnings_attribution_preparer_recovery as attribution
    seed,output=Path(seed).resolve(),Path(output).resolve();require(not output.exists() and authorization.strip(),'New authorized overload successor required')
    state=r.read(seed.parent/'state.json');require(state.get('status')=='execution_failed' and state.get('stage')=='signal_author','Exact stopped signal failure required')
    old=r.read(seed/'protocol.json');require(old.get('attribution_preparer_recovery') and old.get('batch_review')=='batched-editorial-review-v3','Supported inherited attribution source required')
    for c in old['code']:require(r.sha(c['path'])==c['sha256'],'Original overload source code changed')
    receipt=inspect(seed);protocol=copy.deepcopy(old);protocol['code']=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol['signal_provider_recovery']={**receipt,'authorization':authorization}
    bundle=pipe.evidence.load_bundle(old['evidence_manifest']);catalog=r.read(seed/'passages.json');derived,inherited,_=attribution.apply(protocol,bundle,catalog)
    validate(protocol['signal_provider_recovery'],protocol,derived,catalog,{role:v['content'] for role,v in inherited.items()})
    output.mkdir(parents=True)
    for name in ('passages.json','qa-grounding.json'):(output/name).write_bytes((seed/name).read_bytes())
    protocol['qa_grounding_path']=str(output/'qa-grounding.json');protocol['qa_grounding_sha256']=r.sha(output/'qa-grounding.json')
    r.save(output/'protocol.json',protocol);pipe.load(output)
    return receipt
