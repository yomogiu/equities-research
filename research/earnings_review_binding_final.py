"""Combined final correction after an authenticated empty binding/handoff stop."""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_review_binding_repair as prior_repair
from . import earnings_review_binding_recovery as contract
VERSION='authenticated-combined-review-final-correction-v1'
PREPARATION_VERSION='authenticated-combined-review-final-preparation-v1'

PROGRAM=r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_review_binding_repair as h,earnings_file_runner as r,earnings_file_context as c,earnings_mixed_runner as b
v=h.verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=r.verify_job(job)
assert done['content']=={'bindings':[]}
assert q['bindings']==v['bindings'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['review'] and (job/'prompt.md').read_text()==v['prompt']
assert sorted(x.name for x in (root/'jobs').iterdir()) in (['binding-repair'],['binding-repair','final-correction-2'])
try:h.completed(root)
except ValueError as error:assert str(error)=='Every missing field exactly once'
else:raise AssertionError('Exact stopped binding failure required')
reader=c.Evidence(v['index'],root/'unused-read-only.jsonl',_replay=True);handoff=json.loads(reader._handoff_body());artifacts=b.read(Path(v['index']).parent/'artifacts.json')
assert 'unreviewed_original_review_json' in artifacts and 'missing_review_targets' in artifacts
assert 'unreviewed_original_review_json' not in handoff['artifacts'] and 'missing_review_targets' not in handoff['artifacts']
assert 'handoff' in c.complete_ranges(c.audit(v['index'],job/'retrieval.jsonl'),'handoff_batch','name')
sid=done['receipt']['session']['id'];assert sid not in v['prior']['session_ids']
tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];assert tokens<v['prior']['max_tokens']
print(json.dumps({'prior':v['prior'],'tokens':tokens,'session_ids':v['prior']['session_ids']+[sid],'binding_output_sha256':b.sha(job/'output.json'),'binding_reservation_sha256':b.sha(root/'reservation.json'),'source_root':v['previous_root'],'source_currentness':v['source_currentness']}))
'''

def stopped(root):
 root=Path(root).resolve();code=Path(b.read(root/'jobs/binding-repair/request.json')['code_root']).resolve()
 c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed closed binding code required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged binding verifier required')
 v=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True))
 c.require(len(set(v['session_ids']))==len(v['session_ids'])==5 and v['prior']['spent_correction_rounds']==0,'Exactly original four roles plus empty binding session required')
 return v

def artifacts(v):
 # Keep existing bound review references visible to support selection without
 # printing the ledger twice in the typed handoff.
 return {**prior_repair.contents(v['prior']),'original_review_bindings':v['prior']['review']}

def metadata(protocol,units):
 case=b.read(protocol['case_path']);return {'role':'correction','repair_version':VERSION,'round':2,'before_sha256':b.digest(units),'unit_sha256':{k:b.digest(v['value'])for k,v in units.items()},'case':case['scope_notes'],'period':case.get('period')}

def prompt(protocol,index,job):
 from . import earnings_file_pipeline as p
 return p.instruction('correction',index,job,protocol)+'\nThis is the FINAL original correction2, combining fresh source adjudication of missing review bindings WITH actual authored corrections. Inspect COMPLETE original call/support/candidate and entire original ledger/targets in handoff. Return ONLY {"bindings":[{"unit_id":"exact missing factual analysis unit","passage_ids":["exact original P IDs"]}],"correction":{"before_sha256":"exact original unit batch digest","changes":[...]}}. Bind every missing target once from real original source support; preserve review prose/criteria/valid bindings and all other decisions. Do not infer evidence from reviewer prose, labels or prefixes. Then author all required material and editorial corrections to the original candidate using the ordinary correction change schema and exact before hashes. Do not return bindings alone or treat an unbound review as accepted. If unsupported, block explicitly rather than invent support. Use ctx.validate_result on the combined object. No extra correction is authorized. NEW independent FULLreview2 remains mandatory after this completed correction.\n'

def validate_proposal(index,job,value,a,catalog,bundle):
 from . import earnings_file_pipeline as p,earnings_batch_review as batch
 c.require(isinstance(value,dict) and set(value)=={'bindings','correction'},'Combined bindings and authored correction only')
 review=contract.apply(json.loads(a['unreviewed_original_review_json']),a['units'],catalog,{'bindings':value['bindings']})
 p.coverage('review',index,job,review,catalog,a)
 accepted,findings,passed=p.review_result(review,a['units'],a['state'],a['signals'],catalog,Path(a['original_review_job']))
 c.require(not passed and findings,'Original factual revisions must remain explicit')
 plan,hashes=batch.resolve_correction_hashes(a['units'],value['correction'],bound_batch_sha256=b.digest(a['units']))
 c.require(plan.get('changes'),'Actual authored correction required; bindings alone cannot consume final round')
 plan,basis=batch.resolve_basis_citations(a['units'],plan,bundle);items,_=batch.apply(a['units'],plan,batch.EDITORIAL_VERSION);state,signals=batch.validate(items,bundle,catalog)
 p.coverage('correction',index,job,items,catalog,a)
 return {'state':state,'signals':signals,'bound_review':review,'findings':findings,'correction':plan,'hash_derivation':hashes,'basis_derivation':basis}

def initialize(root,*,source_currentness):
 from . import earnings_file_pipeline as p,earnings_file_runner as runner,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=stopped(root);previous=Path(v['source_root']);prior_repair.reservation_path(previous,root);prior_repair.currentness(previous,source_currentness);c.require(source_currentness==v['source_currentness'],'Same exact qualified original scope required')
 destination=root/'final-correction-reservation.json';job=root/'jobs/final-correction-2';c.require(not destination.exists() and not job.exists(),'One immutable final correction slot required')
 protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');a=artifacts(v);bundle=evidence.load_bundle(protocol['evidence_manifest']);markdown=p.markdown.report(a['state'],bundle,catalog,a['signals']);index=c.assemble(protocol['evidence_manifest'],catalog,root/'final-context',artifacts=a,metadata=metadata(protocol,a['units']),markdown=markdown)
 bindings={'role':'correction','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(a),'metadata_sha256':b.digest(metadata(protocol,a['units'])),'inherited_tokens':v['tokens'],'spent_correction_rounds':2,'binding_output_sha256':v['binding_output_sha256'],'binding_reservation_sha256':v['binding_reservation_sha256'],'source_currentness_sha256':source_currentness['sha256']}
 record={'version':VERSION,'root':str(root),'prior':v,'job':str(job),'index':str(index),'bindings':bindings,'models':v['prior']['models'],'max_tokens':v['prior']['max_tokens']-v['tokens'],'source_currentness':source_currentness,'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('correction',index)};c.write(destination,record);return record

def frozen(root,method):
 root=Path(root).resolve();job=root/'jobs/final-correction-2'
 if not (job/'request.json').exists():return None
 code=Path(b.read(job/'request.json')['code_root']).resolve();c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed final verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged final verifier required')
 if code==Path(__file__).resolve().parent.parent:return None
 c.require(method in ('verify_reservation','completed'),'Exact frozen operation required')
 program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_review_binding_final as h;print(json.dumps(getattr(h,sys.argv[3])(Path(sys.argv[2]))))'
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))

def verify_reservation(root):
 old=frozen(root,'verify_reservation')
 if old is not None:return old
 from . import earnings_file_runner as runner
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();record=b.read(root/'final-correction-reservation.json');v=stopped(root);previous=Path(v['source_root']);prior_repair.reservation_path(previous,root);prior_repair.currentness(previous,record['source_currentness'],as_of=launched_at(root/'jobs/final-correction-2'));c.require(record['source_currentness']==v['source_currentness'],'Qualified scope changed')
 protocol=b.read(previous/'protocol.json');a=artifacts(v);index=root/'final-context/index.json';job=root/'jobs/final-correction-2';expected={'role':'correction','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(a),'metadata_sha256':b.digest(metadata(protocol,a['units'])),'inherited_tokens':v['tokens'],'spent_correction_rounds':2,'binding_output_sha256':v['binding_output_sha256'],'binding_reservation_sha256':v['binding_reservation_sha256'],'source_currentness_sha256':record['source_currentness']['sha256']}
 c.require(record=={'version':VERSION,'root':str(root),'prior':v,'job':str(job),'index':str(index),'bindings':expected,'models':v['prior']['models'],'max_tokens':v['prior']['max_tokens']-v['tokens'],'source_currentness':record['source_currentness'],'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('correction',index)},'Final original lineage/assignment/usage changed')
 c.require(b.read(index.parent/'artifacts.json')==a and b.read(index.parent/'metadata.json')==metadata(protocol,a['units']),'Final context changed');c.Evidence(index,job/'retrieval.jsonl',_replay=True).verify();return record

def completed(root):
 old=frozen(root,'completed')
 if old is not None:return old
 from . import earnings_file_runner as runner,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=runner.verify_job(job)
 c.require(q['bindings']==v['bindings'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['correction'] and (job/'prompt.md').read_text()==v['prompt'],'Exact original final correction assignment required')
 previous=Path(v['prior']['source_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);out=validate_proposal(Path(v['index']),job,done['content'],artifacts(v['prior']),catalog,bundle);sid=done['receipt']['session']['id'];tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];ids=v['prior']['session_ids']+[sid]
 c.require(len(set(ids))==len(ids)==6 and tokens<v['prior']['prior']['max_tokens'],'Six distinct real sessions and unchanged original allowance required')
 return {**out,'session_ids':ids,'tokens':tokens,'max_tokens':v['prior']['prior']['max_tokens'],'models':v['models'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],'spent_correction_rounds':2,'start_round':2}

def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');record={'version':PREPARATION_VERSION,'repair_root':str(root),'final_reservation_sha256':b.sha(root/'final-correction-reservation.json'),**v};c.write(output,record);return record

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['final_reservation_sha256']==b.sha(root/'final-correction-reservation.json'),'Exact final reservation required');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['spent_correction_rounds']==2,'Final correction/state/accounting changed');return v
