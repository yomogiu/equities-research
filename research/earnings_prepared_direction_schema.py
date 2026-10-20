"""Qualified unsupported-review-direction continuation of a closed, explicitly blocked correction.

All completed work stays charged. Only the original final correction and fresh
independent review may follow; the scope bridge is evidence, never acceptance.
"""
import copy,json,subprocess,sys,re,inspect
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-review-direction-schema-continuation-v1'
DIRECTIONS=('improving','deteriorating','conditional','unresolved')
def schema_bridge(message,findings,units):
    match=re.fullmatch(r'The contract requires a neutral direction for (signal-[1-4]), but the result validator rejects that direction as unknown\. This schema conflict prevents submitting a valid atomic batch\.',message)
    if not match:raise ValueError('Exact closed unsupported-direction conflict required')
    sid=match[1]
    if sid not in findings or sid not in units or units[sid].get('value',{}).get('id')!=sid:raise ValueError('Original pending signal finding required')
    reason=findings[sid]
    if not isinstance(reason,str) or not reason.startswith('Use neutral direction for this context-dependent movement.') or '\nSOURCE PASSAGE IDS\n' not in reason:raise ValueError('Exact source-bound neutral review finding required')
    ids=json.loads(reason.split('\nSOURCE PASSAGE IDS\n')[1])
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or not all(isinstance(x,str) and x for x in ids):raise ValueError('Original unique review passage bindings required')
    if units[sid]['value']['direction'] not in DIRECTIONS:raise ValueError('Original signal must satisfy unchanged direction schema')
    return {'kind':'unsupported-review-direction-schema-v1','signal_id':sid,'original_finding':reason,'allowed_directions':list(DIRECTIONS),'review_passage_ids':ids,
     'notice':'The review requested the unsupported literal direction neutral. Neutral is not an allowed enum and is not automatically equivalent to any allowed value. Preserve the original review rationale, comparisons, attribution and passage bindings. Independently inspect the complete original sources and choose an existing allowed direction only if its original definition faithfully describes this development. Do not infer a replacement from this notice. If no allowed direction can satisfy the source and review substance, return blocked. Preserve all other pending findings. A fresh independent full review remains mandatory.'}
PROGRAM=r'''
import sys,json,copy,re
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2]);
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k) for k in ('review_preparation_path','signal_preparation_path','preparation_path','analysis_preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','correction-1','retrieval','review-0','signal_author']
assert protocol['max_correction_rounds']==2 and 0<protocol['max_tokens']<=1200000
result=p.verify(root);assert result['status']=='blocked' and result['stage']=='correction-1'
job=root/'jobs/correction-1';q=b.read(job/'request.json');v=r.verify_job(job)
assert set(v['content'])=={'blocked'} and v['content']['blocked']==result['reason'] and not (job/'resume.json').exists()
assert [q['model'],q['effort']]==protocol['models']['correction'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');assert b.digest(deps)==q['bindings']['artifact_sha256']
assert (job/'prompt.md').read_text()==p.instruction('correction',index,job,protocol)
values=[r.verify_job(x) for x in sorted((root/'jobs').iterdir())];sessions=[x['receipt']['session']['id'] for x in values];tokens=sum(x['receipt']['session']['usage']['totalTokens'] for x in values)
assert len(set(sessions))==5 and result['tokens']==tokens and tokens<protocol['max_tokens']
state,signals=p.batch.validate(deps['units'],bundle,catalog)
assert tuple(p.signals.DIRECTIONS)==DIRECTIONS
bridge=schema_bridge(result['reason'],deps['findings'],deps['units']);bridge['original_direction_rules']=p.signals.RULES
assert all(pid in {x['passage_id'] for x in catalog['passages']} for pid in bridge['review_passage_ids'])
findings=copy.deepcopy(deps['findings']);sid=bridge['signal_id']
findings[sid]+='\nAUTHENTICATED UNCHANGED SIGNAL SCHEMA\n'+json.dumps(bridge,sort_keys=True)
print(json.dumps({'state':state,'signals':signals,'findings':findings,'schema_bridge':bridge,'tokens':tokens,'session_ids':sorted(sessions),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':2,'spent_correction_rounds':1,'failed_output_sha256':b.sha(job/'output.json')}))
'''
def replay(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/correction-1/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original verifier origin changed')
    program='DIRECTIONS='+repr(DIRECTIONS)+'\n'+inspect.getsource(schema_bridge)+PROGRAM
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root)],text=True))
def prepare(previous,case,output):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
    c.require(v['case_sha256']==b.sha(case) and 0<v['tokens']<v['max_tokens'] and v['start_round']==2,'Original case, remaining cap and final round required')
    c.write(output,v);return v
def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Direction continuation lineage changed')
    actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Original work, usage, models or spent round changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['start_round']==2 and v['spent_correction_rounds']==1,'Original case/catalogue/final round required')
    return v
