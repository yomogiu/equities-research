"""One exact duplicate from a completed source-adjudicated turn proposal.

The failed proposal stays immutable and charged. This derives a candidate only;
fresh independent review remains mandatory and correction one remains spent.
"""
from pathlib import Path
import copy,inspect,json,re,subprocess,sys
from . import earnings_mixed_runner as b,earnings_file_context as c
VERSION='authenticated-source-adjudicated-turn-dedup-preparation-v1'

def normalize(original,candidate,targets):
    if not isinstance(targets,list) or len(targets)!=1:raise ValueError('One authenticated original target required')
    t=targets[0];path=t['field_path'];position=t['position'];before=t['before_ids']
    if len(path)!=3 or path[0]!='findings' or type(path[1]) is not int or path[1]<0 or path[2]!='citations':raise ValueError('One typed finding citation position required')
    row=original['findings'][path[1]]
    if row.get('section')!='qa' or row['citations']!=before or len(before)<2 or len(before)!=len(set(before)) or type(position) is not int or not 0<=position<len(before) or before[position]!=t['unknown_id']:raise ValueError('Exact original invalid position and retained support required')
    new=candidate['findings'][path[1]]['citations']
    if not isinstance(new,list) or len(new)!=len(before):raise ValueError('One exact source-adjudicated replacement required')
    selected=new[position];retained=before[:position]+before[position+1:]
    if selected not in retained or selected not in t['allowed_turn_ids'] or new.count(selected)!=2:raise ValueError('Model selection must duplicate an original retained answer turn')
    expected=copy.deepcopy(original);expected['findings'][path[1]]['citations'][position]=selected
    if expected!=candidate:raise ValueError('Every other original field, prose, quote and valid reference must remain exact')
    result=copy.deepcopy(candidate);result['findings'][path[1]]['citations'].pop(position)
    if result['findings'][path[1]]['citations']!=retained:raise ValueError('Original retained citation order required')
    return result

PROGRAM=r'''
import sys,json,copy
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from research import earnings_analysis_turn_address_repair as repair,earnings_file_runner as runner,earnings_file_pipeline as p,earnings_mixed_runner as b,earnings_compact_evidence as evidence
v=repair.verify_reservation(root);job=root/'jobs/address-repair';q=b.read(job/'request.json');done=runner.verify_job(job)
assert q['bindings']==v['bindings'] and q['max_tokens']==v['max_tokens'] and q['max_tool_calls']==48 and [q['model'],q['effort']]==v['models']['analysis'] and (job/'prompt.md').read_text()==v['prompt']
assert not any(job.with_name('address-repair--resume-'+str(i)).exists() for i in (1,2))
previous=Path(v['previous_root']);protocol=b.read(previous/'protocol.json');bundle=evidence.load_bundle(protocol['evidence_manifest']);catalog=b.read(previous/'passages.json');raw=v['prior']['raw'];proposal=done['content']
try:repair.checked_candidate(raw,proposal,bundle['transcript_index'])
except ValueError as error:assert str(error)=='Distinct exact original answer-turn selections required'
else:raise AssertionError('Exact original duplicate rejection required')
candidate=normalize(raw,proposal,v['prior']['targets'])
p.pipe.validate('analysis',candidate,bundle,catalog);p.coverage('analysis',Path(v['index']),job,candidate,catalog,{})
sid=done['receipt']['session']['id'];assert sid not in v['prior']['session_ids'] and len(v['prior']['session_ids'])==2 and v['spent_correction_rounds']==1
tokens=v['prior']['tokens']+done['receipt']['session']['usage']['totalTokens'];assert tokens<v['prior']['max_tokens']<=1200000
print(json.dumps({**{k:v['prior'][k] for k in ('models','max_tokens','case_sha256','catalog_sha256','writing_sha256','report_template')},'content':candidate,'tokens':tokens,'session_ids':[*v['prior']['session_ids'],sid],'spent_correction_rounds':1,'source_proposal_sha256':b.sha(job/'output.json'),'source_reservation_sha256':b.sha(root/'reservation.json'),'derivation':'Remove only the model-inserted duplicate of an already retained original answer-turn citation; preserve original retained order and every other field. No new reference selected and no acceptance.'}))
'''
def replay(root):
    root=Path(root).resolve();code=Path(b.read(root/'jobs/address-repair/request.json')['code_root']).resolve()
    c.require(code.parent.name=='.report-workflow' and re.fullmatch('[a-f0-9]{40}',code.name),'Managed frozen repair verifier required')
    c.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip() and subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()=='https://github.com/yomogiu/equities-research.git','Clean official repair verifier required')
    return json.loads(subprocess.check_output([sys.executable,'-I','-B','-c','import copy\n'+inspect.getsource(normalize)+PROGRAM,str(code),str(root)],text=True))
def prepare(root,case,output):
    root=Path(root).resolve();actual=replay(root);c.require(actual['case_sha256']==b.sha(case),'Original case required');v={'version':VERSION,'repair_root':str(root),**actual};c.write(output,v);return v

def verify(path,case,catalog):
    v=b.read(path);c.require(v['version']==VERSION,'Exact duplicate derivation version required');actual=replay(v['repair_root']);c.require(all(v[k]==x for k,x in actual.items()) and v['case_sha256']==b.sha(case) and v['catalog_sha256']==b.digest(catalog),'Original work, source inspection, proposal or accounting changed');return v
