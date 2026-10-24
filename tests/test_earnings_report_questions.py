"""Fictional expected-answer contracts, source gaps and exact repair binding."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
import test_earnings_file_pipeline as file_tests
import test_earnings_signals as signal_tests
from research import earnings_report_questions as q
from research import earnings_file_pipeline as pipeline, earnings_mixed_runner as base
from research import earnings_signals as signals


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.items={'analysis:0':{'value':{'text':'Fictional supported demand'}}}
        self.state={'fictional':'candidate'}
        self.assessments={name:{'status':'answered','evidence':'The fictional report explains the available source-backed answer.',
              'unit_ids':['analysis:0'],'report_locations':['outlook' if name=='valuation' else name],'gap':''} for name in q.QUESTIONS}
        self.review={'batch_sha256':base.digest(self.items),'report_sha256':'fictional-report-digest',
            'report_criteria':{k:{'status':'pass','evidence':'Fictional original evidence'} for k in pipeline.legacy.CRITERIA},
            'signal_criteria':{k:{'status':'pass','evidence':'Fictional original evidence'} for k in signals.CRITERIA},
            'decisions':[{'unit_id':'analysis:0','verdict':'pass'}],'reopen':[]}

    def test_all_questions_and_named_disclosed_gaps_pass_completeness(self):
        self.assertTrue(q.validate(self.assessments,self.items,self.review))
        self.assessments['valuation'].update(status='disclosed_gap',gap='No dated trading price or annual EPS supplied',
            evidence='The report explicitly states that P/E is unavailable because these inputs are absent.',unit_ids=[])
        self.assertTrue(q.validate(self.assessments,self.items,self.review))

    def test_omissions_unknown_locations_and_empty_gap_rejected(self):
        changes=[('demand',None),('cash',{'unit_ids':['invented']}),('earnings',{'report_locations':['invented']}),
                 ('valuation',{'status':'disclosed_gap','gap':''}),('outlook',{'evidence':' '})]
        for key,change in changes:
            rows=copy.deepcopy(self.assessments)
            if change is None:del rows[key]
            else:rows[key].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):q.validate(rows,self.items,self.review)

    def test_failure_requires_concrete_affected_repair_unit(self):
        self.assessments['earnings'].update(status='fail',evidence='The report does not explain a disclosed EPS bridge.')
        with self.assertRaisesRegex(ValueError,'repair finding'):q.validate(self.assessments,self.items,self.review)
        self.review['decisions'][0]['verdict']='revise'
        self.assertFalse(q.validate(self.assessments,self.items,self.review))
        self.assessments['earnings']['unit_ids']=[]
        with self.assertRaisesRegex(ValueError,'repair finding'):q.validate(self.assessments,self.items,self.review)

    def test_legacy_review_shape_unchanged_opt_in_requires_assessments(self):
        from unittest.mock import patch
        with patch.object(signals,'report_digest',return_value='fictional-report-digest'):
            pipeline.review_payload(self.review,self.items,self.state)
            with self.assertRaises(ValueError):pipeline.review_payload(self.review,self.items,self.state,q.contract())
            value={**self.review,'question_assessments':self.assessments}
            pipeline.review_payload(value,self.items,self.state,q.contract())
            with self.assertRaises(ValueError):pipeline.review_payload(value,self.items,self.state)
            with self.assertRaisesRegex(ValueError,'contract changed'):
                pipeline.review_payload(value,self.items,self.state,{**q.contract(),'version':'invented'})

    def test_instructions_bound_valuation_and_do_not_require_exhaustive_tables(self):
        text=q.instructions('review')
        for term in ('diluted EPS','gross margin','R&D','share count','FCF','No quarterly EPS annualization','DCF','question_assessments'):
            self.assertIn(term,text)
        self.assertNotIn('question_assessments',q.instructions('analysis'))
        self.assertEqual(q.verify(q.contract()),q.contract())


class QuestionPipelineTests(PassageFixture,unittest.TestCase):
    fake_run=file_tests.FilePipelineTests.fake_run
    drain=file_tests.FilePipelineTests.drain
    pack=signal_tests.SignalTests.pack

    def test_new_financial_request_requires_questions_through_native_review(self):
        from research import earnings_file_runner as runner, earnings_financial_analysis_report as report, earnings_financial_outline as outline
        writing=self.root/'writing.md';writing.write_text('Fictional source-led writing standard.')
        root=self.root/'new-financial'
        protocol=pipeline.initialize(self.casepath,root,writing,
            financial_analysis=report.configuration('2026-07-01','2026-09-30'))
        self.assertEqual(protocol['report_questions'],q.contract())
        with patch.object(outline,'artifact',return_value=copy.deepcopy(self.financial)),patch.object(runner,'run_role',side_effect=self.fake_run):
            for _ in range(8):
                result=pipeline.advance(root,True)
                if result.get('status')=='accepted':break
        self.assertEqual(result['status'],'accepted')
        decision=base.read(root/'decisions/review-0.json')
        self.assertEqual(set(decision['question_assessments']),set(q.QUESTIONS))
        artifacts=base.read(root/'contexts/review-0/artifacts.json')
        self.assertEqual(artifacts['report_questions'],q.contract())
        self.assertIn('financial_analysis',artifacts)

    def test_protocol_rejects_rebound_question_definition(self):
        from research import earnings_financial_analysis_report as report
        writing=self.root/'writing.md';writing.write_text('Fictional writing.')
        root=self.root/'immutable'
        value=pipeline.initialize(self.casepath,root,writing,
            financial_analysis=report.configuration('2026-07-01','2026-09-30'))
        value['report_questions']['questions_sha256']='a'*64
        (root/'protocol.json').write_text(__import__('json').dumps(value))
        with self.assertRaisesRegex(ValueError,'contract changed'):pipeline.load(root)

if __name__=='__main__':unittest.main()
