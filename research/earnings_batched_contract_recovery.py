"""Reuse authenticated authors and first review after a narrow review-contract fix."""
import os,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as r,earnings_role_import as imp
from . import earnings_batch_review as b,earnings_batched_flow as flow
VERSION='authenticated-batched-contract-recovery-v1'
EXPORT='''import json,sys
from pathlib import Path
from research import earnings_mixed_runner as r,earnings_passage_pipeline as p,earnings_batch_review as b,earnings_batched_flow as f,earnings_signals as s,earnings_mechanical_preflight as m
from research.earnings_batched_grounding_recovery import validate
root=Path(sys.argv[1]);protocol,bundle,catalog=p.load(root)
assert protocol['batch_review']==b.EDITORIAL_VERSION and protocol['max_correction_rounds']==2
assert not any((root/'batch-jobs'/('correction-'+str(n))).exists() or (root/'batch-review/batches'/str(n)).exists() for n in (1,2))
inherited=validate(protocol,bundle,catalog);artifacts={};sessions=set();tokens=0
for field in ('reviewed_boundary','batch_attribution_review','operator_review','selection_repair'):
 binding=protocol.get('grounding_recovery',{}).get(field)
 if binding:
  value=f.runner.verify_job(Path(binding['review']['job']))
  tokens+=f.inherited_review_tokens({'session':value['receipt']['session']},sessions)
for role in ('financial','retrieval','analysis','signal_author'):
 if role=='signal_author':
  state={'artifacts':artifacts,'format':m.formatting(artifacts['financial'],bundle)}
  text=s.prompt('analysis',state,bundle,catalog,Path(protocol['writing_standard']).read_text()).replace('accepted report','draft report');model=tuple(protocol['signal_author_model'])
 else:text=p.prompt(role,bundle,Path(protocol['writing_standard']).read_text(),artifacts,[],catalog);model=p.MODELS[role]
 bindings={'protocol_sha256':r.sha(root/'protocol.json'),'role':role,'dependencies_sha256':r.digest(artifacts)}
 if role in inherited:
  result=inherited[role];sid=result['receipt']['session']['id'];assert sid not in sessions;sessions.add(sid)
 else:result=f.job(root,role,text,model,bindings,False,sessions);assert 'pending_status' not in result
 tokens+=result['receipt']['session']['usage']['totalTokens'];out=result['content']
 if role=='retrieval':out,_=p.grounding.normalize_courtesy(out,bundle,catalog)
 if role=='signal_author':s.validate(out,state,bundle,catalog);pack=out
 else:p.validate(role,out,bundle,catalog);artifacts[role]=out
frozen,items,source_bundle,source_catalog,writing=b.load(root/'batch-review')
assert items==b.units(state,pack) and frozen['source_protocol']=={**protocol,'excluded_session_ids':sorted(sessions)}
job=root/'batch-review/batches/0/review';value=r.verify_job(job);q=r.read(job/'request.json')
expected={'protocol_sha256':r.sha(root/'batch-review/protocol.json'),'batch_sha256':r.digest(items),'round':0}
assert q['bindings']==expected and (q['model'],q['effort'])==b.MODEL and value['receipt']['session']['id'] not in sessions
assert (job/'prompt.txt').read_text()==b.prompt(items,items,set(items),{}, {},source_catalog,writing,0,source_bundle,b.EDITORIAL_VERSION,protocol.get('review_context'))
print(json.dumps({'state':state,'pack':pack,'source_protocol':frozen['source_protocol'],'inherited_tokens':tokens,'review_job':str(job),'used_correction_rounds':0}))
'''

