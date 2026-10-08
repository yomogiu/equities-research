"""Lossless source-location completion for an authenticated saved proposal.

Only an exactly empty passage list may be completed. Original explicit citations
select whole canonical scopes; this is navigation, never evidence adjudication.
"""
from __future__ import annotations

import copy

from research import earnings_experiment as base
from research import earnings_mixed_pipeline as legacy

VERSION = 'deterministic-corrections-cited-passages-v1'
MANIFEST_VERSION = 'complete-explicit-cited-scopes-v1'


def resolve(original, bundle, catalog, original_output_sha256):
    """Return a derived plan and exact delta manifest without changing inputs."""
    if (not isinstance(catalog, dict) or not isinstance(catalog.get('passages'), list)
            or not catalog['passages']
            or catalog.get('case_sha256') != bundle['manifest']['case_sha256']):
        raise ValueError('Cited-passage resolution requires the complete original catalog')
    allowed = legacy.ids_for(bundle)
    by_scope = {}
    known = set()
    for row in catalog['passages']:
        if (not isinstance(row, dict) or not isinstance(row.get('passage_id'), str)
                or not row['passage_id'] or row['passage_id'] in known
                or row.get('scope_id') not in allowed):
            raise ValueError('Invalid or duplicate canonical passage catalog entry')
        known.add(row['passage_id'])
        by_scope.setdefault(row['scope_id'], []).append(row['passage_id'])
    if not isinstance(original, dict) or not isinstance(original.get('operations'), list):
        raise ValueError('Saved proposal requires an operations list')
    effective = copy.deepcopy(original)
    changes = []
    for op in effective['operations']:
        if not isinstance(op, dict):
            raise ValueError('Saved proposal operation must be an object')
        legacy.check_ids(op.get('citations'), allowed, 'original explicit citations')
        if op.get('passage_ids') != []:
            # Invalid nonempty values, missing fields and malformed containers
            # must never be guessed, dropped or treated as an empty selection.
            legacy.check_ids(op.get('passage_ids'), known, 'original passages')
            continue
        if any(scope not in by_scope for scope in op['citations']):
            raise ValueError('Every explicit citation must have exact catalog passages')
        scopes = set(op['citations'])
        selected = [row['passage_id'] for row in catalog['passages'] if row['scope_id'] in scopes]
        op['passage_ids'] = selected
        changes.append({'operation_id': op.get('id'), 'citations': copy.deepcopy(op['citations']),
                        'original_passage_ids': [], 'resolved_passage_ids': selected})
    if not changes:
        raise ValueError('No exactly empty passage list to resolve')
    manifest = {'version': MANIFEST_VERSION, 'original_output_sha256': original_output_sha256,
                'original_plan_sha256': base.digest(original),
                'snapshot_sha256': original.get('snapshot_sha256'),
                'catalog_sha256': base.digest(catalog), 'resolved_plan_sha256': base.digest(effective),
                'operations': changes}
    return effective, manifest
