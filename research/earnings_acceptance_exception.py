"""An explicit acceptance edition for an already reviewed budget overrun.

No model is called and no budget is reset. The frozen verifier must authenticate
a final passing review of the exact candidate, with budget overrun as its sole
remaining hold. Authorization binds that review, usage, overrun and destination.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from research import earnings_experiment as base
from research import earnings_report_repair as repair

VERSION = 'authorized-acceptance-exception-v1'

# Run only this fixed program in the source's own hash-bound checkout. Source
# replay's immutable staging writes are replaced by exact read-only comparisons;
# temporary rendering remains permitted. No source file can be created/changed.
EXPORT = r'''
import json,sys,tempfile
from pathlib import Path
from research import earnings_experiment as b
from research import earnings_corrections as c
root=Path(sys.argv[1]).resolve()
original_write=c.repair.write; original_text=c.legacy.immutable_text
def compare_write(path,value):
 path=Path(path).resolve()
 if path.is_relative_to(root):
  text=json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
  if not path.is_file() or path.read_text()!=text:raise ValueError('Exception replay requires existing exact staged records')
 else:original_write(path,value)
def compare_text(path,value):
 path=Path(path).resolve()
 if path.is_relative_to(root):
  if not path.is_file() or path.read_text()!=value:raise ValueError('Exception replay requires existing exact rendered candidate')
 else:original_text(path,value)
c.repair.write=compare_write;c.legacy.immutable_text=compare_text
p,bundle,catalog,writing=c.load(root)
original_verify=c.verify_job;seen={}
def verified(job):
 result=original_verify(job);seen[str(Path(job).resolve())]=result;return result
c.verify_job=verified
progress=c.replay(root,p,bundle,catalog,writing)
if progress['status']!='budget_exhausted':raise ValueError('Only a conclusive budget stop can be excepted')
job=progress.get('job')
if job is None:
 info=progress.get('substantive_review',{})
 if info.get('validation')!='valid':raise ValueError('No authenticated final review at budget stop')
 job=Path(info['output_path']).parent
job=Path(job).resolve()
if not job.is_relative_to(root/'rounds') or job.name not in ('review','review-evidence-1'):
 raise ValueError('Budget stop is not a completed final review')
review=verified(job);content=review['content']
if content.get('verdict')!='pass':raise ValueError('Exception requires a saved passing final review')
if len((job/'prompt.txt').read_text())>min(p.get('max_prompt_chars',350000),350000):
 raise ValueError('A prompt-size hold cannot be excepted as a budget overrun')
folder=job.parent;before=progress['state'];plan=b.read(folder/'plan.json')
candidate=c.apply(before,plan,bundle,catalog)
if candidate!=b.read(folder/'candidate.json'):raise ValueError('Saved candidate differs from exact plan')
if c.rendered(candidate,bundle,catalog)!=(folder/'candidate.html').read_text():
 raise ValueError('Saved rendered candidate changed')
state,status=c.adjudicate(before,candidate,plan,content,bundle,catalog)
if status!='accepted' or state['findings']:raise ValueError('A substantive hold remains')
local={str(path.parent.resolve()) for path in (root/'rounds').rglob('output.json')}
reached={path for path in seen if Path(path).is_relative_to(root)}
requests={str(path.parent.resolve()) for path in (root/'rounds').rglob('request.json')}
nonempty_jobs={str(job.resolve()) for folder in (root/'rounds').iterdir() if folder.is_dir()
               for job in folder.iterdir() if job.is_dir() and any(job.iterdir())}
if local!=reached or requests!=local or nonempty_jobs!=reached:
 raise ValueError('Unreplayed or uncertain extra jobs in stopped source')
rows=[]
for path,result in sorted(seen.items()):
 session=result['receipt']['session'];used=session['usage']['totalTokens']
 if type(used)is not int or used<0:raise ValueError('Measured source usage required')
 rows.append({'job':path,'output_sha256':b.sha(Path(path)/'output.json'),'session_id':session['id'],
              'tokens':used,'inherited':not Path(path).is_relative_to(root)})
measured=sum(row['tokens'] for row in rows if not row['inherited'])
if measured!=progress['tokens']:raise ValueError('Replayed usage does not cover every completed source job')
total=p.get('inherited_tokens',0)+measured;ceiling=p['max_tokens']
if type(ceiling)is not int or total<=ceiling or p.get('new_experiment'):
 raise ValueError('Exact original-budget overrun required; no experiment reset')
with tempfile.TemporaryDirectory() as directory:
 rendered=Path(directory)/'accepted.html'
 c.repair.render(rendered,{**state,'status':'accepted'},bundle,catalog)
 html=rendered.read_text()
print(json.dumps({'state':state,'source_protocol':p['source_protocol'],'accepted_html':html,
 'review':{'job':str(job),'output_sha256':b.sha(job/'output.json'),'candidate_sha256':b.digest(candidate),
           'plan_sha256':b.digest(plan),'verdict':'pass','candidate_html_sha256':b.sha(folder/'candidate.html')},
 'history':{'source_status':progress['status'],'original_max_tokens':ceiling,'inherited_tokens':p.get('inherited_tokens',0),
            'measured_tokens':measured,'total_tokens':total,'overrun_tokens':total-ceiling,
            'prior_rounds':p.get('prior_rounds',0),'completed_local_rounds':int(folder.name)+1,
            'source_jobs':rows},'excluded_session_ids':sorted({row['session_id'] for row in rows})}))
'''


def source_bindings(seed, protocol):
    result = dict(protocol.get('source_bindings', {}))
    for path in seed.rglob('*'):
        if path.is_symlink(): raise ValueError('Source symlinks are forbidden')
        if path.is_file() and not path.name.startswith('.'):
            result[str(path)] = base.sha(path)
    return result


def export_seed(seed):
    seed = Path(seed).resolve(); protocol = base.read(seed/'protocol.json')
    # The ordinary corrections format has no recursive source replay in load;
    # specialized handoffs must first become an ordinary completed edition.
    if protocol.get('version') != 'deterministic-corrections-v1':
        raise ValueError('An ordinary stopped deterministic-corrections edition is required')
    for row in protocol['code'] + protocol.get('source_code', []):
        if base.sha(row['path']) != row['sha256']: raise ValueError('Frozen source verifier changed')
    before = source_bindings(seed, protocol)
    for path, digest in before.items():
        if base.sha(path) != digest: raise ValueError('Frozen source binding changed')
    code = Path(next(row['path'] for row in protocol['code']
                     if row['path'].endswith('/earnings_corrections.py'))).parent.parent
    result = subprocess.run([sys.executable, '-c', EXPORT, str(seed)], cwd=code,
                            env={**os.environ, 'PYTHONPATH': str(code)}, check=True, capture_output=True, text=True)
    if source_bindings(seed, protocol) != before:
        raise ValueError('Source changed during read-only exception replay')
    return protocol, json.loads(result.stdout), before


def authorize(value, seed, output, exported):
    names = {'kind', 'enabled', 'authorization_id', 'authorization_reference', 'reason',
             'seed_protocol_sha256', 'review_output_sha256', 'candidate_sha256', 'plan_sha256',
             'historical_total_tokens', 'original_max_tokens', 'authorized_overrun_tokens', 'output_path'}
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError('Exact acceptance-exception authorization fields required')
    if value['kind'] != 'budget_acceptance_exception' or value['enabled'] is not True:
        raise ValueError('Explicit enabled budget acceptance exception required')
    for key in ('authorization_id', 'authorization_reference', 'reason'):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 4000:
            raise ValueError('Traceable bounded user authorization required: ' + key)
    if value['seed_protocol_sha256'] != base.sha(seed/'protocol.json'):
        raise ValueError('Authorization names a different stopped seed')
    if not isinstance(value['output_path'], str) or Path(value['output_path']).resolve() != output:
        raise ValueError('Authorization names a different exception output')
    for key, source in (('review_output_sha256', 'output_sha256'), ('candidate_sha256', 'candidate_sha256'),
                        ('plan_sha256', 'plan_sha256')):
        if value[key] != exported['review'][source]: raise ValueError('Authorization names a different exact review')
    for key, source in (('historical_total_tokens', 'total_tokens'), ('original_max_tokens', 'original_max_tokens'),
                        ('authorized_overrun_tokens', 'overrun_tokens')):
        if type(value[key]) is not int or value[key] != exported['history'][source]:
            raise ValueError('Authorization does not match exact historical usage/overrun')
    if value['authorized_overrun_tokens'] <= 0:
        raise ValueError('Positive explicit overrun required')


def initialize(seed, output, authorization):
    seed = Path(seed).resolve(); root = Path(output).resolve()
    if root == seed or root.is_relative_to(seed) or root.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('New private sibling exception directory required')
    if root.exists() and any(root.iterdir()): raise ValueError('New exception directory must be empty')
    old, exported, bindings = export_seed(seed)
    authorize(authorization, seed, root, exported)
    names = list(Path(__file__).parent.glob('earnings_*.py')) + [Path(__file__).with_name('earnings_mixed_prime.mjs')]
    protocol = {'version': VERSION, 'seed': str(seed), 'source_protocol': exported['source_protocol'],
                'source_bindings': bindings, 'source_code': old['code'] + old.get('source_code', []),
                'code': [{'path': str(path), 'sha256': base.sha(path)} for path in names],
                'authorization_sha256': base.digest(authorization), 'export_sha256': base.digest(exported),
                'excluded_session_ids': exported['excluded_session_ids']}
    root.mkdir(parents=True, exist_ok=True)
    repair.write(root/'authorization.json', authorization); repair.write(root/'protocol.json', protocol)
    repair.write(root/'source-export.json', exported); repair.write(root/'state.json', exported['state'])
    (root/'report.html').write_text(exported['accepted_html'])
    result = {'status': 'accepted', 'acceptance_basis': 'explicit_user_budget_exception',
              'authorization_sha256': protocol['authorization_sha256'], 'source_review': exported['review'],
              'history': exported['history'], 'state': exported['state'], 'html_sha256': base.sha(root/'report.html'),
              'new_report_model_calls': 0, 'budget_reset': False}
    repair.write(root/'result.json', result)
    return {'status': 'accepted', 'acceptance_basis': result['acceptance_basis'], 'history': result['history']}


def verify(output):
    root = Path(output).resolve(); p = base.read(root/'protocol.json'); auth = base.read(root/'authorization.json')
    if p.get('version') != VERSION or base.digest(auth) != p['authorization_sha256']:
        raise ValueError('Exception protocol or authorization changed')
    for row in p['code']:
        if base.sha(row['path']) != row['sha256'] or base.sha(Path(__file__).parent/Path(row['path']).name) != row['sha256']:
            raise ValueError('Exception verifier code changed')
    for path, digest in p['source_bindings'].items():
        if base.sha(path) != digest: raise ValueError('Original exception source changed')
    old, exported, bindings = export_seed(Path(p['seed']))
    authorize(auth, Path(p['seed']), root, exported)
    if (bindings != p['source_bindings'] or old['code'] + old.get('source_code', []) != p['source_code']
            or exported['source_protocol'] != p['source_protocol']
            or exported['excluded_session_ids'] != p['excluded_session_ids']
            or base.digest(exported) != p['export_sha256'] or exported != base.read(root/'source-export.json')
            or exported['state'] != base.read(root/'state.json')
            or exported['accepted_html'] != (root/'report.html').read_text()):
        raise ValueError('Exception differs from authenticated source replay')
    expected = {'status': 'accepted', 'acceptance_basis': 'explicit_user_budget_exception',
                'authorization_sha256': p['authorization_sha256'], 'source_review': exported['review'],
                'history': exported['history'], 'state': exported['state'], 'html_sha256': base.sha(root/'report.html'),
                'new_report_model_calls': 0, 'budget_reset': False}
    if base.read(root/'result.json') != expected:
        raise ValueError('Exception result differs from authorized exact acceptance')
    return {key: value for key, value in expected.items() if key != 'state'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('seed'); init.add_argument('output'); init.add_argument('authorization')
    sub.add_parser('verify').add_argument('output')
    args = parser.parse_args()
    result = initialize(args.seed, args.output, base.read(args.authorization)) if args.command == 'init' else verify(args.output)
    print(json.dumps(result))


if __name__ == '__main__': main()
