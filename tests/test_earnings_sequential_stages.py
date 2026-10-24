"""Fictional five-stage runs with actual evidence calculations and fake transport."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_earnings_compact_evidence import fixture
from research import earnings_sequential as controller
from research import earnings_sequential_stages as stages
from research import earnings_financial_analysis_report as finance
from research import earnings_file_context as context
from research import earnings_mixed_runner as storage


class SequentialStagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.case, _, _ = fixture(self.root)
        self.writing = self.root/'writing.md'; self.writing.write_text('Explain fictional evidence plainly.')
        self.job = self.root/'job'
        controller.create(self.job, {'case_path':str(self.case), 'writing_standard':str(self.writing),
            'financial_analysis':finance.configuration('2040-01-01','2040-03-31')})
        self.revise = False; self.counter = 0; self.skip_call = False
        self.transport_settings = []
        self.patch_runner = patch.object(stages.runner, 'run_role', side_effect=self.fake_runner)
        self.patch_runner.start(); self.addCleanup(self.patch_runner.stop)
        self.patch_delivery = patch.object(context, 'delivered_entries', side_effect=lambda job, entries:entries)
        self.patch_delivery.start(); self.addCleanup(self.patch_delivery.stop)

    def fake_runner(self, role_dir, prompt, model, effort, bindings, index, **settings):
        self.transport_settings.append(settings)
        role_dir.mkdir(parents=True); reader = context.Evidence(index, role_dir/'retrieval.jsonl')
        for page in range(len(reader.role_batch_plan())):
            if not self.skip_call: reader.role_batch(page)
        role = bindings['role']; self.counter += 1
        if role == 'sequential_review': reader.challenge_batch('guidance risk cash flow debt capital expenditure', 4)
        exchange = reader.index['exchange_ids'][0]
        ref = [exchange]
        if role == 'sequential_analysis':
            paragraph = {'text':'Fictional evidence remains uncertain.', 'citations':ref}
            value = {'title':'Fictional company quarterly report', 'opening':paragraph,
                     'sections':{k:copy.deepcopy(paragraph) for k in stages.SECTIONS},
                     'qa':[{'exchange_id':exchange,'question':'Is this repeatable?',
                            'answer':'Management repeats its assertion.', 'assessment':'Uncertainty remains.', 'citations':ref}],
                     'next_tests':[paragraph]}
        else:
            value = {'verdict':'pass', 'criteria':{k:{'status':'pass','evidence':'The fictional source supports this assessment.', 'citations':ref} for k in stages.CRITERIA},
                     'questions':{k:{'status':'disclosed_gap','evidence':'The report explicitly notes the fictional evidence gap.', 'gap':'No complete fictional evidence.', 'citations':ref} for k in stages.questions.QUESTIONS}, 'findings':[]}
            if self.revise and bindings['revision'] == 0:
                value['verdict'] = 'revise'; value['criteria']['reasoning']['status'] = 'fail'
                value['findings'] = [{'location':'outlook','problem':'Fictional qualification omitted.', 'fix':'State the fictional source qualification.', 'citations':ref}]
        return {'content':value, 'receipt':{'session':{'id':'fictional-session-'+str(self.counter),'usage':{'totalTokens':100}}}}

    def advance(self):
        return controller.advance(self.job, stages.handlers())

    def run_complete(self):
        for _ in range(9):
            result = self.advance()
            if result['status'] != 'ready': return result
        self.fail('Expected bounded completion')

    def test_five_stages_complete_with_zero_cost_tables_and_exact_publication(self):
        result = self.run_complete()
        self.assertEqual(result['status'], 'completed', result.get('reason'))
        self.assertEqual([x['stage'] for x in result['attempts']], ['sources','financial_tables','analysis','review','publication'])
        self.assertEqual(result['tokens_used'], 200)
        self.assertEqual(result['attempts'][1]['outcome']['tokens'], 0)
        receipt = stages.read(self.job/'publication.json')
        self.assertEqual(receipt['candidate_sha256'], storage.sha(self.job/'report.md'))
        self.assertIn('Accepted after independent review', (self.job/'report.html').read_text())
        self.assertIn('| Fictitious café revenue |', (self.job/'report.md').read_text())
        self.assertEqual(self.counter, 2)

    def test_revision_reuses_sources_tables_and_preserves_charged_sessions(self):
        self.revise = True; self.advance(); self.advance()
        financial_sha = storage.sha(self.job/'financial-analysis.json')
        result = self.run_complete()
        self.assertEqual(result['status'], 'completed', result.get('reason'))
        self.assertEqual(result['revision_round'], 1)
        self.assertEqual(result['tokens_used'], 400)
        self.assertEqual(financial_sha, storage.sha(self.job/'financial-analysis.json'))
        self.assertEqual(self.counter, 4)
        self.assertTrue((self.job/'review-r0.json').exists())
        self.assertTrue((self.job/'analysis-r0.json').exists())

    def test_revision_rejects_changed_previous_review_before_paid_author(self):
        self.revise = True
        for _ in range(4): self.advance()
        (self.job/'review-r0.json').write_text('{}')
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.counter, 2)
        self.assertIn('review-r0.json', result['reason'])

    def test_revision_rejects_changed_previous_candidate_before_paid_author(self):
        self.revise = True
        for _ in range(4): self.advance()
        (self.job/'report.md').write_text('Changed unreviewed candidate')
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.counter, 2)
        self.assertIn('report.md', result['reason'])

    def test_source_snapshot_scope_is_deterministically_published(self):
        case = stages.read(self.case)
        cutoff = 'Historical source cutoff: 2040-04-15. Later filings were not included.'
        case['scope_notes'].append(cutoff)
        self.case.write_text(json.dumps(case))
        result = self.run_complete()
        self.assertEqual(result['status'], 'completed', result.get('reason'))
        self.assertIn(cutoff, (self.job/'report.md').read_text())
        self.assertIn(cutoff, (self.job/'report.html').read_text())
        receipt = stages.read(self.job/'publication.json')
        self.assertIn(cutoff, receipt['scope_notes'])
        self.assertEqual(receipt['source_manifest_sha256'], storage.sha(self.job/'sources/manifest.json'))

    def test_reader_scope_keeps_dates_and_material_gap_without_preparer_instructions(self):
        notes = ['Historical event_update for the exact qualified packet and fiscal period recorded in this case.',
                 'Financial observations are deterministic extractions, not independent approval; preserve their original units.',
                 'Transcript speaker roles and Q&A boundaries are provisional. Verify attribution.',
                 'Original source observation dates: 2040-04-15T12:00:00Z, 2040-04-17T12:00:00Z.',
                 'The prior-quarter filing is unavailable.']
        result = '\n'.join(stages._reader_scope(notes))
        self.assertIn('2040-04-15 to 2040-04-17', result)
        self.assertIn('prior-quarter filing is unavailable', result)
        self.assertNotIn('preserve their original units', result)
        self.assertNotIn('Verify attribution', result)

    def test_transport_tools_are_bounded_with_investigation_allowance(self):
        self.assertEqual(self.run_complete()['status'], 'completed')
        for role, settings in zip(('analysis', 'review'), self.transport_settings):
            index = self.job/f'context-{role}-r0/index.json'
            required = stages.runner.work_plan(role, index)['work_tool_limit']
            self.assertEqual(settings['max_tool_calls'], required + 4)
            self.assertLess(settings['max_tool_calls'], 32)

    def test_optional_investigation_shrinks_before_mandatory_review_is_blocked(self):
        self.advance(); self.advance(); self.advance()
        job = stages.read(self.job/'job.json')
        index = stages._role_context(self.job, job, 'review')
        reader = context.Evidence(index, self.job/'unused-plan.jsonl', _replay=True)
        prompt = stages._prompt('review', len(reader.role_batch_plan()))
        mandatory = stages.runner.budget_preflight('review', index, prompt, 1_200_000)
        bounded = stages._editorial_preflight('review', index, prompt, mandatory['planned_tokens'])
        self.assertEqual(bounded['status'], 'ready')
        self.assertEqual(bounded['additional_investigation_calls'], 0)
        self.assertEqual(bounded['max_tool_calls'], mandatory['work_plan']['work_tool_limit'] + 1)
        self.assertEqual(stages._editorial_preflight('review', index, prompt, mandatory['planned_tokens'] - 1)['status'],
                         'insufficient_planned_budget')

    def test_full_original_call_read_is_mandatory(self):
        self.skip_call = True
        result = self.run_complete()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('inspection required', result['reason'])
        self.assertEqual(result['tokens_used'], 100)
        self.assertFalse((self.job/'report.html').exists())

    def test_source_mutation_blocks_before_model_call(self):
        self.advance(); self.advance()
        (self.job/'sources/financial.json').write_text('{}')
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.counter, 0)

    def test_no_legacy_pipeline_or_retrieval_role_is_launched(self):
        from research import earnings_file_pipeline
        with patch.object(earnings_file_pipeline, 'initialize', side_effect=AssertionError('legacy initialization forbidden')), \
             patch.object(earnings_file_pipeline, 'advance', side_effect=AssertionError('legacy orchestration forbidden')):
            self.assertEqual(self.run_complete()['status'], 'completed')

    def test_review_cannot_pass_with_missing_criteria_or_hidden_failures(self):
        known = {'F001'}
        incomplete = {'verdict':'pass','criteria':{},'questions':{},'findings':[]}
        with self.assertRaisesRegex(ValueError, 'eight'):
            stages.validate_review(incomplete, known)

    def test_quarter_does_not_guess_from_latest_context_without_dei(self):
        self.advance()
        bundle = stages.evidence.load_bundle(self.job/'sources/manifest.json')
        with self.assertRaisesRegex(ValueError, 'DocumentPeriodEndDate'):
            stages.financial_configuration(bundle)

    def period_bundle(self, starts):
        raw = self.root/'fictional-period.html'
        raw.write_text('<ix:nonNumeric name="dei:DocumentPeriodEndDate">2040-03-31</ix:nonNumeric>')
        return {'manifest':{'sources':[{'document_id':'fictional-dei', 'path':str(raw), 'sha256':storage.sha(raw)}]},
                'financial':{'source':{'document_id':'fictional-dei','raw_sha256':storage.sha(raw)},
                    'observations':[{'status':'extracted','context_id':str(i)} for i in range(len(starts))],
                    'contexts':{str(i):{'start_date':start,'end_date':'2040-03-31','dimensions':[]} for i,start in enumerate(starts)}}}

    def test_quarter_inferred_only_from_unique_source_dei_and_context(self):
        config = stages.financial_configuration(self.period_bundle(['2040-01-01']))
        self.assertEqual(config, finance.configuration('2040-01-01','2040-03-31'))

    def test_multiple_filed_quarter_starts_block_instead_of_selecting_one(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            stages.financial_configuration(self.period_bundle(['2040-01-01','2040-01-02']))

    def test_render_failure_after_paid_author_preserves_tokens(self):
        with patch.object(stages, 'render_candidate', side_effect=ValueError('fictional render failure')):
            result = self.run_complete()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tokens_used'], 100)
        self.assertIn('render failure', result['reason'])

    def test_model_cannot_inject_its_own_financial_table(self):
        with self.assertRaisesRegex(ValueError, 'inject'):
            stages._text('| Revenue | 999 |')

    def test_budget_preflight_stops_before_paid_call(self):
        self.advance(); self.advance()
        job = stages.read(self.job/'job.json')
        job['tokens_used'] = job['budget_tokens']-100
        (self.job/'job.json').write_text(json.dumps(job))
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('budget', result['reason'])
        self.assertEqual(self.counter, 0)


if __name__ == '__main__': unittest.main()
