"""Offline source-repair scenarios; all sources and issuers are fictitious."""
from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from research import calendar_repair as repair


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
        self.failure = {'issuer_id': 'sec:0000000042', 'source_url': 'https://example.com/calendar',
                        'kind': 'calendar_source', 'code': 'access_blocked'}

    def enqueue(self, failures=None, run='fixture-run', now=None):
        return repair.enqueue(self.root, failures or [self.failure], now or self.now, run)

    def test_error_code_change_and_alias_do_not_duplicate(self):
        self.enqueue()
        changed = dict(self.failure, issuer_id='cik-0000000042', code='http_503')
        queue = self.enqueue([changed], run='fixture-next')
        self.assertEqual(len(queue['items']), 1)
        item = next(iter(queue['items'].values()))
        self.assertEqual(item['occurrences'], 2)
        self.assertEqual(item['failure_codes'], ['access_blocked', 'http_503'])

    def test_repeated_source_run_counts_once(self):
        self.enqueue([self.failure, self.failure])
        queue = self.enqueue()
        self.assertEqual(next(iter(queue['items'].values()))['occurrences'], 1)
        self.assertEqual(queue['agent_execution'], 'not_performed_by_queue')

    def test_normal_gaps_do_not_create_tasks(self):
        gaps = [dict(self.failure, code=code) for code in ['full_transcript_not_observed_this_run',
                'no_structured_earnings_date', 'no_upcoming_date_found', 'identity_review', 'no_issuer_source', 'fetched']]
        queue = self.enqueue(gaps)
        self.assertEqual(queue['items'], {})

    def test_three_expired_claims_block_and_old_worker_cannot_finish(self):
        self.enqueue()
        original = None
        for n in range(3):
            claimed = repair.claim_batch(self.root, f'worker-{n}', lease_seconds=60,
                                         now=self.now + timedelta(seconds=n * 61))
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0]['attempts'], n + 1)
            original = original or claimed[0]
        self.assertEqual(repair.claim_batch(self.root, 'worker-4', now=self.now + timedelta(seconds=183)), [])
        with self.assertRaises(ValueError):
            repair.finish(self.root, original['item_id'], original['lease_token'], 'resolved',
                          'Fictitious repair verified.', [{'source_url': 'https://example.com/calendar'}], now=self.now + timedelta(seconds=184))
        queue = self.enqueue(run='later-run')
        self.assertEqual(next(iter(queue['items'].values()))['state'], 'blocked')

    def test_claim_batch_capped_and_active_lease_not_reclaimed(self):
        self.enqueue([dict(self.failure, source_url=f'https://example.com/{n}') for n in range(7)])
        with self.assertRaises(ValueError):
            repair.claim_batch(self.root, 'worker', limit=6, now=self.now)
        self.assertEqual(len(repair.claim_batch(self.root, 'worker', now=self.now)), 5)
        self.assertEqual(len(repair.claim_batch(self.root, 'other-worker', now=self.now)), 2)
        self.assertEqual(repair.claim_batch(self.root, 'third-worker', now=self.now), [])

    def test_resolution_requires_evidence_and_preserves_terminal_state(self):
        self.enqueue()
        item = repair.claim_batch(self.root, 'worker', now=self.now)[0]
        with self.assertRaises(ValueError):
            repair.finish(self.root, item['item_id'], item['lease_token'], 'resolved', 'Fixed issuer source.', now=self.now)
        with self.assertRaises(ValueError):
            repair.finish(self.root, item['item_id'], item['lease_token'], 'resolved', 'Fixed issuer source.', [{'path': '../escape'}], now=self.now)
        done = repair.finish(self.root, item['item_id'], item['lease_token'], 'resolved', 'Verified new source URL using fixture.',
                             [{'source_url': 'https://example.com/fixed'}], now=self.now)
        self.assertEqual(done['state'], 'resolved')
        queue = self.enqueue(run='new-run')
        self.assertEqual(next(iter(queue['items'].values()))['state'], 'resolved')
        next_quarter = self.enqueue(run='quarter-run', now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(len(next_quarter['items']), 2)
        self.assertEqual(next_quarter['counts'], {'pending': 1, 'resolved': 1})

    def test_new_failure_after_resolution_reopens_with_original_attempt_budget(self):
        self.enqueue()
        item = repair.claim_batch(self.root, 'worker', now=self.now)[0]
        repair.finish(self.root, item['item_id'], item['lease_token'], 'resolved',
                      'Verified fixture recovery.', [{'source_url':'https://example.com/calendar'}], now=self.now)
        queue = self.enqueue(run='regression', now=self.now + timedelta(hours=1))
        reopened = next(iter(queue['items'].values()))
        self.assertEqual(reopened['state'], 'pending')
        self.assertEqual(reopened['attempts'], 1)
        self.assertEqual(reopened['history'][-1]['action'], 'failure_recurred')

    def test_third_explicit_retry_is_blocked(self):
        self.enqueue()
        for n in range(3):
            item = repair.claim_batch(self.root, 'worker', now=self.now)[0]
            result = repair.finish(self.root, item['item_id'], item['lease_token'], 'pending',
                                   'Temporary fixture error persists.', now=self.now)
        self.assertEqual(result['state'], 'blocked')

    def test_extract_only_observed_failures_from_calendar(self):
        payload = {'checked_issuer_ids': ['issuer:checked'], 'provider_refreshed': False,
                   'provider': {'status': 'network_error', 'source_url': 'https://example.com/provider'},
                   'coverage': [
                       {'issuer_id': 'issuer:checked', 'issuer_source_status': 'checked',
                        'source_attempts': [{'url': 'https://example.com/bad', 'status': 'http_404'},
                                            {'url': 'https://example.com/good', 'status': 'fetched'}]},
                       {'issuer_id': 'issuer:unchecked', 'issuer_source_status': 'worker_error', 'source_attempts': []}]}
        found = repair.failures_from(payload, 'calendar')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['code'], 'http_404')
        del payload['checked_issuer_ids']; del payload['provider_refreshed']
        self.assertEqual(len(repair.failures_from(payload, 'calendar')), 3)

    def test_collection_filters_optional_absence(self):
        payload = {'gaps': [self.failure, dict(self.failure, code='full_transcript_not_observed_this_run')]}
        self.assertEqual(repair.failures_from(payload, 'collection'), [self.failure])
        invalid = dict(self.failure, code='invalid_submissions_response')
        self.assertEqual(repair.failures_from({'gaps':[invalid]}, 'collection'), [invalid])

    def test_explicit_run_and_timezone_required(self):
        with self.assertRaises(ValueError):
            self.enqueue(run='')
        with self.assertRaises(ValueError):
            self.enqueue(now=datetime(2026, 9, 20))
        with self.assertRaises(ValueError):
            self.enqueue([dict(self.failure, source_url='https://user:secret@example.com/')])


if __name__ == '__main__':
    unittest.main()
