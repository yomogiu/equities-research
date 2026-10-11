"""Source-derived presentation and batched structural checks; no model calls.

Never repair unknown references, attribution or substantive prose by guessing.
The authenticated author artifacts remain unchanged. A new frozen policy opts in.
"""
import copy
from . import earnings_report_repair as repair
from . import earnings_passage_pipeline as pipe
from . import earnings_signals as signals
from . import earnings_mixed_runner as runner

POLICY = 'mechanical-report-review-v2'


def formatting(financial, bundle):
    """Compile display identity and citations from already selected exact facts."""
    rows = {}
    for key, entry in repair.row_catalog(financial, bundle).items():
        row = entry['row']
        rows[key] = {'label': row['metric'], 'dimensions': row['dimensions'],
                     'citations': sorted({fid for cell in row['cells'] for fid in cell['fact_ids']})}
    result = {'rows': rows, 'basis': {'text': '', 'citations': []}}
    # No inferred GAAP, percentage, fiscal year, entity or accounting basis.
    repair.validate_format(result, financial, bundle)
    return result


def check(state, bundle, catalog, pack=None):
    """Collect every structural defect before sending a candidate for review."""
    issues = []
    def inspect(stage, callback):
        try:
            callback()
        except (ValueError, KeyError, TypeError) as error:
            issues.append({'stage': stage, 'reason': str(error)})
    for role in ('financial', 'retrieval', 'analysis'):
        inspect(role, lambda role=role: pipe.validate(role, state['artifacts'][role], bundle, catalog))
    inspect('format', lambda: repair.validate_format(state['format'], state['artifacts']['financial'], bundle))
    if pack is not None:
        inspect('signals', lambda: signals.validate(pack, state, bundle, catalog))
    return {'version': POLICY, 'state_sha256': runner.digest(state),
            'catalog_sha256': runner.digest(catalog), 'source_bundle_sha256': runner.digest(bundle),
            'format_sha256': runner.digest(state.get('format')), 'issues': issues,
            'status': 'blocked' if issues else 'ready_for_independent_review'}


def presentation_only(before, after):
    """Only moving an unchanged basis note is safe without reopening claims.

    Labels, citations, folds, summaries, source rows and hidden rows can change
    meaning. They deliberately retain conservative dependency invalidation.
    """
    left, right = copy.deepcopy(before), copy.deepcopy(after)
    if 'layout' not in left or 'layout' not in right:
        return False
    old = left['layout'].pop('basis_position', None)
    new = right['layout'].pop('basis_position', None)
    return old != new and left == right and old in ('before_tables', 'after_tables') and new in ('before_tables', 'after_tables')
