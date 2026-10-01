"""One remaining-budget schema recovery for an authentic native revision-one draft.

This composes the frozen initial recovery. The additional host validation envelope
is an explicit intervention: machine feedback becomes visible to the independent
reviewer without changing model content, sources, prompts, or the two-round budget.
Only the exact historical commentator-r1 is quarantined; acceptance requires r2.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import threading
from . import earnings_experiment as base
from . import earnings_native as native
from . import earnings_native_recovery as initial

VERSION='earnings-native-revision-schema-recovery-v1'
JOB='commentator-r1'
RECEIPT='revision-schema-recovery.json'
ERROR=initial.ERROR
ORIGINALS=initial.ORIGINALS


def dependencies(run):
    return {'prior_review':str(Path(run).resolve()/'reviewer-r0'/'output.json')}


def diagnose(content,case):
    try: base.validate_content('commentator',content,case,{})
    except ValueError as error:
        if str(error)!=ERROR: raise ValueError('Unsupported revision schema failure') from error
    else: raise ValueError('Revision quarantine requires invalid model content')
    diagnostic=deepcopy(content); missing=[]
    for index,finding in enumerate(content.get('findings',[])):
        quoted={q.get('exchange_id') for q in finding.get('quotes',[])}
        absent=[eid for eid in finding.get('exchange_ids',[]) if eid not in quoted]
        if absent:
            missing.append({'finding_index':index,'finding_id':finding.get('id'),'exchange_ids':absent})
            diagnostic['findings'][index]['exchange_ids']=[eid for eid in finding['exchange_ids'] if eid in quoted]
    if len(missing)!=1 or missing[0]['finding_index']!=2 or len(missing[0]['exchange_ids'])!=1:
        raise ValueError('Revision quarantine only covers one unquoted reference in the third finding')
    finding=content['findings'][2]
    if len(finding['exchange_ids'])!=4 or len({q.get('exchange_id') for q in finding['quotes']})!=3:
        raise ValueError('Revision quarantine requires four referenced and three quoted exchanges')
    # Diagnostic only, never saved as the output or supplied to a model.
    base.validate_content('commentator',diagnostic,case,{})
    return {'validation_error':ERROR,'missing_quote_bindings':missing,
            'diagnostic':'Removing this one reference in memory passes the unchanged validator; retained model content is unmodified.'}


def check_original(run,receipt=None):
    run=Path(run).resolve(); native.verify_config(run); initial.policy(run); initial.initial_review(run)
    case=base.read(run/'case.json'); job=base.inside(run,JOB); request=base.read(job/'request.json')
    expected_deps=dependencies(run)
    if (request.get('role')!='commentator' or request.get('revision')!=1
            or request.get('dependencies')!={k:base.sha(v) for k,v in expected_deps.items()}
            or base.read(job/'dependencies.json')!=expected_deps):
        raise ValueError('Only commentator-r1 with original prior-review dependency can be quarantined')
    content=base.parse_response((job/'final.txt').read_text()); scope=diagnose(content,case)
    output=base.read(job/'output.json'); metadata=output.get('validation')
    if set(output)!={'request_sha256','content','validation'} or output['request_sha256']!=base.digest(request) or output['content']!=content:
        raise ValueError('Revision envelope must preserve the exact runtime model content')
    if (not isinstance(metadata,dict) or set(metadata)!={'status','error','missing_quote_bindings','required_change'}
            or metadata.get('status')!='failed' or metadata.get('error')!=ERROR
            or metadata.get('missing_quote_bindings')!=scope['missing_quote_bindings']
            or not isinstance(metadata.get('required_change'),str) or not metadata['required_change'].strip()):
        raise ValueError('Revision envelope requires exact machine-error metadata and concrete repair instruction')
    value={'version':VERSION,'job':JOB,'status':'quarantined_for_independent_review',
           'adapter_sha256':base.sha(__file__),'native_sha256':base.sha(native.__file__),
           'initial_recovery_sha256':base.sha(initial.__file__),
           'initial_recovery_receipt_sha256':base.sha(run/initial.RECEIPT),
           'config_sha256':base.sha(run/'config.json'),'case_sha256':base.digest(case),
           'originals':{name:base.sha(base.inside(job,name)) for name in ORIGINALS},
           'content_sha256':base.digest(content),'validation_metadata_sha256':base.digest(metadata),'scope':scope,
           'maximum_shared_correction_rounds':2,'remaining_correction_rounds':1,
           'required_revision_review':{'verdict':'revise','target':'commentator','revision':1},
           'required_accepted_commentator':'commentator-r2',
           'intervention':'Host machine-error metadata added outside unchanged raw model content to the reviewer dependency envelope; original role prompts and shared two-round budget retained.'}
    if receipt is not None and receipt!=value: raise ValueError('Frozen revision recovery or original evidence changed')
    return value


@contextmanager
def historical_exception(run,receipt):
    run=Path(run).resolve(); original_verify=native.verify_job; original_validate=native.validate_content
    state=threading.local()
    def validate(role,content,case,dep_paths):
        normalized={k:str(v) for k,v in dep_paths.items()}
        if (getattr(state,'historical',False) and role=='commentator' and normalized==dependencies(run)
                and base.digest(content)==receipt['content_sha256'] and base.digest(case)==receipt['case_sha256']): return
        return original_validate(role,content,case,dep_paths)
    def verify(job,role,case,dep_paths):
        historical=Path(job).resolve()==run/JOB
        if historical:
            check_original(run,receipt)
            if role!='commentator' or {k:str(v) for k,v in dep_paths.items()}!=dependencies(run):
                raise ValueError('Revision quarantine role or dependencies differ')
        previous=getattr(state,'historical',False); state.historical=historical
        try:return original_verify(job,role,case,dep_paths)
        finally:state.historical=previous
    native.validate_content=validate; native.verify_job=verify
    try:yield
    finally:native.verify_job=original_verify; native.validate_content=original_validate


def prepare(run):
    run=Path(run).resolve()
    if (run/RECEIPT).exists():return policy(run)
    if (run/'accepted.json').exists():raise ValueError('Cannot quarantine an accepted run')
    receipt=check_original(run)
    with historical_exception(run,receipt):
        native.verify_job(run/JOB,'commentator',base.read(run/'case.json'),dependencies(run))
    base.save(run/RECEIPT,receipt)
    return receipt


def policy(run):
    run=Path(run).resolve(); receipt=base.read(base.inside(run,RECEIPT));check_original(run,receipt)
    with historical_exception(run,receipt):
        native.verify_job(run/JOB,'commentator',base.read(run/'case.json'),dependencies(run))
    return receipt


def revision_review(run):
    run=Path(run).resolve(); path=run/'reviewer-r1'/'output.json'; content=base.read(path)['content']
    if content.get('verdict')!='revise' or not any(f.get('target')=='commentator' for f in content.get('findings',[])):
        raise ValueError('Revision quarantine requires reviewer-r1 revise targeting commentator; run stopped')
    return path


@contextmanager
def adapter(run,creating_acceptance=False):
    run=Path(run).resolve(); receipt=policy(run)
    with initial.adapter(run,creating_acceptance=creating_acceptance), historical_exception(run,receipt):
        original_role=native.run_role; original_acceptance=native.verify_acceptance
        def role(target,role_name,revision,case_path,case,dep_paths):
            if Path(target).resolve()!=run:raise ValueError('Revision recovery cannot execute another run')
            output=original_role(target,role_name,revision,case_path,case,dep_paths)
            if role_name=='reviewer' and revision==1:
                try:revision_review(run)
                except ValueError:
                    base.save(run/'revision-schema-recovery-blocked.json',{'status':'blocked','stage':'revision_review',
                              'review_sha256':base.sha(output),'revision_schema_recovery_sha256':base.sha(run/RECEIPT),
                              'reason':'Revision-one reviewer did not request commentator correction'})
                    raise
            return output
        def acceptance(target,value):
            if Path(target).resolve()!=run:raise ValueError('Revision recovery cannot verify another run')
            policy(run);revision_review(run)
            if value.get('roles',{}).get('commentator')!='commentator-r2' or value.get('revisions')!=2:
                raise ValueError('Revision recovery requires fully validated commentator-r2 within original budget')
            binding=base.sha(run/RECEIPT)
            if creating_acceptance and 'revision_schema_recovery_sha256' not in value:value['revision_schema_recovery_sha256']=binding
            if value.get('revision_schema_recovery_sha256')!=binding:raise ValueError('Acceptance lacks revision recovery binding')
            return original_acceptance(target,value)
        native.run_role=role;native.verify_acceptance=acceptance
        try:yield
        finally:native.run_role=original_role;native.verify_acceptance=original_acceptance


def execute(run):
    with adapter(run,creating_acceptance=True):native.execute(run)


def verify(run):
    with adapter(run):return native.verify(run)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','run','verify']);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.output);print('Revision-one draft quarantined; no role launched.')
    elif args.command=='run':execute(args.output)
    else:print(json.dumps(verify(args.output),indent=2))


if __name__=='__main__':main()
