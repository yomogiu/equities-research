"""Fictitious named greetings; retain all business content and frozen v2 behavior."""
import copy
import unittest
from research import earnings_qa_grounding as q
from test_earnings_qa_header_repair import fixture


class NamedCourtesyTests(unittest.TestCase):
    def test_named_reply_is_courtesy_only_in_new_version(self):
        bundle, catalog = fixture(question='Hello.', chief='Hi, Alex.')
        original = copy.deepcopy((bundle, catalog))
        self.assertIsNone(q.build(bundle, catalog, q.HEADER_VERSION)['exchanges'][0]['mechanical_disposition'])
        result = q.build(bundle, catalog, q.NAMED_GREETING_VERSION)
        self.assertEqual(result['exchanges'][0]['mechanical_disposition'], 'courtesy_only')
        self.assertEqual((bundle, catalog), original)
        self.assertEqual(result['exchanges'][0]['turns'][1]['passage_offsets'][0]['start'], catalog['passages'][1]['start'])

    def test_substantive_unknown_and_outside_exchange_addresses_stay(self):
        for reply in ['Hi, Alex. Revenue rose.', 'Hi, Alex. Why?', 'Hi, Bea.',
                      'Hi, Stranger.', 'Alex.', 'Hi, Alex.\nMargins fell.',
                      'Hi, Alex, demand improved.']:
            with self.subTest(reply=reply):
                bundle, catalog = fixture(question='Hello.', chief=reply)
                self.assertIsNone(q.build(bundle, catalog, q.NAMED_GREETING_VERSION)['exchanges'][0]['mechanical_disposition'])
        bundle, catalog = fixture(question='Hello.', chief='Hi, Alex.', role='unknown')
        self.assertIsNone(q.build(bundle, catalog, q.NAMED_GREETING_VERSION)['exchanges'][0]['mechanical_disposition'])

    def test_missing_source_coverage_is_not_courtesy(self):
        bundle, catalog = fixture(question='Hello.', chief='Hi, Alex.')
        catalog['passages'][1]['start'] += 1
        catalog['passages'][1]['text'] = catalog['passages'][1]['text'][1:]
        self.assertIsNone(q.build(bundle, catalog, q.NAMED_GREETING_VERSION)['exchanges'][0]['mechanical_disposition'])

    def test_normalizer_replays_v3_and_preserves_original(self):
        bundle, catalog = fixture(question='Hello.', chief='Hi, Alex.')
        bundle['qa_grounding'] = q.build(bundle, catalog, q.NAMED_GREETING_VERSION)
        output = {'exchange_coverage': [dict(exchange_id='E1', question='Hello', answer='Greeting',
                  consequence='None', question_passage_ids=[], answer_passage_ids=[],
                  continuation_exchange_ids=[], grounding_status='courtesy_only', grounding_notes='Greeting'),
                  dict(exchange_id='E2', question='Why?', answer='Rose', question_passage_ids=['PQ2'],
                  answer_passage_ids=['PA2'], continuation_exchange_ids=[], grounding_status='bound', grounding_notes='Source')]}
        original = copy.deepcopy(output)
        derived, receipts = q.normalize_courtesy(output, bundle, catalog)
        q.require_analysis_ready(derived, bundle, catalog)
        self.assertEqual(output, original)
        self.assertEqual(derived['exchange_coverage'][1], original['exchange_coverage'][1])
        self.assertTrue(receipts)
