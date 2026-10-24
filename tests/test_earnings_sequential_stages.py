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
        self.revise = False; self.financial_revise = False; self.counter = 0; self.skip_call = False
        self.model_calls = []
        self.transport_settings = []; self.skip_author_filing = False; self.skip_support = False
        self.patch_mutator = None; self.review_mutator = None; self.revise_forever = False
        self.patch_runner = patch.object(stages.runner, 'run_role', side_effect=self.fake_runner)
        self.patch_runner.start(); self.addCleanup(self.patch_runner.stop)
        self.patch_delivery = patch.object(context, 'delivered_entries', side_effect=lambda job, entries:entries)
        self.patch_delivery.start(); self.addCleanup(self.patch_delivery.stop)

    def fake_runner(self, role_dir, prompt, model, effort, bindings, index, **settings):
        self.transport_settings.append(settings)
        self.model_calls.append((model, effort))
        role_dir.mkdir(parents=True); reader = context.Evidence(index, role_dir/'retrieval.jsonl')
        for page in range(len(reader.role_batch_plan())):
            if self.skip_support:
                for packet in reader.role_batch_plan()[page]['packets']:
                    if packet['method'] != 'support_batch': getattr(reader,packet['method'])(packet['start'],packet['limit'])
            elif not self.skip_call: reader.role_batch(page)
        role = bindings['role']; self.counter += 1
        if role == 'sequential_review': reader.challenge_batch('guidance risk cash flow debt capital expenditure', 4)
        elif not self.skip_author_filing: reader.filing_batch(stages.AUTHOR_FILING_QUERY, 4)
        exchange = reader.index['exchange_ids'][0]
        ref = [exchange]
        if role == 'sequential_analysis':
            paragraph = {'text':'Fictional evidence remains uncertain.', 'citations':ref}
            value = {'title':'Fictional company quarterly report', 'opening':paragraph,
                     'sections':{k:copy.deepcopy(paragraph) for k in stages.SECTIONS},
                     'qa':[{'exchange_id':exchange,'question':'Is this repeatable?',
                            'answer':'Management repeats its assertion.', 'assessment':'Uncertainty remains.', 'citations':ref}],
                     'next_tests':[paragraph]}
            if 'section_revision' in reader.artifacts:
                revision = reader.artifacts['section_revision']
                replacements = copy.deepcopy(revision['current_components'])
                for name, component in replacements.items():
                    if isinstance(component, list):
                        key = 'assessment' if name == 'qa' else 'text'
                        component[0][key] += ' The fictional qualification remains material.'
                    else:
                        component['text'] += ' The fictional qualification remains material.'
                value = {'replacements':replacements}
                if self.patch_mutator: self.patch_mutator(value, reader)
        else:
            value = {'verdict':'pass', 'criteria':{k:{'status':'pass','evidence':'The fictional source supports this assessment.', 'citations':ref} for k in stages.CRITERIA},
                     'questions':{k:{'status':'disclosed_gap','evidence':'The report explicitly notes the fictional evidence gap.', 'gap':'No complete fictional evidence.', 'citations':ref} for k in stages.questions.QUESTIONS}, 'findings':[]}
            if self.revise_forever or ((self.revise or self.financial_revise) and bindings['revision'] == 0):
                value['verdict'] = 'revise'; value['criteria']['reasoning']['status'] = 'fail'
                value['findings'] = [{'location':'financial_tables' if self.financial_revise else 'outlook',
                                      'problem':'Fictional qualification omitted.', 'fix':'State the fictional source qualification.', 'citations':ref}]
            if self.review_mutator: self.review_mutator(value, reader)
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
        self.assertEqual(self.model_calls, [('gpt-6.1-sol','medium'), ('gpt-6.1-sol','medium'),
                                            ('gpt-6-luna','max'), ('gpt-6.1-sol','medium')])
        self.assertEqual(financial_sha, storage.sha(self.job/'financial-analysis.json'))
        self.assertEqual(self.counter, 4)
        self.assertTrue((self.job/'review-r0.json').exists())
        self.assertTrue((self.job/'analysis-r0.json').exists())

    def begin_revision(self):
        self.revise = True
        for _ in range(4): result = self.advance()
        self.assertEqual(result['stage'], 'analysis')
        self.assertEqual(result['revision_round'], 1)
        return result

    def test_verified_patch_changes_only_reviewed_component_and_fresh_review_sees_full_candidate(self):
        self.begin_revision()
        before = stages.read(self.job/'analysis-r0.json')
        result = self.advance()
        self.assertEqual(result['stage'], 'review', result.get('reason'))
        after = stages.read(self.job/'analysis-r1.json')
        for location, component in stages._components(before).items():
            if location != 'outlook': self.assertEqual(stages._components(after)[location], component)
        self.assertNotEqual(after['sections']['outlook'], before['sections']['outlook'])
        proof = stages.read(self.job/'correction-r1.json')
        self.assertEqual(set(proof['component_changes']), {'outlook'})
        self.assertEqual(result['artifacts']['correction-r1.json'], storage.sha(self.job/'correction-r1.json'))
        self.assertEqual(result['tokens_used'], 300)
        self.assertEqual(self.run_complete()['status'], 'completed')
        for role in ('analysis', 'review'):
            directory = self.job/f'context-{role}-r1'
            metadata = stages.read(directory/'metadata.json')
            self.assertEqual(metadata['review_scope'], 'verified_section_revision')
            reader = context.Evidence(directory/'index.json', self.job/'unused.jsonl', _replay=True)
            methods = {packet['method'] for page in reader.role_batch_plan() for packet in page['packets']}
            self.assertNotIn('call_batch', methods)
            self.assertIn('support_batch', methods)
            log = context.audit(directory/'index.json', self.job/f'roles/{role}-r1/retrieval.jsonl')
            self.assertFalse(any(entry['method'] == 'call_batch' for entry in log))
        review_artifacts = stages.read(self.job/'context-review-r1/artifacts.json')
        self.assertEqual(review_artifacts['previous_review'], stages.read(self.job/'review-r0.json'))
        self.assertEqual(set(stages.read(self.job/'review-r1.json')['criteria']), set(stages.CRITERIA))
        self.assertEqual(set(stages.read(self.job/'review-r1.json')['questions']), set(stages.questions.QUESTIONS))
        index = stages.read(self.job/'context-review-r1/index.json')
        self.assertIn('report.md', index['files'])
        self.assertEqual((self.job/'context-review-r1/report.md').read_text(), (self.job/'report.md').read_text())

    def test_patch_cannot_modify_unreviewed_component(self):
        self.begin_revision()
        old_candidate = (self.job/'report.md').read_bytes()
        def malicious(value, reader):
            value['replacements']['opening'] = {'text':'Unauthorized change.', 'citations':[]}
        self.patch_mutator = malicious
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tokens_used'], 300)
        self.assertEqual(self.counter, 3)
        self.assertEqual((self.job/'report.md').read_bytes(), old_candidate)
        self.assertFalse((self.job/'correction-r1.json').exists())

    def test_patch_new_original_citation_requires_delivered_support(self):
        self.begin_revision()
        def unread(value, reader):
            value['replacements']['outlook']['citations'] = [reader.index['exchange_ids'][1]]
        self.patch_mutator = unread
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('Every output citation requires', result['reason'])
        self.assertEqual(result['tokens_used'], 300)

    def test_patch_trusted_table_id_still_requires_original_inspection(self):
        self.begin_revision()
        def unread(value, reader):
            ids = reader.artifacts['financial_validation']['trusted_table_ids']
            self.assertTrue(ids)
            value['replacements']['outlook']['citations'] = [ids[0]]
        self.patch_mutator = unread
        result = self.advance()
        self.assertEqual(result['status'], 'blocked', result.get('reason'))
        self.assertIn('Every output citation requires', result['reason'])
        self.assertEqual(result['tokens_used'], 300)

    def test_delta_reviewer_cannot_cite_uninspected_original_from_old_full_call(self):
        self.begin_revision(); self.advance()
        def unread(value, reader):
            value['criteria']['reasoning']['citations'] = [reader.index['exchange_ids'][1]]
        self.review_mutator = unread
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('Every output citation requires', result['reason'])
        self.assertEqual(result['tokens_used'], 400)
        self.assertFalse((self.job/'report.html').exists())

    def test_modified_revision_proof_is_rejected_even_if_active_hash_is_rebound(self):
        self.begin_revision(); job = self.advance()
        proof_path = self.job/'correction-r1.json'
        proof = stages.read(proof_path); proof['component_changes']['outlook']['before'] = '0' * 64
        proof_path.write_text(json.dumps(proof))
        job['artifacts']['correction-r1.json'] = storage.sha(proof_path)
        (self.job/'job.json').write_text(json.dumps(job))
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('revision proof changed', result['reason'])
        self.assertEqual(self.counter, 3)
        self.assertEqual(result['tokens_used'], 300)

    def test_original_source_change_after_patch_stops_before_fresh_review(self):
        self.begin_revision(); self.advance()
        case = stages.read(self.case)
        source = Path(case['sources'][0]['path'])
        source.write_text(source.read_text() + ' Unreviewed fictional change.')
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.counter, 3)
        self.assertEqual(result['tokens_used'], 300)
        self.assertFalse((self.job/'report.html').exists())

    def test_delta_review_still_requires_all_criteria(self):
        self.begin_revision(); self.advance()
        def incomplete(value, reader): value['criteria'].pop('reasoning')
        self.review_mutator = incomplete
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('eight', result['reason'])
        self.assertEqual(result['tokens_used'], 400)
        self.assertFalse((self.job/'report.html').exists())

    def test_repeated_delta_review_rejections_remain_bounded_and_unpublished(self):
        self.revise_forever = True
        result = self.run_complete()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['revision_round'], 1)
        self.assertEqual(result['tokens_used'], 400)
        self.assertEqual(self.counter, 4)
        self.assertIn('no progress', result['reason'])
        self.assertFalse((self.job/'correction-r2.json').exists())
        self.assertTrue((self.job/'review-r1.json').exists())
        self.assertFalse((self.job/'report.html').exists())

    def test_revision_rejects_changed_previous_review_before_paid_author(self):
        self.revise = True
        for _ in range(4): self.advance()
        (self.job/'review-r0.json').write_text('{}')
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(self.counter, 2)
        self.assertIn('review-r0.json', result['reason'])

    def prepare_interim_basis(self):
        from research import financial_evidence
        from test_earnings_compact_evidence import refreeze
        source = self.root/'filing.html'
        raw = source.read_bytes().decode()
        declaration = ('The consolidated financial statements have been prepared in accordance with '
                       'generally accepted accounting principles for interim financial information and pursuant '
                       'to the rules and regulations of the Securities and Exchange Commission.')
        raw = raw.replace('</html>', '<ix:nonNumeric name="us-gaap:BasisOfAccounting" contextRef="c">'+declaration+'</ix:nonNumeric></html>')
        source.write_text(raw)
        case = stages.read(self.case)
        facts = self.root/'financial-source.json'
        extracted = financial_evidence.extract_inline_xbrl(raw, {'document_id':'fictional-filing',
            'raw_sha256':storage.sha(source), 'text_sha256':storage.sha(self.root/'filing.txt')})
        facts.write_text(json.dumps(extracted))
        refreeze(self.case, case, source); refreeze(self.case, case, facts)

    def test_automatic_table_repair_archives_originals_recomputes_and_requires_fresh_review(self):
        self.prepare_interim_basis(); self.financial_revise = True
        for _ in range(3): self.advance()
        original_hash = storage.sha(self.job/'financial-analysis.json')
        source_hash = storage.sha(self.job/'sources/financial.json')
        before = self.advance()
        self.assertEqual((before['status'], before['stage']), ('ready','financial_tables'))
        self.assertEqual(before['revision_round'], 1)
        self.assertTrue(before['automatic_table_repair'])
        self.assertEqual(storage.sha(self.job/'history/financial-r0/financial-analysis.json'), original_hash)
        result = self.advance()
        self.assertEqual((result['status'], result['stage']), ('ready','analysis'), result.get('reason'))
        self.assertEqual(result['tokens_used'], 200)
        self.assertNotEqual(storage.sha(self.job/'financial-analysis.json'), original_hash)
        self.assertEqual(storage.sha(self.job/'sources/financial.json'), source_hash)
        self.assertIn('GAAP', (self.job/'financial-tables.md').read_text())
        result = self.run_complete()
        self.assertEqual(result['status'], 'completed', result.get('reason'))
        self.assertEqual(result['tokens_used'], 400)
        self.assertEqual(result['revision_round'], 1)
        author_context = stages.read(self.job/'context-analysis-r1/artifacts.json')
        self.assertEqual(author_context['financial_tables_markdown'], (self.job/'financial-tables.md').read_text())
        self.assertNotIn('section_revision', author_context)
        self.assertNotIn('financial_tables_markdown', stages.read(self.job/'context-review-r1/artifacts.json'))
        self.assertFalse((self.job/'correction-r1.json').exists())
        self.assertEqual(self.model_calls, [('gpt-6.1-sol','medium')] * 4)
        self.assertEqual(len({a['outcome']['session_id'] for a in result['attempts'] if 'session_id' in a['outcome']}),4)

    def test_unsupported_table_repair_stops_without_spending_another_author_review_pair(self):
        self.financial_revise = True
        result = self.run_complete()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['stage'], 'financial_tables')
        self.assertIn('no table changes', result['reason'])
        self.assertEqual(result['tokens_used'], 200)
        self.assertEqual(self.counter, 2)
        self.assertFalse((self.job/'report.html').exists())
        self.assertEqual(self.advance(), result)
        self.assertFalse(controller.automatic_repair_eligible(self.job))

    def test_table_rebuild_does_not_remove_differing_unbound_output(self):
        self.prepare_interim_basis(); self.financial_revise = True
        for _ in range(4): self.advance()
        different = '{"unrelated":"existing bytes"}'
        (self.job/'financial-analysis.json').write_text(different)
        result = self.advance()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual((self.job/'financial-analysis.json').read_text(), different)
        self.assertEqual(result['tokens_used'], 200)

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
            reader = context.Evidence(index, self.job/'unused-plan.jsonl', _replay=True)
            required = len(reader.role_batch_plan()) + 1
            self.assertEqual(settings['max_tool_calls'], min(8, required + 3) + 1)
            self.assertLessEqual(settings['max_tool_calls'], 9)

    def review_plan(self, available=1_200_000):
        self.advance(); self.advance(); self.advance()
        job = stages.read(self.job/'job.json')
        index = stages._role_context(self.job, job, 'review')
        reader = context.Evidence(index, self.job/'unused-plan.jsonl', _replay=True)
        prompt = stages._prompt('review', len(reader.role_batch_plan()))
        return index, prompt, stages._editorial_preflight('review', index, prompt, available)

    def test_funded_review_is_admitted_below_whole_role_forecast(self):
        index, prompt, forecast = self.review_plan()
        available = forecast['minimum_context_tokens']
        self.assertGreater(forecast['planned_tokens'], available)
        with patch.object(stages.runner, 'budget_preflight', side_effect=AssertionError('legacy forecast forbidden')), \
             patch.object(stages.runner, 'work_plan', side_effect=AssertionError('legacy work plan forbidden')):
            admitted = stages._editorial_preflight('review', index, prompt, available)
        self.assertEqual(admitted['status'], 'ready')
        self.assertEqual(admitted['work_plan']['challenge_checks'], 1)
        self.assertNotIn('validation_checks', admitted['work_plan'])
        self.assertNotIn('filing_checks', admitted['work_plan'])
        self.assertEqual(stages._editorial_preflight('review', index, prompt, available - 1)['status'],
                         'insufficient_context_budget')

    def test_below_forecast_launch_preserves_remaining_cap_and_evidence_coverage(self):
        _, _, forecast = self.review_plan()
        job = stages.read(self.job/'job.json')
        remaining = forecast['minimum_context_tokens'] + 1000
        self.assertLess(remaining, forecast['planned_tokens'])
        job['tokens_used'] = job['budget_tokens'] - remaining
        (self.job/'job.json').write_text(json.dumps(job))
        result = self.advance()
        self.assertEqual(result['status'], 'ready', result.get('reason'))
        self.assertEqual(result['stage'], 'publication')
        self.assertEqual(self.transport_settings[-1]['max_tokens'], remaining)
        self.assertEqual(result['tokens_used'], job['tokens_used'] + 100)
        self.assertEqual(self.counter, 2)

    def test_oversized_mandatory_plan_is_rejected_without_skipping_pages(self):
        index, prompt, _ = self.review_plan()
        with patch.object(context.Evidence, 'role_batch_plan', return_value=[{'utf8_bytes':1000}]*8):
            with self.assertRaisesRegex(ValueError, 'eight-call bounded'):
                stages._editorial_preflight('review', index, prompt, 1_200_000)

    def test_author_without_original_filing_read_is_blocked_after_charging_usage(self):
        self.skip_author_filing = True
        result = self.run_complete()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('Original filing context inspection required', result['reason'])
        self.assertEqual(result['tokens_used'], 100)
        self.assertEqual(self.counter, 1)
        self.assertFalse((self.job/'report.html').exists())

    def test_author_plan_includes_delivered_original_filing_not_search_previews(self):
        self.advance(); self.advance()
        job = stages.read(self.job/'job.json')
        index = stages._role_context(self.job, job, 'analysis')
        reader = context.Evidence(index, self.job/'unused-plan.jsonl', _replay=True)
        pages = len(reader.role_batch_plan())
        prompt = stages._prompt('analysis', pages)
        plan = stages._editorial_preflight('analysis', index, prompt, 1_200_000)
        self.assertEqual(plan['work_plan']['author_filing_checks'], 1)
        self.assertEqual(plan['work_plan']['challenge_checks'], 0)
        self.assertEqual(plan['work_plan']['work_tool_limit'], pages + 1)
        original, ids = reader._filing_batch(stages.AUTHOR_FILING_QUERY, 4)
        self.assertTrue(ids)
        self.assertEqual(plan['tool_packet_utf8_bytes'][-1], len(original.encode()))
        self.assertIn('print(ctx.filing_batch(', prompt)
        self.assertIn('comparison-period one-offs', prompt)
        self.assertIn('strength of commitment', prompt)
        self.assertEqual(self.run_complete()['status'], 'completed')

    def test_compact_sequential_support_still_requires_all_original_evidence(self):
        self.skip_support = True
        result = self.run_complete()
        self.assertEqual(result['status'],'blocked')
        self.assertIn('support inspection required',result['reason'])
        self.assertEqual(result['tokens_used'],100)
        self.assertFalse((self.job/'report.html').exists())

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
