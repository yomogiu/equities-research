"""Authenticate an unattempted final correction after a complete bound review1."""
from pathlib import Path
import subprocess,sys,json
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-pending-final-correction-preparation-v1'
def replay(previous):
 from .earnings_retrieval_reference_repair import frozen
 previous=Path(previous).resolve();code=frozen(b.read(previous/'jobs/review-1/request.json')['code_root'])
 program=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not protocol.get('budget_authorization') and not protocol.get('model_profile')
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
assert sorted(x.name for x in(root/'jobs').iterdir())==['review-1'] and not(root/'jobs/correction-2').exists()
job=root/'jobs/review-1';q=b.read(job/'request.json');done=r.verify_job(job)
assert [q['model'],q['effort']]==protocol['models']['review'] and (job/'prompt.md').read_text()==p.instruction('review',Path(q['context_index']),job,protocol)
frames=[]
def trace(frame,event,arg):
 if event=='return' and frame.f_globals.get('__name__')=='research.earnings_file_pipeline' and frame.f_code.co_name=='_advance':frames.append(frame.f_locals.copy())
sys.setprofile(trace)
try:pending=p.advance(root,False)
finally:sys.setprofile(None)
assert pending['status']=='pending' and pending['stage']=='correction-2' and not pending['resume'] and len(frames)==1
v=frames[0];assert v['round_no']==2 and len(v['sessions'])==5 and pending['tokens']==v['tokens']
state,signals=p.batch.validate(v['items'],bundle,catalog)
assert done['receipt']['session']['id'] in v['sessions'] and v['findings']
print(json.dumps({'state':state,'signals':signals,'findings':v['findings'],'tokens':v['tokens'],'session_ids':sorted(v['sessions']),'review_session':done['receipt']['session']['id'],'review_job':str(job),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens'],'start_round':2,'spent_correction_rounds':1}))
'''
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(previous)],text=True))
def value(previous,case,catalog):
 previous=Path(previous).resolve();v=replay(previous);c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original case/catalog required');return {'version':VERSION,'previous_root':str(previous),'protocol_sha256':b.sha(previous/'protocol.json'),**v}
def prepare(previous,case,output):
 previous=Path(previous).resolve();v=value(previous,case,b.read(previous/'passages.json'));c.require(not Path(output).exists(),'New immutable final preparation required');c.write(output,v);return v
def verify(path,case,catalog):
 v=b.read(path);c.require(v==value(v['previous_root'],case,catalog),'Pending final review/state/usage lineage changed');return v
