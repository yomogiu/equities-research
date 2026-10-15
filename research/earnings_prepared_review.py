"""Resume a proven baseline review transport failure without repeating models.

The original frozen verifier is run unchanged, read-only, with execution off.
Its authenticated state is read from the exception traceback only at the known
baseline editorial-schema failure. Findings and all measured usage are retained.
"""
import json,subprocess,sys,re
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as context
VERSION='authenticated-baseline-review-continuation-v1'

PROGRAM=r'''
import sys,json
from pathlib import Path
code=Path(sys.argv[1]);root=Path(sys.argv[2]);sys.path.insert(0,str(code))
from research import earnings_file_pipeline as p,earnings_mixed_runner as b
assert Path(p.__file__).resolve().is_relative_to(code)
protocol,bundle,catalog=p.load(root)
assert protocol.get('inherited_tokens',0)==0 and not protocol.get('budget_authorization')
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval','review-0','signal_author']
try:p.verify(root)
except ValueError as error:
 assert str(error)=='Editorial repair must locate exact unique text or an exact empty field'
 trace=error.__traceback__;found=[]
 while trace:
  frame=trace.tb_frame
  if frame.f_globals.get('__name__')=='research.earnings_file_pipeline' and frame.f_code.co_name=='_advance':found.append(frame.f_locals.copy())
  trace=trace.tb_next
 assert len(found)==1
 v=found[0]
 assert v['root']==root and v['round_no']==0 and len(v['sessions'])==4
 assert v['value']['receipt']['session']['id'] in v['sessions']
 print(json.dumps({'state':v['state'],'signals':v['pack'],'review':v['value']['content'],
  'tokens':v['tokens'],'session_ids':sorted(v['sessions']),'review_session':v['value']['receipt']['session']['id'],
  'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),
  'review_job':str(root/'jobs/review-0'),'models':protocol['models'],'writing_sha256':protocol['writing_sha256']}))
else:raise ValueError('Expected closed baseline review schema failure')
'''


def replay(previous):
    previous=Path(previous).resolve();q=b.read(previous/'jobs/review-0/request.json');code=Path(q['code_root']).resolve()
    context.require(re.fullmatch(r'[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    context.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name,'Frozen verifier commit changed')
    context.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Unexpected frozen verifier origin')
    context.require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    return json.loads(subprocess.check_output([sys.executable,'-B','-I','-c',PROGRAM,str(code),str(previous)],text=True))


def validate(value,case,catalog):
    from . import earnings_file_pipeline as p,earnings_batch_review as batch
    context.require(value['case_sha256']==b.sha(case) and value['catalog_sha256']==b.digest(catalog),'Continuation case or original catalogue differs')
    protocol=b.read(Path(value['previous_root'])/'protocol.json')
    bundle=p.evidence.load_bundle(protocol['evidence_manifest'])
    items=batch.units(value['state'],value['signals']);state,pack=batch.validate(items,bundle,catalog)
    context.require(state==value['state'] and pack==value['signals'],'Continuation state changed')
    context.require(value['models']=={k:list(v) for k,v in p.MODELS.items()},'Continuation role assignments changed')
    accepted,findings,passed=p.review_result(value['review'],items,state,pack,catalog,Path(value['review_job']))
    context.require(not passed and findings,'Baseline review findings must remain unresolved')
    context.require(any(e['field_path']==['quotes'] and isinstance(e['before'],list) for d in value['review']['decisions'] for e in d['editorial_repairs']),'Known typed quote deletion required')


def prepare(previous,case,output):
    previous=Path(previous).resolve();value={'version':VERSION,'previous_root':str(previous),
        'protocol_sha256':b.sha(previous/'protocol.json'),**replay(previous)}
    from . import earnings_passages
    catalog=earnings_passages.catalog(b.read(previous/'protocol.json')['evidence_manifest'])
    validate(value,case,catalog);context.write(output,value);return value


def verify(path,case,catalog):
    value=b.read(path);previous=Path(value['previous_root'])
    context.require(value['version']==VERSION and value['protocol_sha256']==b.sha(previous/'protocol.json'),'Continuation lineage changed')
    actual=replay(previous)
    context.require(all(value[k]==v for k,v in actual.items()),'Authenticated baseline handoff changed')
    validate(value,case,catalog);return value
