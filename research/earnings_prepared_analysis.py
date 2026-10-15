"""Canonical source addressing for a completed, independently replayed author."""
from pathlib import Path
import copy,json,subprocess,sys,inspect,re
from . import earnings_mixed_runner as base,earnings_file_context as context
VERSION='verified-analysis-addressing-continuation-v1'

def normalize(value,catalog,document_id,sections):
    result=copy.deepcopy(value);parent={p['passage_id']:p['scope_id'] for p in catalog['passages']}
    def walk(item):
        if isinstance(item,dict):
            for key,v in item.items():
                if key in ('citations','opening_citations'):
                    converted=[]
                    for identifier in v:
                        if identifier==document_id:
                            if not sections:raise ValueError('No source-bound call sections')
                            converted.extend(sections)
                        else:converted.append(parent.get(identifier,identifier))
                    item[key]=list(dict.fromkeys(converted))
                else:walk(v)
        elif isinstance(item,list):
            for v in item:walk(v)
    walk(result);return result


def replay(previous):
    previous=Path(previous).resolve();q=base.read(previous/'jobs/analysis/request.json');code=Path(q['code_root']).resolve()
    context.require(re.fullmatch(r'[0-9a-f]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    context.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    program="import sys,json,copy;from pathlib import Path\nsys.path.insert(0,sys.argv[1])\n"+inspect.getsource(normalize)+"""
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
assert protocol.get('preparation_path') and not protocol.get('analysis_preparation_path')
assert sorted(x.name for x in (root/'jobs').iterdir())==['analysis']
job=root/'jobs/analysis';q=b.read(job/'request.json');v=r.verify_job(job)
assert q['bindings']['role']=='analysis' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert [q['model'],q['effort']]==protocol['models']['analysis']
assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest']
value=normalize(v['content'],catalog,bundle['transcript_index']['source']['document_id'],[s['id'] for s in bundle['transcript_index']['sections']])
p.coverage('analysis',Path(q['context_index']),job,value,catalog,{})
p.pipe.validate('analysis',value,bundle,catalog)
a=b.read(protocol['preparation_path']);sessions=[a['session_id'],v['receipt']['session']['id']]
assert len(set(sessions))==2
print(json.dumps({'content':value,'tokens':protocol['inherited_tokens']+v['receipt']['session']['usage']['totalTokens'],'session_ids':sessions,'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens']}))
"""
    return json.loads(subprocess.check_output([sys.executable,'-B','-I','-c',program,str(code),str(previous)],text=True))


def prepare(previous,case,output):
    previous=Path(previous).resolve();v=replay(previous)
    context.require(v['case_sha256']==base.sha(case),'Analysis belongs to another case')
    value={'version':VERSION,'previous_root':str(previous),'protocol_sha256':base.sha(previous/'protocol.json'),
           'output_sha256':base.sha(previous/'jobs/analysis/output.json'),**v}
    context.write(output,value);return value


def verify(path,case,catalog):
    a=base.read(path);old=Path(a['previous_root'])
    context.require(a['version']==VERSION and a['case_sha256']==base.sha(case),'Analysis case changed')
    context.require(a['protocol_sha256']==base.sha(old/'protocol.json') and a['output_sha256']==base.sha(old/'jobs/analysis/output.json'),'Analysis ancestor changed')
    v=replay(old)
    context.require(all(a[k]==v[k] for k in v) and a['catalog_sha256']==base.digest(catalog),'Analysis source addressing or lineage changed')
    return a
