"""Fresh source adjudication of bounded citation fields in a closed author.

No reference is inferred. Original prose, valid addresses and quote selections
are immutable. A successful repair spends correction one, carries all three real
sessions, and still needs signals, fresh full review and report acceptance.
"""
from pathlib import Path
import copy,inspect,json,re,subprocess,sys
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-analysis-address-repair-v1'
PREPARATION_VERSION='authenticated-analysis-address-preparation-v1'


def targets(value,index):
    known={e['id'] for e in index['exchanges']}
    if not known or len(known)!=len(index['exchanges']):raise ValueError('Unique original exchanges required')
    fields=[(['opening_citations'],value['opening_citations'])]
    fields += [(['findings',i,'citations'],f['citations']) for i,f in enumerate(value['findings'])]
    out=[];unknown=set()
    for path,ids in fields:
        if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):raise ValueError('Exact original citation lists required')
        bad=[(i,x) for i,x in enumerate(ids) if x.startswith('exchange-') and x not in known]
        if not bad:continue
        if len(bad)!=1 or len(ids)<2:raise ValueError('One invalid address and retained original support per field required')
        position,identifier=bad[0];unknown.add(identifier)
        out.append({'field_path':path,'before_ids':list(ids),'position':position,'unknown_id':identifier,'allowed_exchange_ids':sorted(known)})
    if len(unknown)!=1 or not 1<=len(out)<=4:raise ValueError('One unknown exchange address in one to four typed fields required')
    return out


def field(value,path):
    for key in path:value=value[key]
    return value


def inspection_candidate(value,index):
    """Diagnostic only: authenticate every other original inspection/field."""
    out=copy.deepcopy(value)
    for target in targets(value,index):
        ids=field(out,target['field_path']);ids.pop(target['position'])
    return out


def checked_candidate(original,candidate,index):
    expected=copy.deepcopy(original)
    for target in targets(original,index):
        path=target['field_path'];old=target['before_ids'];position=target['position'];new=field(candidate,path)
        if not isinstance(new,list) or any(not isinstance(x,str) for x in new):raise ValueError('Exact replacement citation list required')
        count=len(new)-len(old)+1
        if not 1<=count<=3 or new[:position]!=old[:position] or new[position+count:]!=old[position+1:]:raise ValueError('Only the invalid address position may change')
        selected=new[position:position+count]
        if not set(selected)<=set(target['allowed_exchange_ids']) or len(new)!=len(set(new)):raise ValueError('Distinct exact original exchange selections required')
        dest=field(expected,path[:-1]);dest[path[-1]]=list(new)
    if expected!=candidate:raise ValueError('Original prose, valid citations, structure and quotations must remain exact')
    return expected


PROGRAM=r'''
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval']
assert not any(protocol.get(k) for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert protocol['max_correction_rounds']==2 and protocol['max_tokens']<=1200000
assert protocol.get('report_template')=='source-led-six-sections-v1' and protocol.get('financial_mode')=='deterministic-original-facts-v1'
values={}
for role in ('retrieval','analysis'):
 job=root/'jobs'/role;q=b.read(job/'request.json');v=r.verify_job(job)
 assert q['bindings']['role']==role and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
 assert [q['model'],q['effort']]==protocol['models'][role]
 assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest']
 assert (job/'prompt.md').read_text()==p.instruction(role,Path(q['context_index']),job,protocol)
 values[role]=v
raw=values['analysis']['content'];selected=targets(raw,bundle['transcript_index']);bad=selected[0]['unknown_id']
try:p.verify(root)
except ValueError as error:assert str(error)=='Required original evidence was not completely inspected: '+bad
else:raise AssertionError('Exact original unknown address coverage failure required')
diagnostic=inspection_candidate(raw,bundle['transcript_index'])
for role,content in [('retrieval',values['retrieval']['content']),('analysis',diagnostic)]:
 job=root/'jobs'/role;q=b.read(job/'request.json');p.coverage(role,Path(q['context_index']),job,content,catalog,{})
 p.pipe.validate(role,content,bundle,catalog)
q=b.read(root/'jobs/analysis/request.json');deps=b.read(Path(q['context_index']).parent/'artifacts.json')
assert deps['retrieval']==values['retrieval']['content'] and b.digest(deps)==q['bindings']['artifact_sha256']
sessions=[values[x]['receipt']['session']['id'] for x in ('retrieval','analysis')]
assert len(set(sessions))==2
tokens=sum(values[x]['receipt']['session']['usage']['totalTokens'] for x in ('retrieval','analysis'))
assert 0<tokens<protocol['max_tokens']
print(json.dumps({'raw':raw,'targets':selected,'dependencies':deps,'tokens':tokens,'session_ids':sessions,'models':protocol['models'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template']}))
'''


