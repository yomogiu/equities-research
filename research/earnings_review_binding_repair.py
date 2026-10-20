"""Opt-in original four-role review-binding repair; no report acceptance."""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_review_binding_recovery as contract
VERSION='authenticated-missing-review-source-repair-v1'
PREPARATION_VERSION='authenticated-missing-review-source-preparation-v1'


def currentness(previous,ref,*,as_of=None):
 from . import earnings_source_revalidation as proof
 previous=Path(previous).resolve();code=Path(b.read(previous/'jobs/review-0/request.json')['code_root']).resolve();private=code.parent.parent
 c.require(isinstance(ref,dict)and set(ref)=={'path','sha256'},'Explicit source proof required');path=proof.library.resolve(private,ref['path']);c.require(b.sha(path)==ref['sha256'],'Source proof changed');old=proof.verify(private,path,**({}if as_of is None else {'as_of':as_of}));record=b.read(path);new=b.read(proof.library.resolve(private,'library/packets/'+record['new_packet_id']+'.json'));spec=b.read(previous.parent/'request.json')['spec'];case=b.read(b.read(previous/'protocol.json')['case_path'])
 from .earnings_analysis_turn_address_repair import qualified_identity
 return qualified_identity(spec,case,record,old,new)


def reservation_path(previous,output):
 previous=Path(previous).resolve();output=Path(output).resolve();code=Path(b.read(previous/'jobs/review-0/request.json')['code_root']).resolve();private=code.parent.parent;run=previous.parent.name
 c.require(re.fullmatch('[a-f0-9]{24}',run)and previous==private/'reporting/runs'/run/'pipeline'and output==private/'reporting/repairs/review-bindings'/run,'One canonical original review repair path required')
 import os
 def mentions(value):
  if isinstance(value,dict):return any(mentions(x)for x in value.values())
  if isinstance(value,list):return any(mentions(x)for x in value)
  if not isinstance(value,str):return False
  parts=Path(os.path.normpath(value)).parts
  return value==run or parts[-4:]==('reporting','runs',run,'pipeline') or parts[-3:]==('reporting','runs',run)
 for path in (private/'reporting/repairs').glob('**/reservation.json'):
  if path.parent!=output:c.require(not mentions(b.read(path)),'Alternate/legacy prior repair usage must be reconciled')


def authenticate(previous):
 prior=contract.authenticate(previous);protocol=b.read(Path(previous)/'protocol.json');q=b.read(Path(previous)/'jobs/review-0/request.json');deps=b.read(Path(q['context_index']).parent/'artifacts.json')
 return {**prior,'state':deps['state'],'signals':deps['signals'],'max_tokens':protocol['max_tokens'],'catalog_sha256':b.digest(prior['catalog']),'original_review_job':str(Path(previous)/'jobs/review-0')}


def contents(prior):
 return {'state':prior['state'],'signals':prior['signals'],'units':prior['items'],'unreviewed_original_review_json':json.dumps(prior['review'],ensure_ascii=False,sort_keys=True),'missing_review_targets':prior['targets'],'original_review_job':prior['original_review_job']}


def prompt(protocol,index,job):
 from . import earnings_file_pipeline as p
 return p.instruction('analysis',index,job,protocol)+'\nThis is ONLY fresh source adjudication of missing factual analysis review-passage bindings, spending original correction1. Inspect COMPLETE original call, support pages, candidate, whole original decision ledger and each target. Return ONLY {"bindings":[{"unit_id":"exact missing factual analysis unit","passage_ids":["exact original catalog P IDs"]}]}. Every missing field exactly once, one to eight distinct original passages each. Do not infer evidence from reviewer prose, labels or prefixes; do not change criteria, classifications, prose, valid references, candidate or other decisions. If original sources do not support the unchanged review finding, block rather than invent evidence. Use ctx.validate_result(proposal). This job neither accepts the review/report nor authors corrections. A separately authenticated final original correction2 and NEW independent FULLreview2 remain mandatory.\n'


