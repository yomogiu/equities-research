"""Source-adjudicated addresses after one authenticated completed retrieval.

Only typed address fields may change. This spends original correction one and
carries both real sessions into the original lifecycle; fresh full review remains
mandatory. Neither ID similarity nor model prose supplies a source mapping.
"""
from pathlib import Path
import copy
from . import earnings_mixed_runner as b, earnings_file_context as c
from . import earnings_retrieval_repair as original, earnings_retrieval_reference_repair as ref
VERSION='authenticated-single-retrieval-addresses-v1'
PREPARATION_VERSION='authenticated-single-retrieval-address-preparation-v1'
QUOTED_VERSION='authenticated-single-retrieval-quoted-addresses-v1'
QUOTED_PREPARATION_VERSION='authenticated-single-retrieval-quoted-address-preparation-v1'

def exact_duplicate_membership(raw,catalog,index):
 from collections import Counter
 out=copy.deepcopy(raw);rows=out['exchange_coverage'];exchanges={e['id']:e for e in index['exchanges']};counts=Counter(r['exchange_id'] for r in rows)
 c.require(len(rows)==len(exchanges) and set(counts)<=set(exchanges),'Original exchange membership cardinality required')
 missing=set(exchanges)-set(counts);known={p['passage_id']:p['scope_id'] for p in catalog['passages']};changes=[]
 for number,row in enumerate(rows):
  current=row['exchange_id']
  if counts[current]==1:continue
  qids=row['question_passage_ids'];aids=row['answer_passage_ids']
  c.require(qids and aids and all(x in known for x in qids+aids),'Duplicated ledger identity requires complete known question and answer paragraphs')
  qs={known[x] for x in qids};answers={known[x] for x in aids}
  possible=[e['id'] for e in exchanges.values() if qs<=set(e['question_turn_ids']) and answers<=set(e['answer_turn_ids'])]
  c.require(len(possible)==1,'Unique original question AND answer turn membership required')
  target=possible[0]
  if target==current:continue
  c.require(target in missing,'Only an omitted original exchange can replace a duplicate label')
  row['exchange_id']=target;missing.remove(target);changes.append({'row':number,'before':current,'after':target,'question_passage_ids':qids,'answer_passage_ids':aids})
 c.require(not missing and len({x['exchange_id'] for x in rows})==len(exchanges),'Complete one-to-one original exchange ledger required')
 return out,changes

def quoted_targets(candidate,targets,catalog):
 known={p['passage_id'] for p in catalog['passages']};links=[]
 for number,quote in enumerate(candidate.get('quotes',[])):
  if not isinstance(quote,dict) or quote.get('passage_id') in known:continue
  c.require(set(quote)=={'passage_id'},'Only bare unknown quote addresses qualify')
  matches=[t for t in targets if t['field']=='answer_passage_ids' and t['before_ids']==[quote['passage_id']]]
  c.require(len(matches)==1,'Unknown quote requires one exact sole-address answer target')
  links.append({'quote_index':number,'before_id':quote['passage_id'],'exchange_id':matches[0]['exchange_id']})
 c.require(1<=len(links)<=3 and len({x['before_id'] for x in links})==len(links),'Unique bounded quoted address targets required')
 return links

def apply_quoted(candidate,targets,proposal,catalog):
 links=quoted_targets(candidate,targets,catalog);out=ref.apply(candidate,targets,proposal,catalog)
 for link in links:
  row=next(x for x in proposal['repairs'] if x['exchange_id']==link['exchange_id'] and x['field']=='answer_passage_ids')
  c.require(len(row['after_ids'])==1,'Quoted answer must select exactly one freshly adjudicated paragraph')
  out['quotes'][link['quote_index']]['passage_id']=row['after_ids'][0]
 return out

