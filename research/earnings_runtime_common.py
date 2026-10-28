"""Shared immutable artifacts and signed-in runtime primitives.

No report controller, role workflow or legacy runner is imported here. JSON
serialization, path checks, exclusive writes and exact model selection preserve
the existing receipt contract byte for byte.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil

PROVIDER = 'openai-codex'
ALLOWED = {'gpt-6-luna': {'max'}, 'gpt-5.6-luna': {'xhigh', 'max'}, 'gpt-6.1-sol': {'low', 'medium'}, 'gpt-6.1-terra': {'high'}}


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


def _validate_selection(model, effort):
    if model not in ALLOWED or effort not in ALLOWED[model]:
        raise ValueError('Unauthorized exact model/effort selection')


def immutable_text(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != value:
        raise ValueError('Refusing to overwrite frozen artifact: '+str(path))
    path.write_text(value)
