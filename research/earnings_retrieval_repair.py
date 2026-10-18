"""One charged, source-inspecting retrieval repair after a closed coverage failure.

A reservation does not accept output or create a fresh report lifecycle. The
result must pass original-source coverage, schema and an independent report review.
"""
import json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-retrieval-repair-v1'
PROGRAM=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval']
assert not any(protocol.get(k) for k in ('preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
job=root/'jobs/retrieval';value=r.verify_job(job);q=b.read(job/'request.json')
assert q['bindings']['role']=='retrieval' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert (job/'prompt.md').read_text()==p.instruction('retrieval',Path(q['context_index']),job,protocol)
try:p.verify(root)
except ValueError as error:
 assert str(error).startswith('Required original evidence was not completely inspected: ')
else:raise AssertionError('Exact closed original coverage failure required')
print(json.dumps({'raw':value['content'],'tokens':value['receipt']['session']['usage']['totalTokens'],'session_id':value['receipt']['session']['id'],'max_tokens':protocol['max_tokens'],'models':protocol['models'],'case_sha256':protocol['case_sha256'],'writing_sha256':protocol['writing_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template']}))
'''
def original(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/retrieval/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name,'Original verifier changed')
    c.require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier edits forbidden')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original origin changed')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(root)],text=True))
def budget(prior):
    c.require(type(prior['tokens']) is int and 0<prior['tokens']<prior['max_tokens']<=1200000,'Bounded charged ancestor usage required')
    return prior['max_tokens']-prior['tokens']
def initialize(previous,output):
    from . import earnings_file_pipeline as pipeline
    root=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable repair reservation required')
    prior=original(root);cap=budget(prior);protocol=b.read(root/'protocol.json');catalog=b.read(root/'passages.json')
    output.mkdir();metadata={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(root/'protocol.json'),'spent_correction_rounds':1,'case_scope_notes':b.read(protocol['case_path']).get('scope_notes',[])}
    artifacts={'unreviewed_prior_retrieval':prior['raw'],'qa_grounding':b.read(root/'qa-grounding.json')}
    index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts=artifacts,metadata=metadata)
    job=output/'jobs/retrieval-repair';prompt=pipeline.instruction('retrieval',index,job,protocol)+'\nThis is the sole charged retrieval repair, consuming correction round 1 of the original report. The unreviewed prior retrieval is in artifacts.json. Inspect exact originals and repair ALL invalid source, passage, turn and exchange addresses. Preserve source qualification and full Q&A coverage. Never infer an ID from a prefix or treat old output as evidence. Return the complete validated retrieval object; use Evidence.validate_result before final submission.\n'
    c.require(len(prompt.encode())<=24000,'Bounded repair instructions required');bindings={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(root/'protocol.json'),'source_output_sha256':b.sha(root/'jobs/retrieval/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1}
    record={'version':VERSION,'previous_root':str(root),'source_protocol_sha256':b.sha(root/'protocol.json'),'source_output_sha256':b.sha(root/'jobs/retrieval/output.json'),'prior':prior,'max_tokens':cap,'spent_correction_rounds':1,'job':str(job),'index':str(index),'bindings':bindings,'prompt':prompt,'models':prior['models']}
    c.write(output/'reservation.json',record);return record

def verify_reservation(output):
    output=Path(output).resolve();v=b.read(output/'reservation.json');root=Path(v['previous_root']);c.require(v['version']==VERSION and v['source_protocol_sha256']==b.sha(root/'protocol.json') and v['source_output_sha256']==b.sha(root/'jobs/retrieval/output.json'),'Repair lineage changed')
    prior=original(root);c.require(v['prior']==prior and v['models']==prior['models'] and v['max_tokens']==budget(prior) and v['spent_correction_rounds']==1,'Repair cannot reset usage, models or rounds')
    c.require(Path(v['job'])==output/'jobs/retrieval-repair' and Path(v['index'])==output/'context/index.json','Repair path changed')
    from . import earnings_file_pipeline as pipeline
    protocol=b.read(root/'protocol.json');index=Path(v['index']);job=Path(v['job'])
    expected_artifacts={'unreviewed_prior_retrieval':prior['raw'],'qa_grounding':b.read(root/'qa-grounding.json')}
    expected={'role':'retrieval','repair_version':VERSION,'source_protocol_sha256':b.sha(root/'protocol.json'),'source_output_sha256':b.sha(root/'jobs/retrieval/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(expected_artifacts),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1}
    c.require(v['bindings']==expected and b.read(index.parent/'artifacts.json')==expected_artifacts,'Exact repair context and dependencies required')
    expected_prompt=pipeline.instruction('retrieval',index,job,protocol)+'\nThis is the sole charged retrieval repair, consuming correction round 1 of the original report. The unreviewed prior retrieval is in artifacts.json. Inspect exact originals and repair ALL invalid source, passage, turn and exchange addresses. Preserve source qualification and full Q&A coverage. Never infer an ID from a prefix or treat old output as evidence. Return the complete validated retrieval object; use Evidence.validate_result before final submission.\n'
    c.require(v['prompt']==expected_prompt,'Frozen repair instructions changed')
    return v

def completed(output):
    """Authenticate a completed repair; never converts incomplete execution."""
    from . import earnings_file_runner as runner,earnings_file_pipeline as pipeline,earnings_compact_evidence as evidence
    v=verify_reservation(output);job=Path(v['job']);q=b.read(job/'request.json');value=runner.verify_job(job)
    c.require(q['bindings']==v['bindings'] and (job/'prompt.md').read_text()==v['prompt'],'Repair request or instructions changed')
    c.require([q['model'],q['effort']]==v['models']['retrieval'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48,'Repair changed model or original limits')
    root=Path(v['previous_root']);protocol=b.read(root/'protocol.json');catalog=b.read(root/'passages.json');bundle=evidence.load_bundle(protocol['evidence_manifest'])
    pipeline.coverage('retrieval',Path(v['index']),job,value['content'],catalog,{})
    pipeline.pipe.validate('retrieval',value['content'],bundle,catalog)
    sid=value['receipt']['session']['id'];c.require(sid!=v['prior']['session_id'],'Fresh retrieval repair session required')
    tokens=v['prior']['tokens']+value['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'No lifecycle cap reset')
    return {'content':value['content'],'tokens':tokens,'session_id':sid,'session_ids':[v['prior']['session_id'],sid],'max_tokens':v['prior']['max_tokens'],'models':v['models'],'case_sha256':v['prior']['case_sha256'],'catalog_sha256':v['prior']['catalog_sha256'],'writing_sha256':v['prior']['writing_sha256'],'report_template':v['prior']['report_template'],'spent_correction_rounds':1}

PREPARATION_VERSION='authenticated-charged-retrieval-preparation-v1'
def prepare(output,case,destination):
    output=Path(output).resolve();v=completed(output);c.require(v['case_sha256']==b.sha(case),'Original case required')
    record={'version':PREPARATION_VERSION,'repair_root':str(output),'reservation_sha256':b.sha(output/'reservation.json'),**v};c.write(destination,record);return record

def verify(path,case,catalog):
    v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Repair preparation lineage changed')
    actual=completed(root);c.require(all(v[k]==x for k,x in actual.items()),'Repair preparation changed or usage reset')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['spent_correction_rounds']==1,'Original source identity and spent round required')
    return v
