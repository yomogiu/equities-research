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


def prepare(root, packet_id, output, writing, authorization, *, reviewed_sidecar=None):
    """Derive records with optional externally authorized source-bound mappings.

    reviewed_sidecar is an explicit coordinator-selected authorization dictionary,
    including private-root-relative proposal/review paths and exact expected source
    and artifact hashes. No sidecars are discovered or authorized by this function.
    Whole-index coverage remains provisional and goes to independent report review.
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
    source = {k: filing[k] for k in ('document_id', 'raw_sha256', 'text_sha256')}
    raw = library.load_bytes(root, filing['raw_path'], filing['raw_sha256'])
    facts = financial.extract_inline_xbrl(raw.decode('utf-8'), source)
    if not facts['observations']:
        raise ValueError('No structured filing observations; financial preparation needs review')
    text = library.load_bytes(root, call['text_path'], call['text_sha256']).decode('utf-8')
    call_raw = library.load_bytes(root, call['raw_path'], call['raw_sha256'])
    current_catalog = library.catalog(root)
    issuer_name = current_catalog['issuers'][packet['issuer_id']].get('issuer')
    call_source = {k: call[k] for k in ('document_id', 'text_sha256', 'raw_sha256')}
    if reviewed_sidecar is not None:
        # Native mapping receipts identify the durable catalog document. Packet
        # document_id is a separate qualified-packet identity; keep both bound.
        catalog_document_id = call.get('catalog_document_id')
        if not isinstance(catalog_document_id, str) or not catalog_document_id:
            raise ValueError('Reviewed transcript requires explicit catalog document identity')
        call_source['document_id'] = catalog_document_id
    call_source.update(issuer_id=packet['issuer_id'], catalog_id=current_catalog['catalog_id'],
                       issuer_names=[issuer_name] if isinstance(issuer_name, str) else [])
    mapping_artifacts = []
    if reviewed_sidecar is None:
        index = transcript.index_publisher_transcript(text, call_source, call_raw)
    else:
        # Existing issuer/period/completeness/freshness gates above still apply.
        if not isinstance(reviewed_sidecar, dict):
            raise ValueError('Explicit reviewed sidecar authorization required')
        proposal = library.load_bytes(root, reviewed_sidecar['proposal_path'], reviewed_sidecar['proposal_sha256'])
        review = library.load_bytes(root, reviewed_sidecar['review_path'], reviewed_sidecar['review_sha256'])
        index = reviewed_index.apply_reviewed_sidecar(text, call_raw, call_source, proposal, review, reviewed_sidecar)
        if index['coverage']['mapping_blockers']:
            raise ValueError('Reviewed Q&A mapping remains unresolved: ' + ', '.join(index['coverage']['mapping_blockers']))
        mapping_artifacts = [{'path': str(library.resolve(root, reviewed_sidecar[key+'_path'])),
                              'sha256': reviewed_sidecar[key+'_sha256']}
                             for key in ('proposal', 'review')]
    if not index['exchanges']:
        raise ValueError('Q&A boundaries need review before transcript-led analysis')
    # Keep provisional speaker/boundary uncertainty in the evidence for review.
    output.mkdir(parents=True, exist_ok=True)
    base.save(output/'financial.json', facts); base.save(output/'transcript-index.json', index)
    sources = []
    for doc in docs:
        for representation, name in (('raw', 'raw'), ('text', 'text')):
            path = library.resolve(root, doc[name+'_path'])
            if path.suffix == '.gz':
                raise ValueError('Compressed sources require a separately bound uncompressed representation')
            evidence_id = call_source['document_id'] if doc is call else doc['document_id']
            sources.append({'document_id': evidence_id, 'kind': 'filing' if doc['kind'] in ('periodic_filing', 'annual_background') else doc['kind'],
                            'representation': representation, 'path': str(path),
                            'sha256': doc[name+'_sha256'], 'url': doc['source_url']})
            if doc is call and reviewed_sidecar is not None:
                sources[-1]['packet_document_id'] = doc['document_id']
                sources[-1]['catalog_document_id'] = call_source['document_id']
    artifacts = [{'path': str(p), 'sha256': base.sha(p)} for p in (output/'financial.json', output/'transcript-index.json', writing)]
    if reviewed_sidecar is not None:
        selection_path = output/'transcript-sidecar-selection.json'
        base.save(selection_path, reviewed_sidecar)
        artifacts += mapping_artifacts + [{'path': str(selection_path), 'sha256': base.sha(selection_path)}]
    case = {'schema_version': 1, 'scope': 'one_packet_experiment', 'authorization': authorization,
            'case_id': packet_id, 'packet_id': packet_id, 'issuer_id': packet['issuer_id'], 'period': packet['period'],
            'scope_notes': [
                'Historical event_update for the exact qualified packet and fiscal period recorded in this case.',
                'Evidence is limited to the archived packet. Valuation, consensus, portfolio, private-library and prior-call context are unavailable unless explicitly present in its sources.',
                'Financial observations are deterministic extractions, not independent approval; preserve their original units, periods, accounting basis and dimensions.',
                'Transcript speaker roles and Q&A boundaries are provisional. Retain the index uncertainty and verify attribution against original call text.'
            ],
            'sources': sources, 'artifacts': artifacts, 'financial_path': str(output/'financial.json'),
            'transcript_index_path': str(output/'transcript-index.json'),
            'transcript_path': str(library.resolve(root, call['text_path'])), 'writing_standard_path': str(writing)}
    if reviewed_sidecar is not None:
        case['transcript_sidecar'] = index['reviewed_sidecar']
        case['transcript_sidecar_selection_path'] = str(selection_path)
        case['scope_notes'].append('Source-bound speaker/Q&A annotations have independent receipts; generated exchange coverage remains provisional. Unknown occupation does not imply unknown questioner function. Preserve all retained source holds.')
    base.validate_case(case); base.save(output/'case.json', case)
    return output/'case.json'


def advance(output, execute=True):
    """Replay completed stages and execute at most one new worker; fail closed."""
    root = Path(output).resolve()
    kind = base.read(root/'protocol.json').get('version')
    if kind in (corrections.VERSION, corrections.regression.VERSION, corrections.cited_passages.VERSION):
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