def initialize(previous,output,*,source_currentness):
 from . import earnings_file_runner as runner
 previous=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable canonical repair required');reservation_path(previous,output);prior=authenticate(previous);currentness(previous,source_currentness);cap=prior['max_tokens']-prior['tokens'];c.require(cap>128000,'Remaining original allowance must retain full output reservation');protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');output.mkdir();metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')};artifacts=contents(prior);index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts=artifacts,metadata=metadata);job=output/'jobs/binding-repair';bindings={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/review-0/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':source_currentness['sha256']};v={'version':VERSION,'previous_root':str(previous),'prior':prior,'max_tokens':cap,'models':prior['models'],'spent_correction_rounds':1,'source_currentness':source_currentness,'job':str(job),'index':str(index),'bindings':bindings,'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('analysis',index)};c.write(output/'reservation.json',v);return v


def frozen(root,method):
 root=Path(root).resolve();job=root/'jobs/binding-repair'
 if not(job/'request.json').exists():return None
 code=Path(b.read(job/'request.json')['code_root']).resolve();c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed repair verifier required');c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged repair verifier required')
 if code==Path(__file__).resolve().parent.parent:return None
 c.require(method in ('verify_reservation','completed'),'Known frozen operation required');program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_review_binding_repair as h;print(json.dumps(getattr(h,sys.argv[3])(Path(sys.argv[2]))))';return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))


def verify_reservation(root):
 old=frozen(root,'verify_reservation')
 if old is not None:return old
 from . import earnings_file_runner as runner
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();v=b.read(root/'reservation.json');c.require(v['version']==VERSION,'Explicit missing-review repair required');previous=Path(v['previous_root']);reservation_path(previous,root);prior=authenticate(previous);c.require(v['prior']==prior and v['models']==prior['models']and v['max_tokens']==prior['max_tokens']-prior['tokens']and v['spent_correction_rounds']==1,'Original usage/routes/rounds changed');job=root/'jobs/binding-repair';index=root/'context/index.json';currentness(previous,v['source_currentness'],as_of=launched_at(job));protocol=b.read(previous/'protocol.json');artifacts=contents(prior);metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')};expected={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/review-0/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':v['source_currentness']['sha256']};c.require(v['bindings']==expected and Path(v['job'])==job and Path(v['index'])==index and b.read(index.parent/'artifacts.json')==artifacts and b.read(index.parent/'metadata.json')==metadata and v['prompt']==prompt(protocol,index,job)and v['work_plan']==runner.work_plan('analysis',index),'Exact source/context/request plan required');return v


def validate_proposal(index,job,proposal,artifacts,catalog,bundle):
 from . import earnings_file_pipeline as p
 review=contract.apply(json.loads(artifacts['unreviewed_original_review_json']),artifacts['units'],catalog,proposal)
 p.coverage('review',index,job,review,catalog,artifacts)
 accepted,findings,passed=p.review_result(review,artifacts['units'],artifacts['state'],artifacts['signals'],catalog,Path(artifacts['original_review_job']))
 c.require(not passed and findings,'Original factual revisions remain unresolved; no acceptance')
 return review,findings


def completed(root):
 old=frozen(root,'completed')
 if old is not None:return old
 from . import earnings_file_runner as runner,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=runner.verify_job(job);c.require(q['bindings']==v['bindings']and q['max_tokens']==v['max_tokens']and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['review']and(job/'prompt.md').read_text()==v['prompt'],'Exact original review model/request/allowance required');previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);review,findings=validate_proposal(Path(v['index']),job,done['content'],contents(v['prior']),catalog,bundle);sid=done['receipt']['session']['id'];tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(sid not in v['prior']['session_ids']and tokens<v['prior']['max_tokens'],'Distinct charged session and original allowance required');return {'state':v['prior']['state'],'signals':v['prior']['signals'],'bound_review':review,'original_review_output_sha256':v['prior']['review_output_sha256'],'binding_output_sha256':b.sha(job/'output.json'),'session_ids':[*v['prior']['session_ids'],sid],'tokens':tokens,'models':v['models'],'max_tokens':v['prior']['max_tokens'],'case_sha256':v['prior']['case_sha256'],'catalog_sha256':v['prior']['catalog_sha256'],'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],'spent_correction_rounds':1,'start_round':2,'findings':findings}


def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value


def verify(path,case,catalog):
 v=b.read(path);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(Path(v['repair_root'])/'reservation.json'),'Immutable review binding preparation required');actual=completed(v['repair_root']);c.require(all(v[k]==x for k,x in actual.items())and v['case_sha256']==b.sha(case)and v['catalog_sha256']==b.digest(catalog)and len(v['session_ids'])==5 and v['spent_correction_rounds']==1,'Original state/charges/models/rounds changed');return v
