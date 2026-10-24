"""Recognize exact proposals already approved by an independent mapping review.

This receipt does not alter frozen proposals or grant report acceptance. A caller
must select an exact profile and closed review, including complete source delivery.
"""
from pathlib import Path
from . import financial_evidence as f, earnings_runtime_common as b

VERSION='authenticated-text-proposals-v1'

def require(ok,message):
    if not ok:raise ValueError(message)

def approve(profile,source,job,authorization):
    from . import earnings_file_runner as runner, earnings_file_context as context
    identity={k:source.get(k) for k in ('document_id','issuer_id','raw_sha256','text_sha256')}
    require(authorization.get('version')==VERSION and authorization.get('enabled') is True and authorization.get('source')==identity,'Exact caller-owned text adapter authorization required')
    require(b.digest(profile)==authorization['profile_digest'] and profile['source']==source,'Exact proposed profile changed')
    require(all(o.get('method')=='manual_proposal' and o.get('status')=='proposed' for o in profile['observations']),'Only unchanged fallback proposals are eligible')
    f.validate_artifact(profile,{source['document_id']:source})
    job=Path(job).resolve()
    require(b.sha(job/'output.json')==authorization['review_sha256'] and b.sha(job/'request.json')==authorization['request_sha256'],'Selected financial review changed')
    result=runner.verify_job(job);v=result['content'];q=b.read(job/'request.json')
    require(result['receipt']['session']['id']!=authorization['profile_author_id'] and bool(authorization['profile_author_id']),'Independent financial reviewer required')
    require(v.get('issuer_id')==source['issuer_id'] and v.get('period')==authorization['period'] and v.get('financial_mapping_verdict')=='pass' and v.get('financial_issues')==[],'Every financial mapping must pass without unresolved issues')
    index=Path(q['context_index']);reader=context.Evidence(index,job/'retrieval.jsonl',_replay=True)
    require(reader.artifacts.get('financial_proposals')==profile,'Reviewer did not receive the exact proposed profile')
    required={k for k,v in reader.records.items() if k.startswith('D') and any(s['document_id']==source['document_id'] for s in v['spans'])}
    entries=context.delivered_entries(job,context.audit(index,job/'retrieval.jsonl'));covered=set()
    complete=context.complete_ranges(entries,'source_batch','name')
    for e in entries:
        if e['method']=='source_batch' and e['name'] in complete:covered.update(e['ids'])
    covered.update(context.complete_ranges(entries,'scope','id'))
    require(bool(required) and required<=covered,'Complete original financial source delivery required')
    return {'version':VERSION,'profile_digest':authorization['profile_digest'],'review_sha256':authorization['review_sha256'],'session_id':result['receipt']['session']['id'],'source':identity,'observation_ids':sorted(o['observation_id'] for o in profile['observations']),'scope':'Approved financial mappings only; other source findings and report acceptance remain separate.'}

def usable(observation,data):
    return observation.get('status')=='extracted' or (observation.get('status')=='proposed' and observation.get('observation_id') in data.get('proposal_approval',{}).get('observation_ids',[]))

def case_approval(case,source):
    selection=case['financial_proposal_approval'];bound={str(Path(x['path']).resolve()):x['sha256'] for x in case['artifacts']}
    require(case['issuer_id']==source['issuer_id'],'Adapter issuer mismatch')
    def read(name):
        p=Path(selection[name]).resolve();require(str(p) in bound and b.sha(p)==bound[str(p)],'Unbound adapter artifact');return b.read(p)
    auth=read('authorization_path');profile=read('profile_path')
    require(auth['period']==case['period'],'Adapter period mismatch')
    job=Path(selection['review_job']);require(str((job/'output.json').resolve()) in bound,'Selected review must be frozen in case')
    return approve(profile,source,job,auth)
