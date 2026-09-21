"""Calendar invariants using fictitious issuers and offline source responses."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_calendar as cal
from research.library import save


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 9, 20)
        self.owner = {'issuer_id': 'fictitious:example', 'issuer': 'Fictitious Example Inc',
                      'symbol': 'FAKE', 'exchange': 'Nasdaq', 'monitoring_eligible': True,
                      'identity_status': 'verified_fixture'}

    def event(self, day='2026-10-20', **extra):
        return dict({'event_id': 'fake-event', 'issuer_id': self.owner['issuer_id'], 'event_date': day,
                     'event_type': 'results', 'report_date': day, 'call_at': None,
                     'date_status': 'confirmed', 'fiscal_period': 'FY2026-Q3',
                     'source_url': 'https://example.com/events'}, **extra)

    def test_provider_is_estimated_and_requires_eligible_unambiguous_listing(self):
        csv = b'symbol,name,reportDate,fiscalDateEnding,timeOfTheDay\nFAKE,Fictitious Example Inc,2026-10-20,2026-09-30,post-market\n'
        events, stats = cal.provider_events(csv, [self.owner], self.day)
        self.assertEqual(events[0]['date_status'], 'estimated')
        self.assertIsNone(events[0]['fiscal_period'])
        self.assertIsNone(events[0]['call_at'])
        for owners in [[dict(self.owner, monitoring_eligible=False)], [dict(self.owner, exchange='JP')], [self.owner, dict(self.owner, issuer_id='other')]]:
            self.assertEqual(cal.provider_events(csv, owners, self.day)[0], [])
        wrong = csv.replace(b'Fictitious Example Inc', b'Unrelated Business')
        self.assertEqual(cal.provider_events(wrong, [self.owner], self.day)[0][0]['date_status'], 'source_identity_review')
        with self.assertRaisesRegex(ValueError, 'CSV'):
            cal.provider_events(b'{"Information":"Quota exceeded"}', [self.owner], self.day)
        with self.assertRaisesRegex(ValueError, 'stale'):
            cal.provider_events(csv.replace(b'2026-10-20', b'2025-10-20'), [self.owner], self.day)

    def test_revised_date_and_disappeared_event_are_preserved_without_false_freshness(self):
        previous = {'events': [self.event(freshness='current', last_seen_at='previous')]}
        events, changes = cal.reconcile([self.owner], [self.event('2026-10-22')], previous, self.day)
        self.assertEqual(changes[0]['change'], 'revised')
        events, changes = cal.reconcile([self.owner], [], previous, self.day)
        self.assertEqual(events[0]['freshness'], 'not_observed_this_run')
        self.assertEqual(events[0]['last_seen_at'], 'previous')
        rows = cal.coverage_rows([self.owner], events, {}, self.day, 'network_error')
        self.assertEqual(rows[0]['status'], 'stale')
        self.assertIsNone(rows[0]['next_date'])

    def test_duplicate_observations_cannot_erase_conflicts(self):
        events, _ = cal.reconcile([self.owner], [self.event(), self.event('2026-10-21'), self.event()], {}, self.day)
        self.assertEqual(len(events), 2)
        self.assertEqual({e['date_status'] for e in events}, {'conflict'})

    def test_conflicts_across_sources_but_release_and_call_are_distinct(self):
        events, _ = cal.reconcile([self.owner], [self.event(), self.event('2026-10-21', event_id='second')], {}, self.day)
        self.assertEqual({e['date_status'] for e in events}, {'conflict'})
        events, _ = cal.reconcile([self.owner], [self.event(), self.event('2026-10-21', event_id='call', event_type='call', report_date=None)], {}, self.day)
        self.assertEqual({e['date_status'] for e in events}, {'confirmed'})

    def test_pending_identities_never_become_approved_from_a_calendar_date(self):
        pending = dict(self.owner, monitoring_eligible=False)
        events, _ = cal.reconcile([pending], [self.event()], {}, self.day)
        rows = cal.coverage_rows([pending], events, {}, self.day, 'fetched')
        self.assertEqual(rows[0]['status'], 'identity_review')
        self.assertFalse(rows[0]['monitoring_eligible'])

    def test_issuer_confirmation_requires_qualified_source_and_non_tentative_event(self):
        payload = {'@context': 'https://schema.org', '@type': 'Event', 'name': 'Fictitious FY2026-Q3 earnings call', 'startDate': '2026-10-20T16:00:00-04:00'}
        class FakeClient:
            requests, cache_hits = 1, 0
            def __init__(self, *a, **kw): pass
            def get(self, url, **kw):
                return ('<script type="application/ld+json">'+json.dumps(payload)+'</script>').encode(), {'body_path':'objects/fake.gz','sha256':'fake','checked_at':1,'final_url':url}
        entry = {'pages':[{'url':'https://example.com/events', 'issuer_verified':True}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(cal, 'CalendarClient', FakeClient):
            result = cal.scan_issuer(self.owner, entry, Path(tmp), self.day)
            self.assertEqual(result['events'][0]['date_status'], 'confirmed')
            self.assertIsNone(result['events'][0]['report_date'])
            self.assertEqual(result['events'][0]['call_at'], payload['startDate'])
            entry['pages'][0]['issuer_verified'] = False
            self.assertNotEqual(cal.scan_issuer(self.owner, entry, Path(tmp), self.day)['events'][0]['date_status'], 'confirmed')
            entry['pages'][0]['issuer_verified'] = True
            payload['name'] += ' tentative'
            self.assertEqual(cal.scan_issuer(self.owner, entry, Path(tmp), self.day)['events'][0]['date_status'], 'date_needs_review')

    def test_full_658_fixture_universe_is_accounted_for_without_network_or_analysis(self):
        owners = [dict(self.owner, issuer_id='fictitious:'+str(i), symbol='FAKE'+str(i), monitoring_eligible=i%2==0) for i in range(658)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/'inputs/universe.json', {'companies':owners})
            save(root/'inputs/sources.json', {'issuers':{r['issuer_id']:{'pages':[]} for r in owners}})
            save(root/'config.json', {'enabled':False})
            before=(root/'config.json').read_bytes()
            result=cal.run(root,'inputs/universe.json','inputs/sources.json',self.day,provider=False)
            self.assertEqual(len(result['coverage']),658)
            self.assertEqual(result['counts'],{'source_gap':329,'identity_review':329})
            self.assertEqual((root/'config.json').read_bytes(),before)
            self.assertEqual(result['requests'],0)
            self.assertFalse(result['analysis_dispatched'])
            self.assertEqual(json.loads((root/'calendar/collection-candidates.json').read_text())['events'],[])

    def test_targeted_repair_preserves_other_issuers_and_provider_evidence(self):
        second = dict(self.owner, issuer_id='fictitious:second')
        owners = [self.owner, second]
        provider = self.event(event_id='estimate', source_kind='provider_estimate', date_status='estimated', last_seen_at='old', freshness='current')
        other = self.event(event_id='other', issuer_id=second['issuer_id'], last_seen_at='old', freshness='current')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root/'inputs/universe.json', {'companies':owners})
            save(root/'inputs/sources.json', {'issuers':{r['issuer_id']:{'pages':[]} for r in owners}})
            baseline = {'events':[provider, other], 'coverage':[
                dict(issuer_id=r['issuer_id'], issuer_source_status='checked', source_attempts=[]) for r in owners],
                'provider':{'status':'fetched', 'requests':1}, 'as_of':'2026-09-19'}
            save(root/'calendar/latest.json', baseline)
            receipt = dict(issuer_id=self.owner['issuer_id'], events=[self.event(source_kind='issuer_page')],
                           source_status='checked', attempts=[], requests=1)
            with patch.object(cal, 'scan_issuer', return_value=receipt) as scan:
                result = cal.run(root,'inputs/universe.json','inputs/sources.json',self.day,
                                 provider=False,issuer_ids=[self.owner['issuer_id']])
                self.assertEqual(scan.call_count, 1)
            by_id = {e['event_id']:e for e in result['events']}
            self.assertEqual(by_id['other'], other)
            self.assertEqual(by_id['estimate'], provider)
            self.assertEqual(len(result['coverage']), 2)
            self.assertEqual(result['requests'], 1)
            self.assertEqual(result['baseline_as_of'], '2026-09-19')
            self.assertFalse(result['provider_refreshed'])


if __name__ == '__main__':
    unittest.main()
