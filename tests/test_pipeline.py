"""Fictitious scheduler and replay cases; no public-source requests."""
from datetime import datetime, timedelta, timezone
import unittest
import tempfile
from pathlib import Path
from research import library, pipeline

from research.pipeline import due_queue, update_state, select_batch

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
ROWS = [{'issuer_id': 'sec:0000000042', 'collector_issuer_id': 'cik-0000000042', 'symbol': 'FAKE'},
        {'issuer_id': 'issuer:unresolved', 'collector_issuer_id': None, 'symbol': 'UNKNOWN'}]


class PipelineTests(unittest.TestCase):
    def state(self, hours=3, failures=0):
        return {'issuers': {ROWS[0]['issuer_id']: {'baseline_attempted_at': NOW.isoformat(),
                'last_attempt_at': (NOW - timedelta(hours=hours)).isoformat(),
                'consecutive_failures': failures}}}

    def calendar(self, days=0, status='estimated'):
        return {'events': [{'issuer_id': ROWS[0]['issuer_id'], 'event_id': 'fictitious',
                'event_date': (NOW - timedelta(days=days)).date().isoformat(), 'date_status': status}]}

    def test_busy_earnings_window_does_not_starve_baseline(self):
        rows = [{'issuer_id': str(i), 'reason': 'earnings_window'} for i in range(100)]
        rows += [{'issuer_id': 'baseline', 'reason': 'initial_baseline'}]
        selected = select_batch(rows, 6)
        self.assertEqual(len(selected), 6)
        self.assertIn('baseline', [r['issuer_id'] for r in selected])

    def test_baseline_accounts_unseen_and_never_promotes_identity(self):
        due = due_queue(ROWS, {}, {}, {}, NOW)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]['reason'], 'initial_baseline')

    def test_calendar_window_recomputed_without_frozen_candidate_list(self):
        due = due_queue(ROWS, self.state(), self.calendar(), {}, NOW)
        self.assertEqual(due[0]['reason'], 'earnings_window')
        self.assertTrue(due[0]['calendar_dates_are_discovery_hints'])
        self.assertEqual(due_queue(ROWS, self.state(1), self.calendar(), {}, NOW), [])
        self.assertEqual(due_queue(ROWS, self.state(), self.calendar(70), {}, NOW), [])

    def test_late_documents_daily_and_unknown_dates_weekly(self):
        self.assertEqual(due_queue(ROWS, self.state(25), self.calendar(10), {}, NOW)[0]['reason'], 'late_documents')
        self.assertEqual(due_queue(ROWS, self.state(23), self.calendar(10), {}, NOW), [])
        published = {'issuers': {ROWS[0]['issuer_id']: {'packet_id': 'fictitious',
            'missing': {'transcript': {'status': 'pending', 'reason': 'Not observed'}}}}}
        self.assertEqual(due_queue(ROWS, self.state(25), self.calendar(10), published, NOW)[0]['reason'], 'late_documents')
        self.assertEqual(due_queue(ROWS, self.state(169), {}, {}, NOW)[0]['reason'], 'weekly_discovery')

    def test_bounded_failure_backoff_and_budget_deferral_do_not_finish_baseline(self):
        due = due_queue(ROWS, {}, {}, {}, NOW)
        receipt = {'issuer_results': [{'issuer_id': ROWS[0]['collector_issuer_id'], 'documents_checked': 0,
                   'budget_deferred': True, 'gap_codes': ['run_budget_exhausted']}]}
        state = update_state({}, due, receipt, NOW)
        self.assertNotIn('baseline_attempted_at', state['issuers'][ROWS[0]['issuer_id']])
        self.assertEqual(due_queue(ROWS, state, {}, {}, NOW), [])
        self.assertEqual(len(due_queue(ROWS, state, {}, {}, NOW + timedelta(hours=2))), 1)
        receipt['issuer_results'][0].update(budget_deferred=False, gap_codes=['access_blocked'])
        first = update_state({}, due, receipt, NOW)
        self.assertEqual(due_queue(ROWS, first, {}, {}, NOW + timedelta(hours=2))[0]['reason'], 'repair_retry')
        state = update_state(self.state(failures=2), due, receipt, NOW)
        self.assertEqual(state['issuers'][ROWS[0]['issuer_id']]['consecutive_failures'], 3)
        self.assertEqual(due_queue(ROWS, state, self.calendar(), {}, NOW + timedelta(days=1)), [])

    def test_unattempted_rows_not_marked_checked_and_partial_is_not_complete(self):
        due = due_queue(ROWS, {}, {}, {}, NOW)
        self.assertEqual(update_state({}, due, {'issuer_results': []}, NOW)['issuers'], {})
        receipt = {'issuer_results': [{'issuer_id': ROWS[0]['collector_issuer_id'], 'documents_checked': 1,
                   'budget_deferred': False, 'gap_codes': ['full_transcript_not_observed_this_run']}]}
        state = update_state({}, due, receipt, NOW)
        self.assertEqual(state['issuers'][ROWS[0]['issuer_id']]['status'], 'partial')
        self.assertEqual(len(due_queue(ROWS, state, {}, {}, NOW)), 0)


