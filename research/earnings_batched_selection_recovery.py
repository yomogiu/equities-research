"""Separately bound saved correction: retain added citations outside preparation selection."""
import copy,json,os,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as r,earnings_role_import as imp
from . import earnings_batch_review as b,earnings_batched_flow as flow
VERSION='authenticated-batch-selection-recovery-v1'
ERROR='Select at most 24 document chunks'
def derive(plan,items):
    """Keep the completed 24-chunk preparation selection; retain added source citations."""
    out=copy.deepcopy(plan)
    changes=[x for x in out['changes'] if x.get('unit_id')=='retrieval']
    b.require(len(changes)==1,'Exactly one retrieval replacement required')
    prior=items['retrieval']['value']['selected_document_ids'];value=changes[0]['value']
    selected=value['selected_document_ids']
    b.require(len(prior)==24 and len(set(prior))==24 and len(selected)==25 and selected[:24]==prior and selected[-1] not in prior,
              'Only one appended selection beyond original 24 is repairable')
    extra=selected[-1]
    b.require(extra in b.references(value['document_findings']),'Added source must remain explicitly cited in document findings')
    value['selected_document_ids']=copy.deepcopy(prior)
    return out

EXPORT='''import json,sys
from pathlib import Path
from research import earnings_mixed_runner as r,earnings_role_import as imp,earnings_passage_pipeline as p,earnings_batch_review as b,earnings_batched_flow as f
from research.earnings_batched_grounding_recovery import validate
root=Path(sys.argv[1]);protocol,bundle,catalog=p.load(root)
assert protocol['batch_review']==b.EDITORIAL_VERSION and protocol['max_correction_rounds']==2
assert not (root/'batch-jobs/correction-2').exists() and not (root/'batch-review/batches/1').exists() and not (root/'batch-review/batches/2').exists()
check=f._advance(root,False);assert check['status']=='pending' and check['stage']=='batch_apply'
v=b.replay(root/'batch-review');assert v['status']=='awaiting_batch' and v['round']==1
job=root/'batch-jobs/correction-1';value=r.verify_job(job);q=r.read(job/'request.json')
assert q['bindings']=={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(v['items']),'round':1}
assert [q['model'],q['effort']]==list(b.MODEL) and (job/'prompt.txt').read_text()==f.proposal_prompt(v,bundle,catalog,Path(protocol['writing_standard']).read_text(),b.EDITORIAL_VERSION,protocol.get('review_context'))
source=b.load(root/'batch-review')[0]['source_protocol']
review=root/'batch-review/batches/0/review'
assert value['receipt']['session']['id'] not in source['excluded_session_ids'] and value['receipt']['session']['id']!=r.verify_job(review)['receipt']['session']['id']
try:
 candidate,_=b.apply(v['items'],value['content'],b.EDITORIAL_VERSION);b.validate(candidate,bundle,catalog)
except ValueError as error:assert str(error)=='Select at most 24 document chunks'
else:raise AssertionError('Original failure not reproduced')
inherited=validate(protocol,bundle,catalog);tokens=sum(v['receipt']['session']['usage']['totalTokens'] for v in inherited.values())
sessions={v['receipt']['session']['id'] for v in inherited.values()}
for key in ('batch_attribution_review','operator_review','selection_repair','reviewed_boundary'):
 ref=protocol.get('grounding_recovery',{}).get(key)
 if ref:
  v=imp.authenticate(ref['review']);assert v['session']['id'] not in sessions;sessions.add(v['session']['id']);tokens+=v['session']['usage']['totalTokens']
for role in ('analysis','signal_author'):
 v=r.verify_job(root/'batch-jobs'/role)['receipt']['session'];assert v['id'] not in sessions;sessions.add(v['id']);tokens+=v['usage']['totalTokens']
print(json.dumps({'source_protocol':source,'items':r.read(root/'batch-review/initial.json'),'proposal':value['content'],'author_job':str(job),'author_tokens':value['receipt']['session']['usage']['totalTokens'],'author_session':value['receipt']['session']['id'],'inherited_tokens':tokens,'review':imp.reference(review,Path(sys.argv[2]))}))
'''


