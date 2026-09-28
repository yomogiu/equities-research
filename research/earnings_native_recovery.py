"""Quarantine one authentic initial native draft for the normal reviewer/correction graph.

No provider work occurs in prepare. The raw draft is never repaired by the host.
Only its historical validation is excepted; the initial reviewer must request a
commentator revision, and accepted content must pass the unchanged validators.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import threading
from . import earnings_native as native
from . import earnings_experiment as base

VERSION='earnings-native-schema-recovery-v1'
JOB='commentator-r0'
ERROR='Every referenced exchange needs exact source evidence'
RECEIPT='schema-recovery.json'
ORIGINALS=('request.json','dependencies.json','prompt.txt','launch.json','execution.json',
           'events.jsonl','final.txt','stderr.txt','session.jsonl','session-receipt.json','output.json')


def diagnose(content, case):
    """Confirm the narrow defect without editing the retained model output."""
    try:
        base.validate_content('commentator',content,case,{})
    except ValueError as error:
        if str(error)!=ERROR: raise ValueError('Unsupported initial schema failure') from error
    else: raise ValueError('Quarantine requires a currently invalid initial draft')
    findings=content.get('findings',[]); missing=[]; diagnostic=deepcopy(content)
    for index,finding in enumerate(findings):
        quoted={q.get('exchange_id') for q in finding.get('quotes',[])}
        absent=[eid for eid in finding.get('exchange_ids',[]) if eid not in quoted]
        if absent:
            missing.append({'finding_index':index,'finding_id':finding.get('id'),'exchange_ids':absent})
            diagnostic['findings'][index]['exchange_ids']=[eid for eid in finding['exchange_ids'] if eid in quoted]
    if len(missing)!=1 or missing[0]['finding_index']!=0 or len(missing[0]['exchange_ids'])!=2:
        raise ValueError('Quarantine only covers two unquoted references in the first finding')
    # Diagnostic only: catches other quote/schema defects hidden by the first error.
    base.validate_content('commentator',diagnostic,case,{})
    return {'validation_error':ERROR,'missing_quote_bindings':missing,
            'diagnostic':'Removing only these two references in memory passes the unchanged validator; retained output is unmodified.'}


def check_original(run, receipt=None):
    run=Path(run).resolve(); native.verify_config(run)
    case=base.read(run/'case.json'); job=base.inside(run,JOB)
    request=base.read(job/'request.json')
    if request.get('role')!='commentator' or request.get('revision')!=0 or request.get('dependencies')!={}:
        raise ValueError('Only the initial independent commentator can be quarantined')
    content=base.parse_response((job/'final.txt').read_text())
    expected={'request_sha256':base.digest(request),'content':content}
    if base.read(job/'output.json')!=expected: raise ValueError('Quarantined output differs from actual final response')
    scope=diagnose(content,case)
    value={'version':VERSION,'job':JOB,'status':'quarantined_for_independent_review',
           'adapter_sha256':base.sha(__file__),'native_sha256':base.sha(native.__file__),
           'config_sha256':base.sha(run/'config.json'),'case_sha256':base.digest(case),
           'originals':{name:base.sha(base.inside(job,name)) for name in ORIGINALS},
           'content_sha256':base.digest(content),'scope':scope,
           'maximum_shared_correction_rounds':2,
           'required_initial_review':{'verdict':'revise','target':'commentator'},
           'accepted_quarantined_draft_permitted':False}
    if receipt is not None and receipt!=value: raise ValueError('Frozen schema-recovery receipt or originals changed')
    return value


@contextmanager
def historical_exception(run, receipt):
    """Expose the exception only while verifying the exact historical job."""
    run=Path(run).resolve(); original_verify=native.verify_job; original_validate=native.validate_content
    state=threading.local()
    def validate(role,content,case,dependencies):
        if (getattr(state,'historical',False) and role=='commentator' and dependencies=={}
                and base.digest(content)==receipt['content_sha256'] and base.digest(case)==receipt['case_sha256']):
            return
        return original_validate(role,content,case,dependencies)
    def verify(job,role,case,dependencies):
        historical=Path(job).resolve()==run/JOB
        if historical:
            check_original(run,receipt)
            if role!='commentator' or dependencies!={}: raise ValueError('Quarantine role/dependencies differ')
        prior=getattr(state,'historical',False); state.historical=historical
        try: return original_verify(job,role,case,dependencies)
        finally: state.historical=prior
    native.validate_content=validate; native.verify_job=verify
    try: yield
    finally: native.verify_job=original_verify; native.validate_content=original_validate


def prepare(run):
    run=Path(run).resolve(); native.verify_config(run); job=run/JOB
    if (run/RECEIPT).exists(): return policy(run)
    if (run/'accepted.json').exists(): raise ValueError('Cannot quarantine an accepted run')
    # The host wrapper binds the exact raw JSON, never a hand-edited schema repair.
    request=base.read(job/'request.json')
    content=base.parse_response((job/'final.txt').read_text())
    diagnose(content,base.read(run/'case.json'))
    base.save(job/'output.json',{'request_sha256':base.digest(request),'content':content})
    receipt=check_original(run)
    with historical_exception(run,receipt):
        native.verify_job(job,'commentator',base.read(run/'case.json'),{})
    base.save(run/RECEIPT,receipt)
    return receipt


def policy(run):
    run=Path(run).resolve(); receipt=base.read(base.inside(run,RECEIPT))
    check_original(run,receipt)
    with historical_exception(run,receipt):
        native.verify_job(run/JOB,'commentator',base.read(run/'case.json'),{})
    return receipt


def initial_review(run):
    run=Path(run).resolve(); review=run/'reviewer-r0'/'output.json'
    content=base.read(review)['content']
    if content.get('verdict')!='revise' or not any(f.get('target')=='commentator' for f in content.get('findings',[])):
        raise ValueError('Quarantined draft requires reviewer-r0 revise targeting commentator; run stopped')
    return review


@contextmanager
def adapter(run, creating_acceptance=False):
    run=Path(run).resolve(); receipt=policy(run)
    original_role=native.run_role; original_acceptance=native.verify_acceptance
    def role(target,role_name,revision,case_path,case,dependencies):
        if Path(target).resolve()!=run: raise ValueError('Recovery adapter cannot execute another run')
        output=original_role(target,role_name,revision,case_path,case,dependencies)
        if role_name=='reviewer' and revision==0:
            try: initial_review(run)
            except ValueError:
                base.save(run/'schema-recovery-blocked.json',{'status':'blocked','stage':'initial_review',
                          'review_sha256':base.sha(output),'schema_recovery_sha256':base.sha(run/RECEIPT),
                          'reason':'Initial reviewer did not request commentator correction'})
                raise
        return output
    def acceptance(target,value):
        if Path(target).resolve()!=run: raise ValueError('Recovery adapter cannot verify another run')
        policy(run); initial_review(run)
        if value.get('roles',{}).get('commentator')==JOB or value.get('revisions',0)<1:
            raise ValueError('Quarantined draft cannot be accepted')
        binding=base.sha(run/RECEIPT)
        if creating_acceptance and 'schema_recovery_sha256' not in value:
            value['schema_recovery_sha256']=binding
        if value.get('schema_recovery_sha256')!=binding: raise ValueError('Acceptance lacks schema-recovery binding')
        # No exception for any corrected author; native also replays full history.
        return original_acceptance(target,value)
    with historical_exception(run,receipt):
        native.run_role=role; native.verify_acceptance=acceptance
        try: yield
        finally: native.run_role=original_role; native.verify_acceptance=original_acceptance


def execute(run):
    with adapter(run,creating_acceptance=True): native.execute(run)


def verify(run):
    with adapter(run): return native.verify(run)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','run','verify']); parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.output); print('Initial draft quarantined; no role launched.')
    elif args.command=='run':execute(args.output)
    else:print(json.dumps(verify(args.output),indent=2))


if __name__=='__main__': main()
