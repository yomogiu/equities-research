"""One immutable same-slot recovery of an authenticated pre-model auth stop."""
from pathlib import Path
import json,subprocess,sys
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-analysis-auth-storage-recovery-v1'
PREPARATION_VERSION='authenticated-analysis-host-address-preparation-v1'
def stopped(job):
 job=Path(job);q=b.read(job/'request.json');ex=b.read(job/'execution.json')
 c.require(b.read(job/'runtime-failure.json')=={'stage':'auth_storage'} and b.read(job/'wire.json')==[],'Exact pre-model auth stop required')
 c.require(ex['status']=='execution_failed' and ex['exit_code']==1 and ex['request_sha256']==b.digest(q) and ex['launch_sha256']==b.sha(job/'launch.json'),'Closed bound execution required')
 c.require((job/'retrieval.jsonl').stat().st_size==0 and not any((job/n).exists() for n in ('runtime-start.json','runtime-finish.json','sessions','output.json','response.md','delivery.jsonl','transport-lifecycle.jsonl')),'Prior execution cannot be excluded')
 prime=Path(q['code_root'])/'research/earnings_file_prime.mjs';c.require(b.sha(prime)==q['helper_sha256'],'Original helper changed');text=prime.read_text();c.require(text.index("stage = 'auth_storage'")<text.index('auth.drainErrors()')<text.index("stage = 'registry'"),'Auth stage ordering changed')
 return {str(p.relative_to(job)):b.sha(p) for p in sorted(job.rglob('*')) if p.is_file()}
def expected(root,v):
 from . import earnings_analysis_address_repair as a
 failed=root/'jobs/address-repair';hashes=stopped(failed);job=root/'jobs/auth-recovery-1';protocol=b.read(Path(v['previous_root'])/'protocol.json')
 return {'version':VERSION,'reservation_sha256':b.sha(root/'reservation.json'),'failed_artifacts':hashes,'job':str(job),'index':v['index'],'prompt':a.prompt(protocol,Path(v['index']),job),'bindings':{**v['bindings'],'host_recovery_version':VERSION,'failed_request_sha256':b.sha(failed/'request.json'),'failed_artifacts_sha256':b.digest(hashes)},'models':v['models'],'max_tokens':v['max_tokens'],'max_tool_calls':48}
def initialize(root):
 from . import earnings_analysis_address_repair as a
 root=Path(root).resolve();v=a.verify_reservation(root);m=expected(root,v);c.require(not (root/'host-recovery.json').exists() and not Path(m['job']).exists(),'Single immutable host recovery required');m['code_root']=str(Path(__file__).resolve().parent.parent);c.write(root/'host-recovery.json',m);return verify(root)
def verify(root):
 from . import earnings_analysis_address_repair as a
 root=Path(root).resolve();m=b.read(root/'host-recovery.json');v=a.verify_reservation(root);e=expected(root,v);
 from .earnings_second_retrieval_repair import launched_at
 a.currentness(Path(v['previous_root']),v['source_currentness'],as_of=launched_at(Path(e['job'])));
 c.require(set(m)==set(e)|{'code_root'} and all(m[k]==x for k,x in e.items()),'Exact failed lineage/prompt/context/models/limits required')
 code=Path(m['code_root']);c.require(code.parent.name=='.report-workflow' and len(code.name)==40 and all(x in '0123456789abcdef' for x in code.name),'Managed producer required');c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official frozen producer required');return m
def completed(root):
 from . import earnings_analysis_address_repair as a,earnings_file_runner as r,earnings_file_pipeline as p,earnings_compact_evidence as evidence
 root=Path(root).resolve();m=verify(root);code=Path(m['code_root'])
 if code!=Path(__file__).resolve().parent.parent:
  program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_analysis_host_recovery as h;print(json.dumps(h.completed(Path(sys.argv[2]))))';return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True))
 v=a.verify_reservation(root);job=Path(m['job']);q=b.read(job/'request.json');done=r.verify_job(job);c.require(q['bindings']==m['bindings'] and q['code_root']==m['code_root'] and q['max_tokens']==m['max_tokens'] and q['max_tool_calls']==48 and q.get('resume') is None and [q['model'],q['effort']]==m['models']['analysis'] and (job/'prompt.md').read_text()==m['prompt'],'Exact recovery execution required')
 previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);catalog=b.read(previous/'passages.json');candidate=a.checked_candidate(v['prior']['raw'],done['content'],bundle['transcript_index']);p.pipe.validate('analysis',candidate,bundle,catalog);p.coverage('analysis',Path(v['index']),job,candidate,catalog,{})
 sid=done['receipt']['session']['id'];tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(sid not in v['prior']['session_ids'] and tokens<v['prior']['max_tokens'],'Distinct session/original cap required');return {k:v['prior'][k] for k in ('models','max_tokens','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':candidate,'tokens':tokens,'session_ids':[*v['prior']['session_ids'],sid],'spent_correction_rounds':1}
def prepare(root,case,output):
 root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),'host_recovery_sha256':b.sha(root/'host-recovery.json'),**v};c.write(output,value);return value
def preparation(path,case,catalog):
 v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json') and v['host_recovery_sha256']==b.sha(root/'host-recovery.json'),'Immutable recovery lineage required');actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original work/usage/case changed');return v
