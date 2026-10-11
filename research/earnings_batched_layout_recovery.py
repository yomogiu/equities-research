"""Separately bound, lossless completion of a summaries-only presentation object."""
import copy,json,os,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as r,earnings_role_import as imp
from . import earnings_batch_review as b,earnings_batched_flow as flow
VERSION='authenticated-batch-layout-recovery-v1'
ERROR='Unknown compact financial layout schema'
DEFAULTS={'version':'compact-financial-mixed-units-v2','fold':[],'detail_rows':[],'basis_position':'before_tables'}


def derive(plan):
    """Only complete absent neutral routing keys; never infer a row or edit evidence."""
    out=copy.deepcopy(plan);changes=out.get('changes',[])
    formats=[x for x in changes if x.get('unit_id')=='format']
    b.require(len(formats)==1,'Exactly one format replacement required')
    layout=formats[0]['value'].get('layout')
    b.require(isinstance(layout,dict) and set(layout)=={'summaries'} and isinstance(layout['summaries'],list) and layout['summaries'],'Exact summaries-only layout required')
    layout.update(copy.deepcopy(DEFAULTS))
    return out

EXPORT='''import json,sys
from pathlib import Path
from research import earnings_mixed_runner as r,earnings_batched_contract_recovery as old,earnings_batch_review as b,earnings_batched_flow as f
root=Path(sys.argv[1]);p,bundle,catalog,writing=old.load(root)
assert not (root/'batch-jobs/correction-2').exists() and not (root/'batch-review/batches/1').exists() and not (root/'batch-review/batches/2').exists()
v=b.replay(root/'batch-review');assert v['status']=='awaiting_batch' and v['round']==1
job=root/'batch-jobs/correction-1';value=r.verify_job(job);q=r.read(job/'request.json')
text=f.proposal_prompt(v,bundle,catalog,writing,b.EDITORIAL_VERSION,p.get('review_context'))+'\\nWhen adding factual text to an empty accounting-basis field, bind existing original-source citations for that note. Preserve every factual accounting measure and source identity.'
assert q['bindings']=={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(v['items']),'round':1} and [q['model'],q['effort']]==list(b.MODEL) and (job/'prompt.txt').read_text()==text
initial=r.read(root/'batch-review/initial.json');source=b.load(root/'batch-review')[0]['source_protocol']
assert value['receipt']['session']['id'] not in source['excluded_session_ids'] and value['receipt']['session']['id'] != r.verify_job(root/'batch-review/batches/0/review')['receipt']['session']['id']
try:
 candidate,_=b.apply(v['items'],value['content'],b.EDITORIAL_VERSION);b.validate(candidate,bundle,catalog)
except ValueError as e:assert str(e)=='Unknown compact financial layout schema'
else:raise AssertionError('Original failure not reproduced')
print(json.dumps({'source_protocol':source,'items':initial,'proposal':value['content'],'author_job':str(job),'author_tokens':value['receipt']['session']['usage']['totalTokens'],'author_session':value['receipt']['session']['id'],'inherited_tokens':p['contract_recovery']['inherited_tokens'],'review':p['contract_recovery']['review']}))
'''


