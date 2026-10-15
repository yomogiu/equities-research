"""Explicit, replayed preparation adoption; no new claims or budget reset."""
from pathlib import Path
import copy,json,subprocess,sys,re
from . import earnings_mixed_runner as base
from . import earnings_file_context as context

VERSION='verified-retrieval-transport-continuation-v1'

def normalize(value):
    result=copy.deepcopy(value)
    for i,row in enumerate(result['document_findings']):
        if set(row)=={'finding','document_id'}:
            context.require(isinstance(row['finding'],str) and isinstance(row['document_id'],str),'Exact finding transport fields required')
            result['document_findings'][i]={'text':row['finding'],'citations':[row['document_id']]}
        else:context.require(set(row)=={'text','citations'},'Unknown or ambiguous document-finding schema')
    return result


def replay(previous):
    previous=Path(previous).resolve();q=base.read(previous/'jobs/retrieval/request.json');code=Path(q['code_root']).resolve()
    context.require(re.fullmatch(r'[0-9a-f]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    context.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    program="""import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert protocol.get('inherited_tokens',0)==0 and not protocol.get('budget_authorization')
assert sorted(x.name for x in (root/'jobs').iterdir())==['retrieval']
job=root/'jobs/retrieval';q=b.read(job/'request.json');v=r.verify_job(job)
assert q['bindings']['role']=='retrieval' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert [q['model'],q['effort']]==protocol['models']['retrieval']
assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest']
proof=p.coverage('retrieval',Path(q['context_index']),job,v['content'],catalog,{})
print(json.dumps({'raw':v['content'],'tokens':v['receipt']['session']['usage']['totalTokens'],'session_id':v['receipt']['session']['id'],'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens']}))
"""
    return json.loads(subprocess.check_output([sys.executable,'-B','-I','-c',program,str(code),str(previous)],text=True))


def prepare(previous,case,output):
    previous=Path(previous).resolve();v=replay(previous)
    context.require(v['case_sha256']==base.sha(case),'Preparation belongs to another case')
    record={'version':VERSION,'previous_root':str(previous),'protocol_sha256':base.sha(previous/'protocol.json'),
            'output_sha256':base.sha(previous/'jobs/retrieval/output.json'),'case_sha256':base.sha(case),
            'catalog_sha256':v['catalog_sha256'],'tokens':v['tokens'],'session_id':v['session_id'],
            'max_tokens':v['max_tokens'],'content':normalize(v['raw'])}
    context.write(output,record);return record


def verify(path,case,catalog):
    a=base.read(path);context.require(a['version']==VERSION and a['case_sha256']==base.sha(case),'Preparation case changed')
    old=Path(a['previous_root']);context.require(a['protocol_sha256']==base.sha(old/'protocol.json') and a['output_sha256']==base.sha(old/'jobs/retrieval/output.json'),'Preparation ancestor changed')
    v=replay(old)
    context.require(a['content']==normalize(v['raw']) and all(a[k]==v[k] for k in ('tokens','session_id','max_tokens','case_sha256','catalog_sha256')) and a['catalog_sha256']==base.digest(catalog),'Preparation derivation changed')
    return a
