"""Fictitious supplemental display and typed remediation regressions."""
import copy
import unittest

from test_earnings_financial_display import fixture
from test_earnings_passages import PassageFixture
from research import earnings_supplemental_rows as supplemental
from research import earnings_remediation as remediation
from research import earnings_experiment as base


class SupplementalRowsTests(unittest.TestCase):
    def setUp(self):
        self.sheet, self.bundle = fixture()
        self.selection = [{'label': 'Fictional revenue', 'fact_ids': ['F1', 'F2']}]

    def test_source_values_periods_and_input_are_preserved(self):
        original = copy.deepcopy(self.bundle)
        rows = supplemental.build(self.selection, self.bundle)
        self.assertEqual([r['value'] for r in rows], ['1,250', '1,000'])
        self.assertEqual([r['unit'] for r in rows], ['USD millions'] * 2)
        self.assertIn('2040', rows[0]['period'])
        self.assertIn('2039', rows[1]['period'])
        self.assertEqual(self.bundle, original)

    def test_nil_is_not_zero_and_retains_denominator_and_display_unit(self):
        fact = self.bundle['financial']['observations'][0]
        fact.update(nil=True, value=None)
        self.bundle['financial']['units']['USD']['denominator'] = ['xbrli:shares']
        row = supplemental.build([{'label': 'Fictional per-share item', 'fact_ids': ['F1']}], self.bundle)[0]
        self.assertEqual(row['value'], '— (reported nil)')
        self.assertEqual(row['unit'], 'USD/share')
        self.assertIsNone(fact['value'])

    def test_inconsistent_nil_and_missing_value_fail_closed(self):
        fact = self.bundle['financial']['observations'][0]
        for nil, value in [(True, '1'), (False, None)]:
            with self.subTest(nil=nil, value=value):
                fact.update(nil=nil, value=value)
                with self.assertRaises(ValueError):
                    supplemental.build(self.selection, self.bundle)

    def test_cannot_inject_values_or_repeat_or_invent_facts(self):
        for rows in [
            [{'label': 'Fake', 'fact_ids': ['F1'], 'value': '999'}],
            [{'label': 'Fake', 'fact_ids': ['F1', 'F1']}],
            [{'label': 'Fake', 'fact_ids': ['UNKNOWN']}],
            self.selection * 2,
        ]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                supplemental.build(rows, self.bundle)

    def test_cross_metric_entity_dimension_and_unit_comparisons_rejected(self):
        changes = [('concept', 'fake:OtherMetric'), ('entity', 'OTHER'),
                   ('dimensions', [{'dimension': 'fake:Axis', 'member': 'fake:Member', 'type': 'explicitmember'}]),
                   ('unit', {'numerator': ['iso4217:EUR'], 'denominator': []})]
        for field, value in changes:
            bundle = copy.deepcopy(self.bundle)
            facts = bundle['financial']
            if field == 'concept':
                facts['observations'][1]['concept'] = value
            elif field == 'unit':
                facts['units']['OTHER'] = value
                facts['observations'][1]['unit_id'] = 'OTHER'
            else:
                facts['contexts']['b'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                supplemental.build(self.selection, bundle)

    def test_duplicate_period_and_unqualified_facts_rejected(self):
        self.bundle['financial']['observations'][1]['context_id'] = 'a'
        with self.assertRaisesRegex(ValueError, 'period'):
            supplemental.build(self.selection, self.bundle)
        self.bundle['financial']['observations'][1]['context_id'] = 'b'
        self.bundle['financial']['observations'][0]['status'] = 'unresolved'
        with self.assertRaisesRegex(ValueError, 'Unqualified'):
            supplemental.build(self.selection, self.bundle)

    def test_html_escapes_labels_and_links_every_original_fact(self):
        self.selection[0]['label'] = '<script>fictional</script>'
        seen = []
        rendered = supplemental.render(self.selection, self.bundle,
                                       lambda ids: seen.extend(ids) or '<a>source</a>')
        self.assertEqual(seen, ['F1', 'F2'])
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('[F1]', supplemental.render(self.selection, self.bundle))


class TypedRemediationTests(PassageFixture, unittest.TestCase):
    def state(self):
        return {'artifacts': {'financial': copy.deepcopy(self.financial),
                             'retrieval': copy.deepcopy(self.retrieval),
                             'analysis': copy.deepcopy(self.report)},
                'format': copy.deepcopy(remediation.corrections.EMPTY_FORMAT), 'findings': []}

    def apply_value(self, state, path, value):
        target = remediation.targets(state, self.bundle)[tuple(path)]
        operation = {'id': 'fake-edit', 'path': path, 'kind': target['kind'],
                     'before_sha256': base.digest(target['value']), 'after_sha256': base.digest(value),
                     'value': value, 'reason': 'Fictional source verification',
                     'citations': ['D001'], 'passage_ids': [self.ids[0]]}
        self.last_plan = {'snapshot_sha256': base.digest(state), 'operations': [operation]}
        return remediation.apply(state, self.last_plan, self.bundle, self.catalog)

    def test_source_rows_add_rendered_evidence_without_changing_artifacts(self):
        state = self.state()
        candidate = self.apply_value(state, ['format', 'source_rows'],
                                     [{'label': 'Fictional source measure', 'fact_ids': ['F002']}])
        self.assertEqual(candidate['artifacts'], state['artifacts'])
        rendered = remediation.repair.table(candidate['artifacts']['financial'], self.bundle, candidate['format'])
        self.assertIn('Supplemental financial comparison', rendered)
        self.assertIn('[F002]', rendered)
        self.assertNotIn('source_rows', state['format'])

    def test_reviewer_gets_supplemental_original_context_and_exact_field_delta(self):
        state = self.state()
        candidate = self.apply_value(state, ['format', 'source_rows'],
                                     [{'label': 'Fictional source measure', 'fact_ids': ['F002']}])
        context = remediation.context
        view = context.expand_context(context.build(
            state, candidate, self.last_plan, self.bundle, self.catalog,
            remediation.repair.table(candidate['artifacts']['financial'], self.bundle, candidate['format']),
            'Fictional review standard', financial_context_version=context.FINANCIAL_CONTEXT_VERSION))
        self.assertIn('F002', view['scope_ids'])
        self.assertIn('F002', [r['id'] for r in view['financial_observations']['observations']])
        self.assertIn('F002', [r['fact_id'] for r in view['financial_context_resolution']['resolutions']])
        delta = next(r for r in view['field_changes'] if r['path'] == ['format', 'source_rows'])
        self.assertIsNone(delta['before'])
        self.assertEqual(delta['after'], candidate['format']['source_rows'])

    def test_supplemental_rows_can_be_an_explicit_claim_group_occurrence(self):
        state = self.state()
        candidate = self.apply_value(state, ['format', 'source_rows'],
                                     [{'label': 'Fictional source measure', 'fact_ids': ['F002']}])
        self.last_plan['claim_groups'] = [{'id': 'fictional-source-comparison',
                                          'aliases': ['Fictional source measure'],
                                          'required_paths': [['format', 'source_rows']], 'unchanged': []}]
        self.assertEqual(remediation.apply(state, self.last_plan, self.bundle, self.catalog), candidate)

    def test_quote_removal_preserves_retrieval_and_rejects_new_quote(self):
        state = self.state()
        path = ['artifacts', 'analysis', 'findings', 0, 'quotes']
        candidate = self.apply_value(state, path, [])
        self.assertEqual(candidate['artifacts']['analysis']['findings'][0]['quotes'], [])
        self.assertEqual(candidate['artifacts']['retrieval'], state['artifacts']['retrieval'])
        with self.assertRaisesRegex(ValueError, 'original quote subset'):
            self.apply_value(state, path, [{'passage_id': self.ids[1]}])

    def test_source_link_change_still_requires_exact_question_membership(self):
        from research import earnings_qa_grounding as qa
        self.bundle['qa_grounding'] = qa.build(self.bundle, self.catalog)
        state = self.state()
        row = state['artifacts']['retrieval']['exchange_coverage'][0]
        self.assertTrue(row['answer_passage_ids'])
        with self.assertRaisesRegex(ValueError, 'outside the indexed'):
            self.apply_value(state, ['artifacts', 'retrieval', 'exchange_coverage', 0, 'question_passage_ids'],
                             row['answer_passage_ids'])

    def test_known_exchange_cannot_create_an_unindexed_reverse_continuation(self):
        from research import earnings_qa_grounding as qa
        self.bundle['qa_grounding'] = qa.build(self.bundle, self.catalog)
        state = self.state()
        rows = state['artifacts']['retrieval']['exchange_coverage']
        self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, 'explicit indexed followup'):
            self.apply_value(state, ['artifacts', 'retrieval', 'exchange_coverage', 1, 'continuation_exchange_ids'],
                             [rows[0]['exchange_id']])
