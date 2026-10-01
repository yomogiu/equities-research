"""Additional read-only verification of frozen mixed-model experiment receipts.

Kept separate so completed protocols and their original code remain unchanged.
"""
from datetime import datetime
from pathlib import Path
from research import earnings_experiment as base
from research import earnings_mixed_pipeline as pipeline
from research import earnings_mixed_continuation as continuation
from research import earnings_compact_evidence as evidence
from research.earnings_mixed_runner import verify_job


def _job(job,expected_role,expected_path):
    if job['role']!=expected_role or Path(job['path']).resolve()!=expected_path.resolve():
        raise ValueError('Unexpected role or job path')
    value=verify_job(expected_path)
    req=base.read(expected_path/'request.json')
    if (req['model'],req['effort'])!=pipeline.MODELS[expected_role]:
        raise ValueError('Role model/effort differs from protocol')
    if value['receipt']!=job['receipt']:
        raise ValueError('Job receipt differs')
    return value['receipt']['session']['id']


def audit_strict(root):
    root=Path(root).resolve();result=pipeline.verify_result(root)
    identities=[];keys=[]
    for job in result['jobs']:
        key=(job['role'],job['round']);keys.append(key)
        identities.append(_job(job,job['role'],root/'jobs'/f"{job['role']}-r{job['round']}"))
    if len(set(keys))!=len(keys) or len(set(identities))!=len(identities):
        raise ValueError('Repeated role or session identity')
    if ('financial',0) not in keys or ('retrieval',0) not in keys:
        raise ValueError('Initial preparation missing')
    return result


def audit_continuation(root):
    root=Path(root).resolve();result=continuation.verify(root);protocol=base.read(root/'protocol.json')
    parent=Path(protocol['parent']);pp=pipeline.verify_protocol(parent)
    if protocol['models']!=pp['models']:
        raise ValueError('Continuation model declaration changed')
    jobs=result['jobs']
    if [j.get('role') for j in jobs]!=['analysis','review']:
        raise ValueError('Exactly ordered analysis and independent review required')
    ids=[_job(j,j['role'],root/'jobs'/j['role']) for j in jobs]
    prep=[]
    for role in ('financial','retrieval'):
        path=parent/'jobs'/f'{role}-r0';v=verify_job(path)
        ids.append(_job({'role':role,'path':str(path),'receipt':v['receipt']},role,path))
        prep.append(v['receipt'])
    if len(set(ids))!=4:
        raise ValueError('Fresh distinct author, reviewer and preparer sessions required')
    downstream=(datetime.fromisoformat(jobs[1]['receipt']['finished_at'])-datetime.fromisoformat(jobs[0]['receipt']['started_at'])).total_seconds()
    maximum=max(p['elapsed_seconds'] for p in prep)
    if downstream<0 or maximum<0 or result['downstream_wall_seconds']!=downstream or result['reused_preparation_max_seconds']!=maximum or result['projected_critical_path_seconds']!=maximum+downstream:
        raise ValueError('Timing does not match original receipts')
    bundle=evidence.load_bundle(pp['evidence_manifest']);deps=base.read(root/'artifacts.json')
    qualified=base.read(root/'candidate-qualification.json');writing=Path(pp['writing_standard']).read_text()
    partial={k:deps[k] for k in ('financial','retrieval')}
    for j in jobs:
        prompt=pipeline.prompt_for(j['role'],bundle,writing,partial)
        prompt+='\n\nPREPARATION HANDOFF POLICY\nInvalid candidate quotations have been quarantined by deterministic exact-source validation. The retrieval artifact includes only accepted original quotations; all other retrieval fields and source text are unchanged. Rejected candidates are unavailable for quoting. The final report must still satisfy all original evidence and writing checks.\n'+pipeline.packed({'rejected_candidates':qualified['rejected_candidates']})
        if (Path(j['path'])/'prompt.txt').read_text()!=prompt:
            raise ValueError('Actual prompt differs from frozen evidence/dependencies')
        partial['analysis']=deps['analysis']
    return result


def main():
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=('strict','continuation'));parser.add_argument('root')
    args=parser.parse_args()
    result=(audit_strict if args.kind=='strict' else audit_continuation)(args.root)
    print(json.dumps({'status':result['status'],'authenticated_jobs':len(result['jobs'])}))

if __name__=='__main__':main()
