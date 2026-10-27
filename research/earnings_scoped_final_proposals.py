"""One explicitly approved exact proposal batch, then fresh signals and full review.

This uses native batch correction semantics, preserves all authenticated usage,
and cannot authorize another correction or increase the original token ceiling.
"""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from . import earnings_mixed_runner as b, earnings_file_context as c
from . import earnings_retrieval_reference_repair as ref
from . import earnings_batch_review as batch, earnings_mechanical_preflight as mechanical
from . import earnings_compact_evidence as evidence

VERSION = 'authenticated-scoped-final-proposals-continuation-v1'
PROGRAM = r'''
import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
from research import earnings_file_context as context,earnings_financial_outline as outline
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert sorted(x.name for x in (root/'jobs').iterdir())==['review-0','signal_author']
assert not any(protocol.get(k) for k in ('review_preparation_path','signal_preparation_path','recovery_path','budget_authorization','authorized_prior_tokens','retrieval_repair_rounds','analysis_repair_rounds'))
retrieval=b.read(protocol['preparation_path']);analysis=b.read(protocol['analysis_preparation_path'])
assert retrieval['version']=='authenticated-exact-retrieval-identity-transport-v1' and analysis['version']=='authenticated-source-label-display-continuation-v1'
assert protocol['inherited_tokens']==analysis['tokens'] and analysis['session_ids'][0]==retrieval['session_id']
assert protocol['max_correction_rounds']==2 and protocol['max_tokens']<=1200000
financial=outline.artifact(bundle['financial'],expanded=protocol.get('report_template')==p.template.VERSION)
state={'artifacts':{'financial':financial,'retrieval':retrieval['content'],'analysis':analysis['content']},'format':p.mechanical.formatting(financial,bundle)}
assert p.mechanical.check(state,bundle,catalog)['status']=='ready_for_independent_review'
case=b.read(protocol['case_path']);tokens=protocol['inherited_tokens'];sessions=list(analysis['session_ids'])
provenance={'retrieval_transport_provenance':retrieval['derivation'],'analysis_display_transport_provenance':analysis['derivation']}
def authenticate(name,role,deps,metadata,report):
 global tokens
 job=root/'jobs'/name;q=b.read(job/'request.json');done=r.verify_job(job);index=Path(q['context_index'])
 assert index.resolve()==root/'contexts'/name/'index.json'
 metadata={**metadata,'case_scope_notes':case.get('scope_notes',[])}
 with tempfile.TemporaryDirectory(prefix='verified-scoped-context-') as temporary:
  expected=context.assemble(protocol['evidence_manifest'],catalog,Path(temporary)/'context',artifacts=deps,metadata=metadata,markdown=report)
  assert b.read(expected)==b.read(index)
 assert q['bindings']=={'protocol_sha256':b.sha(root/'protocol.json'),'role':role,'context_sha256':b.sha(index),'artifact_sha256':b.digest(deps),'metadata_sha256':b.digest(metadata)}
 assert [q['model'],q['effort']]==protocol['models'][role] and (job/'prompt.md').read_text()==p.instruction(role,index,job,protocol)
 assert q['max_tokens']==protocol['max_tokens']-tokens and q['max_tool_calls']==protocol['max_tool_calls_per_job']==48
 p.coverage(role,index,job,done['content'],catalog,deps)
 sid=done['receipt']['session']['id'];used=done['receipt']['session']['usage']['totalTokens']
 assert sid not in sessions and type(used) is int and used>0
 sessions.append(sid);tokens+=used
 return done['content']
metadata={'role':'signal_author','case':case['scope_notes'],'period':case.get('period'),'report_sha256':p.signals.report_digest(state)}
deps={'state':state,'finding_catalog':p.signals.finding_catalog(state),**provenance}
pack=authenticate('signal_author','signal_author',deps,metadata,p.markdown.report(state,bundle,catalog))
pack=p.signals.validate(pack,state,bundle,catalog);items=p.batch.units(state,pack)
state,pack=p.batch.validate(items,bundle,catalog)
assert p.mechanical.check(state,bundle,catalog)['status']=='ready_for_independent_review'
metadata={'round':0,'batch_sha256':b.digest(items),'report_sha256':p.signals.report_digest(state),'signals_sha256':b.digest(pack),'pending_findings':{}}
deps={'units':items,'state':state,'signals':pack,'qa_grounding':b.read(root/'qa-grounding.json'),**provenance}
review=authenticate('review-0','review',deps,metadata,p.markdown.report(state,bundle,catalog,pack))
accepted,findings,passed=p.review_result(review,items,state,pack,catalog,root/'jobs/review-0');assert not passed and findings
assert len(sessions)==len(set(sessions))==4 and tokens<protocol['max_tokens']
print(json.dumps({'state':state,'signals':pack,'items':items,'findings':findings,'tokens':tokens,'session_ids':sessions,
 'review_output_sha256':b.sha(root/'jobs/review-0/output.json'),'case_sha256':protocol['case_sha256'],
 'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens'],'models':protocol['models'],
 'writing_sha256':protocol['writing_sha256'],'report_template':protocol['report_template'],
 'grounding':bundle['qa_grounding'],'catalog':catalog,'evidence_manifest':protocol['evidence_manifest']}))
'''


