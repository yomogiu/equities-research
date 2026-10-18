"""Authenticated successor for one completed correction's empty GAAP basis IDs."""
import json,subprocess,sys,re
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-header-basis-continuation-v1'
PROGRAM=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k) for k in ('review_preparation_path','signal_preparation_path','preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','correction-1','retrieval','review-0','signal_author']
try:p.verify(root)
except ValueError as error:
 assert str(error)=='Invalid/duplicate/unknown basis sources'
 t=error.__traceback__;v=None
 while t:
  f=t.tb_frame
  if f.f_globals.get('__name__')=='research.earnings_file_pipeline' and f.f_code.co_name=='_advance':v=f.f_locals
  t=t.tb_next
 assert v is not None and v['round_no']==1 and len(v['sessions'])==5
 job=root/'jobs/review-0';review=r.verify_job(job)
 print(json.dumps({'state':v['state'],'signals':v['pack'],'before':v['before'],'raw_correction':v['value']['content'],'review':review['content'],'review_job':str(job),'review_session':review['receipt']['session']['id'],'tokens':v['tokens'],'session_ids':sorted(v['sessions']),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template']}))
else:raise AssertionError('Exact closed basis failure required')
'''
def replay(previous):
    previous=Path(previous).resolve();q=b.read(previous/'jobs/correction-1/request.json');code=Path(q['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name,'Frozen verifier changed')
    c.require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen code edits forbidden')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Frozen origin changed')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(previous)],text=True))
def derive(value):
    from . import earnings_batch_review as batch,earnings_compact_evidence as evidence
    root=Path(value['previous_root']);protocol=b.read(root/'protocol.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);catalog=b.read(root/'passages.json')
    plan,notes=batch.resolve_basis_citations(value['before'],value['raw_correction'],bundle)
    c.require(len(notes)==1,'Exact single basis-address derivation required')
    candidate,_=batch.apply(value['before'],plan,batch.EDITORIAL_VERSION);batch.validate(candidate,bundle,catalog)
    return {'content':plan,'job':str(root/'jobs/correction-1'),'round':1},notes

def prepare(previous,case,output):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
    c.require(v['case_sha256']==b.sha(case),'Original case required')
    v['prepared_correction'],v['address_derivation']=derive(v);c.write(output,v);return v

def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Basis lineage changed')
    actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Original roles, usage or models changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Case/catalogue changed')
    correction,notes=derive(v);c.require(v['prepared_correction']==correction and v['address_derivation']==notes,'Only exact basis-address derivation permitted')
    return v
