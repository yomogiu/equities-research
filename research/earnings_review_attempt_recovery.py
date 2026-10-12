"""Verify a saved second correction after an authenticated handoff repair.

No third author, source substitution, budget reset or accepted-stage regeneration.
"""
import copy,json,os,subprocess,sys
from pathlib import Path
from . import earnings_batch_review as b,earnings_mixed_runner as r,earnings_role_import as imp,earnings_editorial_stage as editorial
VERSION='authenticated-final-review-handoff-v1'
EXPORT='''import sys,json,copy
from pathlib import Path
from research import earnings_split_review_recovery as m,earnings_batch_review as b,earnings_batched_flow as f,earnings_mixed_runner as r
root=Path(sys.argv[1]);p,bundle,catalog,writing,_=m.load(root)
assert p['split_review_recovery']['used_correction_rounds']==0
v=b.replay(root/'batch-review',stop_before=2);assert v['status']=='awaiting_batch' and v['round']==2
sessions=set(b.load(root/'batch-review')[0]['source_protocol']['excluded_session_ids']);tokens=p['split_review_recovery']['inherited_tokens']+v['tokens']
for file in (root/'batch-review').glob('batches/*/review/output.json'):sessions.add(r.verify_job(file.parent)['receipt']['session']['id'])
for n in [1,2]:
 prior=b.replay(root/'batch-review',stop_before=n)
 job=root/'batch-jobs'/('correction-'+str(n))
 result=f.job(root,job.name,f.proposal_prompt(prior,bundle,catalog,writing,b.FACTUAL_VERSION),b.MODEL,{'protocol_sha256':r.sha(root/'protocol.json'),'batch_sha256':r.digest(prior['items']),'round':n},False,sessions)
 assert result['content']==r.read(root/'batch-review/batches'/str(n)/'plan.json')
 tokens+=result['receipt']['session']['usage']['totalTokens']
plan=r.read(root/'batch-review/batches/2/plan.json');items,changed=b.apply(v['items'],plan,b.FACTUAL_VERSION);b.validate(items,bundle,catalog)
pending=set(v['findings'])|changed;accepted={k:x for k,x in v['accepted'].items() if k not in pending}
job=root/'batch-review/batches/2/review';value=r.verify_job(job);q=r.read(job/'request.json')
assert q['bindings']=={'protocol_sha256':r.sha(root/'batch-review/protocol.json'),'batch_sha256':r.digest(items),'round':2}
assert [q['model'],q['effort']]==list(b.MODEL)
text=b.prompt(v['items'],items,pending,accepted,v['findings'],catalog,writing,2,bundle,b.FACTUAL_VERSION,b.load(root/'batch-review')[0].get('review_context'))
assert (job/'prompt.txt').read_text()==text
assert value['receipt']['session']['id'] not in {r.verify_job(root/'batch-review/batches'/str(n)/'review')['receipt']['session']['id'] for n in [0,1]}
raw=b.bind_review_response(value['content'],q['bindings'])
assert raw['reopen']==[] and len(raw['decisions'])==1 and raw['decisions'][0]['unit_id']=='financial' and raw['decisions'][0]['verdict']=='revise'
assert set(raw['decisions'][0]['passage_ids'])<={o['id'] for o in bundle['financial']['observations']} and raw['decisions'][0]['passage_ids']
try:b.adjudicate(items,pending,accepted,raw,catalog,r.sha(job/'output.json'),b.FACTUAL_VERSION)
except ValueError as e:assert str(e)=='Exact original evidence required'
else:raise AssertionError('Original contract failure required')
assert not (root/'batch-jobs/correction-3').exists()
state,pack=b.materialize(items);canonical=b.units(state,pack)
for k in accepted:
 if canonical[k]!=items[k]:
  assert k.startswith('signal-') and canonical[k]['depends_on']==items[k]['depends_on']
  assert {a:x for a,x in canonical[k]['value'].items() if a!='finding_id'}=={a:x for a,x in items[k]['value'].items() if a!='finding_id'}
  accepted[k]['identity_derivation']={'original_unit_sha256':accepted[k]['unit_sha256'],'same_position_finding_id_only':True}
  accepted[k]['unit_sha256']=r.digest(canonical[k])
print(json.dumps({'source_protocol':b.load(root/'batch-review')[0]['source_protocol'],'items':canonical,'accepted':accepted,'reason':raw['decisions'][0]['reason'],'review_job':str(job),'author_job':str(root/'batch-jobs/correction-2'),'sessions':sorted(sessions),'inherited_tokens':tokens+value['receipt']['session']['usage']['totalTokens']}))
'''


def original(seed):
    seed=Path(seed).resolve();p=r.read(seed/'protocol.json');code=Path(next(iter(p['code']))).parent.parent
    result=subprocess.run([sys.executable,'-c',EXPORT,str(seed)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},capture_output=True,text=True)
    b.require(result.returncode==0,'Original final review handoff failed authentication: '+result.stderr[-1400:])
    return code,json.loads(result.stdout)


