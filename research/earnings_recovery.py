"""One-session recovery for an interrupted experiment; original executor stays frozen.

prepare snapshots the failed attempt; recover resumes it once; continue runs the
unchanged five-role executor with a narrowly scoped recovered-job verifier.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import time
from . import earnings_experiment as base

VERSION = 'earnings-recovery-v1'
JOB = 'extractor-r0'
CONTINUATION = '''Continue the original extractor task from the evidence already inspected in this session. Finish the required exact JSON output now. Do not re-read the full documents, expand the search, inspect other roles, or modify files. Preserve source accuracy, exact observation IDs, period distinctions, and explicit gaps; omit unsupported checks rather than inventing them. Return exactly one JSON object matching the original extractor schema, with no prose outside it.'''
ORIGINALS = ('execution.json', 'stdout.txt', 'stderr.txt', 'request.json', 'dependencies.json', 'prompt.txt', 'launch.json')


def entries(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def messages(events):
    return [e['message'] for e in events if e.get('type') == 'message']


def session_path(job):
    paths = list((job / 'sessions').rglob('*.jsonl'))
    if len(paths) != 1:
        raise ValueError('Recovery requires exactly one original session')
    return base.inside(job, paths[0])


def original_session(events, prompt):
    heads = [e for e in events if e.get('type') == 'session']
    msgs = messages(events)
    users = [m for m in msgs if m.get('role') == 'user']
    if len(heads) != 1 or not heads[0].get('id'):
        raise ValueError('Unique original session identity required')
    if len(users) != 1 or base.message_text(users[0]) != prompt:
        raise ValueError('Original session prompt differs')
    if not msgs or msgs[-1].get('role') != 'assistant' or msgs[-1].get('stopReason') != 'aborted':
        raise ValueError('Original session must end with an observed abort')
    return heads[0]['id']


def prepare(run):
    run = Path(run).resolve(); job = base.inside(run, JOB)
    case = base.read(run / 'case.json'); base.validate_case(case)
    if (run / 'recovery-policy.json').exists():
        return policy(run)
    if (job / 'output.json').exists() or (job / 'recovery').exists():
        raise ValueError('Existing recovery or output requires reconciliation')
    if base.read(job / 'execution.json').get('status') != 'launch_uncertain' or (job / 'stdout.txt').read_bytes():
        raise ValueError('Only interrupted empty-output attempt can be recovered')
    request = base.read(job / 'request.json')
    if request.get('role') != 'extractor' or request.get('revision') != 0 or request.get('dependencies') != {} or request.get('case_sha256') != base.digest(case):
        raise ValueError('Only initial extractor of this frozen case can be recovered')
    if request.get('prompt_sha256') != base.sha(job / 'prompt.txt'):
        raise ValueError('Original prompt changed')
    path = session_path(job)
    sid = original_session(entries(path), (job / 'prompt.txt').read_text())
    recovery = job / 'recovery'; recovery.mkdir()
    (recovery / 'before-session.jsonl').write_bytes(path.read_bytes())
    (recovery / 'continuation.txt').write_text(CONTINUATION)
    value = {'version': VERSION, 'job': JOB, 'case_sha256': base.digest(case),
             'base_module_sha256': base.sha(base.__file__), 'adapter_sha256': base.sha(__file__),
             'session_path': str(path.relative_to(job)), 'session_id': sid,
             'before_session_sha256': base.sha(recovery / 'before-session.jsonl'),
             'continuation_sha256': base.sha(recovery / 'continuation.txt'),
             'originals': {name: base.sha(job / name) for name in ORIGINALS},
             'maximum_resumes': 1, 'timeout_seconds': 600}
    base.save(run / 'recovery-policy.json', value)
    return value


def policy(run):
    run = Path(run).resolve(); p = base.read(run / 'recovery-policy.json')
    job = base.inside(run, p['job']); recovery = base.inside(job, 'recovery')
    case = base.read(run / 'case.json'); base.validate_case(case)
    if p.get('version') != VERSION or p.get('job') != JOB or p.get('maximum_resumes') != 1 or p.get('timeout_seconds') != 600:
        raise ValueError('Unsupported recovery policy')
    if p['case_sha256'] != base.digest(case) or p['adapter_sha256'] != base.sha(__file__) or p['base_module_sha256'] != base.sha(base.__file__):
        raise ValueError('Frozen recovery code or case changed')
    if set(p['originals']) != set(ORIGINALS) or any(base.sha(base.inside(job,n)) != h for n,h in p['originals'].items()):
        raise ValueError('Original failed attempt changed')
    if base.sha(recovery / 'before-session.jsonl') != p['before_session_sha256']:
        raise ValueError('Original session snapshot changed')
    if base.sha(recovery / 'continuation.txt') != p['continuation_sha256'] or (recovery / 'continuation.txt').read_text() != CONTINUATION:
        raise ValueError('Recovery continuation changed')
    sid = original_session(entries(recovery / 'before-session.jsonl'), (job / 'prompt.txt').read_text())
    if sid != p['session_id'] or session_path(job) != base.inside(job, p['session_path']):
        raise ValueError('Recovery session identity changed')
    return p


def recovered_session(run):
    run = Path(run).resolve(); p = policy(run); job = run / JOB; recovery = job / 'recovery'
    path = base.inside(job, p['session_path'])
    before = (recovery / 'before-session.jsonl').read_bytes(); after = path.read_bytes()
    if not after.startswith(before) or after == before:
        raise ValueError('Recovered session must append to exact original bytes')
    ev = entries(path); heads = [e for e in ev if e.get('type') == 'session']
    msgs = messages(ev); users = [m for m in msgs if m.get('role') == 'user']
    if len(heads) != 1 or heads[0].get('id') != p['session_id']:
        raise ValueError('Recovered session identity changed')
    if len(users) != 2 or base.message_text(users[0]) != (job / 'prompt.txt').read_text() or base.message_text(users[1]) != CONTINUATION:
        raise ValueError('Exactly one approved continuation required')
    if not msgs or msgs[-1].get('role') != 'assistant' or msgs[-1].get('stopReason') != 'stop':
        raise ValueError('Recovery lacks final completed assistant response')
    if base.parse_response(base.message_text(msgs[-1])) != base.parse_response((recovery / 'stdout.txt').read_text()):
        raise ValueError('Recovery response differs from runtime stdout')
    models = [e for e in ev if e.get('type') == 'model_change']
    final = msgs[-1]
    provider = models[-1].get('provider') if models else final.get('provider')
    if provider != 'openai-codex':
        raise ValueError('Recovery must use approved subscription provider')
    return {'id': p['session_id'], 'path': p['session_path'], 'sha256': base.sha(path),
            'provider': provider, 'model': models[-1].get('modelId') if models else final.get('model')}


def recover(run):
    run = Path(run).resolve(); p = prepare(run); job = run / JOB; recovery = job / 'recovery'
    if (recovery / 'launch.json').exists():
        raise ValueError('Recovery already launched; reconcile without a second resume')
    if base.sha(base.inside(job, p['session_path'])) != p['before_session_sha256']:
        raise ValueError('Original session changed before resume')
    base.save(recovery / 'launch.json', {'status': 'launched', 'started_at': time.time(),
                                       'policy_sha256': base.sha(run / 'recovery-policy.json')})
    cmd = ['prime-agent', '--offline', '--provider', 'openai-codex', '--no-extensions', '--no-skills',
           '--no-prompt-templates', '--no-context-files', '--tools', 'ipython', '--session-dir',
           str(job / 'sessions'), '--resume', str(base.inside(job,p['session_path'])), '-p']
    start = time.monotonic()
    with (recovery / 'stdout.txt').open('w') as out, (recovery / 'stderr.txt').open('w') as err:
        try:
            result = subprocess.run(cmd, input=CONTINUATION, text=True, stdout=out, stderr=err, cwd=job, timeout=600)
        except subprocess.TimeoutExpired:
            base.save(recovery / 'execution.json', {'status': 'launch_uncertain', 'elapsed_seconds': time.monotonic()-start})
            raise ValueError('Recovery timed out; no further automatic resume permitted')
    execution = {'status': 'returned', 'exit_code': result.returncode, 'elapsed_seconds': time.monotonic()-start,
                 'policy_sha256': base.sha(run / 'recovery-policy.json')}
    # Persist the real process outcome even if session validation subsequently fails.
    base.save(recovery / 'execution.json', execution)
    if result.returncode:
        raise ValueError('Recovery process failed; inspect retained recovery stderr')
    receipt = recovered_session(run)
    base.save(recovery / 'session-receipt.json', receipt)
    content = base.parse_response((recovery / 'stdout.txt').read_text())
    case = base.read(run / 'case.json'); base.validate_content('extractor', content, case, {})
    base.save(job / 'output.json', {'request_sha256': base.digest(base.read(job/'request.json')), 'content': content})
    verify_recovered_job(job, 'extractor', case, {})


def verify_recovered_job(job, role, case, dependencies):
    job = Path(job).resolve(); run = job.parent; p = policy(run); recovery = job / 'recovery'
    if job.name != JOB or role != 'extractor' or dependencies:
        raise ValueError('Recovery scope differs from approved initial extractor')
    request = base.read(job/'request.json'); output = base.read(job/'output.json')
    if request.get('role') != role or request.get('revision') != 0 or request.get('case_sha256') != base.digest(case) or request.get('dependencies') != {}:
        raise ValueError('Recovered request binding mismatch')
    if request.get('prompt_sha256') != base.sha(job/'prompt.txt') or output.get('request_sha256') != base.digest(request):
        raise ValueError('Recovered output binding mismatch')
    ex = base.read(recovery/'execution.json'); launch = base.read(recovery/'launch.json')
    ph = base.sha(run/'recovery-policy.json')
    if ex.get('status') != 'returned' or ex.get('exit_code') != 0 or ex.get('policy_sha256') != ph or launch.get('policy_sha256') != ph:
        raise ValueError('Recovery needs actual successful execution bound to policy')
    receipt = recovered_session(run)
    if base.read(recovery/'session-receipt.json') != receipt:
        raise ValueError('Recovered session receipt changed')
    if base.parse_response((recovery/'stdout.txt').read_text()) != output.get('content'):
        raise ValueError('Recovered output differs from runtime response')
    base.validate_content(role, output['content'], case, dependencies)
    return receipt['id']


@contextmanager
def adapter(run):
    run = Path(run).resolve(); policy(run); original = base.verify_job
    def scoped(job, role, case, dependencies):
        if Path(job).resolve() == run / JOB:
            return verify_recovered_job(job, role, case, dependencies)
        return original(job, role, case, dependencies)
    base.verify_job = scoped
    try:
        yield
    finally:
        base.verify_job = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare','recover','continue','verify'])
    parser.add_argument('--output', required=True); parser.add_argument('--case')
    args = parser.parse_args()
    if args.command == 'prepare': prepare(args.output)
    elif args.command == 'recover': recover(args.output)
    else:
        with adapter(args.output):
            if args.command == 'verify': print(json.dumps(base.verify(args.output),indent=2))
            else:
                if not args.case: parser.error('continue requires original --case path')
                base.execute(args.case,args.output)


if __name__ == '__main__': main()
