"""Add private, source-bound audit findings to a correction handoff.

An audit is fallible reviewer input. Its hash proves provenance, never that its
claims were independently accepted; normal proposal and review still apply.
"""
from __future__ import annotations
import copy
import re
from pathlib import Path
from research import earnings_experiment as base
from research import earnings_mixed_pipeline as legacy
from research import earnings_report_repair as repair

VERSION = 'deterministic-corrections-regression-v1'
DEFAULT_TOKEN_CEILING = 600000


def fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(label + ': exact fields required')


def read(path, source_protocol, bundle, catalog):
    """Validate all supplemental input before creating a correction directory."""
    path = Path(path).resolve()
    value = base.read(path)
    fields(value, ('version', 'case_sha256', 'evidence_sha256', 'audit', 'findings'),
           'Regression findings')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Regression findings version must be 1')
    for key, source in (('case_sha256', 'case_path'), ('evidence_sha256', 'evidence_manifest')):
        if (value[key] != source_protocol[key] or
                base.sha(source_protocol[source]) != source_protocol[key]):
            raise ValueError('Regression findings case/evidence binding changed')
    if catalog['case_sha256'] != value['case_sha256'] or bundle['manifest']['case_sha256'] != value['case_sha256']:
        raise ValueError('Regression findings belong to a different frozen bundle')
    fields(value['audit'], ('path', 'sha256'), 'Regression audit')
    audit = value['audit']
    if not isinstance(audit['path'], str) or not audit['path'].strip():
        raise ValueError('Regression audit requires an absolute file path')
    audit_path = Path(audit['path'])
    if not audit_path.is_absolute() or not audit_path.is_file():
        raise ValueError('Regression audit requires an absolute file path')
    audit_path = audit_path.resolve()
    if (not isinstance(audit['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', audit['sha256'])
            or base.sha(audit_path) != audit['sha256']):
        raise ValueError('Regression audit hash changed')
    findings = value['findings']
    if not isinstance(findings, list) or not 1 <= len(findings) <= 12:
        raise ValueError('Regression findings requires one to twelve findings')
    seen = set()
    for finding in findings:
        fields(finding, ('target', 'passage', 'reason', 'required_change', 'citations', 'passage_ids'),
               'Regression finding')
        if finding['target'] not in ('financial', 'retrieval', 'analysis', 'formatter'):
            raise ValueError('Unknown regression finding target')
        for key in ('passage', 'reason', 'required_change'):
            legacy.check_text(finding[key], 'regression finding ' + key)
            if len(finding[key]) > 4000:
                raise ValueError('Regression finding text exceeds 4000 characters')
        legacy.check_ids(finding['citations'], legacy.ids_for(bundle), 'regression citations')
        legacy.check_ids(finding['passage_ids'], {p['passage_id'] for p in catalog['passages']},
                         'regression original passages')
        for key in ('citations', 'passage_ids'):
            if len(finding[key]) > 64:
                raise ValueError('Regression finding evidence list exceeds 64 IDs')
        fid = repair.finding_id(finding)
        if fid in seen:
            raise ValueError('Duplicate regression finding')
        seen.add(fid)
    bindings = {str(path): base.sha(path), str(audit_path): audit['sha256']}
    return copy.deepcopy(findings), bindings


def append(snapshot, findings):
    """Preserve every original finding and add stable, ordinary pending IDs."""
    result = copy.deepcopy(snapshot)
    existing = {f['id']: f['finding'] for f in result['findings']}
    for finding in findings:
        fid = repair.finding_id(finding)
        if fid in existing:
            if existing[fid] != finding:
                raise ValueError('Regression finding ID collision')
            continue
        result['findings'].append({'id': fid, 'finding': copy.deepcopy(finding)})
        existing[fid] = finding
    return result


def budget(protocol, exported, seed_protocol):
    """A supplemental handoff inherits usage and may only reduce ceilings."""
    for field, source in (('prior_rounds', 'used_rounds'), ('inherited_tokens', 'spent_tokens')):
        if (type(protocol.get(field)) is not int or protocol[field] != exported[source]
                or protocol[field] < 0):
            raise ValueError('Regression findings inherited budget changed: ' + field)
    rounds = protocol.get('max_rounds')
    tokens = protocol.get('max_tokens')
    ceiling = seed_protocol.get('max_tokens', DEFAULT_TOKEN_CEILING)
    if type(rounds) is not int or not 1 <= rounds <= 2 - exported['used_rounds']:
        raise ValueError('Regression findings correction round budget expanded')
    if tokens is not None and (type(tokens) is not int or tokens <= 0 or (ceiling is not None and tokens > ceiling)):
        raise ValueError('Regression findings token budget expanded')


def verify(protocol, initial, bundle, catalog, exported, seed_protocol):
    """Replay additions instead of trusting the mutable initial snapshot hash."""
    record = protocol.get('regression_findings')
    fields(record, ('path', 'sha256'), 'Regression findings binding')
    findings, bindings = read(record['path'], protocol['source_protocol'], bundle, catalog)
    if bindings.get(record['path']) != record['sha256'] or any(
            protocol['source_bindings'].get(path) != digest for path, digest in bindings.items()):
        raise ValueError('Regression findings source binding changed')
    if protocol.get('imported_proposal') or protocol.get('new_experiment'):
        raise ValueError('Regression findings cannot reuse a proposal or reset the experiment')
    budget(protocol, exported, seed_protocol)
    if append(exported['snapshot'], findings) != initial:
        raise ValueError('Regression findings initial snapshot differs from source plus additions')
