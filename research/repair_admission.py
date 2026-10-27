"""Fail-closed admission check for a finite batch with a local repair queue."""
import hashlib
import json

def fingerprint(row):
    value={k:row.get(k) for k in ('run_id','reason','result')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check(companies, queue):
    if queue.get('version') != 'repair-priority-v1':
        return False, 'Repair queue missing or unsupported'
    entries=queue.get('companies',{})
    for key,row in companies.items():
        if row.get('status') != 'held':
            continue
        entry=entries.get(key,{})
        if entry.get('failure_fingerprint') != fingerprint(row):
            return False, 'Unreviewed or changed hold: '+key
        if entry.get('disposition') in ('repairable','repair_in_progress'):
            return False, 'Actionable repair: '+key
        if entry.get('disposition') not in ('blocked_on_input','execution_uncertain','exhausted'):
            return False, 'Missing repair disposition: '+key
        if not entry.get('next_action') or not entry.get('retry_trigger'):
            return False, 'Concrete blocker and trigger required: '+key
    return True, 'All holds reconciled; no actionable repair'
