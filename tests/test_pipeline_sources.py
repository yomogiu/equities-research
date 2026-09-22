"""Fictitious fixtures for full-universe source approval boundaries."""
import json
import tempfile
import unittest
from pathlib import Path

from research.pipeline_sources import prepare


def company(n, **values):
    return {'issuer_id': f'sec:{n:010d}', 'symbol': f'FAKE{n}',
            'issuer': f'Fictitious Company {n}', 'exchange': 'Fictitious Exchange',
            'regulator_id': f'{n:010d}', 'identity_status': 'verified_sec_directory',
            'monitoring_eligible': True, **values}


class PipelineSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('inputs/watchlist.catalog.json', {'companies': [company(1), company(2), company(3, monitoring_eligible=False)]})

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def test_all_verified_companies_get_sec_and_blocked_remain_accounted(self):
        result = prepare(self.root)
        self.assertEqual(len(result['universe']), 2)
        self.assertEqual(len(result['coverage']), 3)
        self.assertEqual(result['coverage'][0]['collector_issuer_id'], 'cik-0000000001')
        self.assertEqual(result['coverage'][1]['reason'], 'sec_only')
        self.assertEqual(result['coverage'][2]['status'], 'blocked')
        self.assertIsNone(result['coverage'][2]['collector_issuer_id'])
        self.assertEqual(json.loads((self.root/'pipeline/collection-watchlist.json').read_text()), result['universe'])

    def test_observed_pages_and_saved_documents_do_not_authorize_hosts(self):
        self.write('inputs/calendar-sources.json', {'issuers': {'sec:0000000001': {'pages': [
            {'url': 'https://observed.example.com/results', 'trust': 'observed_candidate'},
            {'url': 'https://reviewed-claim.example.com/results', 'trust': 'reviewed_issuer_source'}]}}})
        self.write('library/catalog.json', {'documents': {'fake': {'issuer_id': 'sec:0000000001',
                   'sources': [{'source_url': 'https://untrusted.example.com/report.pdf'}]}}})
        result = prepare(self.root, persist=False)
        self.assertEqual(result['registry']['issuers']['FAKE1']['pages'], [])
        self.assertEqual(len(result['coverage'][0]['candidate_sources']), 3)
        self.assertFalse((self.root/'pipeline').exists())

    def test_existing_sources_and_verified_override_approve_only_exact_hosts(self):
        self.write('inputs/source-registry.json', {'schema_version': 1, 'issuers': {'FAKE1': {
            'cik': '1', 'allowed_hosts': ['cdn.example.com'],
            'pages': [{'url': 'https://issuer.example.com/results'}],
            'documents': [{'url': 'https://cdn.example.com/release.pdf', 'kind': 'release'}]}}})
        self.write('inputs/calendar-source-overrides.json', {'issuers': {'sec:0000000001': {'pages': [
            {'url': 'https://reviewed.example.com/results', 'issuer_verified': True},
            {'url': 'https://pending.example.com/results', 'issuer_verified': False}]}}})
        self.write('inputs/calendar-sources.json', {'issuers': {'sec:0000000001': {'pages': [
            {'url': 'https://issuer.example.com/events', 'trust': 'observed_candidate'},
            {'url': 'https://sub.issuer.example.com/results', 'trust': 'observed_candidate'}]}}})
        result = prepare(self.root)
        entry = result['registry']['issuers']['FAKE1']
        self.assertEqual(len(entry['pages']), 3)
        self.assertEqual(len(entry['documents']), 1)
        self.assertNotIn('pending.example.com', entry['allowed_hosts'])
        self.assertNotIn('sub.issuer.example.com', entry['allowed_hosts'])
        self.assertEqual(len(result['coverage'][0]['candidate_sources']), 2)

    def test_source_identity_mismatch_keeps_sec_only(self):
        self.write('inputs/source-registry.json', {'schema_version': 1, 'issuers': {'FAKE1': {
            'cik': '9', 'pages': [{'url': 'https://wrong.example.com/results'}]}}})
        result = prepare(self.root)
        self.assertEqual(result['registry']['issuers']['FAKE1']['pages'], [])
        self.assertIn('configured_source_identity_mismatch', result['coverage'][0]['source_issues'])
        self.assertEqual(result['coverage'][0]['reason'], 'sec_only')

    def test_approved_source_does_not_promote_unresolved_identity(self):
        self.write('inputs/calendar-source-overrides.json', {'issuers': {'sec:0000000003': {'pages': [
            {'url': 'https://reviewed.example.com/results', 'issuer_verified': True}]}}})
        result = prepare(self.root)
        self.assertNotIn('FAKE3', result['registry']['issuers'])
        self.assertEqual(result['coverage'][2]['status'], 'blocked')

    def test_verified_foreign_requires_source_and_preserves_stable_mapping(self):
        foreign = company(4, issuer_id='issuer:fictitiousforeign', regulator_id=None,
                          identity_status='verified_non_us_listing', exchange='Fictitious Foreign Exchange')
        self.write('inputs/watchlist.catalog.json', {'companies': [foreign]})
        self.assertEqual(prepare(self.root)['coverage'][0]['reason'], 'verified_listing_needs_approved_source')
        self.write('inputs/calendar-source-overrides.json', {'issuers': {'issuer:fictitiousforeign': {'pages': [
            {'url': 'https://foreign.example.com/results', 'issuer_verified': True}]}}})
        result = prepare(self.root)
        self.assertEqual(result['universe'][0]['exchange'], 'Fictitious Foreign Exchange')
        self.assertEqual(result['coverage'][0]['issuer_id'], 'issuer:fictitiousforeign')
        self.assertTrue(result['coverage'][0]['collector_issuer_id'])
        self.assertNotIn('regulator_id', result['universe'][0])

    def test_invalid_regulator_and_duplicate_symbol_fail_closed(self):
        self.write('inputs/watchlist.catalog.json', {'companies': [company(1), company(2, symbol='FAKE1'),
                    company(3, regulator_id='not-cik'), company(4, issuer_id='sec:0000009999')]})
        result = prepare(self.root)
        self.assertEqual(result['universe'], [])
        self.assertEqual([r['reason'] for r in result['coverage']], [
            'duplicate_symbol_requires_collector_identity_review', 'duplicate_symbol_requires_collector_identity_review',
            'invalid_regulator_identity', 'conflicting_stable_regulator_identity'])

    def test_credential_urls_cannot_enter_registry(self):
        self.write('inputs/calendar-source-overrides.json', {'issuers': {'sec:0000000001': {'pages': [
            {'url': 'https://example.com/results?token=secret', 'issuer_verified': True}]}}})
        result = prepare(self.root)
        self.assertEqual(result['registry']['issuers']['FAKE1']['pages'], [])
        self.assertEqual(result['coverage'][0]['candidate_sources'], [])

    def test_duplicate_stable_identity_rejected(self):
        self.write('inputs/watchlist.catalog.json', {'companies': [company(1), company(1)]})
        with self.assertRaisesRegex(ValueError, 'Duplicate tracked'):
            prepare(self.root)


if __name__ == '__main__':
    unittest.main()
