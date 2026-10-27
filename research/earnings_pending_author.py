"""Opt-in source-bound continuation of one closed retrieval, no spent correction."""
from pathlib import Path
import json,subprocess,sys,copy
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-pending-author-retrieval-preparation-v1'
def original(previous):
 from .earnings_retrieval_reference_repair import frozen
 previous=Path(previous).resolve();code=frozen(b.read(previous/'jobs/retrieval/request.json')['code_root'])
 program=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval']
assert not any(protocol.get(k) for k in ('inherited_tokens','budget_authorization','recovery_path','preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','model_profile'))
job=root/'jobs/retrieval';q=b.read(job/'request.json');v=r.verify_job(job)
assert q['bindings']['role']=='retrieval' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert [q['model'],q['effort']]==protocol['models']['retrieval'] and q['max_tokens']==protocol['max_tokens']
assert (job/'prompt.md').read_text()==p.instruction('retrieval',Path(q['context_index']),job,protocol)
p.coverage('retrieval',Path(q['context_index']),job,v['content'],catalog,{})
pending=p.advance(root,False)
assert pending['status']=='pending' and pending['stage']=='analysis' and not pending['resume'] and pending['tokens']==v['receipt']['session']['usage']['totalTokens']
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
print(json.dumps({'protocol':protocol,'content':v['content'],'tokens':pending['tokens'],'session_id':v['receipt']['session']['id'],'catalog_sha256':b.digest(catalog)}))
'''
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(previous)],text=True))
def value(previous,case):
 from .earnings_prepared_retrieval import normalize
 previous=Path(previous).resolve();v=original(previous);p=v['protocol'];c.require(p['case_sha256']==b.sha(case),'Exact original case required')
 return {'version':VERSION,'previous_root':str(previous),'protocol_sha256':b.sha(previous/'protocol.json'),'output_sha256':b.sha(previous/'jobs/retrieval/output.json'),'case_sha256':b.sha(case),'catalog_sha256':v['catalog_sha256'],'tokens':v['tokens'],'session_id':v['session_id'],'max_tokens':p['max_tokens'],'models':p['models'],'writing_sha256':p['writing_sha256'],'report_template':p['report_template'],'spent_correction_rounds':0,'content':normalize(v['content'])}
def prepare(previous,case,output):
 c.require(not Path(output).exists(),'New immutable pending author preparation required');v=value(previous,case);c.write(output,v);return v
def verify(path,case,catalog):
 a=b.read(path);c.require(a==value(a['previous_root'],case) and a['catalog_sha256']==b.digest(catalog),'Pending author lineage or original settings changed');return a
