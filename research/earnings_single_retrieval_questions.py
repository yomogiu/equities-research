"""Explicit source-adjudicated question addresses after one closed retrieval.

The diagnostic schema check uses the complete original question membership only
as a placeholder to check every OTHER original field, never as a repair mapping.
Actual replacements require a fresh source read, validation and full review.
"""
from pathlib import Path
import copy,inspect,json,subprocess,sys,re
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_retrieval_repair as original,earnings_retrieval_reference_repair as ref
VERSION='authenticated-single-retrieval-question-addresses-v1'
PREPARATION_VERSION='authenticated-single-retrieval-question-address-preparation-v1'

def targets(raw,catalog,index):
 candidate,found,preserved=ref.candidate_and_targets(raw,raw,catalog,index)
 c.require(not preserved and candidate==raw and len(found)==1 and found[0]['field']=='question_passage_ids','Exactly one original question-address field required')
 known={p['passage_id']for p in catalog['passages']};t=found[0];bad=[x for x in t['before_ids']if x not in known]
 c.require(len(bad)==1 and len(t['before_ids'])==len(set(t['before_ids'])) and 1<=len(t['allowed_passage_ids'])<=32 and 1<=len(t['required_scope_ids'])<=32,'One unknown question address with bounded complete original membership required')
 return found

def apply(candidate,selected,proposal,catalog):
 c.require(len(selected)==1 and selected[0]['field']=='question_passage_ids','One explicit question target required')
 out=ref.apply(candidate,selected,proposal,catalog)
 for t in selected:
  known={p['passage_id']for p in catalog['passages']};before=t['before_ids'];position=next(i for i,x in enumerate(before)if x not in known);after=next(x for x in out['exchange_coverage']if x['exchange_id']==t['exchange_id'])[t['field']];count=len(after)-len(before)+1
  c.require(1<=count<=32 and after[:position]==before[:position] and after[position+count:]==before[position+1:],'Only the invalid question address position may change')
 return out

def derive(previous):
 from . import earnings_compact_evidence as evidence
 previous=Path(previous).resolve();prior=original.original(previous);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);selected=targets(prior['raw'],catalog,bundle['transcript_index'])
 q=b.read(previous/'jobs/retrieval/request.json');code=ref.frozen(q['code_root'])
 program=r'''
import sys,json,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);selected=json.loads(sys.argv[3]);protocol,bundle,catalog=p.load(root);job=root/'jobs/retrieval';q=b.read(job/'request.json');done=r.verify_job(job);raw=done['content'];known={x['passage_id']for x in catalog['passages']};t=selected[0]
assert not any(protocol.get(k) for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval'] and [q['model'],q['effort']]==protocol['models']['retrieval'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert protocol['max_tokens']<=1200000 and protocol['max_correction_rounds']==2 and protocol.get('report_template')=='source-led-six-sections-v1'
assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest'] and (job/'prompt.md').read_text()==p.instruction('retrieval',Path(q['context_index']),job,protocol)
rows=[x for x in raw['exchange_coverage']if x['exchange_id']==t['exchange_id']];assert len(rows)==1 and rows[0][t['field']]==t['before_ids'];e=next(x for x in bundle['transcript_index']['exchanges']if x['id']==t['exchange_id']);assert t['allowed_passage_ids']==[x['passage_id']for x in catalog['passages']if x['scope_id']in e['question_turn_ids']]
bad=[x for x in t['before_ids']if x not in known];assert len(bad)==1
try:p.verify(root)
except ValueError as error:assert str(error)=='Required original evidence was not completely inspected: '+bad[0]
else:raise AssertionError('Exact original question-address failure required')
# Preserve the ENTIRE original exchange ledger. Omit only the unknown typed ID
# for inspection outside that position; no other row or address is waived.
inspected=copy.deepcopy(raw);next(x for x in inspected['exchange_coverage']if x['exchange_id']==t['exchange_id'])[t['field']]=[x for x in t['before_ids']if x in known]
p.coverage('retrieval',Path(q['context_index']),job,inspected,catalog,{})
# Placeholder for schema checking ONLY: complete known question membership,
# not a selected replacement, source mapping, preparation or accepted output.
diagnostic=copy.deepcopy(raw);next(x for x in diagnostic['exchange_coverage']if x['exchange_id']==t['exchange_id'])[t['field']]=list(t['allowed_passage_ids']);p.pipe.validate('retrieval',diagnostic,bundle,catalog)
print(json.dumps({'checked':True}))
'''
 subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(previous),json.dumps(selected)],text=True)
 return prior,copy.deepcopy(prior['raw']),selected

