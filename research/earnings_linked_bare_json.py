"""Explicit immutable bare-JSON derivation for one closed linked address repair."""
import json,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_single_retrieval_answer_quote as h
VERSION='authenticated-linked-bare-json-preparation-v1'


def unique(pairs):
 out={}
 for k,v in pairs:
  c.require(k not in out,'Duplicate JSON field forbidden');out[k]=v
 return out


def proposal(text):
 c.require(isinstance(text,str)and text.strip().startswith('{')and text.strip().endswith('}'),'Exact bare JSON object required')
 value=json.loads(text,object_pairs_hook=unique);c.require(isinstance(value,dict)and set(value)=={'repairs'},'Only original typed repair proposal required');return value


PROGRAM=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2]);from research import earnings_single_retrieval_answer_quote as h,earnings_file_runner as r,earnings_mixed_runner as b,earnings_file_context as c
v=h.verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');r.verify_request(job,q);launch=b.read(job/'launch.json');execution=b.read(job/'execution.json')
assert not(job/'output.json').exists()and not(job/'resume.json').exists()and not(job/'runtime-failure.json').exists()
assert execution['status']=='execution_failed'and execution['exit_code']==0 and execution['request_sha256']==launch['request_sha256']==b.digest(q)and execution['launch_sha256']==b.sha(job/'launch.json')
assert q['bindings']==v['bindings']and q['max_tokens']==v['max_tokens']and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['retrieval']and(job/'prompt.md').read_text()==v['prompt']
receipt=r.receipt(job,q);assert receipt==execution['session'];start=b.read(job/'runtime-start.json');finish=b.read(job/'runtime-finish.json')
assert start['launch_id']==launch['id']
for x in(start,finish):assert x['session_id']==receipt['id']and x['model']==q['model']and x['effort']==q['effort']and x['oauth']is True
messages=[x['message']for x in map(json.loads,(job/receipt['path']).read_text().splitlines())if x.get('type')=='message'];wire=b.read(job/'wire.json');assert len(wire)==receipt['model_turns'];r.verify_wire(q,wire,messages);c.audit(q['context_index'],job/'retrieval.jsonl')
text=(job/'response.md').read_text()
try:r.parse(text)
except ValueError as error:assert str(error)=='Exactly one JSON metadata block required in Markdown result'
else:raise AssertionError('Only exact bare response envelope failure eligible')
print(json.dumps({'reservation':v,'request':q,'execution':execution,'receipt':receipt,'text':text,'artifact_sha256':{str(p.relative_to(root)):b.sha(p)for p in root.rglob('*')if p.is_file()and not p.name.endswith('.lock')}}))
'''


def authenticate(root):
 root=Path(root).resolve();q=b.read(root/'jobs/reference-repair/request.json');code=h.ref.frozen(q['code_root']);return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True))


def completed(root):
 from . import earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=authenticate(root);reservation=v['reservation'];previous=Path(reservation['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);selected=proposal(v['text']);result=h.apply(reservation['candidate'],reservation['targets'],selected,catalog,bundle['transcript_index']);job=Path(reservation['job']);pipeline.coverage('retrieval_reference',Path(reservation['index']),job,{'citations':sorted({s for t in reservation['targets']for s in t['required_scope_ids']}),'passage_ids':[x for row in selected['repairs']for x in row['after_ids']]},catalog,{})
 oldq=b.read(previous/'jobs/retrieval/request.json');pipeline.coverage('retrieval',Path(oldq['context_index']),previous/'jobs/retrieval',result,catalog,{});pipeline.pipe.validate('retrieval',result,bundle,catalog);sid=v['receipt']['id'];c.require(sid!=reservation['prior']['session_id'],'Distinct real repair session required');tokens=reservation['prior']['tokens']+v['receipt']['usage']['totalTokens'];c.require(tokens<reservation['prior']['max_tokens'],'Original allowance exceeded');return {k:reservation['prior'][k]for k in ('max_tokens','models','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':result,'tokens':tokens,'session_id':sid,'session_ids':[reservation['prior']['session_id'],sid],'spent_correction_rounds':1,'address_derivation':selected,'raw_response_sha256':b.sha(job/'response.md'),'closed_failed_artifact_sha256':v['artifact_sha256']}


def prepare(root,case,output):
 root=Path(root).resolve();value=completed(root);c.require(value['case_sha256']==b.sha(case),'Original case required');out={'version':VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**value};c.write(output,out);return out


def verify(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Immutable bare derivation lineage required');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items())and v['case_sha256']==b.sha(case)and v['catalog_sha256']==b.digest(catalog)and len(v['session_ids'])==2 and v['spent_correction_rounds']==1,'Original content/usage/models/rounds changed');return v
