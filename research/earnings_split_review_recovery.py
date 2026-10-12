"""Explicitly migrate authenticated legacy work into separate acceptance tracks.

Old protocols and attempts remain immutable. Factual rounds and all usage carry
forward; a legacy combined verdict is projected only along its declared kinds.
"""
import copy,json,os,subprocess,sys,difflib
from pathlib import Path
from . import earnings_mixed_runner as r,earnings_role_import as imp,earnings_batch_review as b
from . import earnings_batched_contract_recovery as legacy,earnings_batched_flow as flow,earnings_editorial_stage as editorial
VERSION='authenticated-split-review-recovery-v1'
FINAL_EXPORT='''import sys,json,copy
from pathlib import Path
from research import earnings_mixed_runner as r,earnings_report_flow as f,earnings_batch_review as b
root=Path(sys.argv[1]);checked=f.advance(root,False)
assert checked['status']=='blocked'
p,_,bundle,catalog,writing=b.load(root/'batch-review');v=b.replay(root/'batch-review')
assert v['status']=='blocked' and v['round']==2 and not (root/'batch-jobs/correction-3').exists()
review=root/'batch-review/batches/2/review';raw=r.verify_job(review)['content'];raw=b.bind_review_response(raw,{'batch_sha256':r.digest(v['items'])})
assert set(v['findings'])=={d['unit_id'] for d in raw['decisions'] if d['verdict']=='revise'}
assert all(d['review_kind']=='editorial' and d['editorial_repairs'] for d in raw['decisions'] if d['verdict']=='revise')
accepted=copy.deepcopy(v['accepted'])
for d in raw['decisions']:
 if d['verdict']=='revise':accepted[d['unit_id']]={'unit_sha256':r.digest(v['items'][d['unit_id']]),'review_receipt_sha256':r.sha(review/'output.json'),'source_references':sorted(b.references(v['items'][d['unit_id']]['value'])),'legacy_projection':'editorial_only_factual_pass'}
assert set(accepted)==set(v['items'])
state,pack=b.materialize(v['items']);canonical=b.units(state,pack)
for key,item in canonical.items():
 if r.digest(item)!=r.digest(v['items'][key]):
  assert key.startswith('signal-') and item['depends_on']==v['items'][key]['depends_on']
  assert {k:x for k,x in item['value'].items() if k!='finding_id'}=={k:x for k,x in v['items'][key]['value'].items() if k!='finding_id'}
  accepted[key]['identity_derivation']={'original_unit_sha256':accepted[key]['unit_sha256'],'reason':'Existing deterministic same-position content-derived finding ID rebind; all signal claims and sources unchanged'}
  accepted[key]['unit_sha256']=r.digest(item)
sessions=set(p['source_protocol']['excluded_session_ids'])
for file in root.glob('**/execution.json'):
 value=r.read(file)
 if value.get('status')=='completed':sessions.add(value['session']['id'])
rootp=r.read(root/'protocol.json')
if rootp.get('selection_recovery'):
 from research.earnings_role_import import authenticate
 sessions.add(authenticate(rootp['selection_recovery']['author'])['session']['id'])
print(json.dumps({'state':state,'pack':pack,'source_protocol':p['source_protocol'],'inherited_tokens':checked['detail']['tokens'],'used_correction_rounds':2,'accepted':accepted,'editorial_review':raw,'review_job':str(review),'sessions':sorted(sessions)}))
'''


