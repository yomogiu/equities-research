"""Canonical source addressing for a completed, independently replayed author."""
from pathlib import Path
import copy,json,subprocess,sys,inspect,re
from . import earnings_mixed_runner as base,earnings_file_context as context
VERSION='verified-analysis-addressing-continuation-v1'
DUPLICATE_VERSION='authenticated-single-duplicate-analysis-quotation-v1'
EXCHANGE_VERSION='authenticated-quoted-turn-exchange-address-v1'

def resolve_quoted_exchange(value,catalog,index):
    """Derive one unknown Q&A citation from unique original quoted answer turns.

    No similarity, prefix or prose matching is used. Full frozen validation and
    inspection still follow, and this candidate requires independent review.
    """
    exchanges={e['id']:e for e in index['exchanges']};passages={p['passage_id']:p for p in catalog['passages']}
    unknown=[(i,c) for i,f in enumerate(value['findings']) for c in f['citations'] if c.startswith('exchange-') and c not in exchanges]
    if len(unknown)!=1:raise ValueError('Exactly one unknown exchange citation required')
    position,old=unknown[0];finding=value['findings'][position]
    if finding.get('section')!='qa' or finding['citations']!=[old] or not finding['quotes']:raise ValueError('One isolated quoted Q&A citation required')
    turns=set()
    for quote in finding['quotes']:
        if not isinstance(quote,dict) or set(quote)!={'passage_id'} or quote['passage_id'] not in passages:raise ValueError('Exact original quotation selections required')
        turns.add(passages[quote['passage_id']]['scope_id'])
    matches=[e['id'] for e in exchanges.values() if turns<=set(e['answer_turn_ids'])]
    if len(matches)!=1:raise ValueError('Unique original quoted-answer exchange membership required')
    result=copy.deepcopy(value);result['findings'][position]['citations']=[matches[0]];return result

def remove_single_duplicate(value):
    """Retain the first exact quote selection; preserve every distinct selection.

    This derives a candidate, not an accepted report. The frozen verifier must
    still authenticate complete source inspection and the full derived schema.
    """
    result=copy.deepcopy(value);seen=set();removed=0
    for finding in result['findings']:
        quotes=[]
        for quote in finding['quotes']:
            if not isinstance(quote,dict) or set(quote)!={'passage_id'} or not isinstance(quote['passage_id'],str):
                raise ValueError('Exact passage selections required')
            pid=quote['passage_id']
            if pid in seen:removed+=1
            else:quotes.append(quote);seen.add(pid)
        finding['quotes']=quotes
    if removed!=1:raise ValueError('Exactly one duplicate analysis quotation required')
    return result

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


