"""Fictional exact narrative patches; no models or live source data."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research import earnings_sequential_revisions as revisions


class SequentialRevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = self.root/'original.txt'
        self.raw.write_text('Entirely fictional original evidence Q1.')
        case = self.root/'case.json'
        case.write_text(json.dumps({'sources': [{'path': str(self.raw), 'sha256': self.sha(self.raw)}], 'artifacts': []}))
        source_outputs = self.save_many({
            'sources/manifest.json': {'case_path': str(case), 'case_sha256': self.sha(case), 'scope_notes': ['Fictional snapshot.']},
            'sources/financial.json': {'fictional_fact': 10},
            'writing-standard.md': 'Plain fictional analysis.', 'passages.json': {'fictional': True}})
        self.financial = {'fictional_revenue': 10}
        financial_outputs = self.save_many({'financial-analysis.json': self.financial,
                                           'financial-configuration.json': {'fictional_quarter': '2040-Q1'},
                                           'financial-tables.md': '| Fictional revenue | 10 |'})
        paragraph = {'text': 'Fictional uncertainty remains.', 'citations': ['Q1']}
        self.analysis = {'title': 'Fictional company', 'opening': copy.deepcopy(paragraph),
                         'sections': {name: copy.deepcopy(paragraph) for name in revisions.SECTIONS},
                         'qa': [{'exchange_id': 'Q1', 'question': 'Fictional question?', 'answer': 'Fictional answer.',
                                 'assessment': 'Fictional uncertainty.', 'citations': ['Q1']}],
                         'next_tests': [copy.deepcopy(paragraph)]}
        self.review = {'verdict': 'revise', 'criteria': {'source_accuracy': {'status': 'pass', 'evidence': 'Fictional evidence.', 'citations': ['Q1']},
                                                       'reasoning': {'status': 'fail', 'evidence': 'Missing caveat.', 'citations': ['Q1']}},
                       'questions': {}, 'findings': [{'location': 'earnings', 'problem': 'Missing qualification.',
                                                     'fix': 'State the fictional qualification.', 'citations': ['F1']}]}
        baseline = self.save_many({'analysis-r0.json': self.analysis, 'review-r0.json': self.review})
        candidate = self.render(self.analysis, self.financial, self.root/'sources/manifest.json')
        (self.root/'report.md').write_text(candidate)
        candidate_sha = self.sha(self.root/'report.md')
        self.job = {'revision_round': 1, 'candidate_artifact': 'report.md',
                    'artifacts': {**source_outputs, **financial_outputs, **baseline},
                    'revision_input': {'report.md': candidate_sha},
                    'attempts': [
                        {'id': 's0', 'stage': 'sources', 'status': 'completed', 'revision_round': 0, 'outcome': {'outputs': source_outputs}},
                        {'id': 'f0', 'stage': 'financial_tables', 'status': 'completed', 'revision_round': 0, 'outcome': {'outputs': financial_outputs}},
                        {'id': 'a0', 'stage': 'analysis', 'status': 'completed', 'revision_round': 0,
                         'outcome': {'outputs': {'analysis-r0.json': baseline['analysis-r0.json'], 'report.md': candidate_sha}}},
                        {'id': 'r0', 'stage': 'review', 'status': 'revise', 'revision_round': 0,
                         'outcome': {'outputs': {'review-r0.json': baseline['review-r0.json']}, 'input_sha256': candidate_sha}}]}

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save_many(self, values):
        outputs = {}
        for name, value in values.items():
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value if isinstance(value, str) else json.dumps(value))
            outputs[name] = self.sha(path)
        return outputs

    @staticmethod
    def render(analysis, financial, manifest):
        return json.dumps({'analysis': analysis, 'financial': financial,
                           'scope': json.loads(manifest.read_text())['scope_notes']}, sort_keys=True) + '\n'

    def plan(self):
        return revisions.plan(self.root, self.job, self.render)

    def replacement(self):
        return {'replacements': {'earnings': {'text': 'Fictional uncertainty includes the missing qualification.', 'citations': ['Q1', 'F1']}}}

    def rebind_review(self):
        outputs = self.save_many({'review-r0.json': self.review})
        self.job['artifacts'].update(outputs)
        self.job['attempts'][-1]['outcome']['outputs'].update(outputs)

    def test_exact_patch_preserves_every_unaffected_value(self):
        plan = self.plan()
        self.assertEqual(plan['allowed_locations'], ['earnings'])
        self.assertEqual(plan['citations'], ['F1', 'Q1'])
        self.assertEqual(set(plan['previous_passed_criteria']), {'source_accuracy'})
        merged = revisions.apply(plan, self.replacement())
        expected = copy.deepcopy(self.analysis)
        expected['sections']['earnings'] = self.replacement()['replacements']['earnings']
        self.assertEqual(merged, expected)
        self.assertEqual(self.analysis, plan['previous_analysis'])

    def test_missing_extra_locations_and_title_edit_are_rejected(self):
        plan = self.plan()
        for value in ({'replacements': {}}, {'replacements': {**self.replacement()['replacements'], 'title': 'Other'}},
                      {**self.replacement(), 'title': 'Other'}):
            with self.assertRaises(ValueError): revisions.apply(plan, value)

    def test_audit_rejects_changed_unaffected_component_or_rendered_bytes(self):
        plan = self.plan(); merged = revisions.apply(plan, self.replacement())
        changed = copy.deepcopy(merged); changed['sections']['demand']['text'] = 'Unreviewed new claim.'
        with self.assertRaisesRegex(ValueError, 'unreviewed'):
            revisions.audit(self.root, self.job, plan, changed, self.render(changed, self.financial, self.root/'sources/manifest.json'), self.render)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            revisions.audit(self.root, self.job, plan, merged, 'Different candidate', self.render)

    def test_tampered_baseline_and_original_sources_are_rejected(self):
        (self.root/'analysis-r0.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.plan()
        self.save_many({'analysis-r0.json': self.analysis})
        self.raw.write_text('Changed fictional source')
        with self.assertRaisesRegex(ValueError, 'original source changed'):
            self.plan()

    def test_rebound_writing_standard_cannot_change_original_source_contract(self):
        updated = self.save_many({'writing-standard.md': 'Changed writing instruction'})
        self.job['artifacts'].update(updated)
        with self.assertRaisesRegex(ValueError, 'writing-standard bindings changed'):
            self.plan()

    def test_multiple_findings_on_one_component_require_one_replacement(self):
        self.review['findings'].append({'location': 'earnings', 'problem': 'Another fictional issue.',
                                        'fix': 'Explain the second caveat.', 'citations': ['D2']})
        self.rebind_review()
        plan = self.plan()
        self.assertEqual(plan['allowed_locations'], ['earnings'])
        self.assertEqual(len(plan['previous_review']['findings']), 2)
        self.assertIn('D2', plan['citations'])
        revisions.apply(plan, self.replacement())

    def test_financial_findings_require_changed_archives_and_changes_require_findings(self):
        self.review['findings'][0]['location'] = 'financial_tables'
        self.rebind_review()
        with self.assertRaisesRegex(ValueError,'changed, archived tables'): self.plan()
        self.review['findings'][0]['location'] = 'earnings'; self.rebind_review()
        updated = self.save_many({'financial-analysis.json': {'fictional_revenue': 11}})
        self.job['artifacts'].update(updated)
        with self.assertRaisesRegex(ValueError,'independent table finding'): self.plan()

    def test_prior_analysis_must_reconstruct_the_reviewed_candidate(self):
        self.job['attempts'][-1]['outcome']['input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'reconstruct'):
            self.plan()

    def test_proof_load_verifies_new_and_reconstructed_old_candidates(self):
        plan = self.plan(); merged = revisions.apply(plan, self.replacement())
        text = self.render(merged, self.financial, self.root/'sources/manifest.json')
        proof = revisions.audit(self.root, self.job, plan, merged, text, self.render)
        self.job['artifacts'].update(self.save_many({'analysis-r1.json': merged, 'report.md': text, 'correction-r1.json': proof}))
        del self.job['revision_input']
        loaded = revisions.load(self.root, self.job, self.render)
        self.assertEqual(loaded['proof'], proof)
        self.assertEqual(loaded['plan'], plan)
        self.assertNotEqual(proof['candidate_before_sha256'], proof['candidate_after_sha256'])
        self.assertEqual(proof['changed_locations'], ['earnings'])
        self.assertIn('all eight criteria', proof['review_requirement'])
        (self.root/'correction-r1.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'):
            revisions.load(self.root, self.job, self.render)

    def test_patch_lists_keep_exact_qa_and_next_test_shapes(self):
        self.review['findings'][0]['location'] = 'qa'; self.rebind_review()
        plan = self.plan()
        bad = {'replacements': {'qa': [{'text': 'Not a Q&A row'}]}}
        with self.assertRaisesRegex(ValueError, 'Q&A fields'):
            revisions.apply(plan, bad)
        replacement = copy.deepcopy(self.analysis['qa']); replacement[0]['assessment'] = 'Corrected fictional assessment.'
        self.assertEqual(revisions.apply(plan, {'replacements': {'qa': replacement}})['qa'], replacement)

    def test_second_correction_binds_first_corrected_candidate_and_its_review(self):
        first_plan = self.plan(); first = revisions.apply(first_plan, self.replacement())
        first_text = self.render(first, self.financial, self.root/'sources/manifest.json')
        first_proof = revisions.audit(self.root, self.job, first_plan, first, first_text, self.render)
        first_files = self.save_many({'analysis-r1.json': first, 'report.md': first_text, 'correction-r1.json': first_proof})
        self.job['artifacts'].update(first_files)
        del self.job['revision_input']
        self.assertIsNotNone(revisions.load(self.root, self.job, self.render))
        second_review = copy.deepcopy(self.review)
        second_review['findings'][0]['location'] = 'demand'
        review_files = self.save_many({'review-r1.json': second_review})
        self.job['artifacts'].update(review_files)
        self.job['attempts'].extend([
            {'id': 'a1', 'stage': 'analysis', 'status': 'completed', 'revision_round': 1, 'outcome': {'outputs': first_files}},
            {'id': 'r1', 'stage': 'review', 'status': 'revise', 'revision_round': 1,
             'outcome': {'outputs': review_files, 'input_sha256': first_files['report.md']}}])
        self.job['revision_round'] = 2
        self.job['revision_input'] = {'report.md': self.job['artifacts'].pop('report.md')}
        second_plan = self.plan()
        self.assertEqual(second_plan['previous_candidate_sha256'], first_proof['candidate_after_sha256'])
        self.assertEqual(second_plan['allowed_locations'], ['demand'])
        second = revisions.apply(second_plan, {'replacements': {'demand': {'text': 'Corrected fictional demand.', 'citations': ['Q1']}}})
        self.assertEqual(second['sections']['earnings'], first['sections']['earnings'])
        second_text = self.render(second, self.financial, self.root/'sources/manifest.json')
        second_proof = revisions.audit(self.root, self.job, second_plan, second, second_text, self.render)
        self.job['artifacts'].update(self.save_many({'analysis-r2.json': second, 'report.md': second_text, 'correction-r2.json': second_proof}))
        del self.job['revision_input']
        self.assertEqual(revisions.load(self.root, self.job, self.render)['proof'], second_proof)

    def test_unknown_review_location_cannot_authorize_title_or_other_fields(self):
        self.review['findings'][0]['location'] = 'title'; self.rebind_review()
        with self.assertRaisesRegex(ValueError, 'Unknown review'):
            self.plan()


if __name__ == '__main__':
    unittest.main()
