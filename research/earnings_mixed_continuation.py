"""Explicit follow-up: reuse authenticated preparation, quarantine bad candidates.

This is not a fresh cold end-to-end timing. It preserves the original trial,
launches only a Sol analyst and independent reviewer, and never hides retries.
"""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from research import earnings_experiment as base
from research import earnings_mixed_pipeline as pipeline
from research import earnings_compact_evidence as evidence
from research.earnings_quote_candidates import qualify_candidates
from research.earnings_mixed_runner import run_role,verify_job

VERSION='luna-sol-quarantine-continuation-v1'


def run(parent,output):
    parent=Path(parent).resolve();root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True)
    p=pipeline.verify_protocol(parent);bundle=evidence.load_bundle(p['evidence_manifest'])
    inputs={r:verify_job(parent/'jobs'/f'{r}-r0') for r in ('financial','retrieval')}
    for role in inputs:
        request=base.read(parent/'jobs'/f'{role}-r0/request.json')
        expected=pipeline.MODELS[role]
        if (request['model'],request['effort'])!=expected or request['bindings']['protocol_sha256']!=base.sha(parent/'protocol.json') or request['bindings']['role']!=role:
            raise ValueError('Reused preparation identity does not match frozen case/model')
    qualified=qualify_candidates(p['evidence_manifest'],inputs['retrieval']['content'])
    deps={'financial':inputs['financial']['content'],'retrieval':qualified['content']}
    for role,out in deps.items():pipeline.validate_output(role,out,bundle)
    base.save(root/'candidate-qualification.json',qualified)
    code=[{'path':str(Path(__file__).parent/name),'sha256':base.sha(Path(__file__).parent/name)} for name in ('earnings_mixed_continuation.py','earnings_quote_candidates.py')]
    protocol={'version':VERSION,'parent':str(parent),'parent_protocol_sha256':base.sha(parent/'protocol.json'),
              'code':code,'preparation':{r:{'output_path':inputs[r]['output_path'],'output_sha256':base.sha(inputs[r]['output_path']),'receipt':inputs[r]['receipt']} for r in inputs},
              'policy_sha256':base.sha(root/'candidate-qualification.json'),'models':p['models'],
              'scope':'Separate follow-up, reusing original r0 preparers. No text repair. All rejected quote candidates remain recorded. New analyst and fresh reviewer. Zero correction rounds in this follow-up.',
              'measurement':'Actual new downstream latency/usage reported separately. Inherited preparation usage shown once. Combined critical path is a projection from measured stages, not a fresh end-to-end run. Original failed retries remain in parent trial metrics.'}
    base.save(root/'protocol.json',protocol)
    if (root/'result.json').exists():return verify(root)
    writing=Path(p['writing_standard']).read_text();jobs=[];validation_errors=[]
    for role in ('analysis','review'):
        prompt=pipeline.prompt_for(role,bundle,writing,deps)
        prompt+='\n\nPREPARATION HANDOFF POLICY\nInvalid candidate quotations have been quarantined by deterministic exact-source validation. The retrieval artifact includes only accepted original quotations; all other retrieval fields and source text are unchanged. Rejected candidates are unavailable for quoting. The final report must still satisfy all original evidence and writing checks.\n'+pipeline.packed({'rejected_candidates':qualified['rejected_candidates']})
        result=run_role(root/'jobs'/role,prompt,*pipeline.MODELS[role],
                        {'protocol_sha256':base.sha(root/'protocol.json'),'role':role,'dependencies_sha256':base.digest(deps)},timeout=1200)
        jobs.append({'role':role,'path':str(root/'jobs'/role),'receipt':result['receipt']})
        try:pipeline.validate_output(role,result['content'],bundle)
        except (ValueError,KeyError,TypeError) as exc:validation_errors.append({'role':role,'error':str(exc)})
        if role=='analysis':deps['analysis']=result['content']
        else:review=result['content']
    base.save(root/'artifacts.json',deps);base.save(root/'review.json',review)
    text=pipeline.report_text(deps['analysis'],deps['financial'],bundle)
    pipeline.immutable_text(root/'report.txt',text)
    accepted=not validation_errors and review.get('verdict')=='pass'
    pipeline.render(root,deps['analysis'],deps['financial'],bundle,
                    'Independent substantive and writing review passed · candidate-quarantine follow-up' if accepted else 'DRAFT — independent review or validation requires corrections · candidate-quarantine follow-up')
    wall=(datetime.fromisoformat(jobs[-1]['receipt']['finished_at'])-datetime.fromisoformat(jobs[0]['receipt']['started_at'])).total_seconds()
    result={'version':VERSION,'status':'accepted' if accepted else 'draft','protocol_sha256':base.sha(root/'protocol.json'),
            'jobs':jobs,'downstream_wall_seconds':wall,'reused_preparation_max_seconds':max(i['receipt']['elapsed_seconds'] for i in inputs.values()),
            'projected_critical_path_seconds':max(i['receipt']['elapsed_seconds'] for i in inputs.values())+wall,
            'projection_warning':'Reused preparation plus new downstream measured stages; NOT a newly measured full pipeline wall time.',
            'validation_errors':validation_errors,'correction_rounds':0,'artifact_digest':base.digest(deps),
            'review_sha256':base.sha(root/'review.json'),'report_sha256':base.sha(root/'report.txt'),
            'html_sha256':base.sha(root/'report.html'),'words':pipeline.word_count(text)}
    base.save(root/'result.json',result)
    return verify(root)


