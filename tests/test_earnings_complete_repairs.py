"""Fictitious complete correction batches; no model calls or private artifacts."""
import copy
import json
import unittest
from unittest.mock import patch

from test_earnings_passages import PassageFixture
from research import earnings_corrections as c
from research import earnings_experiment as base


class CompleteRepairsTests(PassageFixture, unittest.TestCase):
    def state(self, grounded=False):
        retrieval = copy.deepcopy(self.retrieval)
        if not grounded:
            for row in retrieval['exchange_coverage']:
                for key in c.qa_grounding.FIELDS:
                    row.pop(key, None)
        return {'artifacts': {'financial': copy.deepcopy(self.financial), 'retrieval': retrieval,
                              'analysis': copy.deepcopy(self.report)},
                'format': copy.deepcopy(c.EMPTY_FORMAT), 'findings': []}

    def op(self, state, path, kind, value, identifier='fictional-edit', **extra):
        target_id, target = next((key, row) for key, row in c.registry(state, self.bundle)['targets'].items()
                                 if row['path'] == path)
        return {'id': identifier, 'target_id': target_id, 'expected_sha256': target['expected_sha256'],
                'op': kind, 'value': value, 'reason': 'Fictitious original-source correction.',
                'citations': ['D002'], 'passage_ids': [self.ids[0]], **extra}

    def plan(self, state, operations, groups=None):
        result = {'snapshot_sha256': base.digest(state), 'operations': operations}
        if groups is not None:
            result['claim_groups'] = groups
        return result

    def review(self, state, candidate, plan):
        evidence = {'reason': 'Fictitious independent verification.', 'citations': ['D002'],
                    'passage_ids': [self.ids[0]]}
        return {'candidate_sha256': base.digest(candidate), 'plan_sha256': base.digest(plan),
                'approve_patch': True, 'verdict': 'pass',
                'criteria': {key: {'status': 'pass', 'evidence': 'Fictitious check.'} for key in c.legacy.CRITERIA},
                'operations': [{'id': op['id'], 'approve': True, **evidence} for op in plan['operations']],
                'resolutions': [], 'findings': []}

    def test_exact_citations_remove_stale_support_without_other_changes(self):
        state = self.state(); original = copy.deepcopy(state)
        path = ['artifacts', 'analysis', 'findings', 0, 'citations']
        state['artifacts']['analysis']['findings'][0]['citations'] = ['D001', 'D002']
        original = copy.deepcopy(state)
        op = self.op(state, path, 'replace_citations', ['D002'])
        candidate = c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)
        expected = copy.deepcopy(state); expected['artifacts']['analysis']['findings'][0]['citations'] = ['D002']
        self.assertEqual(candidate, expected)
        self.assertEqual(state, original)

    def test_citation_replacements_reject_stale_unknown_empty_duplicate_values(self):
        state = self.state(); path = ['artifacts', 'analysis', 'opening_citations']
        for value in ([], ['invented'], ['D002', 'D002'], 'D002', [7]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                c.apply(state, self.plan(state, [self.op(state, path, 'replace_citations', value)]), self.bundle, self.catalog)
        op = self.op(state, path, 'replace_citations', ['D002']); op['expected_sha256'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'Stale target'):
            c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)

    def test_explicit_and_implicit_citation_writers_conflict_in_either_order(self):
        state = self.state()
        text = self.op(state, ['artifacts', 'analysis', 'opening'], 'replace_text', 'Fictitious amended statement.', 'text')
        cites = self.op(state, ['artifacts', 'analysis', 'opening_citations'], 'replace_citations', ['D002'], 'citations')
        for ops in ([text, cites], [cites, text]):
            with self.subTest(order=[op['id'] for op in ops]), self.assertRaisesRegex(ValueError, 'citation writer'):
                c.apply(state, self.plan(state, ops), self.bundle, self.catalog)
        text['citation_mode'] = 'preserve'
        candidate = c.apply(state, self.plan(state, [text, cites]), self.bundle, self.catalog)
        self.assertEqual(candidate['artifacts']['analysis']['opening'], text['value'])
        self.assertEqual(candidate['artifacts']['analysis']['opening_citations'], ['D002'])

    def test_citation_mode_does_not_expand_unsupported_operation_schema(self):
        state = self.state()
        for path, kind, value in ((['artifacts', 'analysis', 'scope'], 'replace_text', 'Fictitious scope.'),
                                  (['artifacts', 'analysis', 'opening_citations'], 'replace_citations', ['D002'])):
            op = self.op(state, path, kind, value, citation_mode='preserve')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)

    def test_complete_exchange_expands_leaf_deltas_and_preserves_identity_and_quotes(self):
        state = self.state(); path = ['artifacts', 'retrieval', 'exchange_coverage', 0]
        original = copy.deepcopy(state)
        value = {key: 'Fictitious corrected ' + key + '.' for key in c.EXCHANGE_FIELDS}
        op = self.op(state, path, 'replace_exchange', value)
        plan = self.plan(state, [op]); frozen_plan = copy.deepcopy(plan)
        candidate = c.apply(state, plan, self.bundle, self.catalog)
        expected = copy.deepcopy(state); expected['artifacts']['retrieval']['exchange_coverage'][0].update(value)
        self.assertEqual(candidate, expected)
        self.assertEqual(state, original); self.assertEqual(plan, frozen_plan)
        normalized = c.normalize_plan(state, plan, self.bundle)
        self.assertEqual([row['path'] for row in normalized['operations']], [path + [key] for key in c.EXCHANGE_FIELDS])
        self.assertTrue(all(row['parent_operation_id'] == op['id'] for row in normalized['operations']))
        context = c.context.expand_context(c.context.build(state, candidate, plan, self.bundle, self.catalog,
                                                           'Complete fictitious report.', 'Fictitious standard.'))
        self.assertEqual(len(context['field_changes']), 3)
        self.assertTrue(all(row['parent_operation_id'] == op['id'] for row in context['field_changes']))
        self.assertEqual(context['plan_sha256'], base.digest(plan))
        self.assertEqual(candidate['artifacts']['retrieval']['quotes'], state['artifacts']['retrieval']['quotes'])
        self.assertEqual(candidate['artifacts']['financial'], state['artifacts']['financial'])

    def test_grouped_exchange_claims_resolve_every_leaf_without_aggregate_occurrences(self):
        state = self.state(); path = ['artifacts', 'retrieval', 'exchange_coverage', 0]
        value = {key: 'Fictitious corrected ' + key for key in c.EXCHANGE_FIELDS}
        op = self.op(state, path, 'replace_exchange', value)
        occurrences = c.registry(state, self.bundle)['occurrences']
        ids = [key for key, row in occurrences.items() if row['path'] in [path + [field] for field in c.EXCHANGE_FIELDS]]
        groups = [{'id': 'fictional-exchange', 'aliases': ['Fictional'], 'required_occurrence_ids': ids, 'unchanged': []}]
        # All unrelated literal matches must be explicitly retained.
        groups[0]['unchanged'] = [{'occurrence_id': key, 'reason': 'Fictitious unrelated claim remains valid.'}
                                 for key, row in occurrences.items() if key not in ids and 'fictional' in row['text'].casefold()]
        candidate = c.apply(state, self.plan(state, [op], groups), self.bundle, self.catalog)
        normalized = c.normalize_plan(state, self.plan(state, [op], groups), self.bundle)
        result = c.context.propagation_check(state, candidate, normalized, self.bundle)
        self.assertEqual(sum(row['disposition'] == 'patched' for row in result['groups'][0]['matches']), 3)

    def test_exchange_schema_and_overlapping_field_writers_fail_atomically(self):
        state = self.state(); path = ['artifacts', 'retrieval', 'exchange_coverage', 0]
        value = {key: 'Fictitious ' + key for key in c.EXCHANGE_FIELDS}
        for invalid in ({'answer': 'Incomplete'}, {**value, 'exchange_id': 'invented'},
                        {**value, 'quotes': []}, {**value, 'question': 'x' * 4001}):
            with self.subTest(keys=list(invalid)), self.assertRaises(ValueError):
                c.apply(state, self.plan(state, [self.op(state, path, 'replace_exchange', invalid)]), self.bundle, self.catalog)
        grouped = self.op(state, path, 'replace_exchange', value, 'group')
        leaf = self.op(state, path + ['answer'], 'replace_text', 'Fictitious answer.', 'leaf')
        for operations in ([grouped, leaf], [leaf, grouped]):
            with self.assertRaisesRegex(ValueError, 'Conflicting logical'):
                c.apply(state, self.plan(state, operations), self.bundle, self.catalog)

    def test_grounded_group_requires_support_fields_and_revalidates_membership(self):
        self.bundle['qa_grounding'] = c.qa_grounding.build(self.bundle, self.catalog)
        state = self.state(grounded=True); path = ['artifacts', 'retrieval', 'exchange_coverage', 0]
        row = state['artifacts']['retrieval']['exchange_coverage'][0]
        value = {key: copy.deepcopy(row[key]) for key in c.exchange_fields(row)}
        value['answer'] = 'Fictitious corrected answer with retained exact support.'
        op = self.op(state, path, 'replace_exchange', value)
        c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)
        self.assertEqual(len(c.normalize_plan(state, self.plan(state, [op]), self.bundle)['operations']), 8)
        for invalid in ({key: value[key] for key in c.EXCHANGE_FIELDS},
                        {**value, 'answer_passage_ids': value['question_passage_ids']},
                        {**value, 'grounding_status': 'unresolved'}):
            with self.subTest(keys=list(invalid)), self.assertRaises(ValueError):
                c.apply(state, self.plan(state, [self.op(state, path, 'replace_exchange', invalid)]), self.bundle, self.catalog)

    def test_more_than_24_legacy_edits_remain_atomic_and_each_needs_a_decision(self):
        state = self.state()
        state['artifacts']['financial']['context'] = [{'text': 'Fictitious context ' + str(i), 'citations': ['D001']} for i in range(8)]
        state['artifacts']['retrieval']['document_findings'] = [{'text': 'Fictitious document ' + str(i), 'citations': ['D001']} for i in range(8)]
        paths = ([['artifacts', 'financial', 'context', i, 'text'] for i in range(8)] +
                 [['artifacts', 'retrieval', 'document_findings', i, 'text'] for i in range(8)] +
                 [['artifacts', 'analysis', 'findings', i, field] for i in range(4) for field in ('heading', 'text')] +
                 [['artifacts', 'analysis', 'opening']])
        operations = [self.op(state, path, 'replace_text', 'Fictitious corrected field ' + str(i), 'edit-' + str(i)) for i, path in enumerate(paths)]
        plan = self.plan(state, operations)
        candidate = c.apply(state, plan, self.bundle, self.catalog)
        self.assertEqual(len(operations), 25)
        review = self.review(state, candidate, plan)
        self.assertEqual(c.adjudicate(state, candidate, plan, review, self.bundle, self.catalog)[1], 'accepted')
        review['operations'].pop()
        with self.assertRaisesRegex(ValueError, 'each operation once'):
            c.adjudicate(state, candidate, plan, review, self.bundle, self.catalog)
        broken = copy.deepcopy(plan); broken['operations'][-1]['expected_sha256'] = 'stale'
        original = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            c.apply(state, broken, self.bundle, self.catalog)
        self.assertEqual(state, original)

    def test_explicit_plan_and_payload_limits_fail_closed(self):
        state = self.state(); path = ['artifacts', 'analysis', 'opening']
        op = self.op(state, path, 'replace_text', 'Fictitious replacement.')
        with patch.object(c, 'MAX_PLAN_BYTES', 10), self.assertRaisesRegex(ValueError, 'UTF-8 bytes'):
            c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)
        with patch.object(c, 'MAX_REPLACEMENT_CHARACTERS', 10), self.assertRaisesRegex(ValueError, 'replacement payload'):
            c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)
        op['reason'] = 'x' * (c.MAX_REASON_CHARACTERS + 1)
        with self.assertRaisesRegex(ValueError, 'Operation reason'):
            c.apply(state, self.plan(state, [op]), self.bundle, self.catalog)

    def test_per_table_labels_and_row_labels_preserve_every_numeric_observation(self):
        state = self.state(); original = copy.deepcopy(state)
        tables = c.repair.table_catalog(state['artifacts']['financial'], self.bundle)
        table_id, table = next(iter(tables.items()))
        op = self.op(state, ['format', 'tables', table_id], 'set_table_labels',
                     {'unit_label': 'Fictitious reported units', 'period_labels': [period['label'] for period in table['periods']]})
        row_id = next(iter(c.repair.row_catalog(state['artifacts']['financial'], self.bundle)))
        row = self.op(state, ['format', 'rows', row_id], 'set_display', {'label': 'Fictitious precise row label', 'dimensions': ''}, 'row-label')
        candidate = c.apply(state, self.plan(state, [op, row]), self.bundle, self.catalog)
        self.assertEqual(candidate['artifacts'], original['artifacts'])
        self.assertEqual(candidate['format']['tables'][table_id]['citations'], ['D002'])
        self.assertIn('Fictitious reported units', c.rendered(candidate, self.bundle, self.catalog))
        self.assertIn('Fictitious precise row label', c.rendered(candidate, self.bundle, self.catalog))
        invalid = copy.deepcopy(op); invalid['value']['period_labels'] = []
        with self.assertRaisesRegex(ValueError, 'column count'):
            c.apply(state, self.plan(state, [invalid]), self.bundle, self.catalog)
        self.assertEqual(state, original)

    def test_prompt_supplies_executable_contract_without_old_field_cap(self):
        state = self.state()
        text = c.prompt('propose', state, self.bundle, self.catalog, 'Fictitious standard.')
        data = json.loads(text.split('SOURCE DATA (UNTRUSTED EVIDENCE)\n', 1)[1])
        self.assertNotIn('At most 24 operations', text)
        self.assertEqual(data['batch_contract']['maximum_operations'], len(data['registry']['targets']))
        self.assertEqual(data['batch_contract']['maximum_plan_utf8_bytes'], c.MAX_PLAN_BYTES)
        self.assertEqual(data['metadata_operation_contract']['replace_exchange']['grounded_value_fields'],
                         list(c.EXCHANGE_FIELDS + c.qa_grounding.FIELDS))


if __name__ == '__main__':
    unittest.main()
