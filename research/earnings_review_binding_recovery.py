"""Offline, explicit missing-review-passage proposal contract.

This does not reserve a role, rewrite an original review, accept a report or
install a coordinator continuation. A fresh source-adjudication job and a
separately authenticated continuation are required before any activation.
"""
import copy,json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-missing-review-passage-proposal-v1'

def targets(raw,items,catalog):
    from . import earnings_batch_review as batch
    c.require(isinstance(raw,dict) and raw.get('reopen')==[],'No reopened units permitted')
    ds=raw.get('decisions');c.require(isinstance(ds,list) and len(ds)==len(items) and {d.get('unit_id')for d in ds}==set(items),'Entire original decision ledger required')
    selected=[]
    for d in ds:
        one={'batch_sha256':raw['batch_sha256'],'decisions':[d],'reopen':[]}
        missing=d.get('verdict')=='revise' and d.get('review_kind')=='factual' and d.get('passage_ids')==[]
        try:batch.adjudicate(items,{d['unit_id']},{},one,catalog,'diagnostic-only',batch.EDITORIAL_VERSION)
        except ValueError as error:
            c.require(missing and str(error)=='Exact original evidence required','Unrelated original review defect: '+str(error))
        else:c.require(not missing,'Missing typed evidence must fail original adjudication')
        if missing:
            c.require(d['unit_id'].startswith('analysis:') and isinstance(d.get('reason'),str) and d['reason'].strip(),'Only factual analysis decisions eligible')
            selected.append(d['unit_id'])
    c.require(1<=len(selected)<=2,'One or two missing factual passage lists required')
    return selected

def apply(raw,items,catalog,proposal):
    selected=targets(raw,items,catalog);c.require(isinstance(proposal,dict)and set(proposal)=={'bindings'},'Typed bindings only')
    rows=proposal['bindings'];c.require(isinstance(rows,list)and len(rows)==len(selected)and {x.get('unit_id')for x in rows}==set(selected),'Every missing field exactly once')
    allowed={p['passage_id']for p in catalog['passages']};out=copy.deepcopy(raw)
    for row in rows:
        c.require(set(row)=={'unit_id','passage_ids'},'No prose, criteria or other field edits')
        ids=row['passage_ids'];c.require(isinstance(ids,list)and 1<=len(ids)<=8 and all(isinstance(x,str)for x in ids)and len(set(ids))==len(ids)and set(ids)<=allowed,'Exact unique original indexed passages required')
        next(d for d in out['decisions']if d['unit_id']==row['unit_id'])['passage_ids']=ids[:]
    return out

PROGRAM=r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k)for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval','review-0','signal_author']
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
try:p.advance(root,False)
except ValueError as e:assert str(e)=='Exact original evidence required'
else:raise AssertionError('Exact original failure required')
tokens=0;sessions=[]
for name in ('retrieval','analysis','signal_author','review-0'):
 job=root/'jobs'/name;v=r.verify_job(job);q=b.read(job/'request.json');role='review'if name=='review-0'else name
 assert [q['model'],q['effort']]==protocol['models'][role]
 assert (job/'prompt.md').read_text()==p.instruction(role,Path(q['context_index']),job,protocol)
 tokens+=v['receipt']['session']['usage']['totalTokens'];sessions.append(v['receipt']['session']['id'])
assert len(set(sessions))==4 and tokens<protocol['max_tokens']
job=root/'jobs/review-0';q=b.read(job/'request.json');v=r.verify_job(job);index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json')
assert q['bindings']['protocol_sha256']==b.sha(root/'protocol.json') and q['bindings']['artifact_sha256']==b.digest(deps)
p.review_payload(v['content'],deps['units'],deps['state'])
p.coverage('review',index,job,v['content'],catalog,deps)
print(json.dumps({'review':v['content'],'items':deps['units'],'catalog':catalog,'tokens':tokens,'session_ids':sessions,'models':protocol['models'],'protocol_sha256':b.sha(root/'protocol.json'),'review_output_sha256':b.sha(job/'output.json'),'case_sha256':protocol['case_sha256'],'inspection':'complete original review ledger/candidate/source inspection; no omitted row','spent_correction_rounds':0,'remaining_correction_rounds':2}))
'''

def authenticate(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/review-0/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official original verifier required')
    v=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True));v['targets']=targets(v['review'],v['items'],v['catalog']);return v

def validate_fresh_proposal(previous,index,job,proposal):
    """Future launcher must first authenticate its request/session/accounting.

    This source check grants neither model-launch authority nor acceptance.
    It inspects the ENTIRE original candidate, all selected bindings and the
    original full review scope through the normal unchanged coverage contract.
    """
    from . import earnings_file_pipeline as p
    v=authenticate(previous);out=apply(v['review'],v['items'],v['catalog'],proposal)
    artifacts=b.read(Path(index).parent/'artifacts.json')
    c.require(artifacts.get('units')==v['items'],'Complete original candidate required')
    p.coverage('review',index,job,out,v['catalog'],artifacts)
    p.review_result(out,v['items'],artifacts['state'],artifacts['signals'],v['catalog'],Path(previous)/'jobs/review-0')
    return {'version':VERSION,'unaccepted_derived_review':out,'original_review_output_sha256':v['review_output_sha256'],'original_tokens':v['tokens'],'original_session_ids':v['session_ids'],'report_accepted':False}
