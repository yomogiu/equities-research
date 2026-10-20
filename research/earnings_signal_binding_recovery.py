"""Offline contract for fresh adjudication of empty signal passage fields.

No launcher, reservation, successor, selected evidence or acceptance is provided.
Original prose, classifications and valid citations remain immutable. Independent
complete source adjudication and a new independent full review are mandatory.
"""
import copy,json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-empty-signal-passage-proposal-v1'


def targets(pack,catalog):
    c.require(isinstance(pack,dict)and set(pack)=={'report_sha256','signals'},'Exact original signal pack required')
    rows=pack['signals'];c.require(isinstance(rows,list)and 1<=len(rows)<=4,'Bounded original signals required');c.require(all(isinstance(x,dict)for x in rows),'Typed original signals required')
    ids=[s.get('id')for s in rows];c.require(all(isinstance(x,str)and x in ('signal-1','signal-2','signal-3','signal-4')for x in ids)and len(set(ids))==len(ids),'Distinct original signal identities required')
    allowed=[p['passage_id']for p in catalog['passages']];c.require(allowed and len(set(allowed))==len(allowed),'Unique original passage catalog required')
    chosen=[]
    for s in rows:
        c.require(isinstance(s.get('passage_ids'),list),'Original typed passage lists required')
        if s['passage_ids']==[]:chosen.append(s['id'])
        else:c.require(all(isinstance(x,str)for x in s['passage_ids'])and len(set(s['passage_ids']))==len(s['passage_ids'])and set(s['passage_ids'])<=set(allowed),'Unrelated invalid original passage list')
    c.require(chosen,'Empty original typed passage list required');return chosen


def apply(pack,catalog,proposal):
    selected=targets(pack,catalog);c.require(isinstance(proposal,dict)and set(proposal)=={'bindings'},'Typed bindings only')
    rows=proposal['bindings'];c.require(isinstance(rows,list)and len(rows)==len(selected)and all(isinstance(x,dict)for x in rows),'Every empty field exactly once')
    names=[x.get('signal_id')for x in rows];c.require(all(isinstance(x,str)for x in names),'Typed original signal IDs required');c.require(len(set(names))==len(names)and set(names)==set(selected),'Every original empty field exactly once')
    allowed={p['passage_id']for p in catalog['passages']};out=copy.deepcopy(pack)
    for row in rows:
        c.require(set(row)=={'signal_id','passage_ids'},'No prose, classifications, citations or extra fields')
        ids=row['passage_ids'];c.require(isinstance(ids,list)and 1<=len(ids)<=8 and all(isinstance(x,str)for x in ids)and len(set(ids))==len(ids)and set(ids)<=allowed,'Bounded distinct exact original passages required')
        next(s for s in out['signals']if s['id']==row['signal_id'])['passage_ids']=ids[:]
    return out


PROGRAM=r'''
import sys,json,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k)for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval','signal_author']
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
try:p.advance(root,False)
except ValueError as e:assert str(e)=='Invalid/duplicate/unknown signal passages'
else:raise AssertionError('Exact original empty signal passage failure required')
values={};sessions=[];tokens=0
for role in ('retrieval','analysis','signal_author'):
 job=root/'jobs'/role;q=b.read(job/'request.json');v=r.verify_job(job);index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');metadata=b.read(index.parent/'metadata.json')
 assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':role,'context_sha256':b.sha(index),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
 assert [q['model'],q['effort']]==protocol['models'][role] and b.read(index)['manifest']==protocol['evidence_manifest']
 assert (job/'prompt.md').read_text()==p.instruction(role,index,job,protocol)
 p.coverage(role,index,job,v['content'],catalog,deps)
 if role!='signal_author':p.pipe.validate(role,v['content'],bundle,catalog)
 else:
  raw=v['content'];state=deps['state'];diagnostic=copy.deepcopy(raw)
  # Whole original catalog membership is diagnostic schema material ONLY.
  # No member is selected as evidence or returned as an accepted binding.
  all_ids=[x['passage_id']for x in catalog['passages']]
  for signal in diagnostic['signals']:
   if signal['passage_ids']==[]:signal['passage_ids']=all_ids[:]
  p.signals.validate(diagnostic,state,bundle,catalog)
 values[role]=v['content'];sessions.append(v['receipt']['session']['id']);tokens+=v['receipt']['session']['usage']['totalTokens']
assert len(set(sessions))==3 and tokens<protocol['max_tokens']
print(json.dumps({'raw_signals':raw,'state':state,'catalog':catalog,'tokens':tokens,'session_ids':sessions,'models':protocol['models'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'protocol_sha256':b.sha(root/'protocol.json'),'signal_output_sha256':b.sha(root/'jobs/signal_author/output.json'),'inspection':'Complete original retained three-role inspection; schema exception only empty typed signal passage fields; no selected binding','spent_correction_rounds':0,'remaining_correction_rounds':2}))
'''


def authenticate(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/signal_author/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed frozen verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen verifier required')
    value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True));value['targets']=targets(value['raw_signals'],value['catalog']);return value
