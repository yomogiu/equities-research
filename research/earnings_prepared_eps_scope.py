"""Qualified EPS-scope continuation of a closed, explicitly blocked correction.

All completed work stays charged. Only the original final correction and fresh
independent review may follow; the scope bridge is evidence, never acceptance.
"""
import copy,json,subprocess,sys,re,inspect
from pathlib import Path
from decimal import Decimal
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-resolved-eps-scope-continuation-v1'
CONCEPTS=('us-gaap:IncomeLossFromContinuingOperationsPerDilutedShare',
 'us-gaap:DiscontinuedOperationIncomeLossFromDiscontinuedOperationNetOfTaxPerDilutedShare',
 'us-gaap:EarningsPerShareDiluted')
def scope_bridge(financial,ids):
    if not isinstance(ids,list) or len(ids)!=3 or len(set(ids))!=3:raise ValueError('Three distinct ordered EPS fact IDs required')
    rows=[]
    for identifier,concept in zip(ids,CONCEPTS):
        found=[x for x in financial['observations'] if x['id']==identifier]
        if len(found)!=1 or found[0]['concept']!=concept:raise ValueError('Exact continuing/discontinued/total EPS concepts required')
        rows.append(found[0])
    if len({(x['context_id'],x['unit_id'],x['source_raw_sha256'],x['source_document_id']) for x in rows})!=1:raise ValueError('EPS scope must share original context/unit/source')
    context=financial['contexts'][rows[0]['context_id']]
    if context.get('dimensions') or not context.get('start_date') or not context.get('end_date'):raise ValueError('Unsegmented duration EPS context required')
    if any(x.get('status')!='extracted' or x.get('nil') or not x.get('support',{}).get('raw_span_sha256') for x in rows):raise ValueError('Original extracted EPS support required')
    if Decimal(rows[0]['value'])+Decimal(rows[1]['value'])!=Decimal(rows[2]['value']):raise ValueError('EPS scope reconciliation differs')
    return {'kind':'original-continuing-discontinued-total-diluted-eps-v1','context':context,
            'facts':[{k:x[k] for k in ('id','concept','value','context_id','unit_id','source_document_id','source_raw_sha256','support')} for x in rows],
            'notice':'Continuing operations plus discontinued operations equals total diluted EPS. Preserve each accounting scope; this source evidence does not accept the report or waive complete source inspection/fresh review.'}
def blocked_scope(message):
    return isinstance(message,str) and all(x in message for x in ('diluted EPS','diluted earnings per share','accounting-scope','without inventing a basis'))
def qualify_block(message,bridge):
    match=re.match(r'^(D\d+) identifies \$(\d+(?:\.\d+)?) as diluted EPS, while (F\d+) reports \$(\d+(?:\.\d+)?) as diluted earnings per share\.',message)
    if not blocked_scope(message) or not match:raise ValueError('Exact closed EPS scope conflict required')
    facts=bridge['facts']
    if match[3]!=facts[2]['id'] or Decimal(match[2])!=Decimal(facts[0]['value']) or Decimal(match[4])!=Decimal(facts[2]['value']):raise ValueError('EPS evidence must resolve the exact blocked values and total fact')
    return match[1]
PROGRAM=r'''
import sys,json,copy,re
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2]);ids=json.loads(sys.argv[3])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert not any(protocol.get(k) for k in ('review_preparation_path','signal_preparation_path','preparation_path','analysis_preparation_path','recovery_path','budget_authorization'))
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis','correction-1','retrieval','review-0','signal_author']
assert protocol['max_correction_rounds']==2 and 0<protocol['max_tokens']<=1200000
result=p.verify(root);assert result['status']=='blocked' and result['stage']=='correction-1' and blocked_scope(result['reason'])
job=root/'jobs/correction-1';q=b.read(job/'request.json');v=r.verify_job(job)
assert set(v['content'])=={'blocked'} and v['content']['blocked']==result['reason'] and not (job/'resume.json').exists()
assert [q['model'],q['effort']]==protocol['models']['correction'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json');assert b.digest(deps)==q['bindings']['artifact_sha256']
assert (job/'prompt.md').read_text()==p.instruction('correction',index,job,protocol)
values=[r.verify_job(x) for x in sorted((root/'jobs').iterdir())];sessions=[x['receipt']['session']['id'] for x in values];tokens=sum(x['receipt']['session']['usage']['totalTokens'] for x in values)
assert len(set(sessions))==5 and result['tokens']==tokens and tokens<protocol['max_tokens']
state,signals=p.batch.validate(deps['units'],bundle,catalog)
bridge=scope_bridge(bundle['financial'],ids);release_id=qualify_block(result['reason'],bridge)
assert release_id in {d['id'] for d in bundle['documents']['chunks']}
findings=copy.deepcopy(deps['findings'])
assert 'analysis:opening' in findings
findings['analysis:opening']+='\nAUTHENTICATED ORIGINAL EPS SCOPE EVIDENCE\n'+json.dumps(bridge,sort_keys=True)+'\nInspect these exact original facts and complete sources; reconcile the opening without conflating continuing operations and total EPS. Preserve all other pending findings.'
print(json.dumps({'state':state,'signals':signals,'findings':findings,'scope_bridge':bridge,'tokens':tokens,'session_ids':sorted(sessions),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':2,'spent_correction_rounds':1,'failed_output_sha256':b.sha(job/'output.json')}))
'''
def replay(previous,ids):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/correction-1/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original verifier origin changed')
    program='CONCEPTS='+repr(CONCEPTS)+'\n'+inspect.getsource(scope_bridge)+inspect.getsource(blocked_scope)+inspect.getsource(qualify_block)+PROGRAM
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',program,str(code),str(root),json.dumps(ids)],text=True))
def prepare(previous,case,output,ids):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),'scope_fact_ids':ids,**replay(root,ids)}
    c.require(v['case_sha256']==b.sha(case) and 0<v['tokens']<v['max_tokens'] and v['start_round']==2,'Original case, remaining cap and final round required')
    c.write(output,v);return v
def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'EPS continuation lineage changed')
    actual=replay(root,v['scope_fact_ids']);c.require(all(v[k]==x for k,x in actual.items()),'Original work, usage, models or spent round changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['start_round']==2 and v['spent_correction_rounds']==1,'Original case/catalogue/final round required')
    return v