def replay(previous):
    previous=Path(previous).resolve();code=ref.frozen(b.read(previous/'jobs/review-0/request.json')['code_root'])
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',PROGRAM,str(code),str(previous)],text=True))


def apply_proposal(original,proposal,catalog):
    """Translate exact approved fields into one native atomic correction batch."""
    items=original['items'];state=original['state']
    c.require(proposal.get('version')=='source-backed-final-correction-proposal-v1' and
              proposal.get('provider_calls')==0 and proposal.get('frozen_outputs_modified') is False,'Exact offline proposal required')
    c.require(proposal['review_output_sha256']==original['review_output_sha256'] and
              proposal['batch_sha256']==b.digest(items) and
              proposal['original_analysis_sha256']==b.digest(state['artifacts']['analysis']),'Proposal original candidate changed')
    passages={row['passage_id']:row for row in catalog['passages']}
    c.require(proposal['source_passages'] and all(pid in passages and row==passages[pid] for pid,row in proposal['source_passages'].items()),'Proposal original source passages changed')
    operations=proposal['operations'];c.require(isinstance(operations,list) and 0<len(operations)<=32,'Bounded explicit approved operations required')
    changed={};seen=set()
    for op in operations:
        c.require(set(op)=={'unit_id','unit_before_sha256','field','before','after','source_passage_ids','reason'},'Exact approved operation fields required')
        key=op['unit_id'];field=op['field']
        c.require(isinstance(key,str) and re.fullmatch(r'analysis:\d+',key) and key in items and
                  field in ('text','citations','quotes') and (key,field) not in seen,'Unique approved analysis field required')
        seen.add((key,field));old=items[key]['value']
        c.require(op['unit_before_sha256']==b.digest(old) and old[field]==op['before'] and op['before']!=op['after'],'Stale or unchanged approved field')
        c.require(isinstance(op['reason'],str) and op['reason'].strip() and op['source_passage_ids'] and
                  set(op['source_passage_ids'])<=set(proposal['source_passages']),'Exact original support for every operation required')
        changed.setdefault(key,copy.deepcopy(old))[field]=copy.deepcopy(op['after'])
    c.require(len(proposal['affected_units'])==len(set(proposal['affected_units'])) and set(changed)==set(proposal['affected_units']),'Approved affected unit set changed')
    plan={'before_sha256':b.digest(items),'changes':[{'unit_id':key,'before_sha256':b.digest(items[key]['value']),
           'value':value,'reason':'Exact user-approved source-bound proposal; fresh signals and full review required.'} for key,value in changed.items()]}
    candidate,pending=batch.apply(items,plan,batch.EDITORIAL_VERSION)
    revised,unaccepted=batch.materialize(candidate)
    c.require(b.digest(revised['artifacts']['analysis'])==proposal['proposed_analysis_sha256'],'Proposed analysis digest differs')
    return revised,unaccepted,plan,sorted(pending)