def replay(previous,duplicate_quotes=False,quoted_exchange=False):
    context.require(not (duplicate_quotes and quoted_exchange),'One exact derivation required')
    previous=Path(previous).resolve();q=base.read(previous/'jobs/analysis/request.json');code=Path(q['code_root']).resolve()
    context.require(re.fullmatch(r'[0-9a-f]{40}',code.name) and code.parent.name=='.report-workflow','Managed frozen verifier required')
    context.require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==code.name and not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip(),'Frozen verifier changed')
    if duplicate_quotes or quoted_exchange:
        origin=subprocess.check_output(['git','remote','get-url','origin'],cwd=code,text=True).strip()
        context.require(origin in ('https://github.com/yomogiu/equities-research.git','git@github.com:yomogiu/equities-research.git'),'Official frozen verifier required')
    program="import sys,json,copy;from pathlib import Path\nsys.path.insert(0,sys.argv[1])\n"+inspect.getsource(normalize)+inspect.getsource(remove_single_duplicate)+inspect.getsource(resolve_quoted_exchange)+"""
from research import earnings_file_pipeline as p,earnings_file_runner as r,earnings_mixed_runner as b
root=Path(sys.argv[2]);protocol,bundle,catalog=p.load(root)
direct=not protocol.get('preparation_path') and sorted(x.name for x in (root/'jobs').iterdir())==['analysis','retrieval']
assert not protocol.get('analysis_preparation_path') and (protocol.get('preparation_path') or direct)
assert direct or sorted(x.name for x in (root/'jobs').iterdir())==['analysis']
job=root/'jobs/analysis';q=b.read(job/'request.json');v=r.verify_job(job)
assert q['bindings']['role']=='analysis' and q['bindings']['protocol_sha256']==b.sha(root/'protocol.json')
assert [q['model'],q['effort']]==protocol['models']['analysis']
assert b.read(q['context_index'])['manifest']==protocol['evidence_manifest']
value=v['content'] if direct else normalize(v['content'],catalog,bundle['transcript_index']['source']['document_id'],[s['id'] for s in bundle['transcript_index']['sections']])
duplicate=sys.argv[3]=='duplicate'
exchange=sys.argv[3]=='exchange'
if exchange:
 assert direct and protocol['max_correction_rounds']==2 and not protocol.get('review_preparation_path') and not protocol.get('recovery_path')
 try:p.pipe.validate('analysis',value,bundle,catalog)
 except ValueError as error:assert str(error)=='Invalid/duplicate/unknown findings citations'
 else:raise AssertionError('Exact original unknown findings citation required')
 value=resolve_quoted_exchange(value,catalog,bundle['transcript_index'])
if duplicate:
 assert direct and protocol['max_correction_rounds']==2 and not protocol.get('review_preparation_path') and not protocol.get('recovery_path')
 try:p.pipe.validate('analysis',value,bundle,catalog)
 except ValueError as error:
  assert len(getattr(error,'issues',[]))==1 and error.issues[0]['reason']=='Duplicate selection; select a distinct relevant passage.'
 else:raise AssertionError('Exact original duplicate selection failure required')
 value=remove_single_duplicate(value)
p.coverage('analysis',Path(q['context_index']),job,value,catalog,{})
p.pipe.validate('analysis',value,bundle,catalog)
if direct:
 from research import earnings_prepared_retrieval as prepared
 # Authenticate both original instructions/dependencies using the frozen parent.
 retrieval_job=root/'jobs/retrieval';rv=r.verify_job(retrieval_job);rq=b.read(retrieval_job/'request.json')
 assert rq['bindings']['protocol_sha256']==b.sha(root/'protocol.json') and rq['bindings']['role']=='retrieval'
 assert [rq['model'],rq['effort']]==protocol['models']['retrieval']
 assert b.read(rq['context_index'])['manifest']==protocol['evidence_manifest']
 p.coverage('retrieval',Path(rq['context_index']),retrieval_job,rv['content'],catalog,{})
 p.pipe.validate('retrieval',rv['content'],bundle,catalog)
 deps=b.read(Path(q['context_index']).parent/'artifacts.json')
 assert deps['retrieval']==rv['content'] and b.digest(deps)==q['bindings']['artifact_sha256']
 assert (job/'prompt.md').read_text()==p.instruction('analysis',Path(q['context_index']),job,protocol)
 assert (retrieval_job/'prompt.md').read_text()==p.instruction('retrieval',Path(rq['context_index']),retrieval_job,protocol)
 a={'session_id':rv['receipt']['session']['id']};prior_tokens=rv['receipt']['session']['usage']['totalTokens']
else:
 a=b.read(protocol['preparation_path']);prior_tokens=protocol['inherited_tokens']
sessions=[a['session_id'],v['receipt']['session']['id']]
assert len(set(sessions))==2
result={'content':value,'tokens':prior_tokens+v['receipt']['session']['usage']['totalTokens'],'session_ids':sessions,'case_sha256':protocol['case_sha256'],'catalog_sha256':b.digest(catalog),'max_tokens':protocol['max_tokens']}
if duplicate or exchange:result.update(models=protocol['models'],report_template=protocol['report_template'],writing_sha256=protocol['writing_sha256'],spent_correction_rounds=0)
print(json.dumps(result))
"""
    return json.loads(subprocess.check_output([sys.executable,'-B','-I','-c',program,str(code),str(previous),'duplicate' if duplicate_quotes else 'exchange' if quoted_exchange else 'legacy'],text=True))


def prepare(previous,case,output,*,duplicate_quotes=False,quoted_exchange=False):
    context.require(not (duplicate_quotes and quoted_exchange),'One exact derivation required')
    previous=Path(previous).resolve();v=replay(previous,duplicate_quotes=True) if duplicate_quotes else replay(previous,quoted_exchange=True) if quoted_exchange else replay(previous)
    context.require(v['case_sha256']==base.sha(case),'Analysis belongs to another case')
    value={'version':DUPLICATE_VERSION if duplicate_quotes else EXCHANGE_VERSION if quoted_exchange else VERSION,'previous_root':str(previous),'protocol_sha256':base.sha(previous/'protocol.json'),
           'output_sha256':base.sha(previous/'jobs/analysis/output.json'),**v}
    context.write(output,value);return value


def verify(path,case,catalog):
    a=base.read(path)
    if a.get('version')=='authenticated-analysis-address-preparation-v1':
        from . import earnings_analysis_address_repair
        return earnings_analysis_address_repair.verify(path,case,catalog)
    old=Path(a['previous_root'])
    context.require(a['version'] in (VERSION,DUPLICATE_VERSION,EXCHANGE_VERSION) and a['case_sha256']==base.sha(case),'Analysis case changed')
    context.require(a['protocol_sha256']==base.sha(old/'protocol.json') and a['output_sha256']==base.sha(old/'jobs/analysis/output.json'),'Analysis ancestor changed')
    v=replay(old,duplicate_quotes=True) if a['version']==DUPLICATE_VERSION else replay(old,quoted_exchange=True) if a['version']==EXCHANGE_VERSION else replay(old)
    context.require(all(a[k]==v[k] for k in v) and a['catalog_sha256']==base.digest(catalog),'Analysis source addressing or lineage changed')
    return a