class PipelineIntegrationTests(unittest.TestCase):
    def test_reconcile_qualify_packet_without_network_or_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            text = 'Fictitious issuer reports FY2026-Q2 financial results. Revenue was USD 100 million. ' * 8
            (root / 'source.txt').write_text(text)
            owner = {'issuer_id': 'sec:0000000042', 'symbol': 'FAKE', 'issuer': 'Fictitious issuer',
                     'exchange': 'TEST', 'regulator_id': '0000000042', 'monitoring_eligible': True,
                     'identity_status': 'verified_sec_directory'}
            document = {'raw_path': 'source.txt', 'text_path': 'source.txt',
                        'raw_sha256': library.sha(text.encode()), 'text_sha256': library.sha(text.encode()),
                        'url': 'https://example.com/fictitious', 'kind': 'release',
                        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'title': 'Fictitious results'}
            library.save(root / 'audit.json', {'results': [dict(owner, documents=[document])]})
            library.save(root / 'languages.json', {'documents': []})
            library.save(root / 'inputs/watchlist.catalog.json', {'companies': [owner]})
            library.save(root / 'config.json', {'enabled': False, 'earnings_pipeline':
                {'enabled': True, 'audit': 'audit.json', 'languages': 'languages.json'}})
            first = pipeline.run(root, mode='reconcile')
            self.assertEqual(first['eligible'], 1)
            self.assertFalse(first['analysis_dispatched'])
            self.assertEqual(first['publication']['packets_prepared'], 0)
            doc = next(iter(library.catalog(root)['documents'].values()))
            q = library.qualify(root, {'document_id': doc['document_id'], 'text_sha256': doc['text_sha256'],
                'kind': 'release', 'period': 'FY2026-Q2', 'publisher_type': 'issuer', 'completeness': 'full',
                'language': 'en', 'english_coverage': 'full', 'reviewer_session': 'fictitious-review',
                'rationale': 'Fictitious explicit actual results statement.', 'source_accepted': True,
                'source_spans': [{'start': 0, 'end': 51, 'text': text[:51]}]})
            second = pipeline.run(root, mode='reconcile')
            self.assertEqual(second['publication']['packets_prepared'], 1)
            latest = library.read_json(root / 'published/latest.json')['issuers'][owner['issuer_id']]
            packet = library.read_json(root / f"library/packets/{latest['packet_id']}.json")
            self.assertEqual(library.materialize(root, packet)['freshness']['status'], 'ready')
            self.assertEqual(packet['availability']['transcript'], 'pending')
            self.assertEqual(pipeline.run(root, mode='reconcile')['publication']['packets_prepared'], 1)
            self.assertFalse(library.read_json(root / 'config.json')['enabled'])
