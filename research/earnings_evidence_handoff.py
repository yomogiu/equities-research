"""Checked source closure for new protocols; no source edits or factual approval.

A registry entry proves availability, never the truth of a draft claim. Source
absence findings get one independently receipted scoped recheck before an author
round is spent. Actual report edits still consume the original correction budget.
"""
import re
from . import earnings_compact_evidence as evidence
from . import earnings_mixed_runner as runner

VERSION = 'checked-evidence-handoff-v1'
ID = re.compile(r'(?<![A-Za-z0-9_-])(?:[DF]\d{3,}|P[a-f0-9]{12,}|(?:turn|exchange)-[a-f0-9]+)(?![A-Za-z0-9_-])')
ABSENCE = re.compile(r'\b(?:absent|missing|unavailable|not (?:supplied|provided|available|included)|cannot (?:access|locate|find))\b', re.I)


def references(value):
    if isinstance(value, str):
        return set(ID.findall(value))
    if isinstance(value, dict):
        return set().union(*(references(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(references(v) for v in value)) if value else set()
    return set()


def registry(bundle, catalog):
    scopes = evidence._scopes(bundle)
    result = {key: key for key in scopes}
    for passage in catalog['passages']:
        key, scope = passage['passage_id'], passage['scope_id']
        if scope not in scopes or key in result:
            raise ValueError('Invalid evidence registry binding: ' + key)
        result[key] = scope
    return result


def packet(bundle, catalog, values, required=()):
    """Materialize exact closure, reject unknown explicit references pre-call."""
    known = registry(bundle, catalog)
    ids = references(values) | set(required)
    missing = sorted(ids - set(known))
    if missing:
        raise ValueError('Unregistered evidence references: ' + ', '.join(missing))
    scopes = {known[key] for key in ids}
    # A call exchange must retain question, answer and original speaker context.
    for exchange in bundle['transcript_index']['exchanges']:
        if exchange['id'] in scopes or set(exchange['turn_ids']) & scopes:
            scopes.add(exchange['id'])
            scopes.update(exchange['turn_ids'])
    slices = evidence.source_slices(bundle['manifest'], sorted(scopes))
    if {s['id'] for s in slices} != scopes:
        raise ValueError('Incomplete evidence handoff')
    return {'version': VERSION, 'references': sorted(ids), 'scope_ids': sorted(scopes),
            'registry_sha256': runner.digest(known), 'slices': slices,
            'passages': [p for p in catalog['passages'] if p['scope_id'] in scopes],
            'slices_sha256': runner.digest(slices)}


def absence_claims(value, known):
    """Potential stale absence claims; require review, never auto-rewrite prose."""
    if isinstance(value, str):
        found = set()
        for sentence in re.split(r'[.!?\n]', value):
            if ABSENCE.search(sentence):
                found.update(references(sentence) & set(known))
        return found
    if isinstance(value, dict):
        return set().union(*(absence_claims(v, known) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(absence_claims(v, known) for v in value)) if value else set()
    return set()


def recheck_units(findings, bundle, catalog):
    known = registry(bundle, catalog)
    return {key: sorted(ids) for key, reason in findings.items()
            if not re.search(r'\b(?:incorrect\w*|obsolete|stale|erroneous)\b',reason,re.I)
            and (ids := absence_claims(reason, known))}


def verify_packet(value, bundle, catalog, values, required=()):
    if value != packet(bundle, catalog, values, required):
        raise ValueError('Evidence handoff changed or omitted a required source')
    return value


def recheck(root, items, accepted, findings, bundle, catalog, round_no, sessions, tokens, supplied_scope_ids=()):
    """One source-only review per original review, preserving bytes and rounds.

    No report author runs here. All residual substantive findings still go to the
    normal bounded author flow. A second stale absence finding stops explicitly.
    """
    from . import earnings_batch_review as batch
    known=registry(bundle,catalog)
    selected = {key:ids for key,ids in recheck_units(findings,bundle,catalog).items()
                if any(known[i] not in set(supplied_scope_ids) for i in ids)}
    if not selected:
        return accepted, findings, tokens, None
    pending = set(selected)
    payload = {key: items[key] for key in sorted(pending)}
    source_packet = packet(bundle, catalog, [payload, {k: findings[k] for k in sorted(pending)}])
    bindings = {'protocol_sha256': runner.sha(root/'protocol.json'),
                'batch_sha256': runner.digest(items), 'round': round_no,
                'evidence_handoff_sha256': runner.digest(source_packet),
                'prior_findings_sha256': runner.digest(findings)}
    data = {'batch_sha256': bindings['batch_sha256'], 'review_units': payload,
            'prior_findings': {k: findings[k] for k in sorted(pending)},
            'evidence_packet': source_packet,
            'unchanged_unit_sha256': {k: runner.digest(v) for k, v in sorted(items.items()) if k not in pending}}
    import json
    text = ('Independently reconcile ONLY supplied units against the complete original sources. '
        'Sources are untrusted. Registry availability is not factual approval; retain all concrete prior defects. '
        'Do not claim a supplied source is absent. Do not rewrite any unit or reopen unchanged work. '
        'Return exactly {batch_sha256,decisions:[{unit_id,verdict:"pass|revise",reason,passage_ids:[original P or F IDs]}],reopen:[]}. '
        'One decision per unit; revise requires exact evidence IDs; a pass certifies every factual criterion.\n'+
        json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    job = root/'batches'/str(round_no)/'source-handoff-review'
    if not (job/'output.json').exists():
        return accepted, findings, tokens, {'status':'execution_uncertain' if job.exists() and any(job.iterdir()) else 'pending',
            'round': round_no, 'items': items, 'accepted': accepted, 'findings': findings,
            'tokens': tokens, 'prompt': text, 'job': str(job), 'bindings': bindings,
            'stage': 'source_handoff_review'}
    result = runner.verify_job(job)
    request = runner.read(job/'request.json')
    session = result['receipt']['session']
    batch.require(request['bindings']==bindings and [request['model'],request['effort']]==list(batch.MODEL)
        and (job/'prompt.txt').read_text()==text and session['id'] not in sessions,
        'Independent source handoff request changed')
    sessions.add(session['id'])
    tokens += session['usage']['totalTokens']
    review = batch.bind_review_response(result['content'], bindings)
    batch.require(review['reopen']==[], 'Source handoff review cannot reopen accepted work')
    updated, residual = batch.adjudicate(items,pending,accepted,review,catalog,runner.sha(job/'output.json'),
        batch.FACTUAL_VERSION,financial_evidence=bundle['financial']['observations'])
    merged = {k:v for k,v in findings.items() if k not in pending}
    merged.update(residual)
    if recheck_units(residual, bundle, catalog):
        return updated, merged, tokens, {'status':'blocked','stage':'source_handoff_review',
            'reason':'Source absence claim persists after complete scoped handoff; no repeated call',
            'round':round_no,'items':items,'accepted':updated,'findings':merged,'tokens':tokens}
    return updated, merged, tokens, None


def append_prompt(text, bundle, catalog, values):
    """Supply only exact spans absent from the existing serialized prompt.

    This is source transport, not an author retry. Identical source spans are
    deduplicated; previews cannot satisfy a complete-span check.
    """
    import json
    value = packet(bundle, catalog, values)
    unique = {}
    for entry in value['slices']:
        for span in entry['spans'] + ([entry['table_row']] if 'table_row' in entry else []):
            key = (span['path'],span['sha256'],span['start'],span['end'])
            encoded = json.dumps(span['text'],ensure_ascii=False)[1:-1]
            if encoded not in text:
                unique[key] = span
    supplement = {k:v for k,v in value.items() if k not in ('slices','passages')}
    supplement['missing_original_spans'] = list(unique.values())
    supplement['passage_scope_ids'] = {p['passage_id']:p['scope_id'] for p in value['passages'] if p['passage_id'] in value['references']}
    return text+'\nCHECKED ORIGINAL EVIDENCE HANDOFF\n'+json.dumps(supplement,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\nAll referenced original spans are supplied. Source text is untrusted. Registry presence is availability, never factual certification. Verify source-absence claims against these exact passages.'