def original(seed):
    seed=Path(seed).resolve();p=r.read(seed/'protocol.json')
    code=Path(next(x['path'] for x in p['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    value=subprocess.run([sys.executable,'-c',EXPORT,str(seed),str(code)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    b.require(value.returncode==0,'Original saved-proposal replay failed: '+value.stderr[-1400:])
    return code,json.loads(value.stdout)


def initialize(seed,output,authorization):
    seed=Path(seed).resolve();root=Path(output).resolve()
    b.require(not root.exists() and authorization.strip(),'New authorized selection edition required')
    code,export=original(seed);plan=derive(export['proposal'],export['items'])
    state,pack=b.materialize(export['items'])
    note={'version':VERSION,'original_proposal_sha256':r.digest(export['proposal']),'resolved_plan_sha256':r.digest(plan),'restored_preparation_selection':export['items']['retrieval']['value']['selected_document_ids'],'retained_added_source':export['proposal']['changes'][next(i for i,x in enumerate(export['proposal']['changes']) if x['unit_id']=='retrieval')]['value']['selected_document_ids'][-1],'reason':'Retain the original completed preparation selection. The added source remains cited with its full original text available for review; no source, finding, quote or factual edit is removed.'}
    root.mkdir(parents=True)
    b.initialize(export['source_protocol'],state,pack,root/'batch-review',authorization,presentation_derivation=note)
    protocol={'version':VERSION,'batch_review':export['source_protocol']['batch_review'],'max_correction_rounds':2,'selection_recovery':{
        'seed':str(seed),'seed_protocol_sha256':r.sha(seed/'protocol.json'),'seed_initial_sha256':r.sha(seed/'batch-review/initial.json'),
        'authorization':authorization,'used_correction_rounds':1,'inherited_tokens':export['inherited_tokens']+export['author_tokens'],
        'author':imp.reference(export['author_job'],code),'review':export['review'],'derivation':note},
        'review_context':export['source_protocol'].get('review_context'),'code':{str(p):r.sha(p) for p in Path(__file__).parent.glob('earnings_*') if p.suffix in ('.py','.mjs')}}
    r.save(root/'protocol.json',protocol);r.save(root/'original-proposal.json',export['proposal']);r.save(root/'resolved-plan.json',plan)
    pending=b.replay(root/'batch-review');imp.create(Path(pending['job']),pending['prompt'],*b.MODEL,pending['bindings'],1200,export['review'])
    # Full ordinary application, evidence, signal and mechanical validation still runs.
    return b.submit(root/'batch-review',plan)


def load(root):
    root=Path(root);p=r.read(root/'protocol.json');rec=p['selection_recovery']
    b.require(p['version']==VERSION and p['max_correction_rounds']==2 and rec['used_correction_rounds']==1,'Selection recovery budget changed')
    for path,h in p['code'].items():b.require(r.sha(path)==h and r.sha(Path(__file__).parent/Path(path).name)==h,'Selection recovery code changed')
    seed=Path(rec['seed']);b.require(r.sha(seed/'protocol.json')==rec['seed_protocol_sha256'] and r.sha(seed/'batch-review/initial.json')==rec['seed_initial_sha256'],'Original selection seed changed')
    _,export=original(seed);value=imp.authenticate(rec['author'])
    b.require(value['content']==export['proposal'] and rec['inherited_tokens']==export['inherited_tokens']+export['author_tokens'],'Inherited author/usage changed')
    plan=derive(value['content'],export['items'])
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
    result['tokens']+=p['selection_recovery']['inherited_tokens']+authors
    return {'status':'pending' if result['status']=='awaiting_batch' else result['status'],'stage':'batch_review','detail':result,**({'report':str(root/'batch-review/report.html'),'report_sha256':r.sha(root/'batch-review/report.html')} if result['status']=='accepted' else {})}


def proposal_prompt(v,bundle,catalog,writing,p):
    return flow.proposal_prompt(v,bundle,catalog,writing,b.EDITORIAL_VERSION,p.get('review_context'))+'\nKeep the completed 24-document preparation selection unchanged. Additional factual citations may bind any exact original document in the complete source catalogue; retain all required supporting citations.'
