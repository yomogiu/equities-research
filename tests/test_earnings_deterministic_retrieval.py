"""Fictional source navigation; no provider calls, private data or model costs."""
import copy
import unittest
from unittest.mock import patch

from test_earnings_passages import PassageFixture
from test_earnings_compact_evidence import refreeze, write
from research import earnings_compact_evidence as evidence
from research import earnings_deterministic_retrieval as navigation
from research import earnings_experiment as base
from research import earnings_file_context as context
from research import earnings_passage_pipeline as pipe
from research import earnings_passages as passages
from research import earnings_qa_grounding as grounding
from research import transcript_evidence as transcript


class NavigationTests(PassageFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.bundle['qa_grounding'] = grounding.build(self.bundle, self.catalog)

    def changed_call(self, text):
        call = self.root / 'call.txt'
        call.write_bytes(text.encode())
        index = transcript.index_transcript(text, {
            'document_id': 'fictional-call', 'text_sha256': base.sha(call),
            'speakers': [{'name': 'Chief', 'role': 'management'},
                         {'name': 'Questioner', 'role': 'analyst'}]})
        write(self.root / 'index-source.json', index)
        refreeze(self.casepath, self.case, call)
        refreeze(self.casepath, self.case, self.root / 'index-source.json')
        manifest = evidence.prepare(self.casepath, self.root / 'changed-evidence')
        bundle = evidence.load_bundle(manifest)
        catalog = passages.catalog(manifest)
        bundle['qa_grounding'] = grounding.build(bundle, catalog)
        return bundle, catalog

    def test_ready_is_reproducible_and_valid_without_semantic_claims(self):
        before = copy.deepcopy(self.bundle)
        first = navigation.build(self.bundle, self.catalog)
        self.assertEqual(first, navigation.build(self.bundle, self.catalog))
        self.assertEqual(self.bundle, before)
        self.assertEqual(first['status'], 'ready')
        self.assertEqual(first['tokens'], 0)
        self.assertEqual(first['content']['document_findings'], [])
        self.assertIn('no substantive extraction', first['notice'])
        self.assertIn('not editorial recommendations', first['notice'])
        pipe.validate('retrieval', first['content'], self.bundle, self.catalog)
        for row, group in zip(first['content']['exchange_coverage'], self.bundle['qa_grounding']['exchanges']):
            expected = {pid for turn in group['turns'] if not turn['courtesy_only']
                        and turn['id'] in group['question_turn_ids'] + group['answer_turn_ids']
                        for pid in turn['passage_ids']}
            self.assertEqual(set(row['question_passage_ids'] + row['answer_passage_ids']), expected)
            self.assertEqual(row['continuation_exchange_ids'], [])
        self.assertEqual(first['source_bindings']['catalog_sha256'], base.digest(self.catalog))

    def test_uses_existing_filing_selection_without_fabricating_inspection(self):
        index = context.assemble(self.root / 'evidence/manifest.json', self.catalog, self.root / 'context')
        reader = context.Evidence(index, self.root / 'inspection.jsonl')
        _, expected = reader._filing_batch(navigation.QUERY, 4)
        result = navigation.build(self.bundle, self.catalog)
        self.assertEqual(result['content']['selected_document_ids'], expected)
        self.assertLessEqual(len(expected), 4)
        self.assertFalse((self.root / 'inspection.jsonl').exists())
        self.assertIn('not proof of analytical relevance', result['selection']['notice'])

    def test_missing_grounding_falls_back_explicitly(self):
        self.bundle.pop('qa_grounding')
        result = navigation.build(self.bundle, self.catalog)
        self.assertEqual(result['status'], 'fallback_required')
        self.assertNotIn('content', result)
        self.assertIn('grounding is required', result['reasons'][0])

    def test_substantive_unassigned_turn_never_disappears(self):
        bundle, catalog = self.changed_call('Fictitious call.\nQ&A\nChief: Fictional demand fell.\n'
                                            'Questioner: Why?\nChief: Fictional supply delays.\n')
        result = navigation.build(bundle, catalog)
        self.assertEqual(result['status'], 'fallback_required')
        self.assertIn('unassigned', result['reasons'][0])

    def test_ambiguous_interruption_falls_back(self):
        bundle, catalog = self.changed_call('Fictitious call.\nQ&A\nQuestioner: What changed?\n'
                                            'Operator: Please hold.\nChief: Fictional growth.\n')
        result = navigation.build(bundle, catalog)
        self.assertEqual(result['status'], 'fallback_required')
        self.assertIn('requires source attribution', result['reasons'][0])

    def test_exact_courtesy_retained_without_answer_claim(self):
        bundle, catalog = self.changed_call('Fictitious call.\nPrepared remarks\nChief: Fictional operations.\n'
                                            'Q&A\nQuestioner: Hello.\nChief: Thank you.\n')
        result = navigation.build(bundle, catalog)
        self.assertEqual(result['status'], 'ready')
        row = result['content']['exchange_coverage'][0]
        self.assertEqual(row['grounding_status'], 'courtesy_only')
        self.assertEqual(row['answer_passage_ids'], [])
        self.assertEqual(row['question_passage_ids'], [])
        pipe.validate('retrieval', result['content'], bundle, catalog)

    def test_grounding_tamper_is_error_not_fallback(self):
        self.bundle['qa_grounding']['exchanges'][0]['flags'] = ['invented']
        with self.assertRaisesRegex(ValueError, 'differs from replayed'):
            navigation.build(self.bundle, self.catalog)

    def test_unbound_reviewed_disposition_is_rejected(self):
        self.bundle['qa_grounding']['exchanges'][0]['mechanical_disposition'] = 'reviewed_non_qa'
        with self.assertRaisesRegex(ValueError, 'differs from replayed'):
            navigation.build(self.bundle, self.catalog)

    def test_passage_and_source_tampering_fail_closed(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['passages'][0]['text'] = 'Invented source text.'
        with self.assertRaisesRegex(ValueError, 'catalog changed'):
            navigation.build(self.bundle, catalog)
        (self.root / 'call.txt').write_text('Changed call.')
        with self.assertRaises(ValueError):
            navigation.build(self.bundle, self.catalog)

    def test_unavailable_document_selection_has_explicit_gap(self):
        with patch.object(context.Evidence, '_filing_batch', return_value=(
                '# Filing batch\n{"selected_document_ids":[]}\n', [])):
            result = navigation.build(self.bundle, self.catalog)
        self.assertEqual(result['status'], 'fallback_required')
        self.assertIn('source access', result['reasons'][0])


if __name__ == '__main__':
    unittest.main()
