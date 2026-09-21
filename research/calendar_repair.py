"""Private source-repair handoffs; queueing does not execute an agent or model.

Claims are process-safe within one shared private workspace. A coordinator must
persist the private queue remotely before dispatching work across machines.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import urlsplit, urlunsplit
import uuid

from .contracts import digest, require
from .library import issuer_id, lock, private_root, read_json, resolve, save

QUEUE = 'calendar/repair-queue.json'
FAILURES = {
    'access_blocked', 'network_error', 'dns_error', 'parse_error', 'invalid_provider_response',
    'worker_error', 'provider_error', 'cache_integrity_error', 'retry_later', 'host_backoff',
    'size_limit', 'sec_contact_required', 'unapproved_url', 'credential_url',
    'unapproved_issuer_host', 'non_public_address',
}


def stamp(value=None):
    value = value or datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(isinstance(value, datetime) and value.tzinfo is not None, 'Timezone-aware timestamp required')
    return value.astimezone(timezone.utc)


def actual_failure(code):
    return isinstance(code, str) and (code in FAILURES or re.fullmatch(r'http_[45]\d\d', code) is not None)


def source_url(value):
    if value is None or value == '':
        return None
    require(isinstance(value, str), 'Source URL must be a string')
    parsed = urlsplit(value)
    require(parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password,
            'Credential-free HTTP(S) source URL required')
    require(not any(ord(c) < 33 for c in value), 'Invalid URL whitespace')
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or '/', parsed.query, ''))


def load(root):
    target = resolve(root, QUEUE)
    return read_json(target) if target.exists() else {
        'schema_version': 1, 'items': {}, 'agent_execution': 'not_performed_by_queue',
        'persistence': 'local_private_file_requires_coordinator_remote_writeback',
    }


def persist(root, queue):
    queue['counts'] = dict(sorted(Counter(x['state'] for x in queue['items'].values()).items()))
    save(resolve(root, QUEUE), queue)
    return queue


def enqueue(root, failures, observed_at, run_id):
    """Deduplicate real failures and retain terminal dispositions for this quarter."""
    root = private_root(root)
    moment = stamp(observed_at)
    require(isinstance(run_id, str) and run_id.strip() and len(run_id) <= 512, 'Explicit source run ID required')
    quarter = f'{moment.year}-Q{(moment.month - 1) // 3 + 1}'
    require(isinstance(failures, list), 'Failures must be an array')
    with lock(root / 'calendar'):
        queue = load(root)
        for failure in failures:
            code = failure.get('code')
            if not actual_failure(code):
                continue
            iid = failure.get('issuer_id')
            kind = failure.get('kind')
            require(isinstance(iid, str) and iid.strip(), 'Failure issuer ID required')
            require(isinstance(kind, str) and kind.strip(), 'Failure kind required')
            iid = issuer_id(iid)
            url = source_url(failure.get('source_url'))
            key = digest([iid, url, kind, quarter])
            item = queue['items'].setdefault(key, {
                'item_id': key, 'issuer_id': iid, 'source_url': url, 'kind': kind, 'quarter': quarter,
                'state': 'pending', 'attempts': 0, 'max_attempts': 3, 'occurrences': 0,
                'source_run_ids': [], 'failure_codes': [], 'first_seen_at': moment.isoformat(),
                'last_seen_at': moment.isoformat(), 'history': [],
            })
            if run_id not in item['source_run_ids']:
                item['source_run_ids'].append(run_id)
                item['occurrences'] += 1
            if code not in item['failure_codes']:
                item['failure_codes'].append(code)
                item['failure_codes'].sort()
            item['first_seen_at'] = min(item['first_seen_at'], moment.isoformat())
            item['last_seen_at'] = max(item['last_seen_at'], moment.isoformat())
        return persist(root, queue)


def claim_batch(root, worker_id, limit=5, lease_seconds=1800, now=None):
    """Record local leases only; caller owns dispatch and remote persistence."""
    root = private_root(root)
    moment = stamp(now)
    require(isinstance(worker_id, str) and worker_id.strip(), 'Worker session ID required')
    require(type(limit) is int and 1 <= limit <= 5, 'Claim batch must contain one to five items')
    require(type(lease_seconds) is int and 60 <= lease_seconds <= 14400, 'Lease must be 60–14400 seconds')
    with lock(root / 'calendar'):
        queue = load(root)
        claimed = []
        for item in sorted(queue['items'].values(), key=lambda x: (x['first_seen_at'], x['item_id'])):
            if item['state'] == 'claimed' and stamp(item['lease_expires_at']) <= moment:
                item['history'].append({'action': 'lease_expired', 'at': moment.isoformat(), 'worker_id': item['worker_id']})
                item['state'] = 'blocked' if item['attempts'] >= 3 else 'pending'
                item.pop('lease_token', None)
            if item['state'] != 'pending' or len(claimed) >= limit:
                continue
            if item['attempts'] >= 3:
                item['state'] = 'blocked'
                continue
            item.update(state='claimed', worker_id=worker_id, lease_token=uuid.uuid4().hex,
                        lease_expires_at=(moment + timedelta(seconds=lease_seconds)).isoformat(),
                        attempts=item['attempts'] + 1)
            item['history'].append({'action': 'claimed', 'at': moment.isoformat(), 'worker_id': worker_id,
                                    'attempt': item['attempts']})
            claimed.append(dict(item))
        persist(root, queue)
        return claimed


def finish(root, item_id, lease_token, state, notes, evidence=None, now=None):
    root = private_root(root)
    moment = stamp(now)
    require(state in ('resolved', 'blocked', 'pending'), 'Finish state must be resolved, blocked or pending')
    require(isinstance(notes, str) and notes.strip(), 'Substantive disposition notes required')
    require(len(notes.strip()) >= 12, 'Disposition notes must explain the result')
    with lock(root / 'calendar'):
        queue = load(root)
        require(item_id in queue['items'], 'Unknown repair item')
        item = queue['items'][item_id]
        require(item['state'] == 'claimed' and item.get('lease_token') == lease_token, 'Active matching lease required')
        require(stamp(item['lease_expires_at']) > moment, 'Expired worker cannot finish task')
        if state == 'resolved':
            require(isinstance(evidence, list) and evidence, 'Resolution requires inspectable evidence references')
            for entry in evidence:
                require(isinstance(entry, dict) and (entry.get('source_url') or entry.get('path')), 'Evidence URL or private path required')
                if entry.get('source_url'):
                    source_url(entry['source_url'])
                if entry.get('path'):
                    require(resolve(root, entry['path']).is_file(), 'Evidence file does not exist in private storage')
        if state == 'pending' and item['attempts'] >= 3:
            state = 'blocked'
        item.update(state=state, notes=notes, evidence=evidence or [], finished_at=moment.isoformat())
        item['history'].append({'action': state, 'at': moment.isoformat(), 'worker_id': item['worker_id'],
                                'notes': notes, 'evidence': evidence or []})
        item.pop('lease_token', None)
        if state == 'resolved':
            item['resolution_verification'] = 'worker_reported_evidence_requires_coordinator_review'
        persist(root, queue)
        return item


def failures_from(payload, source):
    if source == 'collection':
        return [f for f in payload.get('gaps', []) if actual_failure(f.get('code'))]
    require(source == 'calendar', 'Unknown failure source')
    failures = []
    checked = set(payload['checked_issuer_ids']) if 'checked_issuer_ids' in payload else None
    for row in payload.get('coverage', []):
        iid = row['issuer_id']
        if checked is not None and iid not in checked:
            continue
        if row.get('issuer_source_status') == 'worker_error':
            failures.append({'issuer_id': iid, 'source_url': None, 'code': 'worker_error', 'kind': 'calendar_worker'})
        for attempt in row.get('source_attempts', []):
            if actual_failure(attempt.get('status')):
                failures.append({'issuer_id': iid, 'source_url': attempt.get('url'),
                                 'code': attempt['status'], 'kind': 'calendar_source'})
    provider = payload.get('provider', {})
    if payload.get('provider_refreshed', True) and actual_failure(provider.get('status')):
        failures.append({'issuer_id': 'provider:earnings-calendar', 'source_url': provider.get('source_url'),
                         'code': provider['status'], 'kind': 'calendar_provider'})
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('enqueue')
    add.add_argument('--source', choices=['calendar', 'collection'], required=True)
    add.add_argument('--run-id', required=True)
    add.add_argument('--observed-at')
    claim = commands.add_parser('claim')
    claim.add_argument('--worker-id', required=True)
    claim.add_argument('--limit', type=int, default=5)
    claim.add_argument('--lease-seconds', type=int, default=1800)
    done = commands.add_parser('finish')
    done.add_argument('--item-id', required=True)
    done.add_argument('--lease-token', required=True)
    done.add_argument('--state', choices=['resolved', 'blocked', 'pending'], required=True)
    done.add_argument('--notes', required=True)
    done.add_argument('--evidence', help='Private relative JSON file containing evidence-reference array')
    args = parser.parse_args(argv)
    root = private_root(args.root)
    if args.command == 'enqueue':
        payload = read_json(resolve(root, 'calendar/latest.json' if args.source == 'calendar' else 'collection/source-gaps.json'))
        observed = args.observed_at or payload.get('generated_at') or payload.get('checked_at')
        require(observed, 'Source observation timestamp required')
        queue = enqueue(root, failures_from(payload, args.source), observed, args.run_id)
        result = {'counts': queue['counts'], 'agent_execution': queue['agent_execution']}
    elif args.command == 'claim':
        result = {'claimed': claim_batch(root, args.worker_id, args.limit, args.lease_seconds),
                  'agent_execution': 'not_performed_by_queue'}
    else:
        evidence = read_json(resolve(root, args.evidence)) if args.evidence else None
        item = finish(root, args.item_id, args.lease_token, args.state, args.notes, evidence)
        result = {'item_id': item['item_id'], 'state': item['state']}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
