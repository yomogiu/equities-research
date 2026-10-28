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
    release_case=False
    if 'filing' not in kinds and case.get('source_mode') in ('trading_update_release','financial_report') and 'release' in kinds:
        qualification=case.get('qualification_path','')
        if str(Path(qualification).resolve()) not in frozen:raise ValueError('Financial-release qualification not frozen')
        q=read(qualification)
        releases={(s['document_id'],s['sha256']) for s in case['sources'] if s['kind']=='release' and s['representation']=='raw'}
        qualified={(d['document_id'],d['raw_sha256']) for d in q.get('documents',[]) if d['kind']=='release'}
        coverage=(case['source_mode']=='trading_update_release' and q.get('event',{}).get('kind')=='trading_update' and q.get('completeness')=='limited_trading_update') or (case['source_mode']=='financial_report' and q.get('completeness')=='financial_statements_present')
        release_case=(coverage
                      and q.get('issuer_id')==case.get('issuer_id') and q.get('period')==case.get('period')
                      and bool(q.get('source_gaps')) and bool(releases) and releases==qualified)
    if case.get('source_mode')=='report_only':
        qpath=str(Path(case.get('qualification_path','')).resolve())
        if qpath not in frozen:raise ValueError('Report-only qualification not frozen')
        q=read(qpath);index=read(case['transcript_index_path'])
        reports={(s['document_id'],s['sha256']) for s in case['sources'] if s['kind']=='filing' and s['representation']=='raw'}
        qualified={(d['document_id'],d['raw_sha256']) for d in q.get('documents',[])}
        gap_sources=[s for s in case['sources'] if s['kind']=='source_gap' and s['path']==case['transcript_path']]
        if (q.get('source_mode')!='report_only' or q.get('issuer_id')!=case['issuer_id'] or q.get('period')!=case['period']
            or q.get('completeness')!='financial_statements_present' or not q.get('source_gaps') or not reports or reports!=qualified
            or 'transcript' in kinds or len(gap_sources)!=1 or Path(case['transcript_path']).read_text()!=''
            or any(index.get(k) for k in ('sections','turns','exchanges')) or index.get('coverage',{}).get('status')!='unavailable'):
            raise ValueError('Explicit report-only financial binding and absent call required')
        return
    if 'transcript' not in kinds or ('filing' not in kinds and not release_case):
        raise ValueError('Transcript-led case requires transcript and filing')