def original(seed):
    seed=Path(seed).resolve();p=r.read(seed/'protocol.json')
    if isinstance(p['code'],list):
        old,code,value=legacy.original(seed)
        value['used_correction_rounds']=0;return old,code,value
    code=Path(next(iter(p['code']))).parent.parent
    result=subprocess.run([sys.executable,'-c',FINAL_EXPORT,str(seed)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    b.require(result.returncode==0,'Final legacy replay failed: '+result.stderr[-1400:])
    return p,code,json.loads(result.stdout)


def legacy_copy_response(review,items,catalog):
    fields=editorial.text_fields(items);terms=editorial.terminology(catalog,[f['text'] for f in fields]);edits=[]
    for d in review['decisions']:
        if d['verdict']=='pass':continue
        b.require(d['review_kind']=='editorial','Only editorial legacy findings may enter copy conformance')
        for old in d['editorial_repairs']:
            before,after=old['before'],old['after'];kind='wording'
            for term in terms:
                if before.count(term['short'])==1 and before.replace(term['short'],term['expanded'],1)==after:
                    before,after=term['short'],term['expanded'];kind='term_expansion';break
            edits.append({'unit_id':d['unit_id'],'field_path':old['field_path'],'before':before,'after':after,'kind':kind,'reason':old['reason']})
    response={'verdict':'apply' if edits else 'pass','edits':edits,'reason':'Apply the exact remaining editorial instructions from the authenticated final combined review; unchanged accepted work retains its original receipts.'}
    candidate,pending,audit=editorial.apply_edits(items,response,terms)
    b.require(not pending,'Legacy exhausted-budget migration permits only proven copy edits, never another factual correction')
    return response


def initialize(seed,output,authorization):
    root=Path(output).resolve();seed=Path(seed).resolve()
    b.require(not root.exists() and authorization.strip(),'New authorized split-review continuation required')
    old,code,export=original(seed);sp=copy.deepcopy(export['source_protocol']);sp['batch_review']=b.FACTUAL_VERSION
    if export.get('sessions'):sp['excluded_session_ids']=export['sessions']
    items=b.units(export['state'],export['pack']);bundle,catalog=b.remediation._source_bundle(sp)
    review_ref=imp.reference(export['review_job'],code);locator=None
    if export['used_correction_rounds']==0:
        raw=imp.authenticate(review_ref)['content'];bound=b.bind_review_response(raw,{'batch_sha256':r.digest(items)})
        try:b.adjudicate(items,set(items),{},bound,catalog,'source-review',b.EDITORIAL_VERSION)
        except ValueError as error:
            b.require(str(error)=='Editorial repair must locate exact unique text or an exact empty field','Only exact locator transport may be repaired here')
            resolved,locator=b.resolve_editorial_locators(bound,items)
            b.adjudicate(items,set(items),{},resolved,catalog,'source-review',b.EDITORIAL_VERSION)
    else:legacy_copy_response(export['editorial_review'],items,catalog)
    root.mkdir(parents=True)
    b.initialize(sp,export['state'],export['pack'],root/'batch-review',authorization,
        baseline_review_policy=b.EDITORIAL_VERSION if export['used_correction_rounds']==0 else None,
        editorial_locator_derivation=locator,seeded_factual_acceptance=export.get('accepted'),
        inherited_factual_rounds=export['used_correction_rounds'])
    rec={'seed':str(seed),'seed_protocol_sha256':r.sha(seed/'protocol.json'),'seed_initial_sha256':r.sha(seed/'batch-review/initial.json'),
         'authorization':authorization,'used_correction_rounds':export['used_correction_rounds'],
         'inherited_tokens':export['inherited_tokens'],'review':review_ref,'editorial_locator_derivation':locator}
    p={'version':VERSION,'batch_review':b.FACTUAL_VERSION,'max_correction_rounds':2,'split_review_recovery':rec,
       'code':{str(f):r.sha(f) for f in Path(__file__).parent.glob('earnings_*') if f.suffix in ('.py','.mjs')}}
    r.save(root/'protocol.json',p)
    if not export['used_correction_rounds']:
        pending=b.replay(root/'batch-review')
        imp.create(Path(pending['job']),pending['prompt'],*b.MODEL,pending['bindings'],1200,review_ref)
    return b.summary(b.replay(root/'batch-review'))


def load(root):
    root=Path(root);p=r.read(root/'protocol.json');rec=p['split_review_recovery']
    b.require(p['version']==VERSION and p['max_correction_rounds']==2 and p['batch_review']==b.FACTUAL_VERSION,'Split review budget/policy changed')
    for path,h in p['code'].items():b.require(r.sha(path)==h and r.sha(Path(__file__).parent/Path(path).name)==h,'Split-review implementation changed')
    seed=Path(rec['seed']);b.require(r.sha(seed/'protocol.json')==rec['seed_protocol_sha256'] and r.sha(seed/'batch-review/initial.json')==rec['seed_initial_sha256'],'Legacy source changed')
    _,code,export=original(seed);frozen,items,bundle,catalog,writing=b.load(root/'batch-review')
    sp=copy.deepcopy(export['source_protocol']);sp['batch_review']=b.FACTUAL_VERSION
    if export.get('sessions'):sp['excluded_session_ids']=export['sessions']
    b.require(frozen['source_protocol']==sp and items==b.units(export['state'],export['pack']) and rec['inherited_tokens']==export['inherited_tokens'] and rec['used_correction_rounds']==export['used_correction_rounds'],'Accepted work or inherited usage/budget changed')
    b.require(rec['review']==imp.reference(export['review_job'],code),'Original review reference changed')
    if not rec['used_correction_rounds']:imp.verify(root/'batch-review/batches/0/review')
    else:b.require(frozen['seeded_factual_acceptance']==export['accepted'] and frozen['inherited_factual_rounds']==2,'Terminal factual projection changed')
    return p,bundle,catalog,writing,export


def advance(output,execute=True):
    root=Path(output);p,bundle,catalog,writing,export=load(root);rec=p['split_review_recovery'];v=b.replay(root/'batch-review')
    excluded=set(b.load(root/'batch-review')[0]['source_protocol']['excluded_session_ids'])
    for file in (root/'batch-review').glob('batches/*/review/output.json'):excluded.add(r.verify_job(file.parent)['receipt']['session']['id'])
    for file in root.glob('batch-jobs/correction-*/output.json'):
        n=int(file.parent.name.split('-')[-1]);previous=b.replay(root/'batch-review',stop_before=n)
        result=flow.job(root,'correction-'+str(n),flow.proposal_prompt(previous,bundle,catalog,writing,b.FACTUAL_VERSION),b.MODEL,
          {'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(previous['items']),'round':n},False,excluded)
        plan=root/'batch-review/batches'/str(n)/'plan.json'
        if plan.exists():b.require(r.read(plan)==result['content'],'Applied factual plan differs from original author')
        excluded.add(result['receipt']['session']['id'])
    author_sessions=set(b.load(root/'batch-review')[0]['source_protocol']['excluded_session_ids'])
    author_sessions.update(r.verify_job(f.parent)['receipt']['session']['id'] for f in root.glob('batch-jobs/correction-*/output.json'))
    for f in (root/'batch-review').glob('batches/*/review/output.json'):
        b.require(r.verify_job(f.parent)['receipt']['session']['id'] not in author_sessions,'Factual reviewer reused an author session')
    if v['status']=='awaiting_batch':
        text=flow.proposal_prompt(v,bundle,catalog,writing,b.FACTUAL_VERSION);job=root/'batch-jobs'/('correction-'+str(v['round']))
        if (job/'output.json').exists():excluded.discard(r.verify_job(job)['receipt']['session']['id'])
        result=flow.job(root,job.name,text,b.MODEL,{'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(v['items']),'round':v['round']},execute,excluded)
        if 'pending_status' in result:return {'status':result['pending_status'],'stage':'factual_correction'}
        if not execute:return {'status':'pending','stage':'factual_apply'}
        b.submit(root/'batch-review',result['content']);return {'status':'pending','stage':'factual_review'}
    result=b.advance(root/'batch-review',execute)
    authors=sum(r.verify_job(f.parent)['receipt']['session']['usage']['totalTokens'] for f in root.glob('batch-jobs/correction-*/output.json'))
    tokens=result['tokens']+rec['inherited_tokens']+authors
    if result['status']=='accepted':
        seed_style=None
        if rec['used_correction_rounds']==2:
            seed_style={'response':legacy_copy_response(export['editorial_review'],v['items'],catalog),'review':rec['review']}
        final=editorial.advance(root/'batch-review',root/'final-editorial',execute and v['status']!='pending',legacy_editorial=seed_style)
        final['tokens']=final.get('tokens',0)+tokens;return final
    return {'status':'pending' if result['status']=='awaiting_batch' else result['status'],'stage':'factual_review','tokens':tokens,'detail':result}
