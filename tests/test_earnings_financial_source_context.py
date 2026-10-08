"""Fictional source-bound financial context; no model calls or private inputs."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_repair_context as c


class FinancialSourceContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fictional.html'
        self.text = '<html><ix:nonNumeric name="fake:RentalTextBlock"><p>Fictional rental lasts 24 months.</p><p>Monthly amount <ix:nonFraction>123</ix:nonFraction>.</p></ix:nonNumeric></html>'
        self.path.write_text(self.text)
        start = self.text.index('<ix:nonFraction>')
        end = self.text.index('</ix:nonFraction>') + len('</ix:nonFraction>')
        self.scope = dict(path=str(self.path), sha256=c.evidence._sha_text(self.text), document_id='fictional-document', start=start, end=end)
        self.scopes = {'F001': [self.scope]}
        self.bundle = {'financial': {'observations': [{'id': 'F001'}]}, 'documents': {'chunks': []}}

    def apply(self, version=c.FINANCIAL_CONTEXT_VERSION):
        return c._financial_context(self.scopes, self.bundle, {'F001'}, version)

    def test_exact_enclosing_textblock_preserves_full_narrative_and_provenance(self):
        result = self.apply()['resolutions'][0]
        self.assertEqual(result['status'], 'provided')
        self.assertEqual(result['container']['kind'], 'inline_xbrl_text_block')
        span = self.scopes['F001'][1]
        self.assertEqual(span['sha256'], self.scope['sha256'])
        text = c._materialize(self.scopes, ['F001'])[0]['spans'][1]['text']
        self.assertIn('lasts 24 months', text)
        self.assertTrue(text.endswith('</ix:nonNumeric>'))
        self.assertEqual(self.text[span['start']:span['end']], text)

    def test_opt_in_legacy_unchanged_and_version_checked(self):
        before = copy.deepcopy(self.scopes)
        self.assertIsNone(self.apply(None))
        self.assertEqual(self.scopes, before)
        with self.assertRaisesRegex(ValueError, 'version'):
            self.apply('invented-version')

    def test_same_representation_chunk_containment_only(self):
        self.bundle['documents']['chunks'] = [{**self.scope, 'id': 'D001', 'start': 0, 'end': len(self.text)}]
        row = self.apply()['resolutions'][0]
        self.assertEqual(row['container']['scope_id'], 'D001')
        self.assertEqual(row['context_format'], 'original_source')

    def test_cross_representation_offsets_not_guessed(self):
        self.bundle['documents']['chunks'] = [{**self.scope, 'id': 'D001', 'sha256': '0'*64, 'start': 0, 'end': len(self.text)}]
        row = self.apply()['resolutions'][0]
        self.assertNotIn('scope_id', row['container'])
        self.assertEqual(row['container']['kind'], 'inline_xbrl_text_block')

    def test_tampered_source_rejected(self):
        self.path.write_text(self.text + 'changed')
        with self.assertRaisesRegex(ValueError, 'Frozen source'):
            self.apply()

    def test_large_context_explicitly_insufficient_never_truncated(self):
        with patch.object(c, 'MAX_FINANCIAL_CONTEXT_CHARACTERS', 20):
            row = self.apply()['resolutions'][0]
        self.assertEqual(row['status'], 'insufficient_context')
        self.assertEqual(len(self.scopes['F001']), 1)

    def test_unclosed_html_never_claimed_complete(self):
        text = '<p>Unclosed fictional paragraph 123'
        self.path.write_text(text)
        self.scope.update(sha256=c.evidence._sha_text(text), start=text.index('123'), end=len(text))
        self.assertEqual(self.apply()['resolutions'][0]['status'], 'insufficient_context')

    def test_evidence_response_new_and_legacy_routes(self):
        with patch.object(c, '_index', return_value=(copy.deepcopy(self.scopes), {}, {})):
            old = c.evidence_response(self.bundle, {}, [{'scope_id':'F001','reason':'Original context'}])
        with patch.object(c, '_index', return_value=(copy.deepcopy(self.scopes), {}, {})):
            new = c.evidence_response(self.bundle, {}, [{'scope_id':'F001','reason':'Original context'}], financial_context_version=c.FINANCIAL_CONTEXT_VERSION)
        self.assertNotIn('financial_context_resolution', old)
        self.assertEqual(len(old['scopes'][0]['spans']), 1)
        self.assertEqual(len(new['scopes'][0]['spans']), 2)
        self.assertIn('lasts 24 months', new['scopes'][0]['spans'][1]['text'])

    def test_unicode_offsets_and_spaced_closing_tag_are_exact(self):
        text = '<ix:nonNumeric name="fake:TextBlock"><p>café 😀 123</p ></ix:nonNumeric >'
        self.path.write_text(text)
        self.scope.update(sha256=c.evidence._sha_text(text), start=text.index('123'), end=text.index('123')+3)
        row = self.apply()['resolutions'][0]
        self.assertEqual(row['container']['end'], len(text))
        self.assertEqual(c._materialize(self.scopes, ['F001'])[0]['spans'][1]['text'], text)

    def test_paragraph_fallback_labeled_enclosing_only(self):
        text = '<p>Fictional monthly payment 123.</p>'
        self.path.write_text(text)
        self.scope.update(sha256=c.evidence._sha_text(text), start=text.index('123'), end=text.index('123')+3)
        row = self.apply()['resolutions'][0]
        self.assertEqual(row['container']['kind'], 'p')
        self.assertEqual(row['completeness'], 'enclosing_context_only')


from test_earnings_passages import PassageFixture


class FinancialInitialContextTests(PassageFixture, unittest.TestCase):
    def test_initial_context_version_is_explicit_and_report_stays_unchanged(self):
        before = {'artifacts': {'financial': copy.deepcopy(self.financial),
                  'retrieval': copy.deepcopy(self.retrieval), 'analysis': copy.deepcopy(self.report)},
                  'format': {'rows': {}, 'basis': {'text': '', 'citations': []}}, 'findings': []}
        after = copy.deepcopy(before)
        after['artifacts']['analysis']['opening'] = 'Fictional revised finding.'
        plan = {'operations': [{'id': 'fictional-edit', 'path': ['artifacts','analysis','opening'],
                'reason':'Fictional correction', 'citations':['D001'], 'passage_ids':[self.ids[0]]}]}
        args = (before, after, plan, self.bundle, self.catalog, 'Complete fictional report', 'Rules')
        legacy = c.build(*args)
        updated = c.expand_context(c.build(*args, financial_context_version=c.FINANCIAL_CONTEXT_VERSION))
        self.assertNotIn('financial_context_resolution', legacy)
        self.assertEqual(updated['financial_context_resolution']['version'], c.FINANCIAL_CONTEXT_VERSION)
        self.assertEqual(updated['report'], legacy['report'])
        self.assertEqual(updated['candidate_sha256'], legacy['candidate_sha256'])
