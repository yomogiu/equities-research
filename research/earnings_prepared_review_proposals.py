"""Exact reviewer-proposed edits plus one explicitly requested answer citation.

No model prose is rewritten. Deterministic correction consumes the original
round and requires a NEW independent full review; old review is not acceptance.
"""
import copy,json,re,subprocess,sys,inspect
from pathlib import Path
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-exact-review-proposals-continuation-v1'
def gaap_basis_sources(label,selected,observations):
    if label!='Financial-table figures are GAAP.' or not selected or len(set(selected))!=len(selected):raise ValueError('Exact compiler-selected GAAP label sources required')
    for identifier in selected:
        rows=[o for o in observations if o['id']==identifier]
        if len(rows)!=1 or not rows[0]['concept'].startswith('us-gaap:') or rows[0].get('status')!='extracted':raise ValueError('Native extracted GAAP table facts required')
    return selected[:]
def derive_proposals(items,review,catalog,index):
    if review['reopen'] or len(review['decisions'])!=len(items) or {d['unit_id'] for d in review['decisions']}!=set(items):raise ValueError('Exact complete closed baseline review required')
    result=copy.deepcopy(items);exchanges={e['id']:e for e in index['exchanges']};passages={p['passage_id']:p for p in catalog['passages']};factual=0;changed=[]
    for d in review['decisions']:
        key=d['unit_id'];edits=d['editorial_repairs'];kind=d['review_kind']
        if d['verdict']=='pass':
            if kind!='none' or edits:raise ValueError('Passed unit cannot carry edits')
            continue
        if d['verdict']!='revise' or not edits or kind not in ('editorial','mixed'):raise ValueError('Only exact typed reviewer proposals allowed')
        value=result[key]['value']
        for edit in edits:
            if set(edit)!={'field_path','before','after','reason'} or not edit['reason'].strip():raise ValueError('Exact explained edit required')
            if key.startswith('analysis:') and edit['field_path']==['quotes']:
                before=value['quotes'];after=edit['after']
                if edit['before']!=before or not isinstance(after,list) or len(after)>=len(before):raise ValueError('Exact original quote deletion required')
                cursor=iter(before)
                if not all(any(old==q for old in cursor) for q in after):raise ValueError('Quotation addition/reordering forbidden')
                value['quotes']=copy.deepcopy(after)
            elif key=='format' and kind=='editorial' and edit['field_path']==['basis','text']:
                if value['basis']['text']!=edit['before'] or edit['before']!='' or not isinstance(edit['after'],str) or edit['after']!='Financial-table figures are GAAP.':raise ValueError('Exact reviewer-proposed empty basis label required')
                value['basis']['text']=edit['after']
            else:raise ValueError('No prose or unsupported field rewrites permitted')
        if kind=='mixed':
            factual+=1
            if not key.startswith('analysis:') or value.get('section')!='qa':raise ValueError('One Q&A citation addition only')
            targets=set(re.findall(r'(?<![A-Za-z0-9_-])exchange-[a-f0-9]+(?![A-Za-z0-9_-])',d['reason']))
            if len(targets)!=1:raise ValueError('Reviewer must explicitly identify one exact exchange')
            target=next(iter(targets))
            if target not in exchanges or target in value['citations']:raise ValueError('New exact original exchange required')
            supports=[pid for pid in d['passage_ids'] if pid in passages and passages[pid]['scope_id'] in exchanges[target]['answer_turn_ids']]
            if not supports:raise ValueError('Reviewer-selected original answer evidence required')
            value['citations'].append(target)
        changed.append(key)
    if factual!=1 or not changed:raise ValueError('Exactly one explicitly source-bound citation repair required')
    return result
