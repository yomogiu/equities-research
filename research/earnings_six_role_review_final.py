"""Separate combined final correction for an authenticated six-role review hold."""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_review_binding_recovery as contract,earnings_review_binding_repair as sources
from . import earnings_review_binding_final as combined
VERSION='authenticated-six-role-review-final-v1'
PREPARATION_VERSION='authenticated-six-role-review-final-preparation-v1'
PROGRAM=r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in(root/'jobs').iterdir())==['analysis','correction-1','retrieval','review-0','review-1','signal_author']
assert not any(protocol.get(k)for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
try:p.advance(root,False)
except ValueError as error:
 assert str(error)=='Exact original evidence required';t=error.__traceback__;frames=[]
 while t:
  if t.tb_frame.f_globals.get('__name__')=='research.earnings_file_pipeline'and t.tb_frame.f_code.co_name=='_advance':frames.append(t.tb_frame.f_locals.copy())
  t=t.tb_next
 assert len(frames)==1;frame=frames[0];assert frame['round_no']==1 and frame['name']=='review-1'
else:raise AssertionError('Exact original six-role failure required')
sessions=[];tokens=0
for name in ('retrieval','analysis','signal_author','review-0','correction-1','review-1'):
 job=root/'jobs'/name;q=b.read(job/'request.json');done=r.verify_job(job);role='review'if name.startswith('review-')else 'correction'if name.startswith('correction-')else name;index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');metadata=b.read(index.parent/'metadata.json')
 assert [q['model'],q['effort']]==protocol['models'][role] and (job/'prompt.md').read_text()==p.instruction(role,index,job,protocol)
 assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':role,'context_sha256':b.sha(index),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
 sessions.append(done['receipt']['session']['id']);tokens+=done['receipt']['session']['usage']['totalTokens']
assert len(set(sessions))==6 and tokens==frame['tokens'] and 0<tokens<protocol['max_tokens']
job=root/'jobs/review-1';review=r.verify_job(job)['content'];q=b.read(job/'request.json');index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');p.review_payload(review,frame['items'],frame['state']);p.coverage('review',index,job,review,catalog,deps)
print(json.dumps({'review':review,'items':frame['items'],'state':frame['state'],'signals':frame['pack'],'catalog':catalog,'tokens':tokens,'session_ids':sessions,'models':protocol['models'],'max_tokens':protocol['max_tokens'],'source_root':str(root),'original_review_job':str(job),'review_output_sha256':b.sha(job/'output.json'),'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],'spent_correction_rounds':1}))
'''

def authenticate(previous):
 previous=Path(previous).resolve();code=Path(b.read(previous/'jobs/review-1/request.json')['code_root']).resolve()
 c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed six-role verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged original verifier required')
 v=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(previous)],text=True));v['targets']=contract.targets(v['review'],v['items'],v['catalog']);return v

def reservation_path(previous,root):
 import os
 previous=Path(previous).resolve();root=Path(root).resolve();code=Path(b.read(previous/'jobs/review-1/request.json')['code_root']).resolve();private=code.parent.parent;run=previous.parent.name
 c.require(re.fullmatch('[a-f0-9]{24}',run)and previous==private/'reporting/runs'/run/'pipeline'and root==private/'reporting/repairs/review-final'/run,'One canonical six-role final slot required')
 def mentions(v):
  if isinstance(v,dict):return any(mentions(x)for x in v.values())
  if isinstance(v,list):return any(mentions(x)for x in v)
  if not isinstance(v,str):return False
  parts=Path(os.path.normpath(v)).parts;return v==run or parts[-4:]==('reporting','runs',run,'pipeline')or parts[-3:]==('reporting','runs',run)
 for path in (private/'reporting/repairs').rglob('reservation.json'):
  if path.parent!=root:c.require(not mentions(b.read(path)),'Alternate/legacy six-role repair usage must be reconciled')

def artifacts(v):return {**sources.contents(v),'original_review_bindings':v['review']}
def metadata(protocol,units):return {**combined.metadata(protocol,units),'repair_version':VERSION}
def prompt(protocol,index,job):return combined.prompt(protocol,index,job)+'\nThis separately authenticated lineage has six original charged roles including correction1 and review1. It has no empty-binding repair role. This job spends only the final original correction2; no extra round is authorized.\n'
validate_proposal=combined.validate_proposal

def initialize(previous,root,*,source_currentness):
 from . import earnings_file_pipeline as p,earnings_file_runner as runner,earnings_compact_evidence as evidence
 previous=Path(previous).resolve();root=Path(root).resolve();c.require(not root.exists(),'New immutable canonical final slot required');reservation_path(previous,root);v=authenticate(previous);sources.currentness(previous,source_currentness);protocol=b.read(previous/'protocol.json');a=artifacts(v);bundle=evidence.load_bundle(protocol['evidence_manifest']);root.mkdir();index=c.assemble(protocol['evidence_manifest'],v['catalog'],root/'context',artifacts=a,metadata=metadata(protocol,a['units']),markdown=p.markdown.report(a['state'],bundle,v['catalog'],a['signals']));job=root/'jobs/final-correction-2'
 bindings={'role':'correction','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'original_review_output_sha256':v['review_output_sha256'],'context_sha256':b.sha(index),'artifact_sha256':b.digest(a),'metadata_sha256':b.digest(metadata(protocol,a['units'])),'inherited_tokens':v['tokens'],'spent_correction_rounds':2,'source_currentness_sha256':source_currentness['sha256']}
 out={'version':VERSION,'previous_root':str(previous),'prior':v,'job':str(job),'index':str(index),'bindings':bindings,'models':v['models'],'max_tokens':v['max_tokens']-v['tokens'],'source_currentness':source_currentness,'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('correction',index)};c.write(root/'reservation.json',out);return out

def frozen(root,method):
 root=Path(root).resolve();job=root/'jobs/final-correction-2'
 if not(job/'request.json').exists():return None
 code=Path(b.read(job/'request.json')['code_root']).resolve();c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed final verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged final verifier required')
 if code==Path(__file__).resolve().parent.parent:return None
 c.require(method in ('verify_reservation','completed'),'Exact frozen operation required');program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_six_role_review_final as h;print(json.dumps(getattr(h,sys.argv[3])(Path(sys.argv[2]))))';return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))

def verify_reservation(root):
 old=frozen(root,'verify_reservation')
 if old is not None:return old
 from . import earnings_file_runner as runner
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();record=b.read(root/'reservation.json');previous=Path(record['previous_root']);reservation_path(previous,root);v=authenticate(previous);job=root/'jobs/final-correction-2';sources.currentness(previous,record['source_currentness'],as_of=launched_at(job));protocol=b.read(previous/'protocol.json');a=artifacts(v);index=root/'context/index.json';bindings={'role':'correction','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'original_review_output_sha256':v['review_output_sha256'],'context_sha256':b.sha(index),'artifact_sha256':b.digest(a),'metadata_sha256':b.digest(metadata(protocol,a['units'])),'inherited_tokens':v['tokens'],'spent_correction_rounds':2,'source_currentness_sha256':record['source_currentness']['sha256']}
 c.require(record=={'version':VERSION,'previous_root':str(previous),'prior':v,'job':str(job),'index':str(index),'bindings':bindings,'models':v['models'],'max_tokens':v['max_tokens']-v['tokens'],'source_currentness':record['source_currentness'],'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('correction',index)},'Exact six-role lineage/context/model/usage required');c.require(b.read(index.parent/'artifacts.json')==a and b.read(index.parent/'metadata.json')==metadata(protocol,a['units']),'Original candidate context changed');c.Evidence(index,job/'retrieval.jsonl',_replay=True).verify();return record

def completed(root):
 old=frozen(root,'completed')
 if old is not None:return old
 from . import earnings_file_runner as runner,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=runner.verify_job(job);c.require(q['bindings']==v['bindings']and q['max_tokens']==v['max_tokens']and q['max_tool_calls']==48 and[q['model'],q['effort']]==v['models']['correction']and(job/'prompt.md').read_text()==v['prompt'],'Original final correction request required');previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);out=validate_proposal(Path(v['index']),job,done['content'],artifacts(v['prior']),v['prior']['catalog'],bundle);ids=v['prior']['session_ids']+[done['receipt']['session']['id']];tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(len(set(ids))==len(ids)==7 and tokens<v['prior']['max_tokens'],'Seven real sessions and unchanged lifecycle cap required');return {**out,'session_ids':ids,'tokens':tokens,'max_tokens':v['prior']['max_tokens'],'models':v['models'],'case_sha256':v['prior']['case_sha256'],'catalog_sha256':v['prior']['catalog_sha256'],'writing_sha256':v['prior']['writing_sha256'],'report_template':v['prior']['report_template'],'spent_correction_rounds':2,'start_round':2}

def prepare(root,case,path):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');out={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(path,out);return out

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Exact final reservation required');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items())and v['case_sha256']==b.sha(case)and v['catalog_sha256']==b.digest(catalog)and v['spent_correction_rounds']==2,'Final source/state/usage changed');return v
