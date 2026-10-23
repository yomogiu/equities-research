"""Mechanical evidence navigation, without a model-written retrieval summary.

This prepares source locators, not substantive extraction or source inspection.
The analyst and fresh reviewer still inspect the complete call and support. A
missing or ambiguous Q&A boundary retains the existing model retrieval path.
Corrupt source bindings fail closed rather than becoming a fallback candidate.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from . import earnings_compact_evidence as evidence
from . import earnings_experiment as base
from . import earnings_file_context as context
from . import earnings_passages as passages
from . import earnings_qa_grounding as grounding

VERSION = 'deterministic-source-navigation-v1'
QUERY = 'guidance EBITDA cash debt capital expenditure'
NOTICE = ('Mechanical source navigation only; no substantive extraction, semantic '
          'summary, relevance judgment or completed source inspection. The author '
          'and fresh independent reviewer must inspect the complete original call '
          'and selected filing excerpts. All original source inventory remains '
          'available for further checks. Quote candidates are navigation examples, '
          'not editorial recommendations or an exhaustive set of usable passages.')


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _replay_grounding(bundle, catalog):
    index = bundle['qa_grounding']
    result = grounding.build(bundle, catalog, version=index['version'])
    if bundle.get('operator_review_binding'):
        from .earnings_reviewed_operator import apply
        result, _ = apply(bundle['operator_review_binding'], result, bundle, catalog)
    if bundle.get('batch_attribution_review_binding'):
        from .earnings_reviewed_attribution_batch import apply
        result, _ = apply(bundle['batch_attribution_review_binding'], result, bundle, catalog)
    _require(result == index, 'Source navigation grounding differs from replayed source membership')
    return result


def build(bundle, catalog):
    """Return a source-bound ready handoff or explicit eligibility fallback.

    The returned receipt accounts for zero model tokens, not zero analysis work.
    The caller must freeze/recompute this result and must not manufacture model
    coverage receipts or reuse this as evidence of independent review.
    """
    original = evidence.load_bundle(bundle['manifest'])
    for key in ('transcript_index', 'documents'):
        _require(bundle[key] == original[key], 'Source navigation original ' + key + ' changed')
    _require(catalog == passages.catalog(bundle['manifest']), 'Source navigation passage catalog changed')
    receipt = {
        'version': VERSION, 'status': 'fallback_required', 'tokens': 0,
        'source_bindings': {
            'manifest_sha256': base.digest(bundle['manifest']),
            'catalog_sha256': base.digest(catalog),
            'transcript_index_sha256': base.digest(bundle['transcript_index']),
            'grounding_sha256': base.digest(bundle.get('qa_grounding')),
        },
        'reasons': [], 'notice': NOTICE,
    }
    supplied_grounding = bundle.get('qa_grounding')
    if not isinstance(supplied_grounding, dict) or supplied_grounding.get('version') not in grounding.SUPPORTED_VERSIONS:
        receipt['reasons'] = ['Supported source-bound Q&A grounding is required.']
        return receipt
    index = _replay_grounding(bundle, catalog)
    unresolved = [t['id'] for t in index['unassigned_qa_turns']
                  if t['mechanical_disposition'] == 'unresolved']
    if unresolved:
        receipt['reasons'] = ['Substantive unassigned Q&A turns require source attribution: '
                              + ', '.join(unresolved)]
        return receipt
    rows = []
    for group in index['exchanges']:
        disposition = group.get('mechanical_disposition')
        qids = [pid for turn in group['turns']
                if turn['id'] in group['question_turn_ids'] and not turn['courtesy_only']
                for pid in turn['passage_ids']]
        aids = [pid for turn in group['turns']
                if turn['id'] in group['answer_turn_ids'] and not turn['courtesy_only']
                for pid in turn['passage_ids']]
        status = 'bound'
        if disposition in ('courtesy_only', 'reviewed_non_qa'):
            status, qids, aids = disposition, [], []
        elif disposition == 'reviewed_answer_continuation':
            status, qids = 'continued_answer', []
        elif group['flags'] or not qids or not aids:
            receipt['reasons'].append('Q&A membership requires source attribution: '
                                      + group['exchange_id'])
            continue
        rows.append({
            'exchange_id': group['exchange_id'],
            'question': 'Inspect the exact indexed question passages; no question summary was generated.',
            'answer': 'Inspect the exact indexed response passages; no answer or non-answer judgment was generated.',
            'consequence': 'Analytical importance remains for the author and independent reviewer to assess.',
            'question_passage_ids': qids, 'answer_passage_ids': aids,
            'continuation_exchange_ids': [], 'grounding_status': status,
            'grounding_notes': ('Exact source membership only. Disposition: ' + status
                                + '. Original turns and provisional annotations remain available.'),
        })
    if receipt['reasons']:
        return receipt

    # Share the existing deterministic ranking, deduplication and nonoverlap
    # implementation. Calling its pure method creates no inspection log.
    document_ids = [row['id'] for row in bundle['documents']['chunks']]
    records = {row['id']: row for row in evidence.source_slices(bundle['manifest'], document_ids)}
    filing_text, selected = context.Evidence._filing_batch(SimpleNamespace(records=records), QUERY, 4)
    receipt['selection'] = json.loads(filing_text.splitlines()[1])
    if not selected:
        receipt['reasons'] = ['No eligible complete filing excerpts; source access requires review.']
        return receipt

    # One locator per source turn/excerpt first, then further exact locators up
    # to the legacy contract's lower bound. This is navigation, not importance.
    allowed = set(selected) | {t['id'] for t in bundle['transcript_index']['turns']}
    candidates = [p for p in catalog['passages'] if p['scope_id'] in allowed and p['text'].strip()]
    chosen, scopes = [], set()
    for candidate in candidates:
        if candidate['scope_id'] not in scopes:
            chosen.append(candidate['passage_id'])
            scopes.add(candidate['scope_id'])
        if len(chosen) == 4:
            break
    for candidate in candidates:
        if len(chosen) >= 4:
            break
        if candidate['passage_id'] not in chosen:
            chosen.append(candidate['passage_id'])
    if len(chosen) < 4:
        receipt['reasons'] = ['Fewer than four exact navigation passages for the existing retrieval contract.']
        return receipt
    content = {
        'selected_document_ids': selected, 'exchange_coverage': rows,
        'document_findings': [], 'quotes': [{'passage_id': pid} for pid in chosen],
        'preparation_notice': NOTICE,
    }
    from . import earnings_passage_pipeline as pipe
    pipe.validate('retrieval', content, bundle, catalog)
    receipt.update(status='ready', content=copy.deepcopy(content))
    return receipt
