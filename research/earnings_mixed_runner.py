"""Authenticated, immutable one-prompt Prime sessions for mixed-model experiments.

No tools, inherited instructions, skills, extensions, model fallback or auth exports.
The journal and outgoing payload attest client selection, not server-side weights.
A launch without a verified completed output is intentionally never retried in place.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

VERSION = 'mixed-prime-role-v1'
PROVIDER = 'openai-codex'
ALLOWED = {'gpt-6-luna': {'max'}, 'gpt-5.6-luna': {'xhigh', 'max'}, 'gpt-6.1-sol': {'medium'}}
HELPER = Path(__file__).with_name('earnings_mixed_prime.mjs')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    """Atomic, exclusive creation: interrupted or competing launches cannot replace it."""
    path = Path(path)
    body = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _inside(job, relative):
    path = job / relative
    if not path.resolve().is_relative_to(job.resolve()) or path.is_symlink():
        raise ValueError('Artifact path escapes job')
    return path


def _text(message):
    content = message.get('content')
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError('Invalid message content')
    if any(x.get('type') == 'toolCall' for x in content):
        raise ValueError('Unexpected tool call')
    return ''.join(x['text'] for x in content if x.get('type') == 'text')


def parse_response(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('Role must return a JSON object')
    return value


def session_receipt(job_path, request=None):
    job = Path(job_path).resolve()
    request = request or read(job / 'request.json')
    paths = list((job / 'sessions').rglob('*.jsonl'))
    if len(paths) != 1:
        raise ValueError('Exactly one session required')
    journal = _inside(job, paths[0].relative_to(job))
    entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    heads = [e for e in entries if e.get('type') == 'session']
    if len(heads) != 1 or not heads[0].get('id') or heads[0].get('parentSession'):
        raise ValueError('Fresh unique session identity required')
    if Path(heads[0].get('cwd', '')).resolve() != job:
        raise ValueError('Session directory mismatch')
    models = [e for e in entries if e.get('type') == 'model_change']
    thoughts = [e for e in entries if e.get('type') == 'thinking_level_change']
    if not models or any(e.get('provider') != PROVIDER or e.get('modelId') != request['model'] for e in models):
        raise ValueError('Observed model differs from requested model')
    if not thoughts or any(e.get('thinkingLevel') != request['effort'] for e in thoughts):
        raise ValueError('Observed thinking effort differs')
    if any(e.get('type') in {'compaction', 'branch_summary'} for e in entries):
        raise ValueError('Unexpected context mutation')
    messages = [e['message'] for e in entries if e.get('type') == 'message']
    if len(messages) != 2 or [m.get('role') for m in messages] != ['user', 'assistant']:
        raise ValueError('Exactly one user and assistant message required')
    if _text(messages[0]) != (job / 'prompt.txt').read_text():
        raise ValueError('Journal prompt differs')
    final = messages[-1]
    if final.get('provider') != PROVIDER or final.get('model') != request['model'] or final.get('api') != 'openai-codex-responses':
        raise ValueError('Assistant model identity differs')
    if final.get('stopReason') != 'stop':
        raise ValueError('Incomplete, timed out, or output-limited assistant response')
    if _text(final) != (job / 'stdout.txt').read_text():
        raise ValueError('Journal output differs')
    usage = final.get('usage', {})
    for key in ('input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens'):
        if type(usage.get(key)) is not int or usage[key] < 0:
            raise ValueError('Measured token usage required')
    if usage['totalTokens'] != sum(usage[k] for k in ('input', 'output', 'cacheRead', 'cacheWrite')):
        raise ValueError('Token accounting mismatch')
    return {'id': heads[0]['id'], 'path': str(journal.relative_to(job)), 'sha256': sha(journal),
            'model': request['model'], 'effort': request['effort'], 'provider': PROVIDER,
            'usage': {k: usage[k] for k in ('input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens')},
            'input_semantics': 'uncached input; cacheRead and cacheWrite are separate'}


def _runtime_paths():
    executable = shutil.which('prime-agent')
    if not executable:
        raise RuntimeError('Installed Prime Agent is required')
    launcher = Path(executable).absolute()
    resolved = launcher.resolve()
    # A standalone CLI update can replace an npm bin symlink while leaving the
    # installed SDK beside that bin directory. Inspect only these installation
    # locations; never search user configuration or authentication directories.
    candidates = [resolved.parents[2]] if len(resolved.parents) > 2 else []
    candidates.append(launcher.parent.parent / 'lib/node_modules/prime-agent')
    for sdk in dict.fromkeys(candidates):
        try:
            package = read(sdk / 'package.json')
        except (OSError, ValueError):
            continue
        if package.get('name') != 'prime-agent' or not all((sdk / relative).is_file() for relative in (
                'dist/index.js', 'node_modules/@earendil-works/pi-ai/dist/oauth.js')):
            continue
        node = sdk.parents[2] / 'bin/node' if len(sdk.parents) > 2 else Path()
        if not node.is_file():
            node = Path(shutil.which('node') or '')
        if node.is_file():
            return node, sdk.resolve()
    raise RuntimeError('Prime SDK or Node runtime unavailable; the standalone CLI also requires an installed Prime SDK')


def verify_job(job_path):
    """Recheck every persisted binding before treating a completed job as reusable."""
    job = Path(job_path).resolve()
    names = ('request.json', 'launch.json', 'execution.json', 'output.json', 'prompt.txt',
             'stdout.txt', 'runtime-start.json', 'runtime-finish.json', 'wire.json')
    for name in names:
        _inside(job, name)
    request, launch, execution, output = [read(job / name) for name in names[:4]]
    _validate_selection(request['model'], request['effort'])
    if request.get('version') != VERSION or request.get('job_path') != str(job):
        raise ValueError('Runner or job identity mismatch')
    if request.get('helper_sha256') != sha(HELPER) or request.get('runner_sha256') != sha(__file__):
        raise ValueError('Runner code changed')
    request_hash = digest(request)
    if launch.get('request_sha256') != request_hash or execution.get('request_sha256') != request_hash or output.get('request_sha256') != request_hash:
        raise ValueError('Request binding mismatch')
    if request.get('prompt_sha256') != sha(job / 'prompt.txt'):
        raise ValueError('Prompt changed')
    if execution.get('status') != 'completed' or execution.get('exit_code') != 0 or execution.get('launch_sha256') != sha(job / 'launch.json'):
        raise ValueError('Execution not successfully completed')
    if output.get('execution_sha256') != sha(job / 'execution.json'):
        raise ValueError('Execution changed')
    for name, expected in execution['artifact_sha256'].items():
        if sha(_inside(job, name)) != expected:
            raise ValueError('Execution artifact changed: ' + name)
    if set(execution['artifact_sha256']) != {'runtime-start.json', 'runtime-finish.json', 'wire.json', 'stdout.txt'}:
        raise ValueError('Incomplete runtime bindings')
    session = session_receipt(job, request)
    if session != execution.get('session'):
        raise ValueError('Session evidence changed')
    start, finish, wire = [read(job / name) for name in ('runtime-start.json', 'runtime-finish.json', 'wire.json')]
    if start.get('launch_id') != launch.get('id') or not launch.get('id'):
        raise ValueError('Launch identity mismatch')
    for runtime in (start, finish):
        if runtime.get('session_id') != session['id'] or runtime.get('model') != request['model'] or runtime.get('effort') != request['effort'] or runtime.get('oauth') is not True:
            raise ValueError('Runtime identity or OAuth mismatch')
    if len(wire) != 1 or wire[0] != {'model': request['model'], 'effort': request['effort'], 'tools': 0}:
        raise ValueError('Exact single no-tool request required')
    content = parse_response((job / 'stdout.txt').read_text())
    if output.get('content') != content:
        raise ValueError('Output content changed')
    return {'content': content, 'receipt': execution, 'output_path': str(job / 'output.json')}


def _validate_selection(model, effort):
    if model not in ALLOWED or effort not in ALLOWED[model]:
        raise ValueError('Unauthorized exact model/effort selection')


def _request(job, prompt, model, effort, bindings, timeout):
    _validate_selection(model, effort)
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(bindings, dict):
        raise ValueError('Prompt and binding dictionary required')
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError('Positive timeout required')
    return {'version': VERSION, 'job_path': str(Path(job).resolve()), 'model': model, 'effort': effort,
            'provider': PROVIDER, 'bindings': bindings, 'timeout_seconds': timeout,
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'helper_sha256': sha(HELPER), 'runner_sha256': sha(__file__)}


def run_role(job_path, prompt, model, effort, bindings, timeout=900):
    """Run once or verify a completed job; return content, receipt, and output_path."""
    job = Path(job_path).resolve()
    request = _request(job, prompt, model, effort, bindings, timeout)
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (job / 'request.json').exists():
        if read(job / 'request.json') != request:
            raise ValueError('Immutable role request differs')
        if (job / 'output.json').exists():
            return verify_job(job)
        raise RuntimeError('Existing incomplete role is uncertain; refusing duplicate launch')
    if any(job.iterdir()):
        raise RuntimeError('New role directory must be empty')
    node, sdk = _runtime_paths()
    save(job / 'request.json', request)
    with (job / 'prompt.txt').open('x') as handle:
        os.chmod(job / 'prompt.txt', 0o600)
        handle.write(prompt)
    launch = {'id': str(uuid.uuid4()), 'request_sha256': digest(request),
              'started_at': datetime.now(timezone.utc).isoformat()}
    save(job / 'launch.json', launch)
    started = time.monotonic()
    process = subprocess.Popen([str(node), str(HELPER), str(sdk), str(job)],
                               cwd=job, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    status = 'returned'
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        status = 'timeout'
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = process.returncode
    execution = {'request_sha256': digest(request), 'launch_sha256': sha(job / 'launch.json'),
                 'started_at': launch['started_at'], 'finished_at': datetime.now(timezone.utc).isoformat(),
                 'elapsed_seconds': round(time.monotonic() - started, 6),
                 'exit_code': code, 'status': status}
    if code != 0 or status == 'timeout':
        save(job / 'execution.json', execution)
        raise RuntimeError('Prime role failed or timed out; duplicate launch blocked')
    try:
        execution['session'] = session_receipt(job, request)
        execution['artifact_sha256'] = {name: sha(job / name) for name in
            ('runtime-start.json', 'runtime-finish.json', 'wire.json', 'stdout.txt')}
        content = parse_response((job / 'stdout.txt').read_text())
    except (ValueError, KeyError, OSError):
        execution['status'] = 'invalid_output'
        save(job / 'execution.json', execution)
        raise
    execution['status'] = 'completed'
    save(job / 'execution.json', execution)
    save(job / 'output.json', {'request_sha256': digest(request),
         'execution_sha256': sha(job / 'execution.json'), 'content': content})
    return verify_job(job)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Check registration and OAuth availability; no model call')
    parser.add_argument('--model', choices=ALLOWED, default='gpt-6.1-sol')
    args = parser.parse_args()
    if not args.probe:
        parser.error('Use run_role from the bounded experiment coordinator')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='mixed-prime-probe-') as directory:
        save(Path(directory) / 'request.json', {'model': args.model})
        node, sdk = _runtime_paths()
        result = subprocess.run([str(node), str(HELPER), str(sdk), directory, '--probe'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            failure = Path(directory) / 'runtime-failure.json'
            stage = read(failure).get('stage') if failure.is_file() else None
            if stage == 'auth_storage':
                raise RuntimeError('Prime credential storage unavailable; allow its normal local auth-store lock')
            raise RuntimeError('Prime registration probe failed')
        print(json.dumps(json.loads(result.stdout), indent=2))


if __name__ == '__main__':
    main()
