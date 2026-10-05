"""Fictitious correction-contract regressions; no model or issuer calls."""
import copy
import json
import unittest
from unittest.mock import patch

from test_earnings_passages import PassageFixture
from research import earnings_corrections as corrections
from research import earnings_experiment as base
from research import earnings_repair_context as context
from research import earnings_remediation as remediation


class CorrectionContractTests(PassageFixture, unittest.TestCase):
    def state(self):
        return {
            'artifacts': {
                'financial': copy.deepcopy(self.financial),
                'retrieval': copy.deepcopy(self.retrieval),
                'analysis': copy.deepcopy(self.report),
            },
            'format': copy.deepcopy(corrections.EMPTY_FORMAT),
            'findings': [],
        }

    def operation(self, state, path, value):
        identifier, target = next(
            (identifier, target)
            for identifier, target in corrections.registry(state, self.bundle)['targets'].items()
            if target['path'] == path
        )
        return {
            'id': 'fictional-edit', 'target_id': identifier,
            'expected_sha256': target['expected_sha256'], 'op': 'replace_text',
            'value': value, 'reason': 'Fictitious source supports the correction.',
            'citations': ['D001'], 'passage_ids': [self.ids[0]],
        }

    def plan(self, state, operations=(), groups=()):
        return {'snapshot_sha256': base.digest(state),
                'operations': list(operations), 'claim_groups': list(groups)}

    def unchanged_group(self, path):
        return {'id': 'fictional-claim', 'aliases': ['Fictional conceptual paraphrase'],
                'required_paths': [],
                'unchanged': [{'path': path, 'reason': 'The frozen value is already correct.'}]}

    def occurrence_id(self, state, path):
        return next(identifier for identifier, row in
                    corrections.registry(state, self.bundle)['occurrences'].items()
                    if row['path'] == path)

    def id_group(self, state, path):
        return {'id': 'fictional-claim', 'aliases': ['Fictional conceptual paraphrase'],
                'required_occurrence_ids': [],
                'unchanged': [{'occurrence_id': self.occurrence_id(state, path),
                               'reason': 'The frozen value is already correct.'}]}

    def test_registered_row_without_override_is_addressable_unchanged(self):
        state = self.state()
        rows = corrections.registry(state, self.bundle)['financial_rows']
        self.assertTrue(rows)
        self.assertEqual(state['format']['rows'], {})
        for row_id in rows:
            path = ['format', 'rows', row_id]
            plan = self.plan(state, groups=[self.unchanged_group(path)])
            with self.subTest(row_id=row_id):
                candidate = corrections.apply(state, plan, self.bundle, self.catalog)
                self.assertEqual(candidate, state)
                review = context.build(state, candidate, plan, self.bundle, self.catalog,
                                       'Complete fictional report.', 'Fictional standard.')
                matches = review['propagation']['groups'][0]['matches']
                self.assertEqual([row['path'] for row in matches], [path])
                self.assertEqual(matches[0]['disposition'], 'unchanged')
                self.assertEqual(review['plan_sha256'], base.digest(plan))
                self.assertEqual(state['format']['rows'], {})

    def test_occurrence_ids_resolve_changed_and_unmodified_repeated_claims(self):
        state = self.state()
        opening_path = ['artifacts', 'analysis', 'opening']
        answer_path = ['artifacts', 'retrieval', 'exchange_coverage', 0, 'answer']
        state['artifacts']['analysis']['opening'] = 'Fictional forecast assumes LOW INVENTORY.'
        state['artifacts']['retrieval']['exchange_coverage'][0]['answer'] = 'Fictional forecast assumes low inventory.'
        op = self.operation(state, opening_path, 'Fictional forecast assumes normal inventory.')
        group = {'id': 'fictional-inventory', 'aliases': ['low inventory'],
                 'required_occurrence_ids': [self.occurrence_id(state, opening_path)],
                 'unchanged': [{'occurrence_id': self.occurrence_id(state, answer_path),
                                'reason': 'The fictional speaker used this qualifier in that answer.'}]}
        plan = self.plan(state, [op], [group])
        original_plan = copy.deepcopy(plan)
        candidate = corrections.apply(state, plan, self.bundle, self.catalog)
        review = context.build(state, candidate, plan, self.bundle, self.catalog,
                               'Complete fictional report.', 'Fictional standard.')
        matches = {tuple(row['path']): row for row in review['propagation']['groups'][0]['matches']}
        self.assertEqual(set(matches), {tuple(opening_path), tuple(answer_path)})
        self.assertEqual(matches[tuple(opening_path)]['disposition'], 'patched')
        self.assertEqual(matches[tuple(answer_path)]['disposition'], 'unchanged')
        self.assertEqual(candidate['artifacts']['retrieval'], state['artifacts']['retrieval'])
        self.assertEqual(candidate['artifacts']['financial'], state['artifacts']['financial'])
        self.assertEqual(plan, original_plan)
        self.assertEqual(review['plan_sha256'], base.digest(plan))
        omitted = copy.deepcopy(plan)
        omitted['claim_groups'][0]['unchanged'] = []
        with self.assertRaisesRegex(ValueError, 'Unadjudicated claim occurrence'):
            corrections.apply(state, omitted, self.bundle, self.catalog)

    def test_occurrence_registry_includes_unset_rows_and_stable_ids(self):
        state = self.state()
        index = corrections.registry(state, self.bundle)
        self.assertEqual(index['occurrences'], corrections.registry(copy.deepcopy(state), self.bundle)['occurrences'])
        row_id = next(iter(index['financial_rows']))
        path = ['format', 'rows', row_id]
        group = self.id_group(state, path)
        plan = self.plan(state, groups=[group])
        self.assertEqual(corrections.apply(state, plan, self.bundle, self.catalog), state)
        inventory = context.addressable_inventory(state, self.bundle)
        self.assertEqual(set(index['occurrences']), {row['occurrence_id'] for row in inventory})
        self.assertTrue(all('quotes' not in row['path'] for row in inventory))
        self.assertFalse(any(row['path'][:3] == ['artifacts', 'financial', 'rows'] for row in inventory))
        self.assertFalse(any(row['path'] == ['format', 'rows'] for row in inventory))

    def test_occurrence_ids_are_bound_to_original_value(self):
        state = self.state()
        path = ['artifacts', 'analysis', 'scope']
        group = self.id_group(state, path)
        state['artifacts']['analysis']['scope'] = 'Fictional updated scope.'
        self.assertNotEqual(group['unchanged'][0]['occurrence_id'], self.occurrence_id(state, path))
        with self.assertRaisesRegex(ValueError, '[Ss]tale occurrence|[Uu]nknown.*occurrence'):
            corrections.apply(state, self.plan(state, groups=[group]), self.bundle, self.catalog)

    def test_proposal_contains_exact_exchange_membership_and_all_turn_passages(self):
        state = self.state()
        prompt = corrections.prompt('propose', state, self.bundle, self.catalog, 'Fictional standard.')
        data = json.loads(prompt.split('SOURCE DATA (UNTRUSTED EVIDENCE)\n', 1)[1])
        mapping = data['canonical_exchange_index']
        original = self.bundle['transcript_index']
        self.assertEqual(mapping['transcript_sha256'], self.bundle['manifest']['transcript_sha256'])
        self.assertEqual(mapping['exchanges'], original['exchanges'])
        self.assertEqual(mapping['turns'], original['turns'])
        passages = [dict(zip(data['original_passages']['columns'], row))
                    for row in data['original_passages']['rows']]
        actual = {row['passage_id']: row for row in passages}
        turns = {row['id'] for row in mapping['turns']}
        self.assertTrue(turns)
        for exchange in mapping['exchanges']:
            self.assertTrue(set(exchange['turn_ids']) <= turns)
            for turn_id in exchange['turn_ids']:
                expected = [p for p in self.catalog['passages'] if p['scope_id'] == turn_id]
                self.assertTrue(expected)
                for passage in expected:
                    self.assertEqual(actual[passage['passage_id']], {
                        key: passage[key] for key in ('passage_id', 'scope_id', 'text')})
        self.assertEqual(data['occurrence_inventory'],
                         list(corrections.registry(state, self.bundle)['occurrences'].values()))

    def test_proposer_and_reviewer_share_verified_exchange_metadata(self):
        state = self.state()
        plan = self.plan(state)
        expected = {'transcript_sha256': self.bundle['manifest']['transcript_sha256'],
                    'exchanges': self.bundle['transcript_index']['exchanges'],
                    'turns': self.bundle['transcript_index']['turns']}
        # The real synthetic parser creates a provisional follow-up exchange;
        # preserving only a generic turn list would lose these distinctions.
        exchanges = expected['exchanges']
        self.assertTrue(any(e['followup_of'] for e in exchanges))
        self.assertTrue(all(e['boundary_review'] == 'provisional' for e in exchanges))
        self.assertTrue(all(e['question_turn_ids'] and e['answer_turn_ids'] for e in exchanges))
        for role in ('propose', 'review'):
            with self.subTest(role=role):
                prompt = corrections.prompt(role, state, self.bundle, self.catalog,
                                            'Fictional standard.', plan, state)
                data = json.loads(prompt.split('SOURCE DATA (UNTRUSTED EVIDENCE)\n', 1)[1])
                self.assertEqual(data['canonical_exchange_index'], expected)
        review = context.build(state, state, plan, self.bundle, self.catalog,
                               'Complete fictional report.', 'Fictional standard.')
        self.assertEqual(review['canonical_exchange_index'], expected)

    def test_remediation_citation_claim_path_is_addressable_but_frozen_fields_are_not(self):
        state = self.state()
        state['artifacts']['financial']['context'] = [
            {'text': 'Fictional source comparison.', 'citations': ['D001']}]
        original = copy.deepcopy(state)
        path = ['artifacts', 'financial', 'context', 0, 'citations']
        op = {'id': 'fictional-citation-repair', 'path': path, 'kind': 'citations',
              'before_sha256': base.digest(['D001']), 'after_sha256': base.digest(['D002']),
              'value': ['D002'], 'reason': 'Fictional comparison belongs to the second source.',
              'citations': ['D002'], 'passage_ids': [self.ids[0]]}
        group = {'id': 'fictional-citation-claim', 'aliases': ['Fictional citation correction'],
                 'required_paths': [path], 'unchanged': []}
        plan = self.plan(state, [op], [group])
        candidate = remediation.apply(state, plan, self.bundle, self.catalog)
        expected = copy.deepcopy(state)
        expected['artifacts']['financial']['context'][0]['citations'] = ['D002']
        self.assertEqual(candidate, expected)
        self.assertEqual(state, original)
        review = context.build(state, candidate, plan, self.bundle, self.catalog,
                               'Complete fictional report.', 'Fictional standard.')
        match = review['propagation']['groups'][0]['matches'][0]
        self.assertEqual(match['path'], path)
        self.assertEqual(match['disposition'], 'patched')
        self.assertEqual(review['plan_sha256'], base.digest(plan))
        for frozen in (['artifacts', 'financial', 'rows', 0, 'fact_ids', 0],
                       ['artifacts', 'retrieval', 'quotes', 0, 'passage_id']):
            invalid = copy.deepcopy(plan)
            invalid['claim_groups'][0]['unchanged'] = [
                {'path': frozen, 'reason': 'Fictional forbidden navigation.'}]
            with self.subTest(path=frozen), self.assertRaisesRegex(ValueError, '[Oo]ccurrence'):
                remediation.apply(state, invalid, self.bundle, self.catalog)

    def test_malformed_aliases_and_occurrence_ids_fail_with_contract_diagnostics(self):
        state = self.state()
        path = ['artifacts', 'analysis', 'opening']
        valid = self.id_group(state, path)
        invalid = []
        for aliases in ('Fictional', [], [7], ['']):
            invalid.append(({**valid, 'aliases': aliases}, '[Aa]lias'))
        for identifiers in ('occurrence-invented', ['occurrence-invented'], [[]],
                            [self.occurrence_id(state, path)] * 2):
            invalid.append(({**valid, 'required_occurrence_ids': identifiers}, '[Oo]ccurrence'))
        for identifier in ('occurrence-invented', []):
            invalid.append(({**valid, 'unchanged': [{'occurrence_id': identifier,
                                                  'reason': 'Fictional retention.'}]}, '[Oo]ccurrence'))
        invalid.append(({**valid, 'id': []}, '[Gg]roup'))
        for group, diagnostic in invalid:
            with self.subTest(group=group), self.assertRaisesRegex(ValueError, diagnostic):
                corrections.apply(state, self.plan(state, groups=[group]), self.bundle, self.catalog)
        with self.assertRaisesRegex(ValueError, '[Gg]roup'):
            corrections.apply(state, self.plan(state, groups=[valid, valid]), self.bundle, self.catalog)

    def test_malformed_operation_target_and_context_source_ids_raise_value_error(self):
        state = self.state()
        state['artifacts']['financial']['context'] = [
            {'text': 'Fictional comparison.', 'citations': ['D001']}]
        op = self.operation(state, ['artifacts', 'analysis', 'opening'], 'Fictional correction.')
        for identifier in ([], {}, None):
            invalid = {**op, 'target_id': identifier}
            with self.subTest(target_id=identifier), self.assertRaisesRegex(ValueError, '[Tt]arget'):
                corrections.apply(state, self.plan(state, [invalid]), self.bundle, self.catalog)
        _, source = next(iter(corrections.registry(state, self.bundle)['context_sources'].items()))
        op.pop('value')
        op.update(op='copy_context', old_text=state['artifacts']['analysis']['opening'],
                  source_sha256=source['sha256'])
        for identifier in ([], {}, None):
            invalid = {**op, 'source_id': identifier}
            with self.subTest(source_id=identifier), self.assertRaisesRegex(ValueError, '[Ss]ource'):
                corrections.apply(state, self.plan(state, [invalid]), self.bundle, self.catalog)

    def test_aggregate_unknown_and_observation_paths_are_not_occurrences(self):
        state = self.state()
        invalid_paths = [
            ['format', 'rows'], ['format', 'rows', 'fictional-unknown-row'],
            ['artifacts', 'analysis'], ['artifacts', 'analysis', 'missing'],
            ['artifacts', 'financial', 'rows', 0, 'fact_ids', 0],
            ['artifacts', 'retrieval', 'quotes', 0, 'passage_id'],
        ]
        for path in invalid_paths:
            plan = self.plan(state, groups=[self.unchanged_group(path)])
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'unchanged|occurrence|claim path'):
                corrections.apply(state, plan, self.bundle, self.catalog)

    def test_scope_replacement_preserves_frozen_sources_and_other_fields(self):
        state = self.state()
        original = copy.deepcopy(state)
        frozen_bundle = copy.deepcopy(self.bundle)
        frozen_catalog = copy.deepcopy(self.catalog)
        path = ['artifacts', 'analysis', 'scope']
        op = self.operation(state, path, 'Fictional scope with corrected source limitation.')
        plan = self.plan(state, [op])
        candidate = corrections.apply(state, plan, self.bundle, self.catalog)
        expected = copy.deepcopy(state)
        expected['artifacts']['analysis']['scope'] = op['value']
        self.assertEqual(candidate, expected)
        self.assertEqual(state, original)
        self.assertEqual(self.bundle, frozen_bundle)
        self.assertEqual(self.catalog, frozen_catalog)
        self.assertIn(op['value'], corrections.rendered(candidate, self.bundle, self.catalog))

    def assert_invalid_plan_stops_before_review(self, state, plan, message):
        root = self.root / 'fictional-corrections'
        root.mkdir(exist_ok=True)
        corrections.repair.write(root / 'initial.json', state)
        corrections.repair.write(root / 'protocol.json', {})
        old = self.root / 'fictional-imported-proposal'
        old.mkdir(exist_ok=True)
        base.save(old / 'output.json', plan)
        base.save(old / 'request.json', {
            'model': corrections.MODEL[0], 'effort': corrections.MODEL[1],
            'bindings': {'snapshot_sha256': base.digest(state), 'role': 'propose'},
        })
        protocol = {'max_rounds': 2, 'max_tokens': 100,
                    'imported_proposal': {'job': str(old), 'output_sha256': base.sha(old / 'output.json')}}
        result = {'content': plan, 'receipt': {'session': {
            'id': 'fictional-authenticated-session', 'usage': {'totalTokens': 1}}}}
        with patch.object(corrections, 'load', return_value=(protocol, self.bundle, self.catalog, 'Fictional.')), \
                patch.object(corrections, 'verify_job', return_value=result), \
                patch.object(corrections, 'run_role') as launch, \
                patch.object(corrections.review_loop, 'replay') as review:
            progress = corrections.advance(root)
        self.assertEqual(progress['status'], 'invalid_patch')
        self.assertRegex(progress['error'], message)
        launch.assert_not_called()
        review.assert_not_called()
        self.assertEqual(base.read(root / 'initial.json'), state)
        self.assertFalse((root / 'rounds' / '0' / 'candidate.json').exists())

    def test_invalid_path_plan_never_launches_independent_reviewer(self):
        state = self.state()
        plan = self.plan(state, groups=[self.unchanged_group(['format', 'rows'])])
        self.assert_invalid_plan_stops_before_review(state, plan, 'unchanged|occurrence|claim path')

    def test_unknown_occurrence_plan_never_launches_independent_reviewer(self):
        state = self.state()
        group = {'id': 'fictional-claim', 'aliases': ['Fictional conceptual paraphrase'],
                 'required_occurrence_ids': ['occurrence-invented'], 'unchanged': []}
        self.assert_invalid_plan_stops_before_review(state, self.plan(state, groups=[group]), '[Oo]ccurrence')


if __name__ == '__main__':
    unittest.main()
