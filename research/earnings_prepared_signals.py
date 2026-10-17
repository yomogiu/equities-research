"""Continue exact empty signal passage-address lists after authenticated author work.

No prose or existing IDs change. Only complete, already cited and delivered D scopes
expand to their original paragraph IDs, pending a fresh independent report review.
"""
import copy,json,subprocess,sys,re
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-signal-address-continuation-v1'
PROGRAM=r'''
import sys,json
from pathlib import Path
code=Path(sys.argv[1]);root=Path(sys.argv[2]);sys.path.insert(0,str(code))
from research import earnings_file_pipeline as p,earnings_mixed_runner as b
assert Path(p.__file__).resolve().is_relative_to(code)
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k) for k in ['review_preparation_path','signal_preparation_path','recovery_path','preparation_path','budget_authorization'])
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval','signal_author']
try:p.verify(root)
except ValueError as error:
 assert str(error)=='Invalid/duplicate/unknown signal passages'
 trace=error.__traceback__;found=[]
 while trace:
  f=trace.tb_frame
  if f.f_globals.get('__name__')=='research.earnings_file_pipeline' and f.f_code.co_name=='_advance':found.append(f.f_locals.copy())
  trace=trace.tb_next
 assert len(found)==1;v=found[0]
 assert v['role']=='signal_author' and len(v['sessions'])==3 and v['value']['receipt']['session']['id'] in v['sessions']
 print(json.dumps({'state':v['state'],'raw_signals':v['value']['content'],'tokens':v['tokens'],'session_ids':sorted(v['sessions']),'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'models':protocol['models'],'writing_sha256':protocol['writing_sha256']}))
else:raise ValueError('Expected known closed signal-address failure')
'''

def canonicalize(pack,catalog,delivered):
    out=copy.deepcopy(pack);changes=[]
    for s in out.get('signals',[]):
        if s.get('passage_ids')!=[]:continue
        scopes=[x for x in s.get('citations',[]) if re.fullmatch('D[0-9]+',x)]
        c.require(scopes and set(scopes)<=set(delivered),'Exact cited filing scopes must have complete author delivery')
        ids=sorted({p['passage_id'] for p in catalog['passages'] if p['scope_id'] in scopes})
        c.require(0<len(ids)<=128,'Bounded exact source paragraphs required')
        s['passage_ids']=ids;changes.append({'signal_id':s['id'],'cited_scopes':scopes,'derived_passage_ids':ids})
    c.require(changes,'Known empty passage address list required')
    return out,changes

def replay(previous):
    previous=Path(previous).resolve();job=previous/'jobs/signal_author';q=b.read(job/'request.json');code=Path(q['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen code required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name,'Frozen code commit changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Unexpected code origin')
    c.require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen code changed')
    return json.loads(subprocess.check_output([sys.executable,'-B','-I','-c',PROGRAM,str(code),str(previous)],text=True))

def validate(value,case,catalog):
    from . import earnings_file_pipeline as p,earnings_batch_review as batch
    previous=Path(value['previous_root']);protocol=b.read(previous/'protocol.json');job=previous/'jobs/signal_author'
    c.require(value['case_sha256']==b.sha(case) and value['catalog_sha256']==b.digest(catalog),'Exact case/catalogue required')
    entries=c.delivered_entries(job,c.audit(Path(b.read(job/'request.json')['context_index']),job/'retrieval.jsonl'));delivered=set(c.complete_ranges(entries,'scope','id'))
    names=c.complete_ranges(entries,'source_batch','name')
    for e in entries:
        if e['method']=='source_batch' and e['name'] in names:delivered.update(e['ids'])
    signals,derivation=canonicalize(value['raw_signals'],catalog,delivered)
    c.require(value['signals']==signals and value['address_derivation']==derivation,'Only exact source-address expansion permitted')
    bundle=p.evidence.load_bundle(protocol['evidence_manifest']);items=batch.units(value['state'],signals);state,pack=batch.validate(items,bundle,catalog)
    c.require(state==value['state'] and pack==signals,'State/prose changed')
    c.require(value['models']=={k:list(v) for k,v in p.MODELS.items()},'Role model assignments changed')

def prepare(previous,case,output):
    from . import earnings_passages
    previous=Path(previous).resolve();value={'version':VERSION,'previous_root':str(previous),'protocol_sha256':b.sha(previous/'protocol.json'),**replay(previous)}
    catalog=earnings_passages.catalog(b.read(previous/'protocol.json')['evidence_manifest']);job=previous/'jobs/signal_author';entries=c.delivered_entries(job,c.audit(Path(b.read(job/'request.json')['context_index']),job/'retrieval.jsonl'));delivered=set(c.complete_ranges(entries,'scope','id'));names=c.complete_ranges(entries,'source_batch','name')
    for e in entries:
        if e['method']=='source_batch' and e['name'] in names:delivered.update(e['ids'])
    value['signals'],value['address_derivation']=canonicalize(value['raw_signals'],catalog,delivered);validate(value,case,catalog);c.write(output,value);return value

def verify(path,case,catalog):
    value=b.read(path);previous=Path(value['previous_root']);c.require(value['version']==VERSION and value['protocol_sha256']==b.sha(previous/'protocol.json'),'Lineage changed');actual=replay(previous);c.require(all(value[k]==v for k,v in actual.items()),'Authenticated source output changed');validate(value,case,catalog);return value
