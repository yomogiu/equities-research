"""Spend the remaining correction round after a completed correction with an unbound correction hash.

The failed author's output and usage remain immutable and charged. It is never
accepted as inspected; the original final correction must repair exact correction addresses without guessing and inspect originals.
No new correction round or budget is granted.
"""
import json,subprocess,sys,re,inspect
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-invalid-correction-reference-continuation-v1'
def inspection_failure(message):
    return message=='Correction hash must identify one original bound unit'

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
 assert inspection_failure(str(error))
 t=error.__traceback__;v=None;j=None
 while t:
  f=t.tb_frame
  if f.f_globals.get('__name__')=='research.earnings_file_pipeline':
   if f.f_code.co_name=='_advance':v=f.f_locals
   if f.f_code.co_name=='_job':j=f.f_locals
  t=t.tb_next
 assert v is not None and v['round_no']==1 and v['name']=='correction-1' and len(v['sessions'])==5
 job=root/'jobs/correction-1';failed=r.verify_job(job)
 assert failed['receipt']['session']['id'] in v['sessions'] and not (job/'resume.json').exists()
 assert b.sha(job/'output.json')==b.sha(root/'jobs/correction-1/output.json')
 values=[r.verify_job(x) for x in sorted((root/'jobs').iterdir())]
 assert sum(x['receipt']['session']['usage']['totalTokens'] for x in values)==v['tokens']
 state,signals=p.batch.validate(v['before'],bundle,catalog)
 print(json.dumps({'state':state,'signals':signals,'findings':v['findings'],'tokens':v['tokens'],'session_ids':sorted(v['sessions']),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':2,'failed_output_sha256':b.sha(job/'output.json')}))
else:raise AssertionError('Exact closed inspection failure required')
'''
def replay(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/correction-1/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name,'Original verifier changed')
    c.require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier edits forbidden')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original verifier origin changed')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c','import re\n'+inspect.getsource(inspection_failure)+PROGRAM,str(code),str(root)],text=True))
def prepare(previous,case,output):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
    c.require(v['case_sha256']==b.sha(case) and 0<=v['tokens']<v['max_tokens'] and v['start_round']==2,'Original case, remaining cap and last round required')
    c.write(output,v);return v

def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Inspection lineage changed')
    actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Original work, usage, models or spent round changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original case/catalogue required')
    c.require(v['start_round']==2 and 0<=v['tokens']<v['max_tokens'],'No reset of correction rounds or budget permitted')
    return v
