"""Versioned, quote-only qualification for an opt-in benchmark follow-up.

This policy does not change the frozen benchmark. It stores nothing, repairs no
source text, and leaves every nonquote field and retained candidate unchanged.
Source/bundle integrity errors and unknown scope IDs remain fatal.
"""
from __future__ import annotations

from copy import deepcopy

from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base

VERSION = 'earnings-quote-candidates-v1'
MIN_UNIQUE_QUOTES = 4
# Only these exact resolver failures describe an individual quote candidate.
# A new/unknown resolver failure must propagate rather than weakening integrity.
CANDIDATE_ERRORS = frozenset({
    'Nonempty exact quote required',
    'Quote start must be an integer Unicode offset',
    'Quote differs from source or lies outside scope',
    'Ambiguous quote: supply a source start offset or narrower scope',
})


def qualify_candidates(manifest, retrieval_output):
    """Return a deep-copied retrieval batch with exact validated quotes only.

    At least four distinct (document, source hash, start, end) quotations must
    survive. Valid duplicates retain their original metadata and order but do
    not satisfy the uniqueness threshold. Rejected candidates retain their
    original values plus a quote-specific diagnostic. Provenance supplied by a
    candidate may not contradict its resolved source. No output is persisted.
    """
    # Validate the complete frozen snapshot even for an empty/malformed batch.
    bundle = evidence.load_bundle(manifest)
    if not isinstance(retrieval_output, dict) or not isinstance(retrieval_output.get('quotes'), list):
        raise ValueError('Retrieval output requires a quotes list')
    sources = {o['id']: {'path': o['source_path'], 'sha256': o['source_sha256'],
                         'document_id': o['source_document_id']}
               for o in bundle['financial']['observations']}
    sources.update({c['id']: {k: c[k] for k in ('path', 'sha256', 'document_id')}
                    for c in bundle['documents']['chunks']})
    transcript_source = {'path': bundle['manifest']['transcript_path'],
                         'sha256': bundle['manifest']['transcript_sha256'],
                         'document_id': bundle['transcript_index']['source']['document_id']}
    sources.update({item['id']: transcript_source
                    for group in ('sections', 'turns', 'exchanges')
                    for item in bundle['transcript_index'][group]})
    candidates = retrieval_output['quotes']
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError('Quote candidates must be objects with a known scope ID')
        if not isinstance(candidate.get('scope_id'), str) or candidate['scope_id'] not in sources:
            raise ValueError('Unknown source ID in quote candidate')
        provenance = {**sources[candidate['scope_id']], 'offset_unit': 'unicode_character'}
        for key, value in provenance.items():
            if key in candidate and candidate[key] != value:
                raise ValueError('Quote candidate source provenance mismatch: ' + key)

    content = deepcopy(retrieval_output)
    accepted, resolved_quotes, rejected, unique = [], [], [], set()
    for candidate in candidates:
        try:
            resolved = evidence.resolve_quote(
                manifest, candidate['scope_id'], candidate.get('text'), start=candidate.get('start'))
        except ValueError as exc:
            if str(exc) not in CANDIDATE_ERRORS:
                raise
            rejected.append({'candidate': deepcopy(candidate), 'error': str(exc)})
            continue
        for key in ('document_id', 'path', 'sha256', 'offset_unit'):
            if key in candidate and candidate[key] != resolved[key]:
                raise ValueError('Quote candidate source provenance mismatch: ' + key)
        if 'end' in candidate and (type(candidate['end']) is not int or candidate['end'] != resolved['end']):
            rejected.append({'candidate': deepcopy(candidate),
                             'error': 'Quote end differs from exact source span'})
            continue
        accepted.append(deepcopy(candidate))
        resolved_quotes.append(resolved)
        unique.add((resolved['document_id'], resolved['sha256'], resolved['start'], resolved['end']))
    if len(unique) < MIN_UNIQUE_QUOTES:
        raise ValueError('At least four unique valid quote candidates required; found ' + str(len(unique)))
    content['quotes'] = accepted
    return {'version': VERSION, 'content': content, 'accepted_quote_evidence': resolved_quotes,
            'rejected_candidates': rejected, 'original_sha256': base.digest(retrieval_output),
            'derived_sha256': base.digest(content)}