def original(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/analysis/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official verifier required')
    program='import sys,json,copy;from pathlib import Path\nsys.path.insert(0,sys.argv[1])\n'+inspect.getsource(targets)+inspect.getsource(field)+inspect.getsource(inspection_candidate)+PROGRAM
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True))


def contents(prior):
    # A JSON string is explicit unreviewed output, not a source inventory. The
    # invalid original address must never be supplied as an evidence locator.
    from . import earnings_file_pipeline as pipeline
    diagnostic=copy.deepcopy(prior['raw'])
    for target in prior['targets']:field(diagnostic,target['field_path']).pop(target['position'])
    inventory={'citations':sorted(pipeline.refs(diagnostic))}
    return {**prior['dependencies'],'original_valid_source_inventory':inventory,'unreviewed_prior_analysis_json':json.dumps(prior['raw'],ensure_ascii=False,sort_keys=True),'address_targets':prior['targets']}


def prompt(protocol,index,job):
    from . import earnings_file_pipeline as pipeline
    return pipeline.instruction('analysis',index,job,protocol)+'\nThis is a bounded source-adjudicated citation repair, spending original correction round one. Decode artifacts["unreviewed_prior_analysis_json"] as the ORIGINAL unreviewed author. Inspect the complete original call and supporting source pages. Return that complete original analysis with changes ONLY at the invalid citation positions named in address_targets. Select one to three exact allowed ORIGINAL exchange IDs at each position based on original source support, never prefix/similarity guesses. Preserve all prose, titles, scope, valid citations, order, quotes and other structure byte-for-byte as JSON values. Do not rewrite analysis or treat original author prose as evidence. Use ctx.validate_result(candidate) before final submission. Fresh independent FULL report review remains mandatory; this is not acceptance.\n'


def qualified_identity(spec,case,proof,old,new):
    identifiers=(proof['old_packet_id'],proof['new_packet_id'])
    c.require(old['packet_id']==identifiers[0] and new['packet_id']==identifiers[1],'Exact qualified proof endpoints required')
    c.require(spec['packet_id'] in identifiers,'Qualification belongs to another packet')
    packet=old if spec['packet_id']==identifiers[0] else new
    c.require(all(case.get(k)==spec.get(k)==packet.get(k) for k in ('packet_id','issuer_id','period')),'Original report/case/qualified identity changed')
    return 'old_packet' if packet is old else 'new_packet'


def currentness(previous,ref,*,as_of=None):
    from . import earnings_source_revalidation as proof
    previous=Path(previous).resolve();q=b.read(previous/'jobs/analysis/request.json');code=Path(q['code_root']).resolve();private=code.parent.parent
    c.require(isinstance(ref,dict) and set(ref)=={'path','sha256'},'Explicit source qualification reference required')
    path=proof.library.resolve(private,ref['path']);c.require(b.sha(path)==ref['sha256'],'Source qualification proof changed')
    old=proof.verify(private,path,**({} if as_of is None else {'as_of':as_of}));record=b.read(path)
    new=b.read(proof.library.resolve(private,'library/packets/'+record['new_packet_id']+'.json'))
    request=b.read(previous.parent/'request.json');case=b.read(b.read(previous/'protocol.json')['case_path'])
    return qualified_identity(request['spec'],case,record,old,new)


def reservation_path(previous,output):
    previous=Path(previous).resolve();output=Path(output).resolve()
    code=Path(b.read(previous/'jobs/analysis/request.json')['code_root']).resolve();private=code.parent.parent
    run=previous.parent.name
    c.require(re.fullmatch('[a-f0-9]{24}',run) and previous==private/'reporting/runs'/run/'pipeline','Canonical original report required')
    c.require(output==private/'reporting/repairs/analysis-addresses'/run,'One canonical repair reservation per original run required')