def reservation_path(previous,output):
 previous=Path(previous).resolve();output=Path(output).resolve();code=ref.frozen(b.read(previous/'jobs/retrieval/request.json')['code_root']);private=code.parent.parent;run=previous.parent.name
 c.require(re.fullmatch('[a-f0-9]{24}',run) and previous==private/'reporting/runs'/run/'pipeline','Canonical original report required')
 c.require(output==private/'reporting/repairs/retrieval-addresses'/run,'One canonical question repair reservation required')
 def mentions(v):
  if isinstance(v,dict):return any(mentions(x)for x in v.values())
  if isinstance(v,list):return any(mentions(x)for x in v)
  if not isinstance(v,str):return False
  parts=Path(v).parts
  return v in (run,str(previous),str(previous.parent)) or parts[-4:]==('reporting','runs',run,'pipeline') or parts[-3:]==('reporting','runs',run)
 for path in (private/'reporting/repairs').rglob('reservation.json'):
  if path==output/'reservation.json':continue
  c.require(not mentions(b.read(path)),'Existing canonical or legacy repair must be reconciled; no alternate slot or usage reset')

def instruction():
 return 'Use only the bound Evidence API. Freshly inspect the COMPLETE original question AND answer in all source_scope_ids, following every next_start. Adjudicate the single unknown QUESTION paragraph address from that original evidence; never infer a mapping from identifier prefix, similarity or prior prose. Return only {repairs:[{exchange_id,field,before_ids,after_ids}]}. Replace only the invalid position using allowed original question paragraph IDs that support the unchanged question. Preserve all original valid addresses/order, other fields, answers, quotes, prose and work. If unsupported, stop explicitly. Validate the typed proposal. This spends original correction1; fresh independent FULL report review and exact completion proof remain mandatory.\n'

def prompt(index):
 return instruction()+"```python\nimport sys\nsys.path.insert(0,"+repr(str(Path(__file__).resolve().parent.parent))+")\nfrom research.earnings_file_context import Evidence\nctx=Evidence.for_job()\nprint(ctx.handoff_batch())\n```\nThen print(ctx.source_batch(SOURCE_SCOPE_IDS)) for every metadata source_scope_ids; follow next_start and print(ctx.validate_result(proposal)). No introspection or invented locators."

def initialize(previous,output,*,source_currentness):
 from . import earnings_file_runner as runner
 previous=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable question reservation required');reservation_path(previous,output);prior,candidate,selected=derive(previous);original.currentness(previous,source_currentness);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');output.mkdir()
 meta={'role':'retrieval_reference','repair_version':VERSION,'source_scope_ids':sorted({s for t in selected for s in t['required_scope_ids']}),'targets':selected,'spent_correction_rounds':1};index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts={'reference_candidate':candidate,'reference_targets':selected},metadata=meta)
 bindings={'role':'retrieval_reference','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/retrieval/output.json'),'context_sha256':b.sha(index),'candidate_sha256':b.digest(candidate),'targets_sha256':b.digest(selected),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':source_currentness['sha256']}
 v={'version':VERSION,'previous_root':str(previous),'prior':prior,'candidate':candidate,'targets':selected,'tokens':prior['tokens'],'max_tokens':original.budget(prior),'models':prior['models'],'spent_correction_rounds':1,'job':str(output/'jobs/reference-repair'),'index':str(index),'prompt':prompt(index),'bindings':bindings,'source_currentness':source_currentness,'work_plan':runner.work_plan('retrieval_reference',index)};c.write(output/'reservation.json',v);return v

