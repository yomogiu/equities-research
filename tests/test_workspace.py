"""Offline contracts for the private workspace; every issuer and quote is fictitious."""
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research import freshness, handoffs, library, workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.text = ('Fictitious Example FY2026-Q3. Revenue was USD 100 million. '
                     '收入增加。これは架空の資料です。 가상의 자료입니다.\n' * 12)
        self.raw = b'%PDF-1.4 fictitious fixture, not a real filing'
        self.iid = 'sec:0000000042'
        self.write_bytes('sources/report.pdf.gz', gzip.compress(self.raw))
        self.write_bytes('sources/report.txt.gz', gzip.compress(self.text.encode()))
        self.document = {'raw_path': 'sources/report.pdf.gz', 'raw_sha256': library.sha(self.raw),
                         'text_path': 'sources/report.txt.gz', 'text_sha256': library.sha(self.text.encode()),
                         'url': 'https://example.com/fictitious-report', 'kind': 'release',
                         'retrieved_at': datetime.now(timezone.utc).isoformat(),
                         'title': 'Fictitious Example FY2026-Q3', 'report_date': '2026-09-30'}
        self.audit = {'results': [{'issuer_id': self.iid, 'issuer': 'Fictitious Example',
                      'symbol': 'FAKE', 'exchange': 'TEST', 'identity_status': 'verified',
                      'monitoring_eligible': True, 'documents': [self.document]}]}
        library.save(self.root / 'audit.json', self.audit)
        library.save(self.root / 'config.json', {'enabled': False})
        self.cat = library.build_catalog(self.root, 'audit.json')
        self.did = next(iter(self.cat['documents']))

    def write_bytes(self, relative, body):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def qualification(self, **changes):
        value = {'document_id': self.did, 'text_sha256': library.sha(self.text.encode()),
                 'kind': 'release', 'period': 'FY2026-Q3', 'publisher_type': 'issuer',
                 'completeness': 'full', 'language': 'en', 'english_coverage': 'full',
                 'reviewer_session': 'qualification-review', 'rationale': 'Fictitious title states fiscal quarter.',
                 'source_accepted': True, 'source_spans': [{'start': 0, 'end': 27, 'text': self.text[:27]}]}
        value.update(changes)
        return value

    def packet(self, **qualification_changes):
        q = library.qualify(self.root, self.qualification(**qualification_changes))
        return library.make_packet(self.root, self.iid, 'FY2026-Q3', [q['qualification_id']])

    def plan(self, translated=False, max_revisions=2):
        p = self.packet(**({'language': 'zh', 'english_coverage': 'partial'} if translated else {}))
        return handoffs.create_plan(self.root, p, max_revisions=max_revisions)

    def enabled(self):
        library.save(self.root / 'config.json', {'enabled': True})

    def current(self, plan):
        return library.read_json(handoffs.plan_path(self.root, plan['plan_id']))

    def role_task(self, plan, role, revision=0):
        return next(t for t in self.current(plan)['tasks'].values()
                    if t['role'] == role and t['revision'] == revision)

    def claim(self, plan, role, worker=None, revision=0):
        t = self.role_task(plan, role, revision)
        verifier = lambda root, paths: {'verified_commit': 'fictitious-local-test', 'paths': paths}
        return handoffs.claim(self.root, plan['plan_id'], t['task_id'], worker or role + '-session',
                              verifier=verifier, publisher=lambda root, plan, event: {'verified_commit': 'fictitious-local-test'})['task']

    def complete(self, plan, task, content):
        return handoffs.complete(self.root, plan['plan_id'], task['task_id'], task['lease_token'], content)

    def extraction(self, plan):
        doc = handoffs.packet_for(self.root, plan)['documents'][0]
        return {'quotes': [{'document_id': doc['document_id'], 'text': 'Revenue was USD 100 million.',
                            'speaker': 'Fictitious issuer', 'locator': 'first paragraph'}],
                'data': [], 'gaps': ['Transcript unavailable'], 'report_markdown': 'Fictitious extraction.'}

    def commentary(self, plan):
        doc = handoffs.packet_for(self.root, plan)['documents'][0]
        return {'commentary': [{'classification': 'company_claim', 'claim': 'Fictitious issuer reports revenue.',
                                'document_ids': [doc['document_id']], 'locators': ['first paragraph']}],
                'contradictions': [], 'questions': [], 'framework_coverage': {'valuation': 'unavailable'},
                'report_markdown': 'Fictitious commentary; valuation unavailable.'}

    def review(self, verdict='pass', translation=False):
        names = (['meaning', 'numbers_units_periods', 'attribution', 'coverage'] if translation else
                 ['identity_period_scope', 'evidence_fidelity', 'counterevidence', 'role_framework', 'actionable_review'])
        return {'verdict': verdict, 'findings': ([] if verdict == 'pass' else [
                    {'target': 'extractor', 'severity': 'material', 'claim': 'Fictitious quote needs context.',
                     'evidence': 'Fictitious fixture first paragraph.', 'required_change': 'Include context.', 'document_ids': []}]),
                'criteria': {name: {'status': 'pass' if verdict == 'pass' else 'fail',
                                    'evidence': 'Checked fictitious original and output.'} for name in names},
                'report_markdown': 'Fictitious independent review.'}

    def test_cache_revalidation_preserves_retrieval_date_and_binds_exact_bytes(self):
        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        self.document['retrieved_at'] = old
        library.save(self.root / 'audit.json', self.audit)
        cache = {self.document['url']: {'sha256': library.sha(self.raw),
                 'checked_at': datetime.now(timezone.utc).timestamp(),
                 'last_modified': 'Wed, 01 Jul 2026 00:00:00 GMT', 'etag': 'fictitious-v1'}}
        library.save(self.root / 'collection/http-cache.json', cache)
        library.build_catalog(self.root, 'audit.json')
        packet = self.packet()
        doc = packet['documents'][0]
        self.assertEqual(doc['retrieved_at'], old)
        self.assertEqual(doc['etag'], 'fictitious-v1')
        self.assertEqual(doc['source_check_status'], 'verified')
        self.assertEqual(freshness.assess_packet(packet)['status'], 'ready')
        cache[self.document['url']]['sha256'] = '0' * 64
        library.save(self.root / 'collection/http-cache.json', cache)
        library.build_catalog(self.root, 'audit.json')
        changed = self.packet()
        self.assertEqual(changed['documents'][0]['source_check_status'], 'content_changed')
        self.assertIsNone(changed['documents'][0]['checked_at'])
        self.assertEqual(freshness.assess_packet(changed)['status'], 'recheck_required')
        self.assertNotEqual(packet['packet_id'], changed['packet_id'])
        # A rebuilt catalog never mutates the historical packet/snapshot.
        self.assertEqual(library.materialize(self.root, packet)['documents'][0]['etag'], 'fictitious-v1')

    def test_missing_retrieval_time_is_not_inferred_from_audit_build_time(self):
        self.document.pop('retrieved_at')
        self.audit['generated_at'] = datetime.now(timezone.utc).isoformat()
        library.save(self.root / 'audit.json', self.audit)
        library.build_catalog(self.root, 'audit.json')
        packet = self.packet()
        self.assertIsNone(packet['documents'][0]['retrieved_at'])
        self.assertEqual(freshness.assess_packet(packet)['documents'][0]['status'], 'unknown')
        self.assertIn('text', library.materialize(self.root, packet)['documents'][0])

    def test_packet_timestamps_cannot_be_rewritten_with_a_new_packet_hash(self):
        packet = self.packet()
        packet['documents'][0]['retrieved_at'] = '2099-01-01T00:00:00+00:00'
        packet['packet_id'] = library.digest({k:v for k,v in packet.items() if k != 'packet_id'})
        with self.assertRaisesRegex(ValueError, 'timestamps differ'):
            library.materialize(self.root, packet)

    def test_freshness_is_rechecked_at_claim_before_remote_write_or_lease(self):
        plan = self.plan()
        self.enabled()
        verifier, publisher = unittest.mock.Mock(), unittest.mock.Mock()
        later = datetime.now(timezone.utc) + timedelta(hours=25)
        original = freshness.assess_packet
        with patch('research.handoffs.assess_packet', side_effect=lambda p, c: original(p, c, now=later)):
            with self.assertRaisesRegex(ValueError, 'freshness requires source recheck'):
                handoffs.claim(self.root, plan['plan_id'], self.role_task(plan, 'extractor')['task_id'],
                               'extractor-session', verifier=verifier, publisher=publisher)
        verifier.assert_not_called()
        publisher.assert_not_called()
        self.assertEqual(self.current(plan)['status'], 'prepared')
        task = self.claim(plan, 'extractor')
        self.assertEqual(task['freshness_receipt']['status'], 'ready')
        self.assertIn(f"library/snapshots/{self.cat['catalog_id']}.json", task['input_receipt']['paths'])

    def test_fresh_source_alias_is_selected_and_old_packet_remains_readable(self):
        fresh = copy.deepcopy(self.document)
        fresh['url'] = 'https://example.com/fresh-alias'
        self.document['retrieved_at'] = '2000-01-01T00:00:00+00:00'
        self.audit['results'][0]['documents'].append(fresh)
        library.save(self.root / 'audit.json', self.audit)
        library.build_catalog(self.root, 'audit.json')
        packet = self.packet()
        self.assertEqual(packet['documents'][0]['source_url'], fresh['url'])
        for key in ['catalog_id', 'freshness_policy']:
            packet.pop(key)
        packet['packet_id'] = library.digest({k:v for k,v in packet.items() if k != 'packet_id'})
        self.assertEqual(library.materialize(self.root, packet)['freshness']['status'], 'recheck_required')

    def test_gzip_import_deduplicates_legacy_and_audit_with_provenance(self):
        self.write_bytes('collection/raw/report.pdf', self.raw)
        self.write_bytes('collection/text/report.txt', self.text.encode())
        legacy = {**self.document, 'issuer_id': 'cik-42', 'document_id': 'legacy-fixture',
                  'raw_path': 'raw/report.pdf', 'text_path': 'text/report.txt'}
        library.save(self.root / 'collection/manifests/legacy.json', legacy)
        library.save(self.root / 'collection/document-index.json',
                     {'legacy-fixture': {'manifest_path': 'manifests/legacy.json'}})
        cat = library.build_catalog(self.root, 'audit.json')
        self.assertEqual((cat['input_records'], cat['deduplicated_records'], len(cat['documents'])), (2, 1, 1))
        doc = next(iter(cat['documents'].values()))
        self.assertEqual(doc['collector_ids'], ['legacy-fixture'])
        self.assertEqual(len(doc['sources']), 2)
        self.assertEqual(library.document_text(self.root, doc), self.text)
        self.assertEqual(cat['catalog_id'], library.build_catalog(self.root, 'audit.json')['catalog_id'])

    def test_audit_document_url_takes_precedence_over_discovery_page(self):
        self.audit['results'][0]['documents'][0].update(
            url='https://example.com/documents/fictitious-quarter.pdf',
            source_url='https://example.com/investor-relations',
            final_url='https://cdn.example.com/fictitious-quarter.pdf')
        library.save(self.root / 'audit.json', self.audit)
        cat = library.build_catalog(self.root, 'audit.json')
        source = cat['documents'][self.did]['sources'][0]
        self.assertEqual(source['source_url'], 'https://example.com/documents/fictitious-quarter.pdf')
        self.assertEqual(source['discovery_url'], 'https://example.com/investor-relations')
        self.assertEqual(source['final_url'], 'https://cdn.example.com/fictitious-quarter.pdf')
        self.assertEqual(library.read_span(self.root, self.did, 0, 27)['source_url'], source['source_url'])

    def test_null_ticker_does_not_break_known_ticker_lookup_or_search(self):
        self.audit['results'].insert(0, {'issuer_id': 'fictitious:unresolved', 'issuer': 'Fictitious Unlisted',
            'symbol': None, 'exchange': None, 'identity_status': 'unresolved',
            'monitoring_eligible': False, 'documents': []})
        library.save(self.root / 'audit.json', self.audit)
        cat = library.build_catalog(self.root, 'audit.json')
        self.assertEqual(library.resolve_issuer(cat, 'fake'), self.iid)
        self.assertEqual(library.resolve_issuer(cat, 'cik-42'), self.iid)
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            library.resolve_issuer(cat, 'MISSING')
        output = io.StringIO()
        with patch('sys.argv', ['workspace', '--root', str(self.root), 'list', '--issuer', 'FAKE']), contextlib.redirect_stdout(output):
            workspace.main()
        self.assertEqual(json.loads(output.getvalue())[0]['document_id'], self.did)
        library.build_search(self.root)
        self.assertEqual(library.search(self.root, 'Revenue', issuer='FAKE')[0]['document_id'], self.did)

    def test_hash_corruption_is_rejected_without_replacing_catalog(self):
        before = (self.root / 'library/catalog.json').read_bytes()
        self.write_bytes('sources/report.txt.gz', gzip.compress(b'changed source'))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            library.build_catalog(self.root, 'audit.json')
        self.assertEqual((self.root / 'library/catalog.json').read_bytes(), before)

    def test_private_paths_reject_escape_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root / 'escape').symlink_to(Path(other), target_is_directory=True)
            for path in ['../outside.txt', str(Path(other) / 'file'), 'escape/file']:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'escapes'):
                    library.resolve(self.root, path)
        with self.assertRaisesRegex(ValueError, 'outside the public'):
            library.private_root(library.PUBLIC_ROOT / 'private-fixture')

    def test_unicode_literal_search_and_exact_spans(self):
        library.build_search(self.root)
        for query in ['收入增加', '架空', '가상의']:
            hits = library.search(self.root, query, issuer='cik-42', literal=True)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]['document_id'], self.did)
        start = self.text.index('收入增加')
        span = library.read_span(self.root, self.did, start, start + 4)
        self.assertEqual(span['text'], '收入增加')
        self.assertEqual(span['text_sha256'], library.sha(self.text.encode()))
        self.assertEqual(library.search(self.root, 'Revenue')[0]['document_id'], self.did)
        for start, end in [(-1, 5), (0, len(self.text) + 1), (1, 1)]:
            with self.assertRaises(ValueError):
                library.read_span(self.root, self.did, start, end)

    def test_stale_search_catalog_is_rejected(self):
        library.build_search(self.root)
        changed = copy.deepcopy(self.cat)
        changed['catalog_id'] = 'different-catalog'
        library.save(self.root / 'library/catalog.json', changed)
        with self.assertRaisesRegex(ValueError, 'stale search'):
            library.search(self.root, 'Revenue')

    def test_period_qualification_requires_exact_evidence_and_explicit_fiscal_period(self):
        for change in [{'period': '2026-09-30'}, {'text_sha256': 'wrong'},
                       {'source_spans': [{'start': 0, 'end': 5, 'text': 'wrong'}]}, {'source_accepted': False}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                library.qualify(self.root, self.qualification(**change))
        q = library.qualify(self.root, self.qualification(period='FY2026-Q2'))
        with self.assertRaisesRegex(ValueError, 'Unrelated period'):
            library.make_packet(self.root, self.iid, 'FY2026-Q3', [q['qualification_id']])
        annual = library.qualify(self.root, self.qualification(period='FY2025', kind='annual_background'))
        packet = library.make_packet(self.root, self.iid, 'FY2026-Q3', [annual['qualification_id']])
        with self.assertRaisesRegex(ValueError, 'No evidence for requested fiscal period'):
            handoffs.create_plan(self.root, packet)

    def test_same_fiscal_year_annual_report_cannot_enter_earlier_quarter_packet(self):
        qualification = library.qualify(self.root, self.qualification(kind='annual_background', period='FY2026'))
        for period in ['FY2026-Q1', 'FY2026-H1', 'FY2026-Q4']:
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, 'same-year annual background'):
                library.make_packet(self.root, self.iid, period, [qualification['qualification_id']])
        annual = library.make_packet(self.root, self.iid, 'FY2026', [qualification['qualification_id']])
        self.assertEqual(annual['documents'][0]['period'], 'FY2026')
        prior_background = library.make_packet(self.root, self.iid, 'FY2027-Q1', [qualification['qualification_id']])
        self.assertEqual(prior_background['documents'][0]['period'], 'FY2026')

    def test_materialization_rejects_tampered_qualification_and_raw_source(self):
        packet = self.packet()
        doc = packet['documents'][0]
        path = self.root / f"library/qualifications/{doc['qualification_id']}.json"
        original_qualification = path.read_bytes()
        changed = json.loads(original_qualification)
        changed['english_coverage'] = 'none'
        library.save(path, changed)
        with self.assertRaisesRegex(ValueError, 'Qualification hash mismatch'):
            library.materialize(self.root, packet)
        path.write_bytes(original_qualification)
        self.write_bytes('sources/report.pdf.gz', gzip.compress(b'changed original PDF bytes'))
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            library.materialize(self.root, packet)

    def test_materialization_rejects_inconsistent_document_id_even_with_valid_packet_hash(self):
        packet = self.packet()
        packet['documents'][0]['document_id'] = '0' * 64
        packet['packet_id'] = library.digest({key: value for key, value in packet.items() if key != 'packet_id'})
        with self.assertRaisesRegex(ValueError, 'Inconsistent evidence document ID'):
            library.materialize(self.root, packet)

    def test_packets_are_immutable_and_materialization_checks_source_hash(self):
        packet = self.packet()
        self.assertEqual(packet['packet_id'], self.packet()['packet_id'])
        expanded = library.materialize(self.root, packet)
        self.assertEqual(expanded['documents'][0]['text'], self.text)
        with self.assertRaisesRegex(ValueError, 'collision'):
            library.save(self.root / f"library/packets/{packet['packet_id']}.json", {'changed': True}, immutable=True)
        altered = copy.deepcopy(packet)
        altered['period'] = 'FY2026-Q4'
        with self.assertRaisesRegex(ValueError, 'Packet hash mismatch'):
            library.materialize(self.root, altered)
        self.write_bytes('sources/report.txt.gz', gzip.compress(b'changed'))
        with self.assertRaisesRegex(ValueError, 'Source hash mismatch'):
            library.materialize(self.root, packet)

    def test_disabled_execution_prevents_claim_before_remote_lookup(self):
        plan = self.plan()
        verifier = unittest.mock.Mock()
        with self.assertRaisesRegex(ValueError, 'disabled'):
            handoffs.claim(self.root, plan['plan_id'], self.role_task(plan, 'extractor')['task_id'],
                           'extractor-session', verifier=verifier)
        verifier.assert_not_called()
        self.assertEqual(self.current(plan)['status'], 'prepared')

    def test_lease_reclaim_fences_old_worker_and_limits_attempts(self):
        plan = self.plan()
        self.enabled()
        with patch('research.handoffs.time.time', return_value=1000):
            original = self.claim(plan, 'extractor', 'worker-one')
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                self.claim(plan, 'extractor', 'worker-two')
        with patch('research.handoffs.time.time', return_value=3000):
            replacement = self.claim(plan, 'extractor', 'worker-two')
            self.assertNotEqual(original['lease_token'], replacement['lease_token'])
            with self.assertRaisesRegex(ValueError, 'incorrect lease'):
                self.complete(plan, original, self.extraction(plan))
            handoffs.interrupt(self.root, plan['plan_id'], replacement['task_id'], replacement['lease_token'], 'Fixture retry')
            final = self.claim(plan, 'extractor', 'worker-three')
            stopped = handoffs.interrupt(self.root, plan['plan_id'], final['task_id'], final['lease_token'], 'Fixture unavailable')
            self.assertEqual(stopped['status'], 'blocked')
        self.assertEqual(self.current(plan)['status'], 'needs_attention')

    def test_authors_and_reviewers_require_distinct_sessions(self):
        plan = self.plan()
        self.enabled()
        extract = self.claim(plan, 'extractor', 'author-one')
        with self.assertRaisesRegex(ValueError, 'separate sessions'):
            self.claim(plan, 'commentator', 'author-one')
        with self.assertRaisesRegex(ValueError, 'Dependencies incomplete'):
            self.claim(plan, 'reviewer', 'independent-review')
        self.complete(plan, extract, self.extraction(plan))
        commentary = self.claim(plan, 'commentator', 'author-two')
        self.complete(plan, commentary, self.commentary(plan))
        for worker in ['author-one', 'author-two']:
            with self.assertRaisesRegex(ValueError, 'separate session'):
                self.claim(plan, 'reviewer', worker)
        review = self.claim(plan, 'reviewer', 'independent-review')
        receipt = self.complete(plan, review, self.review())
        self.assertEqual(receipt['plan_status'], 'reviewed_locally')
        self.assertEqual(receipt['persistence'], 'not_yet_verified')

    def test_translation_coverage_and_independent_review_gate_authors(self):
        plan = self.plan(translated=True)
        self.enabled()
        p = handoffs.packet_for(self.root, plan)
        doc = p['documents'][0]
        translation = {'document_id': doc['document_id'], 'source_sha256': doc['text_sha256'],
                       'source_language': 'zh', 'target_language': 'en', 'translator_version': 'fictitious-v1',
                       'segments': [{'start': 0, 'end': 27, 'original_text': self.text[:27],
                                     'english_text': 'Fictitious example FY2026 Q3.', 'label': 'translation'}],
                       'untranslated_ranges': [{'start': 27, 'end': len(self.text)}]}
        handoffs.check_translation(translation, p, doc['document_id'])
        for start in [26, 28]:
            broken = copy.deepcopy(translation)
            broken['untranslated_ranges'][0]['start'] = start
            with self.assertRaisesRegex(ValueError, 'gaps or overlaps'):
                handoffs.check_translation(broken, p, doc['document_id'])
        author = self.claim(plan, 'translation', 'translator')
        self.complete(plan, author, translation)
        with self.assertRaisesRegex(ValueError, 'Dependencies incomplete'):
            self.claim(plan, 'extractor')
        with self.assertRaisesRegex(ValueError, 'separate session'):
            self.claim(plan, 'translation_review', 'translator')
        reviewer = self.claim(plan, 'translation_review', 'language-reviewer')
        invalid = self.review(translation=True)
        invalid['criteria']['coverage']['status'] = 'unavailable'
        with self.assertRaisesRegex(ValueError, 'incomplete criteria'):
            self.complete(plan, reviewer, invalid)
        self.complete(plan, reviewer, self.review(translation=True))
        extractor = self.role_task(plan, 'extractor')
        claimed = handoffs.claim(self.root, plan['plan_id'], extractor['task_id'], 'extractor-session',
                                verifier=lambda root, paths: {'paths': paths},
                                publisher=lambda root, plan, event: {'verified_commit': 'fixture'})
        accepted = claimed['accepted_translations'][doc['document_id']]
        self.assertEqual(accepted['task_id'], author['task_id'])
        self.assertEqual(accepted['revision'], 0)
        self.assertEqual(claimed['task']['status'], 'running')

    def test_review_repair_is_targeted_and_bounded(self):
        plan = self.plan(max_revisions=1)
        self.enabled()
        self.complete(plan, self.claim(plan, 'extractor'), self.extraction(plan))
        self.complete(plan, self.claim(plan, 'commentator'), self.commentary(plan))
        self.complete(plan, self.claim(plan, 'reviewer'), self.review('revise'))
        current = self.current(plan)
        revised = [t for t in current['tasks'].values() if t['revision'] == 1]
        self.assertEqual({t['role'] for t in revised}, {'extractor', 'reviewer'})
        with self.assertRaisesRegex(ValueError, 'reuse a reviewer session'):
            self.claim(plan, 'extractor', worker='reviewer-session', revision=1)
        author = self.claim(plan, 'extractor', revision=1)
        self.complete(plan, author, self.extraction(plan))
        reviewer = self.claim(plan, 'reviewer', revision=1)
        receipt = self.complete(plan, reviewer, self.review('revise'))
        self.assertEqual(receipt['plan_status'], 'needs_attention')
        self.assertEqual(max(t['revision'] for t in self.current(plan)['tasks'].values()), 1)

    def test_expired_third_lease_requires_attention(self):
        plan = self.plan()
        self.enabled()
        for instant in [1000, 3000, 5000]:
            with patch('research.handoffs.time.time', return_value=instant):
                self.claim(plan, 'extractor')
        with patch('research.handoffs.time.time', return_value=7000):
            with self.assertRaisesRegex(ValueError, 'retry budget exhausted'):
                self.claim(plan, 'extractor')
        self.assertEqual(self.current(plan)['status'], 'needs_attention')
        self.assertEqual(self.role_task(plan, 'extractor')['status'], 'blocked')

    def test_publish_failure_does_not_dispatch_or_allow_duplicate_claim(self):
        plan = self.plan()
        self.enabled()
        extractor = self.role_task(plan, 'extractor')
        publisher = unittest.mock.Mock(side_effect=RuntimeError('Fictitious remote failure'))
        with self.assertRaisesRegex(RuntimeError, 'remote failure'):
            handoffs.claim(self.root, plan['plan_id'], extractor['task_id'], 'first-worker',
                           verifier=lambda root, paths: {'paths': paths}, publisher=publisher)
        publisher.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'already claimed'):
            self.claim(plan, 'extractor', 'second-worker')

    def test_claim_is_published_before_dispatch_to_worker(self):
        plan = self.plan()
        self.enabled()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)
        with tempfile.TemporaryDirectory() as remote:
            subprocess.run(['git', 'init', '--bare', remote], check=True, capture_output=True)
            git('init', '-b', 'main')
            git('config', 'user.name', 'Fictitious Test')
            git('config', 'user.email', 'fixture@example.invalid')
            git('add', '.')
            git('commit', '-m', 'Fictitious plan and evidence')
            git('remote', 'add', 'origin', remote)
            git('push', '-u', 'origin', 'main')
            before = git('rev-parse', 'HEAD').decode().strip()
            extractor = self.role_task(plan, 'extractor')
            claimed = handoffs.claim(self.root, plan['plan_id'], extractor['task_id'], 'independent-fixture-worker')
            after = git('rev-parse', 'HEAD').decode().strip()
            self.assertNotEqual(before, after)
            self.assertEqual(claimed['claim_persistence']['verified_commit'], after)
            self.assertEqual(git('ls-remote', 'origin', 'refs/heads/main').decode().split()[0], after)
            path = str(handoffs.plan_path(self.root, plan['plan_id']).relative_to(self.root))
            published_plan = json.loads(git('show', after + ':' + path))
            self.assertEqual(published_plan['tasks'][extractor['task_id']]['lease_token'], claimed['task']['lease_token'])

    def test_cli_lists_fictitious_ticker_and_reads_unicode_span(self):
        output = io.StringIO()
        with patch('sys.argv', ['workspace', '--root', str(self.root), 'list', '--issuer', 'fake']), contextlib.redirect_stdout(output):
            workspace.main()
        self.assertEqual(json.loads(output.getvalue())[0]['document_id'], self.did)
        output = io.StringIO()
        with patch('sys.argv', ['workspace', '--root', str(self.root), 'read', self.did, '--end', '27']), contextlib.redirect_stdout(output):
            workspace.main()
        self.assertEqual(json.loads(output.getvalue())['text'], self.text[:27])

    def test_remote_verifier_checks_remote_head_and_exact_artifact_bytes(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)
        with tempfile.TemporaryDirectory() as remote:
            subprocess.run(['git', 'init', '--bare', remote], check=True, capture_output=True)
            git('init', '-b', 'main')
            git('config', 'user.name', 'Fictitious Test')
            git('config', 'user.email', 'fixture@example.invalid')
            git('add', 'audit.json')
            git('commit', '-m', 'Fictitious fixture')
            git('remote', 'add', 'origin', remote)
            git('push', '-u', 'origin', 'main')
            receipt = handoffs.verify_remote(self.root, ['audit.json'])
            self.assertEqual(receipt['verified_commit'], git('rev-parse', 'HEAD').decode().strip())
            (self.root / 'audit.json').write_text('changed bytes')
            with self.assertRaisesRegex(ValueError, 'not persisted'):
                handoffs.verify_remote(self.root, ['audit.json'])
            git('add', 'audit.json')
            git('commit', '-m', 'Not yet pushed')
            with self.assertRaisesRegex(ValueError, 'push private main'):
                handoffs.verify_remote(self.root, ['audit.json'])


if __name__ == '__main__':
    unittest.main()