def derive(previous,*,quoted=False):
 from . import earnings_compact_evidence as evidence, earnings_file_pipeline as pipeline
 previous=Path(previous).resolve();prior=original.original(previous)
 protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest'])
 normalized,exchange_derivation=exact_duplicate_membership(prior['raw'],catalog,bundle['transcript_index'])
 candidate,targets,preserved=ref.candidate_and_targets(normalized,normalized,catalog,bundle['transcript_index'])
 c.require(not preserved and 1<=len(targets)<=3 and all(t['field']=='answer_passage_ids' for t in targets),'Only bounded unknown answer addresses in original complete exchange ledger qualify')
 # Original inspection outside these unknown addresses must already be complete.
 inspected=copy.deepcopy(candidate);inspected['exchange_coverage']=[]
 if quoted:
  links=quoted_targets(candidate,targets,catalog)
  inspected['quotes']=[q for i,q in enumerate(inspected['quotes']) if i not in {x['quote_index'] for x in links}]
 q=b.read(previous/'jobs/retrieval/request.json');pipeline.coverage('retrieval',Path(q['context_index']),previous/'jobs/retrieval',inspected,catalog,{})
 return prior,candidate,targets

def instruction(*,quoted=False):
 return (('The same unknown bare quote address is bound to a sole-address answer target. Select exactly ONE original answer paragraph for each such target; its quote address will follow that exact freshly adjudicated paragraph. No quote text or other fields may change. ' if quoted else '')+'Use only the bound Evidence API to adjudicate every unknown original answer paragraph address. Never guess from ID spelling, prefix, similarity or prior prose. Preserve every valid address, every other field, all prose and all original work. Return only {repairs:[{exchange_id,field,before_ids,after_ids}]}. Each replacement must be an allowed original answer paragraph supporting the unchanged answer. If unsupported, stop explicitly. Read the full target question AND answer via all source_scope_ids; follow next_start for complete coverage. No catalogue introspection. Validate the typed proposal before submission. This consumes original correction1; independent FULL report review is still mandatory.\n')

def initialize(previous,output,*,source_currentness,quoted=False):
 from . import earnings_file_runner as runner
 previous=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable single-retrieval address reservation required')
 prior,candidate,targets=derive(previous,quoted=quoted);original.currentness(previous,source_currentness);cap=original.budget(prior)
 protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');output.mkdir()
 metadata={'role':'retrieval_reference','source_scope_ids':sorted({s for t in targets for s in t['required_scope_ids']}),'targets':targets,'spent_correction_rounds':1}
 if quoted:metadata['repair_version']=QUOTED_VERSION
 index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts={'reference_candidate':candidate,'reference_targets':targets},metadata=metadata)
 code=Path(__file__).resolve().parent.parent
 prompt=instruction(quoted=quoted)+"```python\nimport sys\nsys.path.insert(0,"+repr(str(code))+")\nfrom research.earnings_file_context import Evidence\nctx=Evidence.for_job()\nprint(ctx.handoff_batch())\n```\nThen print(ctx.source_batch(SOURCE_SCOPE_IDS)) for every metadata source_scope_ids, follow next_start if any, and print(ctx.validate_result(proposal))."
 bindings={'role':'retrieval_reference','repair_version':QUOTED_VERSION if quoted else VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/retrieval/output.json'),'context_sha256':b.sha(index),'candidate_sha256':b.digest(candidate),'targets_sha256':b.digest(targets),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':source_currentness['sha256']}
 record={'version':QUOTED_VERSION if quoted else VERSION,'previous_root':str(previous),'prior':prior,'candidate':candidate,'targets':targets,'tokens':prior['tokens'],'max_tokens':cap,'models':prior['models'],'spent_correction_rounds':1,'job':str(output/'jobs/reference-repair'),'index':str(index),'prompt':prompt,'bindings':bindings,'source_currentness':source_currentness,'work_plan':runner.work_plan('retrieval_reference',index)}
 c.write(output/'reservation.json',record);return record

