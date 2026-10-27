"""Source-bound address proposals over two charged, completed retrieval sessions.

Original outputs are immutable. Empty omitted exchange coverage may be preserved
from the authenticated ancestor; ambiguous addresses require a new source read,
not a guessed mapping. Full original inspection and fresh review remain required.
"""
import copy,json,subprocess,sys,re
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-retrieval-reference-repair-v1'
PREPARATION_VERSION='authenticated-reference-retrieval-preparation-v1'
PROGRAM=r'''
import sys,json,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_retrieval_repair as first,earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_mixed_runner as b
v=first.verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=runner.verify_job(job)
assert q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens']
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval-repair']
try:first.completed(root)
except ValueError as e:assert str(e)=='Every Q&A exchange needs exactly one coverage entry' or str(e).startswith('Required original evidence was not completely inspected: ')
else:raise AssertionError('Closed unaccepted retrieval required')
source=Path(v['previous_root']);catalog=b.read(source/'passages.json');inspection=copy.deepcopy(done['content']);inspection['exchange_coverage']=[]
pipeline.coverage('retrieval',Path(v['index']),job,inspection,catalog,{})
assert done['receipt']['session']['id']!=v['prior']['session_id']
print(json.dumps({'reservation':v,'completed':done,'job_request':q}))
'''
def frozen(code):
 code=Path(code).resolve();c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
 c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
 c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Unexpected verifier origin');return code

def prior(first):
 first=Path(first).resolve();code=frozen(b.read(first/'jobs/retrieval-repair/request.json')['code_root'])
 return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(first)],text=True))

def candidate_and_targets(old,new,catalog,index):
 candidate=copy.deepcopy(new);preserved=False
 if candidate['exchange_coverage']==[]:
  c.require(bool(old['exchange_coverage']),'Authenticated original exchange coverage required');candidate['exchange_coverage']=copy.deepcopy(old['exchange_coverage']);preserved=True
 known={p['passage_id']:p for p in catalog['passages']};exchanges={e['id']:e for e in index['exchanges']};rows=candidate['exchange_coverage']
 c.require(len(rows)==len(exchanges) and {r['exchange_id'] for r in rows}==set(exchanges),'Exact original exchange membership required')
 targets=[]
 for row in rows:
  e=exchanges[row['exchange_id']]
  for field,turns in [('question_passage_ids','question_turn_ids'),('answer_passage_ids','answer_turn_ids')]:
   ids=row[field]
   if all(x in known for x in ids):continue
   scopes=e[turns];allowed=[p['passage_id'] for p in catalog['passages'] if p['scope_id'] in scopes]
   c.require(bool(allowed),'Exact canonical source paragraphs required')
   targets.append({'exchange_id':e['id'],'field':field,'before_ids':ids,'allowed_passage_ids':allowed,'required_scope_ids':list(dict.fromkeys(e['question_turn_ids']+e['answer_turn_ids'])),'unaccepted_question':row['question'],'unaccepted_answer':row['answer']})
 c.require(bool(targets),'No ambiguous reference defect to adjudicate');return candidate,targets,preserved

def apply(candidate,targets,proposal,catalog):
 c.require(set(proposal)=={'repairs'} and isinstance(proposal['repairs'],list),'Exact reference repair schema required')
 expected={(t['exchange_id'],t['field']):t for t in targets};seen=set();out=copy.deepcopy(candidate)
 for r in proposal['repairs']:
  c.require(set(r)=={'exchange_id','field','before_ids','after_ids'},'Only typed source addresses may change');key=(r['exchange_id'],r['field']);c.require(key in expected and key not in seen,'Exact unique target required');seen.add(key);t=expected[key]
  ids=r['after_ids'];c.require(r['before_ids']==t['before_ids'] and isinstance(ids,list) and bool(ids) and len(ids)==len(set(ids)) and set(ids)<=set(t['allowed_passage_ids']),'Source-bound replacement paragraph IDs required')
  c.require(set(t['before_ids'])&set(t['allowed_passage_ids'])<=set(ids),'Preserve every already valid address')
  next(x for x in out['exchange_coverage'] if x['exchange_id']==key[0])[key[1]]=ids
 c.require(seen==set(expected),'Every ambiguous reference must be addressed');return out