def frozen(root,method):
 job=Path(root)/'jobs/reference-repair'
 if not(job/'request.json').exists():return None
 code=ref.frozen(b.read(job/'request.json')['code_root'])
 if code==Path(__file__).resolve().parent.parent:return None
 c.require(method in ('verify_reservation','completed'),'Known historical question method required')
 program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_single_retrieval_questions as a;print(json.dumps(getattr(a,sys.argv[3])(Path(sys.argv[2]))))'
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))

def verify_reservation(root):
 historical=frozen(root,'verify_reservation')
 if historical is not None:return historical
 from . import earnings_file_runner as runner
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();v=b.read(root/'reservation.json');c.require(v['version']==VERSION,'Explicit question reservation required');previous=Path(v['previous_root']);reservation_path(previous,root);prior,candidate,selected=derive(previous);c.require((v['prior'],v['candidate'],v['targets'])==(prior,candidate,selected) and v['tokens']==prior['tokens'] and v['max_tokens']==original.budget(prior) and v['models']==prior['models'] and type(v['spent_correction_rounds']) is int and v['spent_correction_rounds']==1,'Original question work/accounting/limits changed');job=root/'jobs/reference-repair';index=root/'context/index.json';original.currentness(previous,v['source_currentness'],as_of=launched_at(job))
 expected={'role':'retrieval_reference','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/retrieval/output.json'),'context_sha256':b.sha(index),'candidate_sha256':b.digest(candidate),'targets_sha256':b.digest(selected),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':v['source_currentness']['sha256']};meta={'role':'retrieval_reference','repair_version':VERSION,'source_scope_ids':sorted({s for t in selected for s in t['required_scope_ids']}),'targets':selected,'spent_correction_rounds':1}
 c.require(Path(v['job'])==job and Path(v['index'])==index and v['bindings']==expected and b.read(index.parent/'metadata.json')==meta and b.read(index.parent/'artifacts.json')=={'reference_candidate':candidate,'reference_targets':selected},'Exact question context/paths required');c.require(v['prompt']==prompt(index) and v['work_plan']==runner.work_plan('retrieval_reference',index),'Question instruction/work plan changed');return v

def completed(root):
 historical=frozen(root,'completed')
 if historical is not None:return historical
 from . import earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Exact question request/limits required');done=runner.verify_job(job);previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);result=apply(v['candidate'],v['targets'],done['content'],catalog)
 pipeline.coverage('retrieval_reference',Path(v['index']),job,{'citations':sorted({s for t in v['targets']for s in t['required_scope_ids']}),'passage_ids':[x for row in done['content']['repairs']for x in row['after_ids']]},catalog,{})
 oldq=b.read(previous/'jobs/retrieval/request.json');pipeline.coverage('retrieval',Path(oldq['context_index']),previous/'jobs/retrieval',result,catalog,{});pipeline.pipe.validate('retrieval',result,bundle,catalog);sid=done['receipt']['session']['id'];c.require(sid!=v['prior']['session_id'],'Distinct fresh question session required');tokens=v['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'Original lifecycle exhausted')
 return {k:v['prior'][k]for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':result,'tokens':tokens,'session_id':sid,'session_ids':[v['prior']['session_id'],sid],'spent_correction_rounds':1,'address_derivation':done['content']}

def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original question case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and type(v['spent_correction_rounds']) is int and v['spent_correction_rounds']==1 and v['reservation_sha256']==b.sha(root/'reservation.json'),'Question preparation lineage changed');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original question case/work/accounting changed');return v
