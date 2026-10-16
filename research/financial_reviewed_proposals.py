"""Replay exact text proposals after authenticated independent mapping review.

This adapter does not upgrade frozen proposals or grant report acceptance. A caller
must select an exact profile and closed review, including complete source delivery.
"""
from pathlib import Path
import copy
from . import financial_evidence as f, earnings_mixed_runner as b

VERSION='authenticated-text-proposals-v1'

def require(ok,message):
    if not ok:raise ValueError(message)

def extract(raw_bytes,text_bytes,source,profile,job,authorization):
    from . import earnings_file_runner as runner, earnings_file_context as context
    identity={k:source.get(k) for k in ('document_id','issuer_id','raw_sha256','text_sha256')}
    require(authorization.get('version')==VERSION and authorization.get('enabled') is True and authorization.get('source')==identity,'Exact caller-owned text adapter authorization required')
    require(f.digest(raw_bytes)==source['raw_sha256'] and f.digest(text_bytes)==source['text_sha256'],'Original financial bytes changed')
    require(b.digest(profile)==authorization['profile_digest'] and profile['source']==source,'Exact proposed profile changed')
    require(all(o.get('method')=='manual_proposal' and o.get('status')=='proposed' for o in profile['observations']),'Only unchanged fallback proposals are eligible')
    f.validate_artifact(profile,{source['document_id']:source})
    text=text_bytes.decode('utf-8')
    for o in profile['observations']:
        s=o['support'];require(text[s['start']:s['end']]==s['quote'],'Exact proposed row differs')
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
    observations=[]
    for old in profile['observations']:
        row=copy.deepcopy(old);row.update(method='reviewed_text_proposal',status='extracted',original_proposal_id=old['observation_id'])
        row['observation_id']=f.seal(row,'observation_id')['observation_id'];observations.append(row)
    artifact=f.make_artifact(source,observations,profile.get('gaps',[]))
    artifact['text_proposal_review']={'version':VERSION,'profile_digest':authorization['profile_digest'],'review_sha256':authorization['review_sha256'],'session_id':result['receipt']['session']['id'],'scope':'Financial mapping only; report acceptance and other source findings remain separate.'}
    return f.seal(artifact,'artifact_sha256')

def case_inputs(case,raw_bytes,source):
    selection=case['reviewed_proposal_adapter'];bound={str(Path(x['path']).resolve()):x['sha256'] for x in case['artifacts']}
    require(case['issuer_id']==source['issuer_id'],'Adapter issuer mismatch')
    def read(name):
        p=Path(selection[name]).resolve();require(str(p) in bound and b.sha(p)==bound[str(p)],'Unbound adapter artifact');return b.read(p)
    auth=read('authorization_path');profile=read('profile_path');text=Path(selection['text_path']);require(str(text.resolve()) in {str(Path(s['path']).resolve()) for s in case['sources']},'Original text must be a frozen source')
    require(auth['period']==case['period'],'Adapter period mismatch')
    job=Path(selection['review_job']);require(str((job/'output.json').resolve()) in bound,'Selected review must be frozen in case')
    return raw_bytes,text.read_bytes(),source,profile,job,auth