def validate_approval(previous,proposal_path,approval,original):
    previous=Path(previous).resolve();private=previous.parents[3]
    c.require(approval.get('version')=='explicit-one-cycle-earnings-correction-v1' and approval.get('scope')=='one_additional_correction_cycle'
              and approval.get('approved') is True and type(approval.get('max_additional_correction_cycles')) is int and approval.get('max_additional_correction_cycles')==1,'Explicit one additional correction approval required')
    evidence_of_approval=approval.get('approval',{})
    c.require(all(isinstance(evidence_of_approval.get(k),str) and evidence_of_approval[k].strip() for k in ('response','question')),'Recorded human approval required')
    reference=Path(approval['proposal_path']);c.require(not reference.is_absolute() and '..' not in reference.parts,'Private-relative approved proposal required')
    c.require((private/reference).resolve()==Path(proposal_path).resolve() and approval['proposal_sha256']==b.sha(proposal_path),'Different approved proposal')
    c.require(approval['source_run_id']==previous.parent.name and approval['source_protocol_sha256']==b.sha(previous/'protocol.json')
              and approval['source_request_sha256']==b.digest(b.read(previous.parent/'request.json')),'Approval original run changed')
    c.require(approval['report_max_tokens']==original['max_tokens'] and approval['inherited_report_tokens']==original['tokens']
              and approval['remaining_tokens']==original['max_tokens']-original['tokens'] and approval['models']==original['models'],'Approval changes inherited usage/routes/remaining allowance')
    c.require(type(approval['source_preparation_tokens']) is int and approval['source_preparation_tokens']>=0 and
              approval['source_preparation_tokens']+approval['report_max_tokens']==approval['original_total_max_tokens']<=1200000,'Original aggregate ceiling required')


def derive(previous,proposal_path,approval_path):
    previous=Path(previous).resolve();proposal_path=Path(proposal_path).resolve();approval_path=Path(approval_path).resolve()
    original=replay(previous);proposal=b.read(proposal_path);approval=b.read(approval_path)
    validate_approval(previous,proposal_path,approval,original)
    c.require(proposal['run_id']==previous.parent.name,'Proposal targets another original run')
    state,unaccepted,plan,pending=apply_proposal(original,proposal,original['catalog'])
    bundle=evidence.load_bundle(original['evidence_manifest']);bundle['qa_grounding']=original['grounding']
    check=mechanical.check(state,bundle,original['catalog']);c.require(check['status']=='ready_for_independent_review','Approved candidate fails complete source/schema checks')
    result={k:v for k,v in original.items() if k not in ('state','signals','items','catalog','evidence_manifest','findings')}
    result.update(version=VERSION,previous_root=str(previous),protocol_sha256=b.sha(previous/'protocol.json'),
        proposal_path=str(proposal_path),proposal_sha256=b.sha(proposal_path),approval_path=str(approval_path),approval_sha256=b.sha(approval_path),
        state=state,signals=unaccepted,findings=original['findings'],start_round=1,spent_correction_rounds=1,remaining_correction_rounds=0,
        derivation={'method':'one-exact-human-approved-native-correction-batch','original_state_sha256':b.digest(original['state']),
                    'derived_state_sha256':b.digest(state),'plan':plan,'invalidated_units':pending,
                    'approved_source_support':[{'unit_id':op['unit_id'],'field':op['field'],'source_passage_ids':op['source_passage_ids']} for op in proposal['operations']],
                    'reviewer_anchor_corrections':copy.deepcopy(proposal.get('reviewer_anchor_corrections',[])),
                    'signal_disposition':'Old signals unaccepted; a fresh signal author must regenerate all signals.',
                    'acceptance':'One fresh full independent review only; failure is terminal without another authorization.'})
    return result


def prepare(previous,case,proposal,approval,output):
    c.require(not Path(output).exists(),'New immutable scoped preparation required')
    value=derive(previous,proposal,approval);c.require(value['case_sha256']==b.sha(case),'Original approved case required')
    c.write(output,value);return value


def verify(path,case,catalog):
    value=b.read(path);c.require(isinstance(value,dict) and value.get('version')==VERSION,'Explicit scoped final preparation required')
    c.require(value==derive(value['previous_root'],value['proposal_path'],value['approval_path']),'Approved candidate/usage/authorization changed')
    c.require(value['case_sha256']==b.sha(case) and value['catalog_sha256']==b.digest(catalog),'Original approved case/catalog required')
    return value
