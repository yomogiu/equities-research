"""Explicit independently reviewed source-attribution edition; no preparer reruns."""
import copy
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_role_import as imported
from . import earnings_attribution_overlay as overlay


def check(value, reason):
 if not value: raise ValueError(reason)


def initialize(seed, output, coverage, review, attestation, authorization):
 from . import earnings_passage_pipeline as pipe
 seed,output=Path(seed).resolve(),Path(output).resolve()
 check(authorization.strip() and not output.exists(),'New authorized directory required')
 old=r.read(seed/'protocol.json');check(old.get('response_recovery') and not old.get('prepared_recovery'),'An authenticated response recovery is required')
 for c in old['code']:check(r.sha(c['path'])==c['sha256'],'Original code changed')
 code=Path(next(c['path'] for c in old['code'] if c['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
 refs=[]
 for q in sorted((seed/'jobs').glob('*/request.json')):
  if (q.parent/'import.json').exists():
   # Verify the wrapper first using its own frozen verifier, then bind original.
   import subprocess,sys,os
   code_text="from pathlib import Path;import sys;from research.earnings_mixed_runner import verify_job;verify_job(Path(sys.argv[1]))"
   subprocess.run([sys.executable,'-c',code_text,str(q.parent)],cwd=code,env={**os.environ,'PYTHONPATH':str(code)},check=True,capture_output=True)
   ref=r.read(q.parent/'import.json')['source']
  else:ref=imported.reference(q.parent,code)
  imported.authenticate(ref);refs.append(ref)
 rounds=max(r.read(q)['bindings']['round'] for q in (seed/'jobs').glob('*/request.json'))
 check(rounds<=2,'Original correction budget exceeded')
 protocol=copy.deepcopy(old);protocol.pop('response_recovery')
 protocol['code']=[{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
 files={str(p):r.sha(p) for p in seed.rglob('*') if p.is_file() and not p.name.endswith('.lock')}
 paths={'coverage':str(Path(coverage).resolve()),'review':str(Path(review).resolve()),'attestation':str(Path(attestation).resolve())}
 cov=r.read(paths['coverage']);ov=r.read(cov['attribution_overlay']['path'])
 for name in ('proposal','review'):files[ov[name]['path']]=r.sha(ov[name]['path'])
 for path in [*paths.values(),cov['attribution_overlay']['path']]:files[path]=r.sha(path)
 protocol['prepared_recovery']={'authorization':authorization,'seed':str(seed),'bindings':files,'paths':paths,'responses':refs,'prior_rounds':rounds}
 output.mkdir(parents=True)
 for name in ('passages.json','qa-grounding.json'):(output/name).write_bytes((seed/name).read_bytes())
 protocol['qa_grounding_path']=str(output/'qa-grounding.json')
 r.save(output/'protocol.json',protocol);pipe.load(output)
 return protocol['prepared_recovery']


def apply(protocol,bundle,catalog):
 from . import earnings_passage_pipeline as pipe
 p=protocol['prepared_recovery'];seed=Path(p['seed'])
 for path,h in p['bindings'].items():check(r.sha(path)==h,'Prepared recovery input changed')
 old=r.read(seed/'protocol.json');comp=copy.deepcopy(protocol)
 for key in ('code','prepared_recovery'):comp.pop(key)
 comp['qa_grounding_path']=old['qa_grounding_path'];original={k:v for k,v in old.items() if k not in ('code','response_recovery')}
 check(comp==original,'Prepared recovery changed original settings')
 receipts=[imported.authenticate(ref) for ref in p['responses']]
 check(len({x['session']['id'] for x in receipts})==len(receipts),'Duplicate inherited session')
 rounds=max(r.read(q)['bindings']['round'] for q in (seed/'jobs').glob('*/request.json'))
 check(p['prior_rounds']==rounds and 0<=rounds<=2,'Inherited rounds changed')
 paths=p['paths'];cov=r.read(paths['coverage']);review=r.read(paths['review']);att=r.read(paths['attestation'])
 check(review.get('final_decision')=='accept' and review.get('proposal')=={'path':paths['coverage'],'sha256':r.sha(paths['coverage'])},'Coverage requires independent approval')
 check(att.get('authorization') and att.get('author_agent')!=att.get('reviewer_agent') and all(att.get(k) for k in ('author_agent','reviewer_agent')),'Independent delegated agents required')
 check(att.get('coverage_review_sha256')==r.sha(paths['review']),'Coverage review attestation changed')
 ov=r.read(cov['attribution_overlay']['path']);check(r.sha(cov['attribution_overlay']['path'])==cov['attribution_overlay']['sha256'],'Overlay receipt changed')
 check(att.get('attribution_review_sha256')==ov['review']['sha256'],'Attribution review attestation changed')
 derived,receipt=overlay.apply(bundle,catalog,ov['proposal']['path'],ov['review']['path']);check(receipt==ov,'Overlay replay differs')
 original=r.read(cov['original_output']['path'])['content'];check(r.sha(cov['original_output']['path'])==cov['original_output']['sha256'],'Original coverage changed')
 check(any(str(Path(ref['job'])/'output.json')==cov['original_output']['path'] for ref in p['responses']),'Coverage source not authenticated')
 out=cov['content'];check({k:v for k,v in out.items() if k!='exchange_coverage'}=={k:v for k,v in original.items() if k!='exchange_coverage'},'Non-attribution retrieval content changed')
 oldrows={x['exchange_id']:x for x in original['exchange_coverage']};newrows={x['exchange_id']:x for x in out['exchange_coverage']}
 check(set(oldrows)==set(newrows) and len(newrows)==len(out['exchange_coverage']),'Coverage membership changed')
 normalized_out,_=overlay.normalize_non_substantive(original,derived,receipt)
 normalized_rows={x['exchange_id']:x for x in normalized_out['exchange_coverage']}
 approved={x['exchange_id'] for x in review['decisions'] if x['decision']=='accept'}
 normalized={x['exchange_id'] for x in cov['normalizations']}
 for eid,row in newrows.items():
  if row!=oldrows[eid]:
   check(eid in approved or (eid in normalized and row==normalized_rows[eid]),'Unreviewed coverage edit')
 financial=r.read(seed/'artifacts.json')['financial']
 financial_results=[value['content'] for ref,value in zip(p['responses'],receipts) if r.read(Path(ref['job'])/'request.json')['bindings']['role']=='financial']
 check(len(financial_results)==1 and pipe.bind_efficient_financial(financial_results[0],bundle)==financial,'Financial artifact differs from authenticated response')
 pipe.validate('financial',financial,derived,catalog);pipe.validate('retrieval',out,derived,catalog)
 return derived,{'financial':financial,'retrieval':out},sum(x['session']['usage']['totalTokens'] for x in receipts),{x['session']['id'] for x in receipts}
