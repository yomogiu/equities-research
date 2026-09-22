"""Resumable whole-universe collection, publication tracking and private handoffs."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import Collector
from .contracts import digest, require
from .freshness import timestamp
from .library import build_catalog, build_search, private_root, read_json, save
from .pipeline_sources import prepare
from .published_quarters import run as published_run


def optional(root, path, default):
    p = root / path
    return read_json(p) if p.exists() else default


def moment(value=None):
    result = value or datetime.now(timezone.utc)
    require(result.tzinfo is not None, 'Timezone-aware run time required')
    return result.astimezone(timezone.utc)


def due_queue(coverage, state, calendar, published, now=None):
    """Recompute windows at dispatch time; never trust an old frozen due list."""
    now = moment(now)
    today = now.astimezone(ZoneInfo('America/New_York')).date()
    events = {}
    for e in calendar.get('events', []):
        try:
            day = datetime.fromisoformat(e['event_date']).date()
        except (KeyError, TypeError, ValueError):
            continue
        if e.get('date_status') not in {'confirmed', 'estimated'}:
            continue
        if -1 <= (today - day).days <= 60:
            events.setdefault(e['issuer_id'], []).append((day, e))
    rows = []
    for row in coverage:
        iid = row['issuer_id']
        prior = state.get('issuers', {}).get(iid, {})
        # Coverage includes unresolved companies, but only the generated watchlist
        # can be selected. A candidate calendar never promotes listing identity.
        if not row.get('collector_issuer_id'):
            continue
        last = timestamp(prior.get('last_attempt_at'))
        age = (now - datetime.fromisoformat(last)).total_seconds() / 3600 if last else None
        active = events.get(iid, [])
        active.sort(key=lambda x: x[0], reverse=True)
        reason, cadence, priority = 'weekly_discovery', 168, 3
        if active:
            day, event = active[0]
            days = (today - day).days
            if days <= 7:
                reason, cadence, priority = 'earnings_window', 2, 0
            else:
                current = published.get('issuers', {}).get(iid, {})
                if not current.get('packet_id') or any((v.get('status') if isinstance(v, dict) else v) in {'pending', 'access_blocked'} for v in current.get('missing', {}).values()):
                    reason, cadence, priority = 'late_documents', 24, 2
        if not prior.get('baseline_attempted_at'):
            reason, cadence, priority = 'initial_baseline', 0, 1
        if 0 < prior.get('consecutive_failures', 0) < 3:
            reason, cadence, priority = 'repair_retry', 2, 2
        if prior.get('consecutive_failures', 0) >= 3:
            cadence = max(cadence, 168)
            reason = 'repair_backoff'
        retry = timestamp(prior.get('retry_after'))
        if retry and now < datetime.fromisoformat(retry):
            continue
        if age is not None and age < cadence:
            continue
        rows.append({'issuer_id': iid, 'collector_issuer_id': row['collector_issuer_id'],
                     'symbol': row['symbol'], 'reason': reason, 'cadence_hours': cadence,
                     'priority': priority, 'last_attempt_at': last,
                     'calendar_event_ids': sorted(e.get('event_id', '') for _, e in active),
                     'calendar_dates_are_discovery_hints': True})
    # Oldest never-attempted company wins within a priority; stable IDs break ties.
    return sorted(rows, key=lambda x: (x['priority'], x['last_attempt_at'] or '', x['issuer_id']))


def update_state(state, selected, receipt, now=None):
    now = moment(now)
    state = dict(state, issuers=dict(state.get('issuers', {})))
    results = {r['issuer_id']: r for r in receipt.get('issuer_results', [])}
    for row in selected:
        result = results.get(row['collector_issuer_id'])
        if not result:
            continue  # The run budget never reached this issuer; keep it due.
        iid = row['issuer_id']
        prior = dict(state['issuers'].get(iid, {}))
        if result.get('budget_deferred'):
            prior['retry_after'] = (now + timedelta(hours=2)).isoformat()
            prior['status'] = 'budget_deferred'
            state['issuers'][iid] = prior
            continue
        prior.update(last_attempt_at=now.isoformat(), baseline_attempted_at=prior.get('baseline_attempted_at') or now.isoformat(),
                     gap_codes=result['gap_codes'], reason=row['reason'], retry_after=None)
        if result['documents_checked']:
            prior.update(last_successful_retrieval_at=now.isoformat(), consecutive_failures=0,
                         status='partial' if result['gap_codes'] else 'collected')
        else:
            failures = prior.get('consecutive_failures', 0) + 1
            prior.update(consecutive_failures=failures, status='repair_required',
                         retry_after=(now + timedelta(hours=2 if failures < 3 else 168)).isoformat())
        state['issuers'][iid] = prior
    state.update(schema_version=1, updated_at=now.isoformat())
    return state


def select_batch(queue, limit):
    # Reserve baseline capacity so a busy earnings season cannot starve unseen names.
    baseline = [r for r in queue if r['reason'] == 'initial_baseline']
    urgent = [r for r in queue if r['reason'] != 'initial_baseline']
    reserved = min(len(baseline), max(1, limit // 3)) if baseline else 0
    picked = urgent[:limit - reserved] + baseline[:reserved]
    taken = {r['issuer_id'] for r in picked}
    return picked + [r for r in queue if r['issuer_id'] not in taken][:limit - len(picked)]


def run(root, mode='plan', limit=25, symbols=None, now=None, collector_factory=Collector):
    root, now = private_root(root), moment(now)
    require(mode in {'plan', 'collect', 'reconcile'}, 'Unknown pipeline mode')
    require(type(limit) is int and 1 <= limit <= 50, 'Batch size must be 1..50')
    (root / 'pipeline').mkdir(exist_ok=True)
    with (root / 'pipeline/.writer.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = read_json(root / 'config.json')
        if mode == 'collect':
            require(config.get('earnings_pipeline', {}).get('enabled') is True, 'Collection pipeline disabled')
        inputs = prepare(root)
        eligible_ids = {r['symbol'] for r in inputs['universe']}
        coverage = [dict(r, collector_issuer_id=r.get('collector_issuer_id') if r.get('symbol') in eligible_ids else None)
                    for r in inputs['coverage']]
        state = optional(root, 'pipeline/state.json', {'schema_version': 1, 'issuers': {}})
        calendar = optional(root, 'calendar/latest.json', {'events': []})
        published = optional(root, 'published/latest.json', {'issuers': {}})
        queue = due_queue(coverage, state, calendar, published, now)
        if symbols:
            require(set(symbols) <= eligible_ids, 'Unknown or identity-blocked requested symbols')
            # Manual symbols scope the queue; they never waive rate/backoff gates.
            queue = [r for r in queue if r['symbol'] in set(symbols)]
        selected = select_batch(queue, limit)
        save(root / 'pipeline/collection-queue.json', {'as_of': now.isoformat(), 'due': queue,
             'selected': selected, 'tracked': len(coverage), 'eligible': len(inputs['universe']),
             'identity_and_source_gaps': len(coverage) - len(inputs['universe'])})
        collection = None
        if mode == 'collect' and selected:
            rows = {r['symbol']: r for r in inputs['universe']}
            # Load indexes and cache only after locking shared collection storage.
            (root / 'collection').mkdir(exist_ok=True)
            with (root / 'collection/.collector.lock').open('a') as collector_lock:
                fcntl.flock(collector_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                worker = collector_factory([rows[r['symbol']] for r in selected], inputs['registry'], root / 'collection',
                    as_of=now.astimezone(ZoneInfo('America/New_York')).date(), sec_user_agent=os.environ.get('SEC_USER_AGENT'))
                worker.client.max_requests = 240
                worker.client.max_bytes = 192 * 1024 * 1024
                collection = worker.run()
            state = update_state(state, selected, collection, now)
            save(root / 'pipeline/state.json', state)
            # Enqueue via the existing CLI contract in the private wrapper; do not
            # interpret successful exit as complete source coverage here.
        publication = None
        if mode != 'plan':
            cfg = config.get('earnings_pipeline', {})
            build_catalog(root, cfg.get('audit', 'reports/retrieval/2026-09-20/universe/results.json'),
                          cfg.get('languages', 'reports/retrieval/2026-09-20/universe/language-review.json'))
            build_search(root)
            publication = published_run(root, as_of=now.astimezone(ZoneInfo('America/New_York')).date())
        remaining = due_queue(coverage, state, calendar,
                              optional(root, 'published/latest.json', {'issuers': {}}), now)
        receipt = {'schema_version': 1, 'at': now.isoformat(), 'mode': mode,
                   'tracked': len(coverage), 'eligible': len(inputs['universe']), 'selected': len(selected),
                   'due_remaining': len(remaining), 'baseline_attempted': sum(bool(r.get('baseline_attempted_at')) for r in state['issuers'].values()),
                   'collection': collection, 'publication': publication, 'model_calls': 0,
                   'analysis_dispatched': False, 'qualification_dispatch': 'separate_agent_handoff'}
        save(root / 'pipeline/latest-run.json', receipt)
        if mode != 'plan':
            save(root / 'pipeline/runs' / (digest(receipt) + '.json'), receipt, immutable=True)
        save(root / 'pipeline/status.json', {k:v for k,v in receipt.items() if k not in {'collection','publication'}})
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--mode', choices=['plan', 'collect', 'reconcile'], default='plan')
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--symbols', help='Comma-separated eligible issuer symbols')
    args = parser.parse_args()
    receipt = run(args.root, args.mode, args.limit, args.symbols.split(',') if args.symbols else None)
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'collection','publication'}}))


if __name__ == '__main__':
    main()
