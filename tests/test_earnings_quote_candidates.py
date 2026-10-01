"""Fictitious quote candidates only; no benchmark/model executions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import earnings_compact_evidence as evidence
from research import earnings_experiment as base
from research import earnings_quote_candidates as policy
from test_earnings_compact_evidence import fixture


class QuoteCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        case_path, _, _ = fixture(self.root)
        self.manifest = evidence.prepare(case_path, self.root / 'bundle')
        self.valid = [{'scope_id': 'D001', 'text': text, 'note': {'original': number}}
                      for number, text in enumerate([
                          'Fictitious café guidance is provisional.',
                          'Fictitious supporting row 000.',
                          'Fictitious supporting row 001.',
                          'Fictitious supporting row 002.'])]
        self.batch = {'quotes': deepcopy(self.valid), 'selected_document_ids': ['D002', 'D001'],
                      'exchange_coverage': [{'exchange_id': 'preserved-as-supplied',
                          'question': 'Fictitious question\u00a0as supplied.',
                          'answer': 'Fictitious answer.', 'metadata': {'untouched': [1, 2]}}],
                      'document_findings': [{'text': 'Original fictional context.', 'citations': ['D001']}],
                      'extra_metadata': {'status': 'original', 'nested': ['unchanged']}}

    def test_valid_preservation_hashes_provenance_and_no_writes(self):
        before = deepcopy(self.batch)
        files = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = policy.qualify_candidates(self.manifest, self.batch)
        self.assertEqual(before, self.batch)
        self.assertEqual(before, result['content'])
        self.assertIsNot(self.batch, result['content'])
        self.assertEqual(policy.VERSION, result['version'])
        self.assertEqual(base.digest(before), result['original_sha256'])
        self.assertEqual(base.digest(result['content']), result['derived_sha256'])
        self.assertEqual([], result['rejected_candidates'])
        self.assertEqual(4, len(result['accepted_quote_evidence']))
        for resolved in result['accepted_quote_evidence']:
            self.assertEqual(resolved, evidence.validate_quote(self.manifest, resolved))
        result['content']['extra_metadata']['nested'].append('mutated derived copy')
        result['content']['quotes'][0]['note']['original'] = 99
        self.assertEqual(before, self.batch)
        self.assertEqual(files, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_nbsp_mismatch_and_ambiguity_rejected_without_repairs(self):
        mismatch = {'scope_id': 'D001', 'text': 'Fictitious\u00a0café guidance is provisional.',
                    'metadata': {'keep': 'exact\u00a0original'}}
        ambiguous = {'scope_id': 'D001', 'text': 'Repeated phrase.', 'note': 'Both occurrences are real'}
        self.batch['quotes'] = [mismatch, *self.valid, ambiguous]
        before = deepcopy(self.batch)
        result = policy.qualify_candidates(self.manifest, self.batch)
        expected = deepcopy(before)
        expected['quotes'] = self.valid
        self.assertEqual(expected, result['content'])
        self.assertEqual(before, self.batch)
        self.assertEqual([mismatch, ambiguous], [r['candidate'] for r in result['rejected_candidates']])
        self.assertIn('Ambiguous', result['rejected_candidates'][1]['error'])
        self.assertEqual(base.digest(before), result['original_sha256'])
        self.assertNotEqual(result['original_sha256'], result['derived_sha256'])

    def test_unknown_scope_is_fatal_even_with_four_valid_candidates(self):
        self.batch['quotes'].append({'scope_id': 'D999', 'text': 'Fictitious'})
        with self.assertRaisesRegex(ValueError, 'Unknown source ID'):
            policy.qualify_candidates(self.manifest, self.batch)

    def test_changed_file_is_fatal_before_candidate_filtering(self):
        (self.root / 'filing.txt').write_text('Changed fictitious source')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            policy.qualify_candidates(self.manifest, self.batch)
        self.batch['quotes'] = []
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            policy.qualify_candidates(self.manifest, self.batch)

    def test_compact_file_tampering_is_fatal(self):
        Path(self.manifest['files']['documents']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Compact evidence file changed'):
            policy.qualify_candidates(self.manifest, self.batch)

    def test_only_quote_specific_validation_errors_are_filtered(self):
        with patch.object(evidence, 'resolve_quote', side_effect=ValueError('Source changed')):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                policy.qualify_candidates(self.manifest, self.batch)
        with patch.object(evidence, 'resolve_quote', side_effect=ValueError('Unexpected integrity failure')):
            with self.assertRaisesRegex(ValueError, 'Unexpected integrity failure'):
                policy.qualify_candidates(self.manifest, self.batch)

    def test_provenance_tampering_is_fatal(self):
        for key, value in [('sha256', '0' * 64), ('document_id', 'fictional-other'),
                           ('path', '/fictional/wrong'), ('offset_unit', 'bytes')]:
            with self.subTest(key=key):
                batch = deepcopy(self.batch)
                batch['quotes'][0][key] = value
                with self.assertRaisesRegex(ValueError, 'source provenance mismatch'):
                    policy.qualify_candidates(self.manifest, batch)
                batch['quotes'][0]['text'] = 'This nonexistent text must not hide bad provenance.'
                with self.assertRaisesRegex(ValueError, 'source provenance mismatch'):
                    policy.qualify_candidates(self.manifest, batch)

    def test_minimum_counts_unique_source_spans_not_candidate_count(self):
        self.batch['quotes'] = self.valid[:3] + [deepcopy(self.valid[0])]
        with self.assertRaisesRegex(ValueError, 'four unique valid.*found 3'):
            policy.qualify_candidates(self.manifest, self.batch)
        self.batch['quotes'] = deepcopy(self.valid) + [deepcopy(self.valid[0])]
        result = policy.qualify_candidates(self.manifest, self.batch)
        self.assertEqual(self.batch['quotes'], result['content']['quotes'])
        self.assertEqual(5, len(result['accepted_quote_evidence']))

    def test_explicit_offset_disambiguates_without_changing_candidate(self):
        source = (self.root / 'filing.txt').read_bytes().decode('utf-8')
        candidate = {'scope_id': 'D001', 'text': 'Repeated phrase.',
                     'start': source.index('Repeated phrase.'), 'metadata': 'preserved'}
        self.batch['quotes'].append(candidate)
        result = policy.qualify_candidates(self.manifest, self.batch)
        self.assertEqual(candidate, result['content']['quotes'][-1])
        self.assertEqual(candidate['start'], result['accepted_quote_evidence'][-1]['start'])


if __name__ == '__main__':
    unittest.main()