def verify(root):
    root=Path(root).resolve();p=base.read(root/'protocol.json');result=base.read(root/'result.json')
    parent=Path(p['parent']);parent_protocol=pipeline.verify_protocol(parent)
    bundle=evidence.load_bundle(parent_protocol['evidence_manifest'])
    if p['parent_protocol_sha256']!=base.sha(parent/'protocol.json') or result['protocol_sha256']!=base.sha(root/'protocol.json'):
        raise ValueError('Protocol binding changed')
    for c in p['code']:
        if base.sha(c['path'])!=c['sha256']:raise ValueError('Continuation code changed')
    inputs={r:verify_job(parent/'jobs'/f'{r}-r0') for r in ('financial','retrieval')}
    for role,value in inputs.items():
        if value['receipt']!=p['preparation'][role]['receipt'] or base.sha(value['output_path'])!=p['preparation'][role]['output_sha256']:
            raise ValueError('Preparation output or receipt changed')
    q=qualify_candidates(parent_protocol['evidence_manifest'],inputs['retrieval']['content'])
    if q!=base.read(root/'candidate-qualification.json') or p['policy_sha256']!=base.sha(root/'candidate-qualification.json'):
        raise ValueError('Candidate derivation changed')
    deps=base.read(root/'artifacts.json');review=base.read(root/'review.json')
    if deps['financial']!=inputs['financial']['content'] or deps['retrieval']!=q['content'] or base.digest(deps)!=result['artifact_digest']:
        raise ValueError('Derived artifact binding changed')
    prefix={k:deps[k] for k in ('financial','retrieval')}
    for job in result['jobs']:
        observed=verify_job(job['path']);request=base.read(Path(job['path'])/'request.json')
        expected=deps['analysis'] if job['role']=='analysis' else review
        if job['receipt']!=observed['receipt'] or observed['content']!=expected or request['bindings']!={'protocol_sha256':result['protocol_sha256'],'role':job['role'],'dependencies_sha256':base.digest(prefix)}:
            raise ValueError('Downstream authenticated output/dependencies changed')
        if job['role']=='analysis':prefix['analysis']=deps['analysis']
    for name,key in (('report.txt','report_sha256'),('report.html','html_sha256'),('review.json','review_sha256')):
        if base.sha(root/name)!=result[key]:raise ValueError('Final file changed: '+name)
    if (root/'report.txt').read_text()!=pipeline.report_text(deps['analysis'],deps['financial'],bundle):
        raise ValueError('Report content differs from author artifacts')
    if result['status']=='accepted':
        for role,value in [*deps.items(),('review',review)]:pipeline.validate_output(role,value,bundle)
        if review['verdict']!='pass' or result['validation_errors']:raise ValueError('Invalid acceptance')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent');p.add_argument('output');a=p.parse_args()
    r=run(a.parent,a.output);print(pipeline.packed({k:r[k] for k in ('status','downstream_wall_seconds','projected_critical_path_seconds','words')}))

if __name__=='__main__':main()
