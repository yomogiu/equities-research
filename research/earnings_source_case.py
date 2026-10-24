"""Frozen source-case storage and validation, independent of report orchestration.

Existing case digests and serialization are preserved for historical source bindings.
"""
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if path.exists() and path.read_text() != body:
        raise ValueError('Refusing to overwrite immutable artifact: ' + str(path))
    path.write_text(body)

def validate_case(case):
    if case.get('schema_version') != 1 or case.get('scope') != 'one_packet_experiment':
        raise ValueError('Explicit bounded experimental case required')
    if not case.get('authorization') or not case.get('sources'):
        raise ValueError('Sources and authorization required')
    for item in case['sources'] + case.get('artifacts', []):
        if sha(item['path']) != item['sha256']:
            raise ValueError('Frozen input changed: ' + item['path'])
    frozen = {str(Path(i['path']).resolve()) for i in case['sources'] + case.get('artifacts', [])}
    for key in ('financial_path','transcript_index_path','transcript_path'):
        if str(Path(case[key]).resolve()) not in frozen:
            raise ValueError('Role input not frozen: '+key)
    if case.get('writing_standard_path') and str(Path(case['writing_standard_path']).resolve()) not in frozen:
        raise ValueError('Writing standard is not frozen')
    kinds = {s['kind'] for s in case['sources']}
    if 'transcript' not in kinds or 'filing' not in kinds:
        raise ValueError('Transcript-led case requires transcript and filing')
