"""One canonical charged fresh-source binding repair; no report acceptance."""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
from . import earnings_signal_binding_recovery as contract
VERSION='authenticated-empty-signal-source-repair-v1'
PREPARATION_VERSION='authenticated-empty-signal-source-preparation-v1'


def currentness(previous,ref,*,as_of=None):
 from . import earnings_source_revalidation as proof
 previous=Path(previous).resolve();code=Path(b.read(previous/'jobs/signal_author/request.json')['code_root']).resolve();private=code.parent.parent
 c.require(isinstance(ref,dict)and set(ref)=={'path','sha256'},'Explicit source proof required');path=proof.library.resolve(private,ref['path']);c.require(b.sha(path)==ref['sha256'],'Source proof changed');old=proof.verify(private,path,**({}if as_of is None else {'as_of':as_of}));record=b.read(path);new=b.read(proof.library.resolve(private,'library/packets/'+record['new_packet_id']+'.json'));spec=b.read(previous.parent/'request.json')['spec'];case=b.read(b.read(previous/'protocol.json')['case_path'])
 from .earnings_analysis_turn_address_repair import qualified_identity
 return qualified_identity(spec,case,record,old,new)


def reservation_path(previous,output):
 previous=Path(previous).resolve();output=Path(output).resolve();code=Path(b.read(previous/'jobs/signal_author/request.json')['code_root']).resolve();private=code.parent.parent;run=previous.parent.name
 c.require(re.fullmatch('[a-f0-9]{24}',run)and previous==private/'reporting/runs'/run/'pipeline'and output==private/'reporting/repairs/signal-bindings'/run,'One canonical original signal repair path required')
 for path in (private/'reporting/repairs').glob('**/reservation.json'):
  if path.parent!=output:c.require(not(isinstance(b.read(path).get('previous_root'),str)and Path(b.read(path)['previous_root']).resolve()==previous),'Alternate prior repair usage must be reconciled')


def contents(prior):
 return {'state':prior['state'],'unreviewed_prior_signals_json':json.dumps(prior['raw_signals'],ensure_ascii=False,sort_keys=True),'empty_signal_targets':prior['targets'],'original_valid_source_inventory':{'citations':sorted({x for row in prior['raw_signals']['signals']for x in row['citations']})}}


def prompt(protocol,index,job):
 from . import earnings_file_pipeline as p
 return p.instruction('analysis',index,job,protocol)+'\nThis is ONLY a fresh source-adjudicated empty signal passage binding repair, spending original correction1. Inspect COMPLETE original call and supporting pages and complete state/original signals in handoff. Return ONLY {"bindings":[{"signal_id":"exact original empty target","passage_ids":["exact original catalog P IDs"]}]}. Bind EVERY named empty target once to one through eight distinct exact original passages based on complete real source support. No prefix/label/prior-prose inference or automatic section expansion. No edits to original signal prose, direction, evidence basis, financial periods, citations or identity. Use ctx.validate_result(proposal) before submission. Report completion and fresh independent full review are later stages performed by the host, not this role.\n'


def initialize(previous,output,*,source_currentness):
 from . import earnings_file_runner as runner
 previous=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable canonical repair required');reservation_path(previous,output);prior=contract.authenticate(previous);currentness(previous,source_currentness);cap=prior['max_tokens']-prior['tokens'];c.require(cap>128000,'Remaining original allowance must retain full output reservation');protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');output.mkdir();metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')};artifacts=contents(prior);index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts=artifacts,metadata=metadata);job=output/'jobs/binding-repair';bindings={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/signal_author/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':source_currentness['sha256']};v={'version':VERSION,'previous_root':str(previous),'prior':prior,'max_tokens':cap,'models':prior['models'],'spent_correction_rounds':1,'source_currentness':source_currentness,'job':str(job),'index':str(index),'bindings':bindings,'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('analysis',index)};c.write(output/'reservation.json',v);return v


def frozen(root,method):
 root=Path(root).resolve();job=root/'jobs/binding-repair'
 if not(job/'request.json').exists():return None
 code=Path(b.read(job/'request.json')['code_root']).resolve();c.require(re.fullmatch('[a-f0-9]{40}',code.name)and code.parent.name=='.report-workflow','Managed repair verifier required');c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official unchanged repair verifier required')
 if code==Path(__file__).resolve().parent.parent:return None
 c.require(method in ('verify_reservation','completed'),'Known frozen operation required');program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_signal_binding_repair as h;print(json.dumps(getattr(h,sys.argv[3])(Path(sys.argv[2]))))';return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))


def verify_reservation(root):
 old=frozen(root,'verify_reservation')
 if old is not None:return old
 from . import earnings_file_runner as runner
 from .earnings_second_retrieval_repair import launched_at
 root=Path(root).resolve();v=b.read(root/'reservation.json');c.require(v['version']==VERSION,'Explicit signal repair required');previous=Path(v['previous_root']);reservation_path(previous,root);prior=contract.authenticate(previous);c.require(v['prior']==prior and v['models']==prior['models']and v['max_tokens']==prior['max_tokens']-prior['tokens']and v['spent_correction_rounds']==1,'Original usage/routes/rounds changed');job=root/'jobs/binding-repair';index=root/'context/index.json';currentness(previous,v['source_currentness'],as_of=launched_at(job));protocol=b.read(previous/'protocol.json');artifacts=contents(prior);metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')};expected={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/signal_author/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':v['source_currentness']['sha256']};c.require(v['bindings']==expected and Path(v['job'])==job and Path(v['index'])==index and b.read(index.parent/'artifacts.json')==artifacts and b.read(index.parent/'metadata.json')==metadata and v['prompt']==prompt(protocol,index,job)and v['work_plan']==runner.work_plan('analysis',index),'Exact source/context/request plan required');return v


