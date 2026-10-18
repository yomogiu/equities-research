"""Charged coverage continuation retaining completed original author and signals.

No ancestor output is edited or declared inspected. A new correction inspects
all originals and candidate, followed by fresh independent review, within old caps.
"""
import json,subprocess,sys,re
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-completed-role-coverage-continuation-v1'
PROGRAM=r'''
import sys,json,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b,earnings_financial_outline as f
protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval','signal_author']
assert not any(protocol.get(k) for k in ('preparation_path','review_preparation_path','analysis_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert protocol['financial_mode']=='deterministic-original-facts-v1' and protocol['max_correction_rounds']==2
artifacts={'financial':f.artifact(bundle['financial'],expanded=bool(protocol.get('report_template')))}
missing=None;sessions=[];tokens=0;findings={}
for role in ('retrieval','analysis','signal_author'):
 job=root/'jobs'/role;v=r.verify_job(job);q=b.read(job/'request.json');index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');metadata=b.read(index.parent/'metadata.json')
 assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':role,'context_sha256':b.sha(index),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
 assert [q['model'],q['effort']]==protocol['models'][role]
 assert b.read(index)['manifest']==protocol['evidence_manifest']
 assert (job/'prompt.md').read_text()==p.instruction(role,index,job,protocol)
 if role!='signal_author':
  assert deps=={**artifacts,'qa_grounding':b.read(root/'qa-grounding.json')}
  p.pipe.validate(role,v['content'],bundle,catalog)
 else:
  state={'artifacts':copy.deepcopy(artifacts),'format':p.mechanical.formatting(artifacts['financial'],bundle)}
  assert deps=={'state':state,'finding_catalog':p.signals.finding_catalog(state)}
  pack=v['content']
  try:p.signals.validate(pack,state,bundle,catalog)
  except ValueError as error:
   assert str(error)=='Invalid/duplicate/unknown signal passages'
   for signal in pack['signals']:findings[signal['id']]=str(error)+'; inspect originals and repair exact passage addresses without changing signal/finding identities.'
 try:p.coverage(role,index,job,v['content'],catalog,deps)
 except ValueError as error:
  assert role in ('retrieval','signal_author') and str(error).startswith('Required original evidence was not completely inspected: ')
  missing=str(error)
  if role=='retrieval':findings['retrieval']=missing
  else:
   for signal in pack['signals']:findings[signal['id']]=findings.get(signal['id'],'')+' '+missing
 if role!='signal_author':artifacts[role]=v['content']
 sid=v['receipt']['session']['id'];assert sid not in sessions;sessions.append(sid);tokens+=v['receipt']['session']['usage']['totalTokens']
assert missing and 0<tokens<protocol['max_tokens']<=1200000
print(json.dumps({'state':state,'signals':pack,'findings':findings,'tokens':tokens,'session_ids':sessions,'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':1,'original_outputs_sha256':{role:b.sha(root/'jobs'/role/'output.json') for role in ('retrieval','analysis','signal_author')}}))
'''
def replay(previous):
 root=Path(previous).resolve();code=Path(b.read(root/'jobs/retrieval/request.json')['code_root']).resolve()
 c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier changed')
 c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original origin changed')
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True))
def prepare(previous,case,output):
 root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
 c.require(v['case_sha256']==b.sha(case),'Original case required');c.write(output,v);return v
def verify(path,case,catalog):
 v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Coverage lineage changed')
 actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Completed work, usage or limits changed')
 c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['start_round']==1,'Original source and charged first correction required');return v