def verify_reservation(root):
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();v=b.read(root/'reservation.json');c.require(v['version'] in (VERSION,QUOTED_VERSION),'Known single retrieval address reservation required');quoted=v['version']==QUOTED_VERSION
 previous=Path(v['previous_root']);prior,candidate,targets=derive(previous,quoted=quoted)
 c.require((v['prior'],v['candidate'],v['targets'])==(prior,candidate,targets),'Original session, candidate or targets changed')
 c.require(v['tokens']==prior['tokens'] and v['max_tokens']==original.budget(prior) and v['models']==prior['models'] and v['spent_correction_rounds']==1,'Original usage/models/limits cannot reset')
 c.require(Path(v['job'])==root/'jobs/reference-repair' and Path(v['index'])==root/'context/index.json','Exact managed address paths required')
 original.currentness(previous,v['source_currentness'],as_of=launched_at(Path(v['job'])))
 expected={'role':'retrieval_reference','repair_version':QUOTED_VERSION if quoted else VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/retrieval/output.json'),'context_sha256':b.sha(Path(v['index'])),'candidate_sha256':b.digest(candidate),'targets_sha256':b.digest(targets),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':v['source_currentness']['sha256']}
 c.require(v['bindings']==expected,'Exact original and target dependencies required')
 # Context integrity is hash-bound; independently inspect its semantic membership.
 c.require(b.read(root/'context/artifacts.json')=={'reference_candidate':candidate,'reference_targets':targets},'Address context changed')
 meta=b.read(root/'context/metadata.json');c.require({k:v for k,v in meta.items() if k!='repair_version'}=={'role':'retrieval_reference','source_scope_ids':sorted({s for t in targets for s in t['required_scope_ids']}),'targets':targets,'spent_correction_rounds':1},'Target scope ledger changed');c.require(meta.get('repair_version')==(QUOTED_VERSION if quoted else None),'Quoted target protocol changed')
 code=Path(__file__).resolve().parent.parent
 prompt=instruction(quoted=quoted)+"```python\nimport sys\nsys.path.insert(0,"+repr(str(code))+")\nfrom research.earnings_file_context import Evidence\nctx=Evidence.for_job()\nprint(ctx.handoff_batch())\n```\nThen print(ctx.source_batch(SOURCE_SCOPE_IDS)) for every metadata source_scope_ids, follow next_start if any, and print(ctx.validate_result(proposal))."
 from . import earnings_file_runner as runner
 c.require(v['work_plan']==runner.work_plan('retrieval_reference',Path(v['index'])),'Exact target page/tool plan changed')
 c.require(v['prompt']==prompt,'Address instructions changed');return v

def completed(root):
 from . import earnings_file_runner as runner, earnings_file_pipeline as pipeline, earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json')
 c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Address role request or original model/limits changed')
 done=runner.verify_job(job);previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest'])
 result=(apply_quoted if v['version']==QUOTED_VERSION else ref.apply)(v['candidate'],v['targets'],done['content'],catalog)
 pipeline.coverage('retrieval_reference',Path(v['index']),job,{'citations':sorted({s for t in v['targets'] for s in t['required_scope_ids']}),'passage_ids':[x for row in done['content']['repairs'] for x in row['after_ids']]},catalog,{})
 oldq=b.read(previous/'jobs/retrieval/request.json');pipeline.coverage('retrieval',Path(oldq['context_index']),previous/'jobs/retrieval',result,catalog,{})
 pipeline.pipe.validate('retrieval',result,bundle,catalog)
 sid=done['receipt']['session']['id'];c.require(sid!=v['prior']['session_id'],'Fresh distinct address session required');tokens=v['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'Original lifecycle exhausted')
 return {k:v['prior'][k] for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':result,'tokens':tokens,'session_id':sid,'session_ids':[v['prior']['session_id'],sid],'spent_correction_rounds':1,'address_derivation':done['content']}

def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');record={'version':QUOTED_PREPARATION_VERSION if b.read(root/'reservation.json')['version']==QUOTED_VERSION else PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,record);return record

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version'] in (PREPARATION_VERSION,QUOTED_PREPARATION_VERSION) and v['reservation_sha256']==b.sha(root/'reservation.json'),'Single retrieval address preparation lineage changed');actual=completed(root);c.require((v['version']==QUOTED_PREPARATION_VERSION)==(b.read(root/'reservation.json').get('version')==QUOTED_VERSION),'Quoted preparation version changed');c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original source/work/accounting changed');return v
