"""One explicit successor for a confirmed zero-output provider overload."""
import copy
import json
from pathlib import Path
from . import earnings_mixed_runner as r, earnings_role_import as imp


def check(value, message):
    if not value:
        raise ValueError(message)


def inspect_failure(job, code):
    job, code = Path(job).resolve(), Path(code).resolve()
    check(not any(p.is_symlink() for p in job.rglob('*')), 'Failure symlinks forbidden')
    q, launch, execution, start = [r.read(job/name) for name in
        ('request.json', 'launch.json', 'execution.json', 'runtime-start.json')]
    r._validate_selection(q['model'], q['effort'])
    check(q['job_path'] == str(job) and q['provider'] == r.PROVIDER, 'Failure identity differs')
    check(q['runner_sha256'] == r.sha(code/'research/earnings_mixed_runner.py') and
          q['helper_sha256'] == r.sha(code/'research/earnings_mixed_prime.mjs'), 'Failure verifier differs')
    check(q['prompt_sha256'] == r.sha(job/'prompt.txt') and launch['request_sha256'] == r.digest(q)
          and execution['request_sha256'] == r.digest(q) and execution['launch_sha256'] == r.sha(job/'launch.json'), 'Failure request binding differs')
    check(execution['status'] == 'returned' and execution['exit_code'] == 1, 'Failure must have observed process exit')
    check(r.read(job/'runtime-failure.json') == {'stage':'output_validation'}, 'Unsupported failure stage')
    check(not any((job/name).exists() for name in ('output.json','runtime-finish.json','import.json')), 'Completed output cannot be retried')
    check(not (job/'stdout.txt').exists() or not (job/'stdout.txt').read_text().strip(), 'Nonempty output cannot be retried')
    check(r.read(job/'wire.json') == [{'model':q['model'],'effort':q['effort'],'tools':0}], 'Unexpected provider request')
    paths = list((job/'sessions').rglob('*.jsonl'))
    check(len(paths) == 1, 'Exactly one failed session required')
    rows = [json.loads(line) for line in paths[0].read_text().splitlines() if line.strip()]
    heads = [x for x in rows if x.get('type') == 'session']
    check(len(heads) == 1 and heads[0].get('id') and not heads[0].get('parentSession') and
          Path(heads[0]['cwd']).resolve() == job, 'Failure session identity differs')
    for typ, field, expected in (('model_change','modelId',q['model']), ('thinking_level_change','thinkingLevel',q['effort'])):
        values = [x for x in rows if x.get('type') == typ]
        check(values and all(x.get(field) == expected for x in values), 'Failure model/effort differs')
        if typ == 'model_change':
            check(all(x.get('provider') == r.PROVIDER for x in values), 'Failure provider differs')
    check(not any(x.get('type') in ('compaction','branch_summary') for x in rows), 'Failure context mutated')
    msgs = [x['message'] for x in rows if x.get('type') == 'message']
    check(len(msgs) == 2 and [m.get('role') for m in msgs] == ['user','assistant'], 'Unexpected failed conversation')
    check(r._text(msgs[0]) == (job/'prompt.txt').read_text(), 'Failure prompt differs')
    final = msgs[1]
    check(final.get('provider') == r.PROVIDER and final.get('model') == q['model'] and final.get('api') == 'openai-codex-responses'
          and final.get('stopReason') == 'error' and final.get('content') == [], 'Only empty failed responses supported')
    check(all(type(final.get('usage',{}).get(k)) is int and final['usage'][k] == 0
              for k in ('input','output','cacheRead','cacheWrite','totalTokens')), 'Nonzero/unknown usage requires separate assessment')
    errors = [x for x in final.get('diagnostics',[]) if x.get('type') == 'provider_stream_failure']
    check(len(errors) == 1 and errors[0].get('error',{}).get('code') == 'server_is_overloaded', 'Only confirmed overload supported')
    check(start.get('launch_id') == launch['id'] and start.get('session_id') == heads[0]['id'] and start.get('oauth') is True
          and start.get('model') == q['model'] and start.get('effort') == q['effort'], 'Failure runtime identity differs')
    return {'session_id':heads[0]['id'],'usage':{k:0 for k in ('input','output','cacheRead','cacheWrite','totalTokens')},
            'elapsed_seconds':execution['elapsed_seconds'],'reason':'server_is_overloaded','attempt':1}


def validate(reference):
    job, code = Path(reference['job']), Path(reference['code'])
    check(imp.inventory(job) == reference['files'], 'Failed attempt changed')
    for name, digest in reference['code_files'].items():
        check(r.sha(code/name) == digest, 'Failed attempt verifier changed')
    check(inspect_failure(job,code) == reference['receipt'], 'Failed attempt receipt differs')


def initialize(seed, output, authorization):
    from . import earnings_passage_pipeline as pipe
    seed, output = Path(seed).resolve(), Path(output).resolve()
    check(authorization.strip() and not output.exists() and output != seed, 'New authorized recovery required')
    old = r.read(seed/'protocol.json')
    check(old['version'] == pipe.VERSION and not any(old.get(k) for k in ('response_recovery','prepared_recovery')),
          'Only original presentation pipeline supported')
    check(not (seed/'result.json').exists(), 'Terminal reviewed work requires separate recovery')
    for rec in old['code']:
        check(r.sha(rec['path']) == rec['sha256'], 'Original code changed')
    code = Path(next(x['path'] for x in old['code'] if x['path'].endswith('/earnings_mixed_runner.py'))).parent.parent
    jobs = {q.parent.name:q.parent for q in (seed/'jobs').glob('*/request.json')}
    check(set(jobs) == {'financial-r0','retrieval-r0','analysis-r0'}, 'Recovery requires exactly two preparers and first analysis failure')
    imports = {name:imp.reference(jobs[name],code) for name in ('financial-r0','retrieval-r0')}
    failed = jobs['analysis-r0']
    failure = {'job':str(failed),'code':str(code),'files':imp.inventory(failed),
               'code_files':{str(p.relative_to(code)):r.sha(p) for p in (code/'research').glob('earnings_*') if p.is_file()},
               'receipt':inspect_failure(failed,code)}
    check(len({imp.authenticate(ref)['session']['id'] for ref in imports.values()} | {failure['receipt']['session_id']}) == 3,
          'Inherited sessions must be distinct')
    protocol = copy.deepcopy(old)
    protocol['code'] = [{'path':str(p),'sha256':r.sha(p)} for p in sorted(Path(__file__).parent.glob('earnings_*')) if p.suffix in ('.py','.mjs')]
    protocol['response_recovery'] = {'authorization':authorization,'seed':str(seed),'protocol_sha256':r.sha(seed/'protocol.json'),
                                    'imports':imports,'provider_retry':failure,'attempt':2}
    output.mkdir(parents=True)
    (output/'passages.json').write_bytes((seed/'passages.json').read_bytes())
    if old.get('qa_grounding_path'):
        (output/'qa-grounding.json').write_bytes(Path(old['qa_grounding_path']).read_bytes())
        protocol['qa_grounding_path'] = str(output/'qa-grounding.json')
    r.save(output/'protocol.json',protocol)
    pipe.load(output)
    return protocol['response_recovery']


def require_retry_prompt(recovery, job_name, text, model, effort):
    ref = recovery.get('provider_retry')
    if ref is None or job_name != 'analysis-r0':
        return
    validate(ref)
    q = r.read(Path(ref['job'])/'request.json')
    check((Path(ref['job'])/'prompt.txt').read_text() == text and (q['model'],q['effort']) == (model,effort),
          'Provider retry must preserve original prompt/model')
