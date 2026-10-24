"""Derive frozen evidence after the caller qualifies an explicit source packet.

No scheduling, model calls, handoffs or publication decisions belong here.
"""
from pathlib import Path
from . import earnings_source_case as base
from . import financial_evidence as financial
from . import transcript_evidence as transcript
from . import reviewed_transcript_index as reviewed_index
from . import library


def prepare_selected(root, packet_id, packet, filing, call, output, writing, authorization, *,
                      reviewed_sidecar=None, reviewed_financial=None, extra_sources=(),
                      extra_artifacts=(), scope_notes=()):
    """Shared derivation after a caller has authenticated its explicit source route."""
    docs = packet['documents']
    source = {k: filing[k] for k in ('document_id', 'raw_sha256', 'text_sha256')}
    raw = library.load_bytes(root, filing['raw_path'], filing['raw_sha256'])
    financial_artifacts = []
    if reviewed_financial is None:
        facts = financial.extract_inline_xbrl(raw.decode('utf-8'), source)
    else:
        from . import financial_html_tables
        financial_html_tables.fields(reviewed_financial, ('profile_path', 'review_path', 'authorization'), 'reviewed financial selection')
        source['issuer_id'] = packet['issuer_id']
        selection = reviewed_financial['authorization']
        profile = library.load_bytes(root, reviewed_financial['profile_path'], selection['profile_sha256'])
        review = library.load_bytes(root, reviewed_financial['review_path'], selection['review_sha256'])
        facts = financial_html_tables.extract(raw, source, profile, review, selection)
        financial_artifacts = [{'path': str(library.resolve(root, reviewed_financial[key+'_path'])),
                                'sha256': selection[key+'_sha256']} for key in ('profile', 'review')]
    if reviewed_financial is not None and selection.get('version')=='exact-reviewed-financial-spans-v1':
        if selection['source_url']!=filing['source_url']:raise ValueError('Reviewed span source URL differs from qualified filing')
        old_raw=Path(selection['original_raw_path']).resolve()
        if not old_raw.is_relative_to(root) or old_raw.is_symlink(): raise ValueError('Original reviewed raw must remain private and bound')
        financial_artifacts.append({'path':str(old_raw),'sha256':base.sha(old_raw)})
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
    if reviewed_financial is not None:
        financial_selection = output/'financial-adapter-authorization.json'
        base.save(financial_selection, reviewed_financial['authorization'])
        artifacts += financial_artifacts + [{'path': str(financial_selection), 'sha256': base.sha(financial_selection)}]
    if reviewed_sidecar is not None:
        selection_path = output/'transcript-sidecar-selection.json'
        base.save(selection_path, reviewed_sidecar)
        artifacts += mapping_artifacts + [{'path': str(selection_path), 'sha256': base.sha(selection_path)}]
    sources.extend(extra_sources)
    artifacts.extend(extra_artifacts)
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
    if reviewed_financial is not None:
        case['financial_adapter'] = {'authorization_path': str(financial_selection),
                                     **{key+'_path': str(library.resolve(root, reviewed_financial[key+'_path'])) for key in ('profile', 'review')}}
        case['scope_notes'].append('Selected ordinary HTML cells were extracted using an independently reviewed, exact-source profile. Profile review does not establish full financial coverage or report acceptance. Unselected cells remain original evidence.')
    case['scope_notes'].extend(scope_notes)
    base.validate_case(case); base.save(output/'case.json', case)
    return output/'case.json'

