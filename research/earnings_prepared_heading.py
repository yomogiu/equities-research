"""One exact independent-review heading edit consumes final correction two.

Original outputs remain immutable. Six completed roles stay charged and fresh
independent full review two is mandatory; no acceptance is inherited.
"""
import copy,inspect,json,re,subprocess,sys
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-final-heading-proposal-continuation-v1'

def derive_heading(items,review):
    decisions=review['decisions']
    if review['reopen'] or len(decisions)!=len(items) or {d['unit_id'] for d in decisions}!=set(items):raise ValueError('Complete closed independent review required')
    changes=[d for d in decisions if d['verdict']!='pass']
    if len(changes)!=1:raise ValueError('Exactly one editorial heading decision required')
    for d in decisions:
        if d['verdict']=='pass' and (d['review_kind']!='none' or d['editorial_repairs']):raise ValueError('Passed units must have no edits')
    d=changes[0];key=d['unit_id'];edits=d['editorial_repairs']
    if d['verdict']!='revise' or d['review_kind']!='editorial' or not re.fullmatch(r'analysis:[0-9]+',key) or len(edits)!=1 or d['passage_ids']:raise ValueError('One source-neutral editorial heading only')
    e=edits[0]
    if set(e)!={'field_path','before','after','reason'} or e['field_path']!=['heading'] or not isinstance(e['reason'],str) or not e['reason'].strip():raise ValueError('Exact explained heading replacement required')
    after=e['after']
    if items[key]['value'].get('heading')!=e['before'] or not isinstance(after,str) or not after.strip() or len(after)>200 or any(x in after for x in ('\n','\r','\x00','<','>')) or after==e['before']:raise ValueError('Exact bounded original heading required')
    result=copy.deepcopy(items);result[key]['value']['heading']=after
    return result,key

PROGRAM=r'''
import sys,json,copy,re
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k) for k in ('preparation_path','analysis_preparation_path','review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert protocol['max_tokens']==1200000 and protocol['max_correction_rounds']==2
names=['analysis','correction-1','retrieval','review-0','review-1','signal_author']
assert sorted(x.name for x in (root/'jobs').iterdir())==names
pending=p.verify(root);assert pending['status']=='pending' and pending['stage']=='correction-2' and not pending.get('resume')
job=root/'jobs/review-1';q=b.read(job/'request.json');v=r.verify_job(job);index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json')
assert [q['model'],q['effort']]==protocol['models']['review'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json') and q['bindings']['artifact_sha256']==b.digest(deps)
assert (job/'prompt.md').read_text()==p.instruction('review',index,job,protocol)
accepted,findings,passed=p.review_result(v['content'],deps['units'],deps['state'],deps['signals'],catalog,job);assert not passed
p.coverage('review',index,job,v['content'],catalog,deps)
items,key=derive_heading(deps['units'],v['content']);state,pack=p.batch.validate(items,bundle,catalog);p.mechanical.check(state,bundle,catalog)
values=[r.verify_job(root/'jobs'/name) for name in names];sessions=[x['receipt']['session']['id'] for x in values];tokens=sum(x['receipt']['session']['usage']['totalTokens'] for x in values)
assert len(set(sessions))==6 and tokens==pending['tokens'] and tokens<protocol['max_tokens']
print(json.dumps({'state':state,'signals':pack,'findings':{key:'Exact independent reviewer heading proposal applied as final correction2; NEW independent FULLreview2 mandatory.'},'original_findings':findings,'tokens':tokens,'session_ids':sorted(sessions),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':2,'spent_correction_rounds':2,'review_output_sha256':b.sha(job/'output.json'),'original_candidate_sha256':b.digest(deps['units']),'derived_candidate_sha256':b.digest(items),'changed_unit':key}))
'''
def replay(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/review-1/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original verifier origin changed')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c','import copy,re\n'+inspect.getsource(derive_heading)+PROGRAM,str(code),str(root)],text=True))
def prepare(previous,case,output):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
    c.require(v['case_sha256']==b.sha(case),'Original case required');c.write(output,v);return v

def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Exact heading lineage required')
    actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Original work, candidate, accounting or rounds changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['start_round']==v['spent_correction_rounds']==2,'Original final round/case/catalogue required');return v