def original(seed):
    seed=Path(seed).resolve();old=r.read(seed/'protocol.json')
    code=Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    result=subprocess.run([sys.executable,'-c',EXPORT,str(seed)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    b.require(result.returncode==0,'Original author/review dependency replay failed: '+result.stderr[-1200:])
    return old,code,__import__('json').loads(result.stdout)


def initialize(seed,output,authorization,resolve_editorial_locators=False):
    root=Path(output).resolve();b.require(not root.exists() and authorization.strip(),'New authorized contract edition required')
    old,code,export=original(seed)
    note=None
    if resolve_editorial_locators:
        original_review=r.verify_job(Path(export['review_job']))['content']
        bound=b.bind_review_response(original_review,{'batch_sha256':r.digest(b.units(export['state'],export['pack']))})
        _,note=b.resolve_editorial_locators(bound,b.units(export['state'],export['pack']))
    root.mkdir(parents=True)
    b.initialize(export['source_protocol'],export['state'],export['pack'],root/'batch-review',authorization,editorial_locator_derivation=note)
    protocol={'version':VERSION,'batch_review':old['batch_review'],'contract_recovery':{
        'seed':str(Path(seed).resolve()),'seed_protocol_sha256':r.sha(Path(seed)/'protocol.json'),
        'seed_initial_sha256':r.sha(Path(seed)/'batch-review/initial.json'),
        'authorization':authorization,'inherited_tokens':export['inherited_tokens'],'used_correction_rounds':0,
        'review':imp.reference(export['review_job'],code)},
        'review_context':old.get('review_context'),'max_correction_rounds':2,'code':{str(p):r.sha(p) for p in Path(__file__).parent.glob('earnings_*') if p.suffix in ('.py','.mjs')}}
    if note:protocol['contract_recovery']['editorial_locator_derivation']=note
    r.save(root/'protocol.json',protocol)
    pending=b.replay(root/'batch-review');ref=protocol['contract_recovery']['review']
    imp.create(Path(pending['job']),pending['prompt'],*b.MODEL,pending['bindings'],1200,ref)
    return b.summary(b.replay(root/'batch-review'))


def load(root):
    p=r.read(root/'protocol.json');b.require(p['version']==VERSION and p['max_correction_rounds']==2,'Contract recovery policy changed')
    for path,h in p['code'].items():b.require(r.sha(path)==h and r.sha(Path(__file__).parent/Path(path).name)==h,'Contract recovery code changed')
    rec=p['contract_recovery'];seed=Path(rec['seed']);b.require(r.sha(seed/'protocol.json')==rec['seed_protocol_sha256'] and r.sha(seed/'batch-review/initial.json')==rec['seed_initial_sha256'],'Original seed changed')
    _,_,export=original(seed)
    b.require(rec['used_correction_rounds']==0 and rec['inherited_tokens']==export['inherited_tokens'],'Inherited correction budget/usage changed')
    frozen,items,bundle,catalog,writing=b.load(root/'batch-review')
    b.require(frozen['source_protocol']==export['source_protocol'] and items==b.units(export['state'],export['pack']),'Saved factual work changed')
    require_note=rec.get('editorial_locator_derivation')
    b.require(frozen.get('editorial_locator_derivation')==require_note,'Editorial locator binding differs')
    if require_note:
        raw=imp.authenticate(rec['review'])['content'];bound=b.bind_review_response(raw,{'batch_sha256':r.digest(items)})
        _,computed=b.resolve_editorial_locators(bound,items)
        b.require(computed==require_note,'Original editorial locator derivation changed')
    imp.verify(root/'batch-review/batches/0/review')
    return p,bundle,catalog,writing


def advance(output,execute=True):
    root=Path(output);p,bundle,catalog,writing=load(root);v=b.replay(root/'batch-review')
    excluded=set(b.load(root/'batch-review')[0]['source_protocol']['excluded_session_ids'])
    for file in root.glob('batch-jobs/correction-*/output.json'):
        number=int(file.parent.name.split('-')[-1]);previous=b.replay(root/'batch-review',stop_before=number)
        request=r.read(file.parent/'request.json')
        expected={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(previous['items']),'round':number}
        text=flow.proposal_prompt(previous,bundle,catalog,writing,b.EDITORIAL_VERSION,p.get('review_context'))+'\nWhen adding factual text to an empty accounting-basis field, bind existing original-source citations for that note. Preserve every factual accounting measure and source identity.'
        b.require(request['bindings']==expected and (request['model'],request['effort'])==b.MODEL and (file.parent/'prompt.txt').read_text()==text,'Correction author binding changed')
        plan=root/'batch-review/batches'/str(number)/'plan.json'
        value=r.verify_job(file.parent)
        if plan.exists():b.require(r.read(plan)==value['content'],'Applied plan differs from authenticated author')
        b.require(value['receipt']['session']['id'] not in excluded,'Correction author reused another session');excluded.add(value['receipt']['session']['id'])
    for file in (root/'batch-review').glob('batches/*/review/output.json'):
        sid=r.verify_job(file.parent)['receipt']['session']['id'];b.require(sid not in excluded,'Reviewer reused author session');excluded.add(sid)
    if v['status']=='awaiting_batch':
        text=flow.proposal_prompt(v,bundle,catalog,writing,b.EDITORIAL_VERSION,p.get('review_context'))
        text+='\nWhen adding factual text to an empty accounting-basis field, bind existing original-source citations for that note. Preserve every factual accounting measure and source identity.'
        bindings={'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(v['items']),'round':v['round']}
        author=root/'batch-jobs'/('correction-'+str(v['round']))
        if (author/'output.json').exists():excluded.discard(r.verify_job(author)['receipt']['session']['id'])
        proposal=flow.job(root,'correction-'+str(v['round']),text,b.MODEL,bindings,execute,excluded)
        if 'pending_status' in proposal:return {'status':proposal['pending_status'],'stage':'batch_correction',**({'execution':proposal['execution']} if 'execution' in proposal else {})}
        if not execute:return {'status':'pending','stage':'batch_apply'}
        b.submit(root/'batch-review',proposal['content']);return {'status':'pending','stage':'batch_review'}
    result=b.advance(root/'batch-review',execute)
    authors=sum(r.verify_job(f.parent)['receipt']['session']['usage']['totalTokens'] for f in root.glob('batch-jobs/correction-*/output.json'))
    result['tokens']+=p['contract_recovery']['inherited_tokens']+authors
    return {'status':'pending' if result['status']=='awaiting_batch' else result['status'],'stage':'batch_review','detail':result,
            **({'report':str(root/'batch-review/report.html'),'report_sha256':r.sha(root/'batch-review/report.html')} if result['status']=='accepted' else {})}
