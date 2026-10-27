"""Fictional exact-review candidate compilation; no model calls."""
import copy
import unittest

import test_earnings_signals as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_batch_review as batch
from research import earnings_exact_repairs as repairs


class ExactRepairTests(PassageFixture, unittest.TestCase):
    state = fixtures.SignalTests.state
    pack = fixtures.SignalTests.pack

    def items(self):
        state = self.state()
        return batch.units(state, self.pack(state))

    def review(self, items, edits, kind='editorial'):
        return {'batch_sha256': batch.runner.digest(items), 'reopen': [], 'decisions': [
            {'unit_id': key, 'verdict': 'revise' if key in edits else 'pass',
             'reason': 'Fictional exact source assessment.', 'passage_ids': [self.ids[0]],
             'review_kind': kind if key in edits else 'none',
             'editorial_repairs': edits.get(key, [])} for key in sorted(items)]}

    def edit(self, path, before, after):
        return {'field_path': path, 'before': before, 'after': after,
                'reason': 'Fictional precise repair.'}

    def build(self, items, review, **overrides):
        bindings = {'bound_batch_sha256': batch.runner.digest(items),
                    'bound_review_sha256': batch.runner.digest(review),
                    'source_review_sha256': 'a' * 64}
        bindings.update(overrides)
        return repairs.build(items, review, self.bundle, self.catalog, **bindings)

    def test_exact_mixed_and_factual_proposals_require_fresh_full_review(self):
        for kind in ('editorial', 'mixed', 'factual'):
            items = self.items()
            before = items['analysis:0']['value']['text']
            review = self.review(items, {'analysis:0': [self.edit(['text'], before, 'Fictional corrected claim.')]}, kind)
            original = copy.deepcopy((items, review, self.bundle, self.catalog))
            result = self.build(items, review)
            self.assertIsNotNone(result)
            self.assertEqual(result['items']['analysis:0']['value']['text'], 'Fictional corrected claim.')
            self.assertEqual((items, review, self.bundle, self.catalog), original)
            self.assertEqual(result['derivation']['provider_calls'], 0)
            self.assertEqual(result['derivation']['required_review_units'], sorted(items))
            self.assertEqual(result['derivation']['status'], 'candidate_pending_fresh_full_review')
            self.assertIn('analysis:next_tests', result['derivation']['dependent_finding_units'])
            self.assertEqual(result['items']['financial'], items['financial'])
            self.assertEqual(result['items']['retrieval'], items['retrieval'])
            self.assertEqual(result, self.build(items, review))

    def test_partial_proposal_falls_back_atomically(self):
        items = self.items()
        before = items['analysis:0']['value']['text']
        review = self.review(items, {'analysis:0': [self.edit(['text'], before, 'Fictional correction.')],
                                     'analysis:1': []}, 'factual')
        self.assertIsNone(self.build(items, review))
        self.assertEqual(items['analysis:0']['value']['text'], before)

    def test_disjoint_spans_apply_against_original_not_inserted_text(self):
        items = self.items()
        items['analysis:0']['value']['text'] = 'Fictional alpha and beta.'
        edits = [self.edit(['text'], 'alpha', 'beta'), self.edit(['text'], 'beta', 'gamma')]
        result = self.build(items, self.review(items, {'analysis:0': edits}))
        self.assertEqual(result['items']['analysis:0']['value']['text'], 'Fictional beta and gamma.')
        reverse = self.build(items, self.review(items, {'analysis:0': list(reversed(edits))}))
        self.assertEqual(result['plan'], reverse['plan'])

    def test_overlapping_or_duplicate_spans_fall_back(self):
        items = self.items()
        items['analysis:0']['value']['text'] = 'Fictional alpha and beta.'
        edit = self.edit(['text'], 'alpha', 'gamma')
        for edits in ([edit, edit], [edit, self.edit(['text'], 'alpha and', 'delta')]):
            self.assertIsNone(self.build(items, self.review(items, {'analysis:0': edits})))

    def test_quote_removal_preserves_original_order_and_sources(self):
        items = self.items()
        quotes = [{'passage_id': self.ids[0]}, {'passage_id': self.ids[1]}]
        items['analysis:0']['value']['quotes'] = quotes
        review = self.review(items, {'analysis:0': [self.edit(['quotes'], quotes, quotes[1:])]})
        result = self.build(items, review)
        self.assertEqual(result['items']['analysis:0']['value']['quotes'], quotes[1:])
        self.assertEqual(items['analysis:0']['value']['quotes'], quotes)

    def test_invalid_result_falls_back_without_mutating_original(self):
        items = self.items()
        before = items['signal-1']['value']['label']
        review = self.review(items, {'signal-1': [self.edit(['label'], before, '')]})
        self.assertIsNone(self.build(items, review))
        self.assertEqual(items['signal-1']['value']['label'], before)

    def test_bad_review_source_or_candidate_binding_raises(self):
        items = self.items()
        review = self.review(items, {})
        for overrides in ({'bound_batch_sha256': 'b' * 64}, {'bound_review_sha256': 'b' * 64},
                          {'source_review_sha256': 'not a receipt hash'}):
            with self.assertRaises(ValueError):
                self.build(items, review, **overrides)

    def test_unknown_citation_or_source_binding_edit_raises(self):
        items = self.items()
        before = items['analysis:0']['value']['text']
        review = self.review(items, {'analysis:0': [self.edit(['text'], before, 'Fictional correction.')]}, 'factual')
        next(row for row in review['decisions'] if row['unit_id'] == 'analysis:0')['passage_ids'] = ['unknown']
        with self.assertRaises(ValueError):
            self.build(items, review)
        review = self.review(items, {'analysis:0': [self.edit(['citations'], [], ['D001'])]})
        with self.assertRaises(ValueError):
            self.build(items, review)

    def test_all_pass_is_not_a_correction(self):
        items = self.items()
        self.assertIsNone(self.build(items, self.review(items, {})))

    def test_source_artifact_rewrite_falls_back(self):
        items = self.items()
        before = items['retrieval']['value']['exchange_coverage'][0]['answer']
        review = self.review(items, {'retrieval': [self.edit(
            ['exchange_coverage', 0, 'answer'], before, 'Fictional revised source extraction.')]})
        self.assertIsNone(self.build(items, review))

    def test_stale_review_and_ambiguous_original_text_are_rejected(self):
        items = self.items()
        before = items['analysis:0']['value']['text']
        review = self.review(items, {'analysis:0': [self.edit(['text'], before, 'Fictional correction.')]})
        changed = copy.deepcopy(items)
        changed['analysis:0']['value']['text'] = 'Fictional different candidate.'
        with self.assertRaisesRegex(ValueError, 'another batch'):
            self.build(changed, review)
        items['analysis:0']['value']['text'] = 'Fictional repeat repeat.'
        review = self.review(items, {'analysis:0': [self.edit(['text'], 'repeat', 'once')]})
        with self.assertRaisesRegex(ValueError, 'exact unique text'):
            self.build(items, review)


if __name__ == '__main__':
    unittest.main()