def initialize(first,output):
 from . import earnings_compact_evidence as evidence,earnings_passage_pipeline as pipe,earnings_retrieval_repair as original
 first=Path(first).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable reference repair required');p=prior(first);v=p['reservation'];source=Path(v['previous_root']);protocol=b.read(source/'protocol.json');catalog=b.read(source/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest'])
 candidate,targets,preserved=candidate_and_targets(v['prior']['raw'],p['completed']['content'],catalog,bundle['transcript_index']);tokens=v['prior']['tokens']+p['completed']['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'No lifecycle reset')
 original.currentness(source,v.get('source_currentness'))
 output.mkdir();metadata={'role':'retrieval_reference','targets':targets,'source_scope_ids':sorted({s for t in targets for s in t['required_scope_ids']}),'spent_correction_rounds':2}
 index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts={'reference_candidate':candidate,'reference_targets':targets},metadata=metadata)
 job=output/'jobs/reference-repair';prompt="Use only the bound Evidence API. Repair exact ambiguous question/answer paragraph addresses; never guess by ID spelling. No prose, other references or classifications may change. Prior source inspection remains authenticated but your target question AND answer must be freshly inspected. Return {repairs:[{exchange_id,field,before_ids,after_ids}]} for every target. Every after ID must be an allowed original paragraph supporting the exact question/answer. If no source-supported replacement exists, stop explicitly rather than inventing one.\n"+"```python\nimport sys\nsys.path.insert(0,"+repr(str(Path(__file__).resolve().parent.parent))+")\nfrom research.earnings_file_context import Evidence\nctx=Evidence.for_job()\nprint(ctx.handoff_batch())\n```\nNext read print(ctx.source_batch(SOURCE_SCOPE_IDS)) using all metadata source_scope_ids; follow next_start if any. No catalogue/attribute inspection or load_structured calls. Finally print(ctx.validate_result(proposal)); repair errors within your bounded calls. This consumes original final correction2; fresh independent full report review still mandatory."
 bindings={'role':'retrieval_reference','repair_version':VERSION,'first_reservation_sha256':b.sha(first/'reservation.json'),'first_output_sha256':b.sha(first/'jobs/retrieval-repair/output.json'),'context_sha256':b.sha(index),'candidate_sha256':b.digest(candidate),'targets_sha256':b.digest(targets),'inherited_tokens':tokens,'spent_correction_rounds':2}
 record={'version':VERSION,'first':str(first),'prior':p,'candidate':candidate,'targets':targets,'preserved_original_exchanges':preserved,'tokens':tokens,'max_tokens':v['prior']['max_tokens']-tokens,'job':str(job),'index':str(index),'prompt':prompt,'bindings':bindings,'models':v['models']};c.write(output/'reservation.json',record);return record

def completed(root):
 from . import earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence
 root=Path(root).resolve();record=b.read(root/'reservation.json');job=Path(record['job'])
 if (job/'request.json').exists():
  code=frozen(b.read(job/'request.json')['code_root'])
  if code!=Path(__file__).resolve().parent.parent:
   program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research.earnings_retrieval_reference_repair import completed;print(json.dumps(completed(Path(sys.argv[2]))))'
   return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True))
 v=record;c.require(v['version']==VERSION,'Known reference repair required');p=prior(v['first']);c.require(p==v['prior'],'Charged original work changed');expected_tokens=p['reservation']['prior']['tokens']+p['completed']['receipt']['session']['usage']['totalTokens'];c.require(v['tokens']==expected_tokens and v['max_tokens']==p['reservation']['prior']['max_tokens']-expected_tokens and v['models']==p['reservation']['models'],'Original token ledger or models changed');job=Path(v['job']);c.require(job==root/'jobs/reference-repair' and Path(v['index'])==root/'context/index.json','Reference paths changed');q=b.read(job/'request.json')
 c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'] and [q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Reference role limits or dependencies changed');done=runner.verify_job(job)
 source=Path(p['reservation']['previous_root']);protocol=b.read(source/'protocol.json');catalog=b.read(source/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);base,targets,preserved=candidate_and_targets(p['reservation']['prior']['raw'],p['completed']['content'],catalog,bundle['transcript_index']);c.require((base,targets,preserved)==(v['candidate'],v['targets'],v['preserved_original_exchanges']),'Candidate provenance changed')
 result=apply(base,targets,done['content'],catalog);pipeline.coverage('retrieval_reference',Path(v['index']),job,{'citations':sorted({s for t in targets for s in t['required_scope_ids']}),'passage_ids':[x for r in done['content']['repairs'] for x in r['after_ids']]},catalog,{})
 # Full preparation inspection stays anchored to the actual completed first job.
 pipeline.coverage('retrieval',Path(p['reservation']['index']),Path(p['reservation']['job']),result,catalog,{})
 pipeline.pipe.validate('retrieval',result,bundle,catalog);ids=[p['reservation']['prior']['session_id'],p['completed']['receipt']['session']['id'],done['receipt']['session']['id']];c.require(len(set(ids))==3,'Distinct charged sessions required');tokens=v['tokens']+done['receipt']['session']['usage']['totalTokens'];original=p['reservation']['prior'];c.require(tokens<original['max_tokens'],'Original cap exhausted')
 return {k:original[k] for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':result,'tokens':tokens,'session_id':ids[-1],'session_ids':ids,'spent_correction_rounds':2,'address_derivation':done['content'],'preserved_original_exchanges':preserved}

def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value

def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Reference preparation lineage changed');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original source, usage or work changed');return v