PROGRAM=r'''
import sys,json,copy,re
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
protocol,bundle,catalog=p.load(root)
assert protocol.get('analysis_preparation_path') and not any(protocol.get(k) for k in ('review_preparation_path','signal_preparation_path','recovery_path','budget_authorization'))
assert b.read(protocol['analysis_preparation_path'])['version'] in ('authenticated-quoted-turn-exchange-address-v1','authenticated-single-duplicate-analysis-quotation-v1')
assert sorted(x.name for x in (root/'jobs').iterdir())==['review-0','signal_author'] and protocol['max_correction_rounds']==2
result=p.verify(root);assert result['status']=='pending' and result['stage']=='correction-1' and not result.get('resume')
job=root/'jobs/review-0';q=b.read(job/'request.json');v=r.verify_job(job);index=Path(q['context_index']);deps=b.read(index.parent/'artifacts.json')
assert [q['model'],q['effort']]==protocol['models']['review'] and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json') and q['bindings']['artifact_sha256']==b.digest(deps)
assert (job/'prompt.md').read_text()==p.instruction('review',index,job,protocol)
accepted,findings,passed=p.review_result(v['content'],deps['units'],deps['state'],deps['signals'],catalog,job);assert not passed
p.coverage('review',index,job,v['content'],catalog,deps)
items=derive_proposals(deps['units'],v['content'],catalog,bundle['transcript_index'])
# Bind only this exact GAAP label to unchanged compiler-selected native GAAP facts.
from research import earnings_financial_display as display
assert items['financial']==deps['units']['financial']
basis=items['format']['value']['basis'];assert basis['text']=='Financial-table figures are GAAP.' and basis['citations']==[]
selected=display.build(items['financial']['value'],bundle)['selected_fact_ids']
basis['citations']=gaap_basis_sources(basis['text'],selected,bundle['financial']['observations'])
state,pack=p.batch.validate(items,bundle,catalog);p.mechanical.check(state,bundle,catalog)
inherited=b.read(protocol['analysis_preparation_path']);sessions=list(inherited['session_ids']);tokens=protocol['inherited_tokens']
for name in ('signal_author','review-0'):
 value=r.verify_job(root/'jobs'/name);sid=value['receipt']['session']['id'];assert sid not in sessions;sessions.append(sid);tokens+=value['receipt']['session']['usage']['totalTokens']
assert tokens==result['tokens'] and tokens<protocol['max_tokens'] and len(set(sessions))==4
print(json.dumps({'state':state,'signals':pack,'findings':{key:'Fresh full independent review required after exact reviewer-proposed deterministic changes; no prior acceptance inherited.' for key in items if items[key]!=deps['units'][key]},'tokens':tokens,'session_ids':sorted(sessions),'models':protocol['models'],'writing_sha256':protocol['writing_sha256'],'max_tokens':protocol['max_tokens'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'report_template':protocol['report_template'],'start_round':1,'spent_correction_rounds':1,'review_output_sha256':b.sha(job/'output.json'),'original_candidate_sha256':b.digest(deps['units']),'derived_candidate_sha256':b.digest(items)}))
'''
def replay(previous):
    root=Path(previous).resolve();code=Path(b.read(root/'jobs/review-0/request.json')['code_root']).resolve()
    c.require(re.fullmatch('[a-f0-9]{40}',code.name) and code.parent.name=='.report-workflow','Managed original verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Original verifier changed')
    c.require(subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Original verifier origin changed')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',inspect.getsource(gaap_basis_sources)+inspect.getsource(derive_proposals)+PROGRAM,str(code),str(root)],text=True))
def prepare(previous,case,output):
    root=Path(previous).resolve();v={'version':VERSION,'previous_root':str(root),'protocol_sha256':b.sha(root/'protocol.json'),**replay(root)}
    c.require(v['case_sha256']==b.sha(case) and v['start_round']==1 and v['spent_correction_rounds']==1,'Original case/round required');c.write(output,v);return v
def verify(path,case,catalog):
    v=b.read(path);root=Path(v['previous_root']);c.require(v['version']==VERSION and v['protocol_sha256']==b.sha(root/'protocol.json'),'Review proposal lineage changed')
    actual=replay(root);c.require(all(v[k]==x for k,x in actual.items()),'Original work, usage, models or derivation changed')
    c.require(v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog) and v['start_round']==1 and v['spent_correction_rounds']==1,'Original case/catalogue/round required');return v
