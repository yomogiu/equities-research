"""Canonical fresh-source linked answer/quotation recovery; no inferred mapping."""
from pathlib import Path
import json,subprocess,sys
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_retrieval_repair as original,earnings_retrieval_reference_repair as ref
from . import earnings_retrieval_answer_quote as linked
VERSION='authenticated-single-retrieval-answer-quote-v1'
PREPARATION_VERSION='authenticated-single-retrieval-answer-quote-preparation-v1'
derive=linked.authenticate
reservation_path=linked.reservation_path

def apply(candidate,selected,proposal,catalog,index):
 c.require(selected==linked.targets(candidate,catalog,index),'Exact linked targets required')
 return linked.apply(candidate,catalog,index,proposal)

def instruction():
 return 'Use only the bound Evidence API. Freshly inspect the COMPLETE original question AND answer in all source_scope_ids, following every next_start. Adjudicate the single unknown linked ANSWER paragraph address and bare quotation from that original evidence; never infer a mapping from identifier prefix, similarity or prior prose. Return only {repairs:[{exchange_id,field,before_ids,after_ids}]}. Replace only the invalid position using exactly ONE allowed original answer paragraph at ONLY the invalid answer-list position and linked bare quotation position, supporting the unchanged question/answer. Preserve all original valid addresses/order, other fields, quotation text, prose and work. If unsupported, stop explicitly. Validate the typed proposal. This spends original correction1; fresh independent FULL report review and exact completion proof remain mandatory.\n'

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
 program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_single_retrieval_answer_quote as a;print(json.dumps(getattr(a,sys.argv[3])(Path(sys.argv[2]))))'
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
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Exact question request/limits required');done=runner.verify_job(job);previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);result=apply(v['candidate'],v['targets'],done['content'],catalog,bundle['transcript_index'])
 pipeline.coverage('retrieval_reference',Path(v['index']),job,{'citations':sorted({s for t in v['targets']for s in t['required_scope_ids']}),'passage_ids':[x for row in done['content']['repairs']for x in row['after_ids']]},catalog,{})
 oldq=b.read(previous/'jobs/retrieval/request.json');pipeline.coverage('retrieval',Path(oldq['context_index']),previous/'jobs/retrieval',result,catalog,{});pipeline.pipe.validate('retrieval',result,bundle,catalog);sid=done['receipt']['session']['id'];c.require(sid!=v['prior']['session_id'],'Distinct fresh question session required');tokens=v['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'Original lifecycle exhausted')
 return {k:v['prior'][k]for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':result,'tokens':tokens,'session_id':sid,'session_ids':[v['prior']['session_id'],sid],'spent_correction_rounds':1,'address_derivation':done['content']}

def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original question case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and type(v['spent_correction_rounds']) is int and v['spent_correction_rounds']==1 and v['reservation_sha256']==b.sha(root/'reservation.json'),'Question preparation lineage changed');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original question case/work/accounting changed');return v