def original(seed):
    seed=Path(seed).resolve();p=r.read(seed/'protocol.json')
    code=Path(next(iter(p['code']))).parent.parent
    value=subprocess.run([sys.executable,'-c',EXPORT,str(seed)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    b.require(value.returncode==0,'Original saved-proposal replay failed: '+value.stderr[-1400:])
    return code,json.loads(value.stdout)


def initialize(seed,output,authorization):
    seed=Path(seed).resolve();root=Path(output).resolve()
    b.require(not root.exists() and authorization.strip(),'New authorized layout edition required')
    code,export=original(seed);plan=derive(export['proposal'])
    state,pack=b.materialize(export['items'])
    note={'version':VERSION,'original_proposal_sha256':r.digest(export['proposal']),'resolved_plan_sha256':r.digest(plan),'added_layout_fields':DEFAULTS,'reason':'Complete absent presentation fields only; retain every summary, citation, row and author replacement verbatim.'}
    root.mkdir(parents=True)
    b.initialize(export['source_protocol'],state,pack,root/'batch-review',authorization,presentation_derivation=note)
    protocol={'version':VERSION,'batch_review':export['source_protocol']['batch_review'],'max_correction_rounds':2,'layout_recovery':{
        'seed':str(seed),'seed_protocol_sha256':r.sha(seed/'protocol.json'),'seed_initial_sha256':r.sha(seed/'batch-review/initial.json'),
        'authorization':authorization,'used_correction_rounds':1,'inherited_tokens':export['inherited_tokens']+export['author_tokens'],
        'author':imp.reference(export['author_job'],code),'review':export['review'],'derivation':note},
        'review_context':export['source_protocol'].get('review_context'),'code':{str(p):r.sha(p) for p in Path(__file__).parent.glob('earnings_*') if p.suffix in ('.py','.mjs')}}
    r.save(root/'protocol.json',protocol);r.save(root/'original-proposal.json',export['proposal']);r.save(root/'resolved-plan.json',plan)
    pending=b.replay(root/'batch-review');imp.create(Path(pending['job']),pending['prompt'],*b.MODEL,pending['bindings'],1200,export['review'])
    # Full ordinary application, evidence, signal and mechanical validation still runs.
    return b.submit(root/'batch-review',plan)


def load(root):
    root=Path(root);p=r.read(root/'protocol.json');rec=p['layout_recovery']
    b.require(p['version']==VERSION and p['max_correction_rounds']==2 and rec['used_correction_rounds']==1,'Layout recovery budget changed')
    for path,h in p['code'].items():b.require(r.sha(path)==h and r.sha(Path(__file__).parent/Path(path).name)==h,'Layout recovery code changed')
    seed=Path(rec['seed']);b.require(r.sha(seed/'protocol.json')==rec['seed_protocol_sha256'] and r.sha(seed/'batch-review/initial.json')==rec['seed_initial_sha256'],'Original layout seed changed')
    _,export=original(seed);value=imp.authenticate(rec['author'])
    b.require(value['content']==export['proposal'] and rec['inherited_tokens']==export['inherited_tokens']+export['author_tokens'],'Inherited author/usage changed')
    plan=derive(value['content'])
    b.require(r.read(root/'original-proposal.json')==value['content'] and r.read(root/'resolved-plan.json')==plan and r.read(root/'batch-review/batches/1/plan.json')==plan,'Saved proposal derivation changed')
    frozen,items,bundle,catalog,writing=b.load(root/'batch-review')
    b.require(items==export['items'] and frozen['source_protocol']==export['source_protocol'] and frozen['presentation_derivation']==rec['derivation'] and rec['derivation']['resolved_plan_sha256']==r.digest(plan),'Factual work/derivation changed')
    imp.verify(root/'batch-review/batches/0/review')
    return p,bundle,catalog,writing,export['author_session']


def advance(output,execute=True):
    root=Path(output);p,bundle,catalog,writing,author_sid=load(root);v=b.replay(root/'batch-review')
    excluded=set(b.load(root/'batch-review')[0]['source_protocol']['excluded_session_ids']);excluded.add(author_sid)
    for file in (root/'batch-review').glob('batches/*/review/output.json'):
        sid=r.verify_job(file.parent)['receipt']['session']['id'];b.require(sid not in excluded,'Reviewer reused author session');excluded.add(sid)
    # Only the second original correction round can require another author call.
    if (root/'batch-jobs/correction-2/output.json').exists():
        previous=b.replay(root/'batch-review',stop_before=2)
        text=proposal_prompt(previous,bundle,catalog,writing,p)
        bindings={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(previous['items']),'round':2}
        value=flow.job(root,'correction-2',text,b.MODEL,bindings,False,excluded)
        plan=root/'batch-review/batches/2/plan.json'
        if plan.exists():b.require(r.read(plan)==value['content'],'Applied second plan differs from authenticated author')
    if v['status']=='awaiting_batch':
        b.require(v['round']==2,'Inherited first round cannot be reset')
        text=proposal_prompt(v,bundle,catalog,writing,p)
        bindings={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(v['items']),'round':2}
        job=root/'batch-jobs/correction-2'
        if (job/'output.json').exists():excluded.discard(r.verify_job(job)['receipt']['session']['id'])
        proposal=flow.job(root,'correction-2',text,b.MODEL,bindings,execute,excluded)
        if 'pending_status' in proposal:return {'status':proposal['pending_status'],'stage':'batch_correction',**({'execution':proposal['execution']} if 'execution' in proposal else {})}
        if not execute:return {'status':'pending','stage':'batch_apply'}
        b.submit(root/'batch-review',proposal['content']);return {'status':'pending','stage':'batch_review'}
    result=b.advance(root/'batch-review',execute)
    authors=sum(r.verify_job(f.parent)['receipt']['session']['usage']['totalTokens'] for f in root.glob('batch-jobs/correction-*/output.json'))
    result['tokens']+=p['layout_recovery']['inherited_tokens']+authors
    return {'status':'pending' if result['status']=='awaiting_batch' else result['status'],'stage':'batch_review','detail':result,**({'report':str(root/'batch-review/report.html'),'report_sha256':r.sha(root/'batch-review/report.html')} if result['status']=='accepted' else {})}


def proposal_prompt(v,bundle,catalog,writing,p):
    return flow.proposal_prompt(v,bundle,catalog,writing,b.EDITORIAL_VERSION,p.get('review_context'))+'\nA layout replacement must include exactly version (compact-financial-mixed-units-v2), fold (list), detail_rows (list), summaries (list), basis_position (before_tables or after_tables). Preserve existing complete values. Summaries require text, row_ids and citations. Do not emit a partial layout.'
