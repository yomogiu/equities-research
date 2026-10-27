"""Finite selected-report workflow: qualified packet -> reviewed signal edition.

The private coordinator owns authorization, scheduling and verified persistence.
This module performs at most one new model call per advance and never self-authorizes.
"""
from pathlib import Path
from . import earnings_experiment as base
from . import earnings_passage_pipeline as pipe
from . import earnings_corrections as corrections
from . import earnings_signals as signals
from . import financial_evidence as financial
from . import transcript_evidence as transcript
from . import reviewed_transcript_index as reviewed_index
from . import library, freshness
from .earnings_source_preparation import prepare_selected as _prepare_selected


def validate_packet(root, packet_id):
    root = Path(root).resolve()
    packet = base.read(library.resolve(root, f'library/packets/{packet_id}.json'))
    library.materialize(root, packet)
    if not packet['identity_verified'] or packet['translation_required']:
        raise ValueError('Verified identity and full English coverage required')
    current = library.catalog(root)
    if current['issuers'].get(packet['issuer_id'], {}).get('monitoring_eligible') is not True:
        raise ValueError('Issuer eligibility requires review')
    latest = base.read(root/'published/latest.json')['issuers'].get(packet['issuer_id'], {})
    if latest.get('packet_id') != packet_id:
        raise ValueError('Packet superseded; select the current qualified packet')
    for doc in packet['documents']:
        candidate = current['documents'].get(doc['catalog_document_id'], {})
        same = [s for s in candidate.get('sources', []) if s['source_url'] == doc['source_url'] and s['raw_sha256'] == doc['raw_sha256']]
        if candidate.get('issuer_id') != packet['issuer_id'] or candidate.get('text_sha256') != doc['text_sha256'] or not same or any(s.get('source_check_status') == 'content_changed' for s in same):
            raise ValueError('Current source changed or disappeared')
    if freshness.assess_packet(packet, base.read(root/'config.json').get('packet_freshness', {}))['status'] != 'ready':
        raise ValueError('Packet requires source freshness revalidation')
    return packet


def prepare(root, packet_id, output, writing, authorization, *, reviewed_sidecar=None, reviewed_financial=None):
    """Derive records with optional externally authorized source-bound mappings.

    reviewed_sidecar is an explicit coordinator-selected authorization dictionary,
    including private-root-relative proposal/review paths and exact expected source
    and artifact hashes. No sidecars are discovered or authorized by this function.
    Whole-index coverage remains provisional and goes to independent report review.
    reviewed_financial optionally names profile/review paths and an externally
    reserved authorization for exact HTML cells; it is never discovered or used
    automatically after inline extraction fails.
    """
    root, output, writing = Path(root).resolve(), Path(output).resolve(), Path(writing).resolve()
    if not authorization.strip():
        raise ValueError('Explicit report authorization required')
    packet = validate_packet(root, packet_id)
    docs = packet['documents']
    filings = [d for d in docs if d['kind'] == 'periodic_filing' and d['period'] == packet['period'] and d['completeness'] == 'full']
    calls = [d for d in docs if d['kind'] == 'transcript' and d['period'] == packet['period'] and d['completeness'] == 'full']
    if len(filings) != 1 or len(calls) != 1:
        raise ValueError('One unambiguous full current-period filing and transcript required')
    filing, call = filings[0], calls[0]
    return _prepare_selected(root, packet_id, packet, filing, call, output, writing, authorization,
                             reviewed_sidecar=reviewed_sidecar, reviewed_financial=reviewed_financial)


def advance(output, execute=True):
    """Replay completed stages and execute at most one new worker; fail closed."""
    root = Path(output).resolve()
    frozen = base.read(root/'protocol.json')
    if frozen.get('version')=='file-backed-markdown-review-v1':
        from . import earnings_file_pipeline
        return earnings_file_pipeline.advance(root,execute)
    if frozen.get('review_attempt_recovery'):
        from . import earnings_review_attempt_recovery
        return earnings_review_attempt_recovery.advance(root,execute)
    if frozen.get('split_review_recovery'):
        from . import earnings_split_review_recovery
        return earnings_split_review_recovery.advance(root,execute)
    if frozen.get('selection_recovery'):
        from . import earnings_batched_selection_recovery
        return earnings_batched_selection_recovery.advance(root,execute)
    if frozen.get('layout_recovery'):
        from . import earnings_batched_layout_recovery
        return earnings_batched_layout_recovery.advance(root,execute)
    if frozen.get('contract_recovery'):
        from . import earnings_batched_contract_recovery
        return earnings_batched_contract_recovery.advance(root,execute)
    if frozen.get('batch_review'):
        from . import earnings_batched_flow
        return earnings_batched_flow.advance(root,execute)
    kind = frozen.get('version')
    if kind in (corrections.VERSION, corrections.regression.VERSION, corrections.cited_passages.VERSION, corrections.financial_evidence.VERSION):
        continuation, _, _, _ = corrections.load(root)
        protocol = continuation['source_protocol']
        if continuation.get('new_experiment') or continuation['prior_rounds'] + continuation['max_rounds'] > 2:
            raise ValueError('Connected continuation must preserve the original correction budget')
        if not protocol.get('deterministic_corrections') or not protocol.get('report_signals'):
            raise ValueError('Connected reports require deterministic corrections and reviewed signals')
        seed = root
        result = corrections.verify(seed)
        if result['status'] != 'accepted':
            result = corrections.advance(seed) if execute else result
            if result['status'] != 'accepted':
                return {'status': result['status'], 'stage': 'corrections', 'detail': result}
            return {'status': 'pending', 'stage': 'signals'}
    else:
        protocol, _, _ = pipe.load(root)
        if not protocol.get('deterministic_corrections') or not protocol.get('report_signals'):
            raise ValueError('Connected reports require deterministic corrections and reviewed signals')
        if not (root/'result.json').exists():
            if not execute:
                return {'status': 'pending', 'stage': 'report'}
            try:
                result = pipe.run(root, max_new_jobs=1)
            except pipe.PendingJobs:
                return {'status': 'pending', 'stage': 'report'}
            # Let the next turn start a continuation; never spend a second job here.
            return {'status': 'pending', 'stage': 'report_reviewed', 'report_status': result['status']}
        result = pipe.verify(root)
        seed = root
        if result['status'] != 'accepted':
            seed = root.with_name(root.name+'-corrections')
            if not (seed/'protocol.json').exists():
                if set(base.read(root/'artifacts.json')) != {'financial', 'retrieval', 'analysis'} or not base.read(root/'review.json'):
                    return {'status': 'blocked', 'stage': 'preparation', 'reason': 'Complete evidence and substantive review required'}
                if not execute:
                    return {'status': 'pending', 'stage': 'corrections'}
                corrections.initialize(root, seed)
            result = corrections.verify(seed)
            if result['status'] != 'accepted':
                result = corrections.advance(seed) if execute else result
                if result['status'] != 'accepted':
                    return {'status': result['status'], 'stage': 'corrections', 'detail': result}
                return {'status': 'pending', 'stage': 'signals'}
    edition = seed.with_name(seed.name+'-signals')
    if not (edition/'protocol.json').exists():
        if not execute:
            return {'status': 'pending', 'stage': 'signals'}
        signals.initialize(seed, edition)
    result = signals.advance(edition, execute)
    return {'status': result['status'], 'stage': 'signals', 'detail': result,
            **({'report': str(edition/'report.html'), 'report_sha256': base.sha(edition/'report.html')} if result['status'] == 'accepted' else {})}
