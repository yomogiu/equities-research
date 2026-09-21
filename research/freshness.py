"""Source access recency, deliberately separate from fiscal-period qualification."""
from datetime import datetime, timezone
import math

DEFAULT_POLICY = {'event_max_age_hours': 24, 'annual_background_max_age_hours': 720}


def timestamp(value):
    """Normalize recorded timestamps only; never substitute a build/file timestamp."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and math.isfinite(value):
            moment = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                return None
        else:
            return None
        return moment.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def policy(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - set(DEFAULT_POLICY):
        raise ValueError('Invalid packet freshness policy')
    result = dict(DEFAULT_POLICY, **value)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in result.values()):
        raise ValueError('Freshness limits must be finite positive hours')
    return result


def assess_document(doc, limits, moment):
    limit = limits['annual_background_max_age_hours' if doc.get('kind') == 'annual_background' else 'event_max_age_hours']
    checked, retrieved = timestamp(doc.get('checked_at')), timestamp(doc.get('retrieved_at'))
    basis = 'checked_at' if checked else 'retrieved_at' if retrieved else None
    observed = checked or retrieved
    age = (moment - datetime.fromisoformat(observed)).total_seconds() / 3600 if observed else None
    if doc.get('source_check_status') == 'content_changed':
        state = 'content_changed'
    elif any(v and datetime.fromisoformat(v) > moment for v in (checked, retrieved)):
        state = 'future_timestamp'
    elif observed is None:
        state = 'unknown'
    elif age > limit:
        state = 'stale'
    else:
        state = 'fresh'
    return {'document_id': doc.get('document_id'), 'source_url': doc['source_url'],
            'status': state, 'basis': basis, 'observed_at': observed,
            'age_hours': round(age, 4) if age is not None else None, 'max_age_hours': limit}


def assess_packet(packet, current_policy=None, now=None):
    moment = now or datetime.now(timezone.utc)
    limits = policy(packet.get('freshness_policy'))
    if current_policy is not None:
        current = policy(current_policy)
        limits = {k: min(v, current[k]) for k, v in limits.items()}
    results = [assess_document(doc, limits, moment) for doc in packet['documents']]
    ready = bool(results) and 'freshness_policy' in packet and all(d['status'] == 'fresh' for d in results)
    return {'evaluated_at': moment.isoformat(), 'status': 'ready' if ready else 'recheck_required',
            'policy': limits, 'documents': results,
            'rule': 'Successful source access recency only; fiscal-period qualification remains required.',
            'next_action': None if ready else 'Re-fetch/revalidate sources, rebuild the catalog, and create a successor packet.'}
