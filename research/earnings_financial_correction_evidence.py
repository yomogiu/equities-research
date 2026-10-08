"""Explicit saved-plan navigation to original financial evidence, never approval.

Financial source slices are typed separately from transcript/document passages.
Only source-cited display rows can acquire this evidence through derivation.
"""
from __future__ import annotations
import copy
from . import earnings_experiment as base
from . import earnings_compact_evidence as evidence
from . import earnings_cited_passages as cited
from . import earnings_mixed_pipeline as legacy

VERSION = 'deterministic-corrections-financial-evidence-v1'
KEY = 'financial_correction_evidence'


def entries(bundle, ids):
    facts = {o['id'] for o in bundle['financial']['observations']}
    legacy.check_ids(ids, facts, 'financial source IDs')
    result = {}
    for source in evidence.source_slices(bundle['manifest'], ids):
        if 'observation' not in source or not source['spans']:
            raise ValueError('Original financial observation and source spans required')
        result['FE-' + base.digest(source)] = {'kind': 'original_financial_observation', 'source': source}
    return result


def validate(value, bundle, catalog):
    """Authenticate typed evidence on every use, even for reviewer decisions."""
    bound = catalog.get(KEY)
    if not isinstance(bound, dict) or not bound:
        raise ValueError('Explicit financial evidence derivation required')
    ids = value.get('financial_evidence_ids')
    legacy.check_ids(ids, set(bound), 'typed financial evidence IDs')
    sources = [bound[i]['source']['id'] for i in ids]
    if value.get('passage_ids') != [] or set(value['citations']) != set(sources):
        raise ValueError('Financial-only evidence requires exact financial citations and empty passage IDs')
    expected = entries(bundle, sources)
    if {i: bound[i] for i in ids} != expected:
        raise ValueError('Financial source evidence changed')
    return sources


def target(snapshot, operation, bundle, catalog):
    from . import earnings_corrections as corrections
    from . import earnings_report_repair as repair
    targets = corrections.registry(snapshot, bundle)['targets']
    t = targets.get(operation.get('target_id'), {})
    if operation.get('op') != 'set_display' or t.get('kind') != 'row':
        raise ValueError('Financial-only correction evidence is limited to display rows')
    sources = validate(operation, bundle, catalog)
    row = repair.row_catalog(snapshot['artifacts']['financial'], bundle)[t['path'][-1]]
    members = {fid for cell in row['row']['cells'] for fid in cell['fact_ids']}
    if not set(sources) <= members:
        raise ValueError('Financial citations do not belong to the target display row')
    return {'target_id': operation['target_id'], 'target_sha256': t['expected_sha256'],
            'row_sha256': base.digest(row), 'row': row, 'source_ids': sources}


def resolve(original, snapshot, bundle, catalog, output_sha256):
    """Derive only empty navigation fields; return complete replayable provenance."""
    clean = {k: v for k, v in catalog.items() if k != KEY}
    effective = copy.deepcopy(original)
    facts = {o['id'] for o in bundle['financial']['observations']}
    financial_ops, ordinary = [], []
    for op in effective['operations']:
        if 'financial_evidence_ids' in op:
            raise ValueError('Original author proposal must be unchanged legacy evidence schema')
        legacy.check_ids(op.get('citations'), legacy.ids_for(bundle), 'original citations')
        if op.get('passage_ids') == [] and set(op['citations']) <= facts:
            financial_ops.append(op)
        else:
            ordinary.append(op)
    if not financial_ops:
        raise ValueError('No empty financial-only display evidence to resolve')
    ordinary_changes = []
    if any(op.get('passage_ids') == [] for op in ordinary):
        partial, receipt = cited.resolve({**original, 'operations': ordinary}, bundle, clean, output_sha256)
        replacements = {op['id']: op for op in partial['operations']}
        effective['operations'] = [replacements.get(op['id'], op) for op in effective['operations']]
        ordinary_changes = receipt['operations']
    ids = list(dict.fromkeys(fid for op in financial_ops for fid in op['citations']))
    bound = entries(bundle, ids)
    typed_catalog = {**clean, KEY: bound}
    by_source = {value['source']['id']: key for key, value in bound.items()}
    changes = []
    for op in financial_ops:
        op['financial_evidence_ids'] = [by_source[fid] for fid in op['citations']]
        correspondence = target(snapshot, op, bundle, typed_catalog)
        changes.append({'operation_id': op['id'], 'original_passage_ids': [],
                        'financial_evidence_ids': op['financial_evidence_ids'], **correspondence})
    manifest = {'version': VERSION, 'original_output_sha256': output_sha256,
                'original_plan_sha256': base.digest(original), 'snapshot_sha256': base.digest(snapshot),
                'catalog_sha256': base.digest(clean), 'resolved_plan_sha256': base.digest(effective),
                'financial_evidence': bound, 'operations': changes,
                'ordinary_passage_operations': ordinary_changes}
    catalog[KEY] = copy.deepcopy(bound)
    return effective, manifest