def validate_proposal(index,job,proposal,artifacts,catalog,bundle):
 from . import earnings_file_pipeline as p
 pack=contract.apply(json.loads(artifacts['unreviewed_prior_signals_json']),catalog,proposal);p.signals.validate(pack,artifacts['state'],bundle,catalog);p.coverage('analysis',index,job,pack,catalog,artifacts);return pack


def bare_json_job(job):
 """Recover only a closed canonical binding response rejected by its envelope.

 Never writes original execution/output files; source adjudication remains in
 validate_proposal and the successor still requires fresh independent review.
 """
 from . import earnings_file_runner as runner
 job=Path(job).resolve();q=b.read(job/'request.json');runner.verify_request(job,q)
 c.require(job.name=='binding-repair' and q['bindings'].get('repair_version')==VERSION,'Canonical binding job required')
 c.require(not(job/'output.json').exists() and not(job/'runtime-failure.json').exists(),'Envelope-only closed failure required')
 launch=b.read(job/'launch.json');execution=b.read(job/'execution.json')
 c.require(execution['status']=='execution_failed' and execution['exit_code']==0 and execution['request_sha256']==b.digest(q) and launch['request_sha256']==b.digest(q) and execution['launch_sha256']==b.sha(job/'launch.json'),'Exact successful process/failed envelope required')
 text=(job/'response.md').read_text()
 try:runner.parse(text)
 except ValueError as error:c.require(str(error)=='Exactly one JSON metadata block required in Markdown result','Exact envelope rejection required')
 else:raise ValueError('Valid envelope is not a bare-response recovery')
 value=json.loads(text);c.require(isinstance(value,dict) and set(value)=={'bindings'},'Bare bindings object only')
 receipt=runner.receipt(job,q);c.require(execution['session']==receipt,'Original measured session changed')
 start=b.read(job/'runtime-start.json');finish=b.read(job/'runtime-finish.json')
 c.require(start.get('launch_id')==launch['id'],'Original launch identity changed')
 for item in (start,finish):c.require(item.get('session_id')==receipt['id'] and item.get('model')==q['model'] and item.get('effort')==q['effort'] and item.get('oauth') is True,'Runtime identity changed')
 events=[json.loads(line) for line in (job/receipt['path']).read_text().splitlines() if line.strip()];messages=[x['message'] for x in events if x.get('type')=='message']
 runner.verify_wire(q,b.read(job/'wire.json'),messages);runner.verify_delivery(job,messages);c.audit(q['context_index'],job/'retrieval.jsonl')
 return {'content':value,'receipt':execution,'bare_response_sha256':b.sha(job/'response.md')}


def completed(root):
 job=Path(root).resolve()/'jobs/binding-repair'
 bare=job.exists() and (job/'response.md').exists() and not(job/'output.json').exists()
 old=None if bare else frozen(root,'completed')
 if old is not None:return old
 from . import earnings_file_runner as runner,earnings_compact_evidence as evidence
 root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=bare_json_job(job) if bare else runner.verify_job(job);c.require(q['bindings']==v['bindings']and q['max_tokens']==v['max_tokens']and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['signal_author']and(job/'prompt.md').read_text()==v['prompt'],'Exact original signal model/request/allowance required');previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);pack=validate_proposal(Path(v['index']),job,done['content'],contents(v['prior']),catalog,bundle);sid=done['receipt']['session']['id'];tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(sid not in v['prior']['session_ids']and tokens<v['prior']['max_tokens'],'Distinct charged session and original allowance required');return {'state':v['prior']['state'],'signals':pack,'session_ids':[*v['prior']['session_ids'],sid],'tokens':tokens,'models':v['models'],'max_tokens':v['prior']['max_tokens'],'case_sha256':v['prior']['case_sha256'],'catalog_sha256':v['prior']['catalog_sha256'],'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],'spent_correction_rounds':1,'start_round':1,'findings':{}}


def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value


def verify(path,case,catalog):
 v=b.read(path);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(Path(v['repair_root'])/'reservation.json'),'Immutable signal repair preparation required');actual=completed(v['repair_root']);c.require(all(v[k]==x for k,x in actual.items())and v['case_sha256']==b.sha(case)and v['catalog_sha256']==b.digest(catalog)and len(v['session_ids'])==4 and v['spent_correction_rounds']==1,'Original state/charges/models/rounds changed');return v
