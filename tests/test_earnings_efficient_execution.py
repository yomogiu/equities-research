"""Fictional lifecycle replay for deterministic preparation and fresh review."""
import copy
import unittest
from unittest.mock import patch

from test_earnings_passages import PassageFixture
import test_earnings_file_pipeline as fixtures
from research import earnings_file_pipeline as pipeline
from research import earnings_file_runner as runner
from research import earnings_mixed_runner as base
from research import earnings_financial_outline as outline
from research import earnings_deterministic_retrieval as retrieval


class EfficientExecutionTests(PassageFixture, unittest.TestCase):
    pack = fixtures.FilePipelineTests.pack
    drain = fixtures.FilePipelineTests.drain
    fake_run = fixtures.FilePipelineTests.fake_run

    def initialize(self, cap=1200000):
        root=self.root/'efficient'
        writing=self.root/'writing.md';writing.write_text('Fictional source-grounded writing.')
        pipeline.initialize(self.casepath,root,writing,max_tokens=cap,execution_profile=pipeline.EFFICIENT_PROFILE)
        return root

    def run_lifecycle(self, failures=0, exact=True):
        root=self.initialize();self.fail_reviews=failures;self.exact_proposals=exact
        with patch.object(outline,'artifact',return_value=copy.deepcopy(self.financial)),patch.object(runner,'run_role',side_effect=self.fake_run) as launch:
            for _ in range(10):
                before=launch.call_count;result=pipeline.advance(root,True)
                self.assertLessEqual(launch.call_count-before,1)
                if result['status'] in ('accepted','blocked'):break
            else:self.fail(str(result))
            roles=[call.args[4]['role'] for call in launch.call_args_list]
            before=launch.call_count
            replay=pipeline.verify(root)
            self.assertEqual(launch.call_count,before)
            self.assertEqual(replay,result)
        return root,result,roles

    def test_no_retrieval_model_and_fresh_review_still_required(self):
        root,result,roles=self.run_lifecycle()
        self.assertEqual(roles,['analysis','signal_author','review'])
        self.assertEqual(result['status'],'accepted')
        self.assertEqual(result['tokens'],120)
        self.assertEqual(len(result['session_ids']),3)
        self.assertFalse((root/'jobs/retrieval').exists())
        compiled=base.read(root/'retrieval-compiled.json')
        self.assertEqual(compiled['tokens'],0)
        self.assertEqual(compiled['status'],'ready')
        self.assertIn('navigation',compiled['notice'])
        self.assertTrue(base.read(root/'budget-preflights/review-0.json')['planned_tokens']>128000)
        self.assertIn('ctx.role_batch(0)',(root/'jobs/review-0/prompt.md').read_text())

    def test_exact_candidate_skips_correction_model_but_not_new_review(self):
        root,result,roles=self.run_lifecycle(failures=1)
        self.assertEqual(roles,['analysis','signal_author','review','review'])
        self.assertEqual(result['correction_rounds'],1)
        self.assertEqual(result['tokens'],160)
        self.assertNotEqual('fictional-review-0',result['review_session'])
        self.assertFalse((root/'jobs/correction-1').exists())
        proof=base.read(root/'deterministic-corrections/correction-1.json')
        self.assertEqual(proof['derivation']['provider_calls'],0)
        self.assertEqual(proof['derivation']['source_review_sha256'],base.sha(root/'jobs/review-0/output.json'))
        self.assertEqual(base.read(root/'decisions/correction-1.json')['tokens'],0)

    def test_missing_exact_proposal_keeps_model_correction(self):
        _,result,roles=self.run_lifecycle(failures=1,exact=False)
        self.assertEqual(roles,['analysis','signal_author','review','correction','review'])
        self.assertEqual(result['tokens'],200)

    def test_exact_edits_do_not_reset_two_round_limit(self):
        root,result,roles=self.run_lifecycle(failures=3)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['correction_rounds'],2)
        self.assertEqual(roles,['analysis','signal_author','review','review','review'])
        self.assertFalse((root/'report.html').exists())
        self.assertFalse((root/'deterministic-corrections/correction-3.json').exists())

    def test_ambiguous_navigation_uses_existing_retrieval_role(self):
        root=self.initialize()
        fallback={'status':'fallback_required','tokens':0,'reasons':['Fictional ambiguous attribution']}
        with patch.object(retrieval,'build',return_value=fallback),patch.object(outline,'artifact',return_value=copy.deepcopy(self.financial)),patch.object(runner,'run_role',side_effect=self.fake_run) as launch:
            pipeline.advance(root,True)
        self.assertEqual(launch.call_args.args[4]['role'],'retrieval')
        self.assertEqual(base.read(root/'retrieval-compiled.json'),fallback)

    def test_insufficient_budget_stops_before_any_provider_launch(self):
        root=self.initialize(cap=100000)
        with patch.object(outline,'artifact',return_value=copy.deepcopy(self.financial)),patch.object(runner,'run_role') as launch:
            result=pipeline.advance(root,True)
        launch.assert_not_called()
        self.assertEqual(result['status'],'budget_exhausted')
        self.assertEqual(result['tokens'],0)
        self.assertFalse((root/'jobs/analysis/request.json').exists())
        forecast=result['budget_preflight']
        self.assertEqual(forecast['registered_final_output_reserve'],128000)
        self.assertGreater(forecast['planned_tokens'],forecast['available_tokens'])

    def test_budget_projection_counts_each_prefix_and_never_logs_inspection(self):
        root=self.initialize()
        with patch.object(outline,'artifact',return_value=copy.deepcopy(self.financial)):
            pipeline.advance(root,False)
        index=root/'contexts/analysis/index.json'
        a=runner.budget_preflight('analysis',index,'Fictional prompt',1200000)
        b=runner.budget_preflight('analysis',index,'Fictional prompt '*100,1200000)
        self.assertGreater(b['planned_tokens'],a['planned_tokens'])
        self.assertEqual(a['planned_model_turns'],a['work_plan']['work_tool_limit']+1)
        self.assertFalse((index.parent/'unused-budget.jsonl').exists())
        self.assertFalse((index.parent/'unused-plan.jsonl').exists())


if __name__=='__main__':unittest.main()
