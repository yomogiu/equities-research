"""Compile exact reviewer edits into an unaccepted, source-validated candidate.

The caller authenticates the review job and its original candidate first. This
module copies typed proposals, never interprets finding prose or invents a fix.
Incomplete or conflicting proposals fall back to the ordinary correction role.
Every successful batch still consumes a correction round and needs a fresh full
independent review; it conveys no acceptance from the proposing reviewer.
"""
from __future__ import annotations

import copy
import re

from . import earnings_batch_review as batch
from . import earnings_mechanical_preflight as mechanical
from . import earnings_mixed_runner as base

VERSION = 'exact-reviewer-candidate-v1'


def _get(value, path):
    for key in path:
        value = value[key]
    return value


def _set(value, path, replacement):
    parent = _get(value, path[:-1])
    parent[path[-1]] = replacement


def _proposed_value(original, repairs):
    """Apply disjoint spans against original text, independent of edit order."""
    grouped = {}
    for repair in repairs:
        path = tuple(repair['field_path'])
        for other in grouped:
            if path != other and (path[:len(other)] == other or other[:len(path)] == path):
                raise ValueError('Overlapping repair paths')
        grouped.setdefault(path, []).append(repair)
    value = copy.deepcopy(original)
    for path, edits in grouped.items():
        before = _get(original, path)
        if isinstance(before, list):
            if len(edits) != 1:
                raise ValueError('Conflicting quote selections')
            # The native adjudicator already verified exact ordered deletion.
            _set(value, path, copy.deepcopy(edits[0]['after']))
            continue
        spans = []
        for edit in edits:
            if not edit['before']:
                if before != '' or len(edits) != 1:
                    raise ValueError('Ambiguous empty-field repair')
                spans.append((0, 0, edit['after']))
            else:
                start = before.index(edit['before'])
                spans.append((start, start + len(edit['before']), edit['after']))
        spans.sort(key=lambda span: span[:2])
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise ValueError('Overlapping exact text repairs')
        replacement = before
        for start, end, after in reversed(spans):
            replacement = replacement[:start] + after + replacement[end:]
        _set(value, path, replacement)
    return value


def build(items, review, bundle, catalog, *, bound_batch_sha256,
          bound_review_sha256, source_review_sha256):
    """Return {plan, items, derivation}, or None when author correction is needed.

    ``review`` is the native {batch_sha256, decisions, reopen} projection after
    complete review/schema/rubric validation. Both bound digests must come from
    the authenticated job, not from untrusted proposed edits; source_review_sha256
    is that job's verified output.json hash. Stale bindings and invalid reviews
    raise, while valid but unsupported or incomplete repair proposals return None.
    No files, provider calls, budgets, round counts or acceptance are changed.
    """
    batch.require(bound_batch_sha256 == base.digest(items), 'Exact authenticated candidate required')
    batch.require(bound_review_sha256 == base.digest(review), 'Exact authenticated review required')
    batch.require(isinstance(source_review_sha256, str) and
                  re.fullmatch(r'[0-9a-f]{64}', source_review_sha256), 'Verified review output hash required')
    _, findings = batch.adjudicate(items, set(items), {}, review, catalog,
                                   source_review_sha256, batch.EDITORIAL_VERSION)
    revised = [decision for decision in review['decisions'] if decision['verdict'] == 'revise']
    if not revised or review['reopen']:
        return None
    # Frozen extraction artifacts are deliberately outside this prose fast path.
    # Classification/source address changes need the ordinary authored plan.
    if any(not decision['editorial_repairs'] or decision['unit_id'] in ('financial', 'retrieval')
           for decision in revised):
        return None
    try:
        changes = []
        for decision in sorted(revised, key=lambda row: row['unit_id']):
            key = decision['unit_id']
            value = _proposed_value(items[key]['value'], decision['editorial_repairs'])
            changes.append({'unit_id': key, 'before_sha256': base.digest(items[key]['value']),
                            'value': value, 'reason': decision['reason']})
        plan = {'before_sha256': base.digest(items), 'changes': changes}
        candidate, pending = batch.apply(items, plan, batch.EDITORIAL_VERSION)
        state, pack = batch.validate(candidate, bundle, catalog)
        preflight = mechanical.check(state, bundle, catalog, pack)
        batch.require(preflight['status'] == 'ready_for_independent_review', 'Candidate failed preflight')
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    derivation = {'version': VERSION, 'status': 'candidate_pending_fresh_full_review',
                  'before_sha256': base.digest(items), 'after_sha256': base.digest(candidate),
                  'review_payload_sha256': base.digest(review),
                  'source_review_sha256': source_review_sha256,
                  'plan_sha256': base.digest(plan), 'provider_calls': 0,
                  'direct_finding_units': sorted(row['unit_id'] for row in revised),
                  'dependent_finding_units': sorted(set(findings) - {row['unit_id'] for row in revised}),
                  'invalidated_units': sorted(pending),
                  'required_review_units': sorted(candidate),
                  'preflight': preflight}
    return {'plan': plan, 'items': candidate, 'derivation': derivation}