def initialize(previous,output,*,source_currentness):
    from . import earnings_retrieval_repair as retrieval,earnings_file_runner as runner
    previous=Path(previous).resolve();output=Path(output).resolve();c.require(not output.exists(),'New immutable address repair required')
    prior=original(previous);reservation_path(previous,output);currentness(previous,source_currentness);cap=retrieval.budget(prior);protocol=b.read(previous/'protocol.json');catalog=b.read(previous/'passages.json');output.mkdir()
    metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')}
    artifacts=contents(prior);index=c.assemble(protocol['evidence_manifest'],catalog,output/'context',artifacts=artifacts,metadata=metadata);job=output/'jobs/address-repair'
    bindings={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/analysis/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':source_currentness['sha256']}
    value={'version':VERSION,'previous_root':str(previous),'prior':prior,'max_tokens':cap,'models':prior['models'],'spent_correction_rounds':1,'source_currentness':source_currentness,'job':str(job),'index':str(index),'bindings':bindings,'prompt':prompt(protocol,index,job),'work_plan':runner.work_plan('analysis',index)}
    c.write(output/'reservation.json',value);return value


def frozen(root,method):
    root=Path(root).resolve();job=root/'jobs/address-repair'
    if not (job/'request.json').exists():return None
    code=Path(b.read(job/'request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen repair verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen repair verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Official repair verifier required')
    if code==Path(__file__).resolve().parent.parent:return None
    c.require(method in ('verify_reservation','completed'),'Known frozen replay required')
    program='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from research import earnings_analysis_address_repair as a;print(json.dumps(getattr(a,sys.argv[3])(Path(sys.argv[2]))))'
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),method],text=True))


def verify_reservation(root):
    historical=frozen(root,'verify_reservation')
    if historical is not None:return historical
    from . import earnings_retrieval_repair as retrieval,earnings_file_runner as runner
    from .earnings_second_retrieval_repair import launched_at
    root=Path(root).resolve();v=b.read(root/'reservation.json');c.require(v['version']==VERSION,'Known address repair required');previous=Path(v['previous_root']);prior=original(previous);reservation_path(previous,root)
    c.require(v['prior']==prior and v['models']==prior['models'] and v['max_tokens']==retrieval.budget(prior) and v['spent_correction_rounds']==1,'Original work/usage/models/rounds changed')
    job=root/'jobs/address-repair';index=root/'context/index.json';protocol=b.read(previous/'protocol.json');artifacts=contents(prior)
    currentness(previous,v['source_currentness'],as_of=launched_at(job))
    metadata={'role':'analysis','repair_version':VERSION,'case':b.read(protocol['case_path'])['scope_notes'],'period':b.read(protocol['case_path']).get('period')}
    expected={'role':'analysis','repair_version':VERSION,'source_protocol_sha256':b.sha(previous/'protocol.json'),'source_output_sha256':b.sha(previous/'jobs/analysis/output.json'),'context_sha256':b.sha(index),'artifact_sha256':b.digest(artifacts),'metadata_sha256':b.digest(metadata),'inherited_tokens':prior['tokens'],'spent_correction_rounds':1,'source_currentness_sha256':v['source_currentness']['sha256']}
    c.require(Path(v['job'])==job and Path(v['index'])==index and v['bindings']==expected,'Exact repair paths/bindings required')
    c.require(b.read(index.parent/'artifacts.json')==artifacts and b.read(index.parent/'metadata.json')==metadata,'Original repair context changed')
    c.require(v['prompt']==prompt(protocol,index,job) and v['work_plan']==runner.work_plan('analysis',index),'Repair instruction/work plan changed');return v


def completed(root):
    historical=frozen(root,'completed')
    if historical is not None:return historical
    from . import earnings_file_runner as runner,earnings_file_pipeline as p,earnings_compact_evidence as evidence
    root=Path(root).resolve();v=verify_reservation(root);job=Path(v['job']);q=b.read(job/'request.json');done=runner.verify_job(job)
    c.require(q['bindings']==v['bindings'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['analysis'] and (job/'prompt.md').read_text()==v['prompt'],'Exact repair execution required')
    previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);catalog=b.read(previous/'passages.json');candidate=checked_candidate(v['prior']['raw'],done['content'],bundle['transcript_index'])
    p.pipe.validate('analysis',candidate,bundle,catalog);p.coverage('analysis',Path(v['index']),job,candidate,catalog,{})
    sid=done['receipt']['session']['id'];c.require(sid not in v['prior']['session_ids'],'Distinct fresh repair session required');tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];c.require(tokens<v['prior']['max_tokens'],'Original lifecycle exhausted')
    return {k:v['prior'][k] for k in ('models','max_tokens','case_sha256','catalog_sha256','writing_sha256','report_template')}|{'content':candidate,'tokens':tokens,'session_ids':[*v['prior']['session_ids'],sid],'spent_correction_rounds':1}


def prepare(root,case,output):
    root=Path(root).resolve();v=completed(root);c.require(v['case_sha256']==b.sha(case),'Original case required');value={'version':PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':b.sha(root/'reservation.json'),**v};c.write(output,value);return value


def verify(path,case,catalog):
    v=b.read(path);root=Path(v['repair_root']);c.require(v['version']==PREPARATION_VERSION and v['reservation_sha256']==b.sha(root/'reservation.json'),'Immutable analysis repair lineage required');actual=completed(root)
    c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original case/work/models/accounting changed');return v