def compile_format(items,bundle):
    """Route the saved author's explicit basis qualifiers through the formatter."""
    out=copy.deepcopy(items);financial=out['financial']['value'];spec=out['format']['value'];rows=b.remediation.repair.row_catalog(financial,bundle);audit=[];seen=set()
    for selected in financial['rows']:
        label=selected['label']
        if 'accounting basis unverified' not in label.lower():continue
        ids=set(selected['fact_ids']);targets=[]
        for key,record in rows.items():
            cell_ids={fid for cell in record['row']['cells'] for fid in cell['fact_ids']}
            if cell_ids and cell_ids<=ids and key in spec['rows'] and spec['rows'][key]['label'].endswith(' (GAAP)'):targets.append(key)
        b.require(targets,'Explicit saved qualification must locate existing certified rows')
        for key in targets:
            b.require(key not in seen and len(label)<=160,'Unambiguous bounded format compilation required');seen.add(key)
            old=copy.deepcopy(spec['rows'][key]);spec['rows'][key]['label']=label
            audit.append({'row_id':key,'before':old,'after':copy.deepcopy(spec['rows'][key]),'saved_author_fact_ids':selected['fact_ids']})
    b.require(audit,'At least one exact unsupported certification required')
    b.require(out['financial']==items['financial'] and all(out[k]==items[k] for k in items if k!='format'),'Compilation cannot change factual work')
    return out,audit


def initialize(seed,output,authorization):
    root=Path(output).resolve();seed=Path(seed).resolve();b.require(not root.exists() and authorization.strip(),'New explicitly bound review checkpoint required')
    code,export=original(seed);sp=copy.deepcopy(export['source_protocol']);sp['excluded_session_ids']=export['sessions']
    bundle,catalog=b.remediation._source_bundle(sp);items,audit=compile_format(export['items'],bundle);b.validate(items,bundle,catalog)
    accepted={k:v for k,v in export['accepted'].items() if k!='format'}
    pending=sorted(set(items)-set(accepted));b.require(set(pending)=={'financial','format'},'Only financial and exact format repair may be pending')
    derivation={'version':VERSION,'source_review':imp.reference(export['review_job'],code),'saved_author':imp.reference(export['author_job'],code),'format_compilation':audit,'source_request_context':'Complete existing source scope D018, when named by the reviewer, must be included; no source is fetched or substituted.'}
    note={'pending':pending,'findings':{k:export['reason'] for k in pending},'derivation':derivation}
    state,pack=b.materialize(items)
    b.initialize(sp,state,pack,root/'batch-review',authorization,seeded_factual_acceptance=accepted,inherited_factual_rounds=2,pending_inherited_review=note)
    p={'version':VERSION,'batch_review':b.FACTUAL_VERSION,'max_correction_rounds':2,'review_attempt_recovery':{'seed':str(seed),'seed_protocol_sha256':r.sha(seed/'protocol.json'),'authorization':authorization,'inherited_tokens':export['inherited_tokens'],'used_correction_rounds':2,'derivation':derivation},'code':{str(f):r.sha(f) for f in Path(__file__).parent.glob('earnings_*') if f.suffix in ('.py','.mjs')}}
    r.save(root/'protocol.json',p);return b.summary(b.replay(root/'batch-review'))


def load(output):
    root=Path(output);p=r.read(root/'protocol.json');rec=p['review_attempt_recovery']
    b.require(p['version']==VERSION and p['batch_review']==b.FACTUAL_VERSION and p['max_correction_rounds']==rec['used_correction_rounds']==2,'Original correction budget changed')
    for name,h in p['code'].items():b.require(r.sha(name)==h and r.sha(Path(__file__).parent/Path(name).name)==h,'Review handoff implementation changed')
    seed=Path(rec['seed']);b.require(r.sha(seed/'protocol.json')==rec['seed_protocol_sha256'],'Original checkpoint changed')
    code,export=original(seed);frozen,items,bundle,catalog,writing=b.load(root/'batch-review');derived,audit=compile_format(export['items'],bundle)
    sp=copy.deepcopy(export['source_protocol']);sp['excluded_session_ids']=export['sessions']
    b.require(frozen['source_protocol']==sp and items==derived and rec['inherited_tokens']==export['inherited_tokens'] and audit==rec['derivation']['format_compilation'],'Saved author/usage/compilation changed')
    b.require(rec['derivation']['source_review']==imp.reference(export['review_job'],code) and rec['derivation']['saved_author']==imp.reference(export['author_job'],code),'Authenticated roles changed')
    b.require(frozen['pending_inherited_review']=={'pending':['financial','format'],'findings':{k:export['reason'] for k in ['financial','format']},'derivation':rec['derivation']} and frozen['seeded_factual_acceptance']=={k:v for k,v in export['accepted'].items() if k!='format'},'Inherited independent acceptance changed')
    return p,bundle,catalog,writing


def advance(output,execute=True):
    root=Path(output);p,*_=load(root);before=b.replay(root/'batch-review');result=b.advance(root/'batch-review',execute)
    tokens=p['review_attempt_recovery']['inherited_tokens']+result['tokens']
    if result['status']=='accepted':
        final=editorial.advance(root/'batch-review',root/'final-editorial',execute and before['status']!='pending');final['tokens']=tokens+final.get('tokens',0);return final
    return {'status':result['status'],'stage':'saved_second_correction_verification','tokens':tokens,'detail':result}
