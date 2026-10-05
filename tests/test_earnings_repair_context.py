"""Fictional bounded repair contexts; no network, real issuers, or model calls."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_repair_context as c
from research import earnings_experiment as base


class RepairContextTests(PassageFixture, unittest.TestCase):
    def state(self):
        return {'artifacts': {'financial': copy.deepcopy(self.financial), 'retrieval': copy.deepcopy(self.retrieval), 'analysis': copy.deepcopy(self.report)},
                'format': {'rows': {}, 'basis': {'text': '', 'citations': []}}, 'findings': []}

    def edit(self, before):
        after = copy.deepcopy(before)
        path = ['artifacts', 'analysis', 'opening']
        after['artifacts']['analysis']['opening'] = 'Fictional corrected finding.'
        plan = {'operations': [{'id': 'edit-1', 'path': path, 'reason': 'Fictional correction', 'citations': ['D001'], 'passage_ids': [self.ids[0]]}]}
        return after, plan

    def test_report_complete_context_selective_source_and_unicode_exact(self):
        before = self.state(); after, plan = self.edit(before)
        report = 'FULL FICTIONAL REPORT\nGAAP table: $9.5\u00a0billion\nLast paragraph.'
        ctx = c.build(before, after, plan, self.bundle, self.catalog, report, 'Fictional writing rules')
        self.assertEqual(ctx['report'], report)
        self.assertEqual(ctx['field_changes'][0]['before'], before['artifacts']['analysis']['opening'])
        self.assertEqual(ctx['field_changes'][0]['after'], after['artifacts']['analysis']['opening'])
        self.assertFalse(ctx['stats']['truncated'])
        self.assertNotIn('original_artifacts', ctx)
        self.assertEqual(ctx['candidate_sha256'], base.digest(after))
        for p in ctx['passages']:
            self.assertEqual(p, next(x for x in self.catalog['passages'] if x['passage_id'] == p['passage_id']))
        self.assertEqual(ctx['source_index']['span_columns'], ['source_index','start','end'])
        self.assertTrue(all(len(span) == 3 for _, spans in ctx['source_index']['rows'] for span in spans))

    def test_passage_neighbors_do_not_cross_scope(self):
        before = self.state(); after, plan = self.edit(before)
        rows = [p for p in self.catalog['passages'] if p['scope_id'] == 'D001']
        selected = rows[1]
        plan['operations'][0]['passage_ids'] = [selected['passage_id']]
        ctx = c.build(before, after, plan, self.bundle, self.catalog, 'Full report', 'Rules')
        actual = {p['passage_id'] for p in ctx['passages']}
        self.assertTrue({p['passage_id'] for p in rows[:3]} <= actual)

    def test_turn_evidence_expands_entire_parent_exchange(self):
        exchange = self.bundle['transcript_index']['exchanges'][0]
        turn = exchange['turn_ids'][-1]
        response = c.evidence_response(self.bundle, self.catalog, [{'scope_id': turn, 'reason': 'Need question and complete response'}])
        parent = next(e for e in response['scopes'] if e['id'] == exchange['id'])
        self.assertEqual(len(parent['spans']), len(exchange['turn_ids']))
        self.assertIn(exchange['id'], response['scope_ids'])
        request = {'scope_id': exchange['id'], 'reason': 'Same evidence'}
        again = c.evidence_response(self.bundle, self.catalog, [request, request], response['scope_ids'])
        self.assertEqual(again['scopes'], [])

    def test_findings_select_original_evidence_and_facts_keep_context(self):
        before = self.state(); after, plan = self.edit(before)
        before['findings'] = [{'id': 'finding-fake', 'finding': {'citations': ['D002'], 'passage_ids': [self.ids[-1]]}}]
        ctx = c.build(before, after, plan, self.bundle, self.catalog, 'Full report', 'Rules')
        self.assertIn('D002', ctx['scope_ids'])
        fact = next(o for o in ctx['financial_observations']['observations'] if o['id'] == 'F002')
        self.assertIn(fact['context_id'], ctx['financial_observations']['contexts'])
        self.assertIn(fact['unit_id'], ctx['financial_observations']['units'])

    def test_unknown_request_empty_reason_and_source_tampering_fail(self):
        for request in ({'scope_id': 'unknown', 'reason': 'Check'}, {'scope_id': 'D001', 'reason': ''}, {'scope_id': 'D001', 'reason': 'Check', 'text': 'inject'}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                c.evidence_response(self.bundle, self.catalog, [request])
        (self.root/'filing.txt').write_text('Corrupted fictional source')
        with self.assertRaisesRegex(ValueError, 'Frozen source changed'):
            c.evidence_response(self.bundle, self.catalog, [{'scope_id': 'D001', 'reason': 'Check'}])

    def test_catalogue_source_offsets_and_hashes_are_verified(self):
        before = self.state(); after, plan = self.edit(before)
        catalog = copy.deepcopy(self.catalog)
        next(p for p in catalog['passages'] if p['passage_id'] == self.ids[0])['text'] = 'Invented'
        with self.assertRaisesRegex(ValueError, 'Passage differs'):
            c.build(before, after, plan, self.bundle, catalog, 'Full report', 'Rules')

    def test_context_bound_fails_instead_of_truncating(self):
        before = self.state(); after, plan = self.edit(before)
        with patch.object(c, 'MAX_CONTEXT_CHARACTERS', 100):
            with self.assertRaises(c.ContextTooLarge):
                c.build(before, after, plan, self.bundle, self.catalog, 'Full report', 'Rules')
            with self.assertRaises(c.ContextTooLarge):
                c.evidence_response(self.bundle, self.catalog, [{'scope_id': 'D001', 'reason': 'Read'}])

    def test_duplicate_claim_occurrences_require_all_dispositions(self):
        before = self.state()
        before['artifacts']['analysis']['opening'] = 'Forecast assumes LOW INVENTORY.'
        before['artifacts']['retrieval']['exchange_coverage'][0]['answer'] = 'Forecast assumes low inventory.'
        after, plan = self.edit(before)
        first = ['artifacts', 'analysis', 'opening']
        second = ['artifacts', 'retrieval', 'exchange_coverage', 0, 'answer']
        plan['claim_groups'] = [{'id': 'inventory', 'aliases': ['low inventory'], 'required_paths': [first], 'unchanged': []}]
        with self.assertRaisesRegex(ValueError, 'Unadjudicated claim occurrence'):
            c.propagation_check(before, after, plan)
        plan['claim_groups'][0]['unchanged'] = [{'path': second, 'reason': 'Original qualifier is correct here.'}]
        result = c.propagation_check(before, after, plan)
        self.assertEqual(len(result['groups'][0]['matches']), 2)
        self.assertEqual(result['groups'][0]['matches'][1]['disposition'], 'unchanged')
        self.assertEqual(before['artifacts']['retrieval']['exchange_coverage'][0]['answer'], after['artifacts']['retrieval']['exchange_coverage'][0]['answer'])
        plan['claim_groups'][0]['required_paths'].append(second)
        with self.assertRaisesRegex(ValueError, 'no operation'):
            c.propagation_check(before, after, plan)

    def test_overlapping_scope_text_deduplicated_and_report_dict_preserved(self):
        before = self.state(); after, plan = self.edit(before)
        exchange = self.bundle['transcript_index']['exchanges'][0]
        plan['operations'][0]['citations'] = [exchange['id'], *exchange['turn_ids']]
        report = {'text': 'Entire report table and narrative', 'links': ['#evidence-1']}
        ctx = c.build(before, after, plan, self.bundle, self.catalog, report, 'Rules')
        self.assertEqual(ctx['report'], report)
        blocks = {b['block_id']: b for b in ctx['source_blocks']}
        for scope in ctx['scopes']:
            for span in scope['spans']:
                block = blocks[span['block_id']]
                text = block['text'][span['start']-block['start']:span['end']-block['start']]
                self.assertEqual(c.evidence._sha_text(text), span['span_sha256'])
        observed = [(b['path'],b['start'],b['end']) for b in blocks.values()]
        self.assertEqual(len(observed), len(set(observed)))
        self.assertNotIn('F002', ctx['scope_ids'])
        self.assertIn('F002', [o['id'] for o in ctx['financial_observations']['observations']])

    def test_target_id_operation_context_preserves_original_plan_digest(self):
        from research import earnings_corrections as corrections
        before = self.state(); after, plan = self.edit(before)
        target = next(k for k, v in corrections.registry(before, self.bundle)['targets'].items()
                      if v['path'] == plan['operations'][0]['path'])
        plan['operations'][0].pop('path')
        plan['operations'][0]['target_id'] = target
        ctx = c.build(before, after, plan, self.bundle, self.catalog, 'Full report', 'Rules')
        self.assertEqual(ctx['plan_sha256'], base.digest(plan))
        self.assertEqual(ctx['field_changes'][0]['path'], ['artifacts', 'analysis', 'opening'])
        self.assertNotIn('path', plan['operations'][0])

    def test_changed_exchange_answer_retains_question_without_explicit_citation(self):
        before = self.state(); after = copy.deepcopy(before)
        after['artifacts']['retrieval']['exchange_coverage'][0]['answer'] = 'Corrected response'
        exchange = self.bundle['transcript_index']['exchanges'][0]
        plan = {'operations': [{'id': 'answer', 'path': ['artifacts','retrieval','exchange_coverage',0,'answer'],
                               'reason': 'Fix answer', 'citations': [], 'passage_ids': []}]}
        ctx = c.build(before, after, plan, self.bundle, self.catalog, 'Full report', 'Rules')
        self.assertIn(exchange['id'], ctx['scope_ids'])
        parent = next(row for row in ctx['scopes'] if row['id'] == exchange['id'])
        self.assertEqual(len(parent['spans']), len(exchange['turn_ids']))

    def test_inventory_excludes_quotes_ids_observations_and_keeps_citations(self):
        before = self.state()
        inventory = c.occurrence_inventory(before)
        self.assertTrue(all('quotes' not in r['path'] for r in inventory))
        self.assertTrue(all('rows' not in r['path'] for r in inventory))
        opening = next(r for r in inventory if r['path'] == ['artifacts', 'analysis', 'opening'])
        self.assertEqual(opening['citations'], ['D001'])
        self.assertEqual(c.propagation_check(before, before, {'operations': []})['declared_groups'], 0)


if __name__ == '__main__':
    unittest.main()
