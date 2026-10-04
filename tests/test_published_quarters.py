"""Fictitious offline source evidence only; no real issuers or public requests."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from research import library, published_quarters as published


class PublishedQuarterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.iid = 'sec:0000000042'
        self.owners = [{'issuer_id': self.iid, 'issuer': 'Fictitious Example', 'symbol': 'FAKE',
                        'monitoring_eligible': True, 'identity_status': 'verified', 'documents': []}]
        library.save(self.root / 'config.json', {'enabled': False})

    def add(self, text, **changes):
        text += '\n' + ('Fictitious financial information with original numerical context. ' * 3)
        index = len(self.owners[0]['documents'])
        raw = changes.pop('raw', text.encode())
        self.root.joinpath('sources').mkdir(exist_ok=True)
        raw_path, text_path = f'sources/{index}.raw', f'sources/{index}.txt'
        self.root.joinpath(raw_path).write_bytes(raw)
        self.root.joinpath(text_path).write_text(text)
        doc = {'url': f'https://example.invalid/fictitious-{index}', 'raw_path': raw_path,
               'raw_sha256': library.sha(raw), 'text_path': text_path,
               'text_sha256': library.sha(text.encode()), 'kind': 'release', 'title': 'Fictitious evidence',
               'retrieved_at': datetime.now(timezone.utc).isoformat(), **changes}
        self.owners[0]['documents'].append(doc)
        return doc

    def catalog(self):
        library.save(self.root / 'audit.json', {'results': self.owners})
        return library.build_catalog(self.root, 'audit.json')

    def run_tracker(self):
        receipt = published.run(self.root, '2026-09-21')
        return receipt, library.read_json(self.root / 'published/latest.json')['issuers'][self.iid]

    def qualify(self, cat, source, period, **changes):
        doc = next(d for d in cat['documents'].values() if d['text_sha256'] == source['text_sha256'])
        text = library.document_text(self.root, doc)
        return library.qualify(self.root, {'document_id': doc['document_id'], 'text_sha256': doc['text_sha256'],
            'period': period, 'kind': 'release', 'completeness': 'full', 'publisher_type': 'issuer',
            'language': 'en', 'english_coverage': 'full', 'source_accepted': True,
            'reviewer_session': 'fictitious-reviewed-session', 'rationale': 'Fictitious original fiscal-results evidence.',
            'source_spans': [{'start': 0, 'end': min(150, len(text)), 'text': text[:150]}], **changes})

    def two_issuer_baseline(self):
        first = self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        second = self.add('Fictitious Other Reports Q2 FY2026 Results.', report_date='2026-06-30')
        self.owners[0]['documents'].pop()
        other = 'sec:0000000043'
        self.owners.append({'issuer_id': other, 'issuer': 'Fictitious Other', 'symbol': 'FAKE2',
                            'monitoring_eligible': True, 'documents': [second]})
        cat = self.catalog()
        self.qualify(cat, second, 'FY2026-Q2')
        published.run(self.root, '2026-09-21')
        return first, second, other, cat

    def test_incremental_skips_other_sources_and_preserves_rows_and_queue(self):
        from unittest.mock import patch
        first, second, other, cat = self.two_issuer_baseline()
        before = library.read_json(self.root / 'published/latest.json')
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.qualify(cat, first, 'FY2026-Q2')
        original = library.load_bytes
        forbidden = {second['raw_path'], second['text_path']}
        def bounded(root, path, checksum):
            self.assertNotIn(path, forbidden, 'Unchanged source read during scoped rebuild')
            return original(root, path, checksum)
        with patch.object(library, 'load_bytes', side_effect=bounded):
            receipt = published.run(self.root, '2026-09-22', issuer_ids={self.iid})
        after = library.read_json(self.root / 'published/latest.json')
        updated_queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertEqual(after['issuers'][other], before['issuers'][other])
        self.assertEqual([r for r in queue if r.get('issuer_id') == other],
                         [r for r in updated_queue if r.get('issuer_id') == other])
        self.assertEqual(after['issuer_as_of'][other], '2026-09-21')
        self.assertEqual(after['issuer_as_of'][self.iid], '2026-09-22')
        self.assertEqual(after['issuers'][self.iid]['status'], 'packet_prepared')
        self.assertEqual(receipt['rebuild_mode'], 'incremental')
        self.assertEqual(receipt['documents_inspected'], 1)
        self.assertEqual(receipt['documents'], 2)
        # A full rebuild at the same cutoff produces the same selected-company result.
        published.run(self.root, '2026-09-22')
        full = library.read_json(self.root / 'published/latest.json')
        # Freshness assessment includes wall-clock evaluation time.
        for result in (after, full):
            result['issuers'][self.iid].pop('freshness')
        self.assertEqual(after['issuers'][self.iid], full['issuers'][self.iid])

    def test_incremental_catalog_change_and_missing_baseline_rebuild_all(self):
        first, second, other, cat = self.two_issuer_baseline()
        cat['catalog_id'] = 'changed-fictitious-catalog'
        library.save(self.root / 'library/catalog.json', cat)
        receipt = published.run(self.root, '2026-09-22', issuer_ids={self.iid})
        self.assertEqual(receipt['rebuild_mode'], 'full')
        self.assertEqual(receipt['documents_inspected'], 2)
        (self.root / 'published/latest.json').unlink()
        receipt = published.run(self.root, '2026-09-22', issuer_ids={self.iid})
        self.assertEqual(receipt['rebuild_mode'], 'full')
        with self.assertRaises(ValueError):
            published.run(self.root, '2026-09-22', issuer_ids={'unknown'})

    def test_actual_fiscal_headline_is_candidate_not_automatic_qualification(self):
        self.add('Fictitious Example Reports Third Quarter Fiscal 2026 Financial Results.', report_date='2026-08-31')
        self.catalog()
        receipt, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q3')
        self.assertEqual(row['status'], 'needs_qualification')
        self.assertIsNone(row['confirmed_period'])
        self.assertIsNone(row['packet_id'])
        span = row['candidate_documents'][0]['source_spans'][0]
        self.assertIn('Third Quarter Fiscal 2026', span['text'])
        self.assertEqual(receipt['model_calls'], 0)
        self.assertFalse(library.read_json(self.root / 'config.json')['enabled'])

    def test_forward_looking_comparative_and_calendar_labels_are_not_published_periods(self):
        for text in ['Fictitious Example Will Report Q3 FY2026 Results on October 1.',
                     'Fictitious Example Q3 FY2026 Financial Results Preview.',
                     'Fictitious Example Q3 FY2026 Guidance.',
                     'Revenue compared with Q3 FY2026 financial results.',
                     'Fictitious Example Reports Q3 2026 Financial Results.',
                     'Fictitious Example revenue increased for the quarter ended September 30, 2026.']:
            self.add(text)
        self.catalog()
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])
        self.assertEqual(row['status'], 'period_unresolved')

    def test_outlook_does_not_override_actual_report_in_previous_sentence(self):
        self.add('Fictitious Example Reports Q2 FY2026 Results. Outlook for Q3 FY2026 financial results is strong.')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q2')

    def test_explicit_fiscal_label_does_not_follow_calendar_quarter(self):
        self.add('Fictitious Example Reports First Quarter Fiscal 2027 Financial Results.', report_date='2026-08-31')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2027-Q1')

    def test_latest_rank_uses_period_end_not_newer_filing_of_old_report(self):
        self.add('Fictitious Example Reports Q1 FY2026 Results.', report_date='2026-03-31', filing_date='2026-09-19')
        self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30', filing_date='2026-08-01')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q2')
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertEqual({item['period']: item['is_latest_observed_period'] for item in queue},
                         {'FY2026-Q1': False, 'FY2026-Q2': True})

    def test_future_dated_report_excluded(self):
        self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        self.add('Fictitious Example Reports Q3 FY2026 Results.', report_date='2026-09-30')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q2')
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertIn('future_dated', [item['status'] for item in queue])

    def test_competing_undated_reports_require_review_not_quarter_number_sorting(self):
        self.add('Fictitious Example Reports Q2 FY2026 Results.')
        self.add('Fictitious Example Reports Q3 FY2026 Results.')
        self.catalog()
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])

    def test_reviewed_undated_call_uses_dated_same_period_sibling(self):
        annual = self.add('Fictitious annual fiscal 2025 report.', report_date='2025-12-31')
        filing = self.add('Fictitious quarterly fiscal 2026 report.', report_date='2026-06-30')
        call = self.add('Fictitious complete earnings call transcript.')
        cat = self.catalog()
        self.qualify(cat, annual, 'FY2025', kind='annual_background')
        self.qualify(cat, filing, 'FY2026-Q2', kind='periodic_filing')
        self.qualify(cat, call, 'FY2026-Q2', kind='transcript')
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q2')
        self.assertEqual(row['status'], 'packet_prepared')
        packet = library.read_json(self.root / 'library/packets' / (row['packet_id'] + '.json'))
        self.assertEqual({d['kind'] for d in packet['documents']},
                         {'annual_background', 'periodic_filing', 'transcript'})
        transcript = next(c for c in row['candidate_documents'] if c.get('kind') == 'transcript')
        self.assertIsNone(transcript['period_end'])
        self.assertIsNone(transcript['published_on'])

    def test_undated_unreviewed_sibling_does_not_borrow_date(self):
        annual = self.add('Fictitious annual report.', report_date='2025-12-31')
        filing = self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        self.add('Fictitious Example Reports Q2 FY2026 Results. Separate unreviewed call.')
        cat = self.catalog()
        self.qualify(cat, annual, 'FY2025', kind='annual_background')
        self.qualify(cat, filing, 'FY2026-Q2', kind='periodic_filing')
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])

    def test_reviewed_newer_period_without_any_date_anchor_stays_unresolved(self):
        older = self.add('Fictitious older results.', report_date='2026-06-30')
        newer = self.add('Fictitious later results.')
        cat = self.catalog()
        self.qualify(cat, older, 'FY2026-Q2')
        self.qualify(cat, newer, 'FY2026-Q3')
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])

    def test_overlapping_period_anchors_cannot_be_ordered_by_filing_date(self):
        def c(period, end, publication):
            return {'period': period, 'period_end': end, 'published_on': publication, 'status': 'qualified'}
        candidates = [c('FY2026-H1', '2026-06-30', '2026-08-01'),
                      c('FY2026-Q2', '2026-06-30', '2026-08-02'),
                      c('FY2026-Q2', None, None)]
        self.assertIsNone(published._latest(candidates)[0])

    def test_grouped_dates_do_not_fall_back_to_amendment_publication(self):
        candidates = [
            {'period': 'FY2026-Q1', 'period_end': None, 'published_on': '2026-09-19', 'status': 'qualified'},
            {'period': 'FY2026-Q1', 'period_end': None, 'published_on': None, 'status': 'qualified'},
            {'period': 'FY2026-Q2', 'period_end': '2026-06-30', 'published_on': '2026-08-01', 'status': 'qualified'},
        ]
        self.assertIsNone(published._latest(candidates)[0])

    def test_undated_older_group_preserves_same_end_annual_quarter_ambiguity(self):
        candidates = [
            {'period': 'FY2024', 'period_end': None, 'published_on': '2025-02-01', 'status': 'qualified'},
            {'period': 'FY2025', 'period_end': '2025-12-31', 'published_on': '2026-03-01', 'status': 'qualified'},
            {'period': 'FY2025-Q4', 'period_end': '2025-12-31', 'published_on': '2026-02-01', 'status': 'qualified'},
            {'period': 'FY2025-Q4', 'period_end': None, 'published_on': None, 'status': 'qualified'},
        ]
        self.assertIsNone(published._latest(candidates)[0])

    def test_all_issuers_included_and_no_identity_bypass(self):
        self.add('Fictitious Example Reports Q3 FY2026 Results.')
        self.owners[0]['monitoring_eligible'] = False
        self.owners.append({'issuer_id': 'fictitious:empty', 'issuer': 'Fictitious Empty', 'symbol': 'NONE',
                            'monitoring_eligible': True, 'documents': []})
        self.catalog()
        receipt, row = self.run_tracker()
        self.assertEqual(row['status'], 'identity_unresolved')
        self.assertIsNone(row['packet_id'])
        self.assertEqual(receipt['issuers'], 2)
        rows = library.read_json(self.root / 'published/latest.json')['issuers']
        self.assertEqual(rows['fictitious:empty']['status'], 'no_documents')
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertTrue(all(item['monitoring_eligible'] is False for item in queue if item['issuer_id'] == self.iid))

    def test_qualified_packet_preserves_stale_sources_and_missing_types(self):
        source = self.add('Fictitious Example Reports Q3 FY2026 Results.', report_date='2026-08-31',
                          retrieved_at='2020-01-01T00:00:00+00:00')
        cat = self.catalog()
        self.qualify(cat, source, 'FY2026-Q3')
        _, row = self.run_tracker()
        self.assertEqual(row['status'], 'packet_prepared')
        self.assertEqual(row['confirmed_period'], 'FY2026-Q3')
        self.assertEqual(row['freshness']['status'], 'recheck_required')
        self.assertEqual(row['missing']['transcript']['status'], 'pending')
        self.assertFalse(row['discovery_complete'])
        packet = library.read_json(self.root / f"library/packets/{row['packet_id']}.json")
        library.materialize(self.root, packet)
        _, again = self.run_tracker()
        self.assertEqual(again['packet_id'], row['packet_id'])

    def test_prior_year_annual_background_attached_without_inventing_q4(self):
        annual = self.add('Fictitious annual report for fiscal 2025.', report_date='2025-12-31', kind='annual_background')
        quarter = self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        cat = self.catalog()
        self.qualify(cat, annual, 'FY2025', kind='annual_background')
        self.qualify(cat, quarter, 'FY2026-Q2')
        _, row = self.run_tracker()
        packet = library.read_json(self.root / f"library/packets/{row['packet_id']}.json")
        self.assertEqual(packet['period'], 'FY2026-Q2')
        self.assertEqual(packet['availability']['annual_background'], 'available')
        self.assertEqual({doc['period'] for doc in packet['documents']}, {'FY2025', 'FY2026-Q2'})

    def test_ambiguous_prior_year_annual_reports_remain_missing(self):
        annual_one = self.add('Fictitious annual report for fiscal 2025 original.', report_date='2025-12-31', kind='annual_background')
        annual_two = self.add('Fictitious annual report for fiscal 2025 alternate.', report_date='2025-12-31', kind='annual_background')
        quarter = self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        cat = self.catalog()
        for annual in [annual_one, annual_two]:
            self.qualify(cat, annual, 'FY2025', kind='annual_background')
        self.qualify(cat, quarter, 'FY2026-Q2')
        _, row = self.run_tracker()
        packet = library.read_json(self.root / f"library/packets/{row['packet_id']}.json")
        self.assertEqual(packet['availability']['annual_background'], 'pending')

    def test_newer_candidate_does_not_make_old_qualified_packet_latest(self):
        source = self.add('Fictitious Example Reports Q2 FY2026 Results.', report_date='2026-06-30')
        self.add('Fictitious Example Reports Q3 FY2026 Results.', report_date='2026-08-31')
        cat = self.catalog()
        self.qualify(cat, source, 'FY2026-Q2')
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q3')
        self.assertEqual(row['confirmed_period'], 'FY2026-Q2')
        self.assertIsNone(row['packet_id'])

    def test_qualification_overrides_automatic_interpretation_and_tamper_rejected(self):
        source = self.add('Fictitious Example Reports Q3 FY2026 Results.', report_date='2026-08-31')
        cat = self.catalog()
        q = self.qualify(cat, source, 'FY2026-Q2')
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026-Q2')
        path = self.root / q['path']
        changed = library.read_json(path)
        changed['period'] = 'FY2099-Q4'
        library.save(path, changed)
        _, row = self.run_tracker()
        self.assertIsNone(row['confirmed_period'])
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertIn('qualification_invalid', [item['status'] for item in queue])

    def test_sec_dei_original_bytes_support_period_and_annual_does_not_imply_q4(self):
        raw = b'''<html><ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">FY</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-06-30</ix:nonNumeric></html>'''
        self.add('Fictitious annual financial report.', raw=raw, kind='annual_background', form='10-K',
                 url='https://www.sec.gov/Archives/edgar/data/42/fictitious/report.htm')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2026')
        evidence = row['candidate_documents'][0]
        self.assertEqual(evidence['period_end'], '2026-06-30')
        self.assertEqual(evidence['basis'], 'sec_inline_xbrl_dei')
        self.assertEqual(len(evidence['raw_source_spans']), 3)
        self.assertIsNone(row['packet_id'])

    def test_sec_dei_transformed_month_name_date_and_nested_spans(self):
        raw = b'''<html><ix:nonNumeric name="dei:DocumentFiscalYearFocus"><span>2027</span></ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q2</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentPeriodEndDate" format="ixt:date-monthname-day-year-en"><span><ix:nonNumeric name="dei:CurrentFiscalYearEndDate">July&#160;26</ix:nonNumeric>, <ix:nonNumeric name="example:CalendarYear">2026</ix:nonNumeric></span></ix:nonNumeric></html>'''
        self.add('Fictitious quarterly financial report.', raw=raw, kind='periodic_filing', form='10-Q',
                 url='https://www.sec.gov/Archives/edgar/data/42/fictitious/report.htm')
        self.catalog()
        _, row = self.run_tracker()
        self.assertEqual(row['period'], 'FY2027-Q2')
        evidence = row['candidate_documents'][0]
        self.assertEqual(evidence['period_end'], '2026-07-26')
        self.assertIn('July&#160;26</ix:nonNumeric>', evidence['raw_source_spans'][2]['text'])

    def test_wrong_sec_cik_and_metadata_only_fiscal_guesses_are_not_accepted(self):
        raw = b'''<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q3</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-08-31</ix:nonNumeric>'''
        self.add('Fictitious annual financial report.', raw=raw,
                 url='https://www.sec.gov/Archives/edgar/data/999/fictitious/report.htm',
                 fiscal_tags={'DocumentFiscalYearFocus': '2026', 'DocumentFiscalPeriodFocus': 'Q3'})
        self.catalog()
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])

    def test_review_identity_stable_after_qualification_and_preserves_hashes(self):
        source = self.add('Fictitious Example Reports Q3 FY2026 Results.', report_date='2026-08-31')
        cat = self.catalog()
        self.run_tracker()
        before = library.read_json(self.root / 'published/review-queue.json')[0]
        qualification = self.qualify(cat, source, 'FY2026-Q3')
        self.run_tracker()
        after = library.read_json(self.root / 'published/review-queue.json')[0]
        self.assertEqual(after['review_id'], before['review_id'])
        self.assertEqual(after['status'], 'qualified')
        self.assertEqual(after['qualification_ids'], [qualification['qualification_id']])
        self.assertEqual(after['source_variants'][0]['raw_sha256'], source['raw_sha256'])
        self.assertEqual(after['text_sha256'], source['text_sha256'])

    def test_repeated_headlines_do_not_duplicate_review_identity(self):
        self.add('Fictitious Example Reports Q3 FY2026 Results.\nFictitious Example Q3 FY2026 Financial Results.')
        self.catalog()
        self.run_tracker()
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertEqual(len(queue), 1)

    def test_non_periodic_sec_dei_does_not_assign_latest_quarter(self):
        raw = b'''<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q3</ix:nonNumeric>
<ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-08-31</ix:nonNumeric>'''
        self.add('Fictitious material event about a director appointment.', raw=raw, form='8-K',
                 url='https://www.sec.gov/Archives/edgar/data/42/fictitious/report.htm')
        self.catalog()
        _, row = self.run_tracker()
        self.assertIsNone(row['period'])

    def test_corrupt_original_source_blocks_preparation(self):
        source = self.add('Fictitious Example Reports Q3 FY2026 Results.')
        cat = self.catalog()
        self.qualify(cat, source, 'FY2026-Q3')
        (self.root / source['raw_path']).write_bytes(b'changed')
        _, row = self.run_tracker()
        self.assertIsNone(row['packet_id'])
        self.assertEqual(row['status'], 'period_unresolved')
        queue = library.read_json(self.root / 'published/review-queue.json')
        self.assertIn('source_invalid', [item['status'] for item in queue])


if __name__ == '__main__':
    unittest.main()
