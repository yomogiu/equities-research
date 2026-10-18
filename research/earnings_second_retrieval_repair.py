"""Final charged retrieval repair after one completed but unaccepted repair.

No attempt is retried. Both completed sessions and their usage remain bound;
round two is spent here, leaving only author/signals and fresh final review.
"""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-second-retrieval-repair-v1'
PREPARATION_VERSION='authenticated-two-charged-retrieval-preparation-v1'
PROGRAM=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);first=Path(sys.argv[2])
from research import earnings_retrieval_repair as old,earnings_file_runner as runner,earnings_mixed_runner as b
v=old.verify_reservation(first);job=Path(v['job']);q=b.read(job/'request.json');value=runner.verify_job(job)
assert q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt']
assert [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48
assert sorted(x.name for x in (first/'jobs').iterdir())==['retrieval-repair']
try:old.completed(first)
except ValueError as error:assert str(error).startswith('Required original evidence was not completely inspected: ')
else:raise AssertionError('Exact completed but unaccepted coverage failure required')
sids=[v['prior']['session_id'],value['receipt']['session']['id']];assert len(set(sids))==2
print(json.dumps({**v['prior'],'raw':value['content'],'tokens':v['prior']['tokens']+value['receipt']['session']['usage']['totalTokens'],'session_ids':sids,'source_root':v['previous_root'],'spent_correction_rounds':1}))
'''
def prior(first):
 first=Path(first).resolve();job=first/'jobs/retrieval-repair';code=Path(b.read(job/'request.json')['code_root']).resolve()
 c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen first-repair verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'First-repair verifier changed')
 c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','First-repair origin changed')
 value=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(first)],text=True))
 c.require(0<value['tokens']<value['max_tokens']<=1200000,'Original remaining lifecycle cap required');return value

def instruction(protocol,index,job):
 from .earnings_file_pipeline import instruction as base_instruction
 return base_instruction('retrieval',index,job,protocol)+'\nThis is the final charged retrieval repair, consuming original correction round 2. Both previous completed retrieval sessions remain charged. The prior repair is unaccepted data in artifacts.json. Inspect complete original call, exact questions and answers, all selected source documents and every cited passage. Repair exact addresses without prefix/topic guessing. Return complete validated retrieval; use Evidence.validate_result. No further correction is authorized after this job; fresh independent report review is still required.\n'
def expected(first,output,v):
 source=Path(v['source_root']);protocol=b.read(source/'protocol.json');catalog=b.read(source/'passages.json')
 artifacts={'unreviewed_prior_retrieval':v['raw'],'qa_grounding':b.read(source/'qa-grounding.json')}
 return source,protocol,catalog,artifacts

def initialize(first,output):
 first=Path(first).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable second repair required');v=prior(first);source,protocol,catalog,artifacts=expected(first,output,v)
 output.mkdir();metadata={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(source/'protocol.json'),'spent_correction_rounds':2,'case_scope_notes':b.read(protocol['case_path']).get('scope_notes',[])}
 index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts=artifacts,metadata=metadata);job=output/'jobs/retrieval-repair-2'
 bindings={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(source/'protocol.json'),'first_reservation_sha256':b.sha(first/'reservation.json'),'first_output_sha256':b.sha(first/'jobs/retrieval-repair/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'inherited_tokens':v['tokens'],'spent_correction_rounds':2}
 record={'version':VERSION,'previous_repair':str(first),'prior':v,'job':str(job),'index':str(index),'bindings':bindings,'models':v['models'],'max_tokens':v['max_tokens']-v['tokens'],'spent_correction_rounds':2,'prompt':instruction(protocol,index,job)}
 c.write(output/'reservation.json',record);return record

def verify_reservation(output):
 output=Path(output).resolve();record=b.read(output/'reservation.json');first=Path(record['previous_repair']);v=prior(first);source,protocol,catalog,artifacts=expected(first,output,v);index=output/'context/index.json';job=output/'jobs/retrieval-repair-2'
 bindings={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(source/'protocol.json'),'first_reservation_sha256':b.sha(first/'reservation.json'),'first_output_sha256':b.sha(first/'jobs/retrieval-repair/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'inherited_tokens':v['tokens'],'spent_correction_rounds':2}
 c.require(record=={'version':VERSION,'previous_repair':str(first),'prior':v,'job':str(job),'index':str(index),'bindings':bindings,'models':v['models'],'max_tokens':v['max_tokens']-v['tokens'],'spent_correction_rounds':2,'prompt':instruction(protocol,index,job)},'Second repair lineage, limits or prompt changed')
 c.require(b.read(index.parent/'artifacts.json')==artifacts,'Second repair original context changed');return record

def completed(output):
 from . import earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence
 v=verify_reservation(output);job=Path(v['job']);q=b.read(job/'request.json');value=runner.verify_job(job)
 c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Second repair request changed')
 source=Path(v['prior']['source_root']);protocol=b.read(source/'protocol.json');catalog=b.read(source/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest'])
 pipeline.coverage('retrieval',Path(v['index']),job,value['content'],catalog,{})
 pipeline.pipe.validate('retrieval',value['content'],bundle,catalog)
 sid=value['receipt']['session']['id'];c.require(sid not in v['prior']['session_ids'],'Fresh second-repair session required')
 tokens=v['prior']['tokens']+value['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'No lifecycle cap reset')
 return {k:v['prior'][k] for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')} | {'content':value['content'],'tokens':tokens,'session_id':sid,'session_ids':v['prior']['session_ids']+[sid],'spent_correction_rounds':2}

def prepare(output,case,destination):
 output=Path(output).resolve();v=completed(output);c.require(v['case_sha256']==b.sha(case),'Original case required');record={'version':PREPARATION_VERSION,'repair_root':str(output),'reservation_sha256':b.sha(output/'reservation.json'),**v};c.write(destination,record);return record

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Second repair preparation lineage changed');actual=completed(root)
 c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['spent_correction_rounds']==2,'Second repair evidence, work or accounting changed');return v
