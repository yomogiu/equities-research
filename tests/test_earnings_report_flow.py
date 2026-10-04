"""Fictional finite report handoffs. No account, source network or model calls."""
import copy
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
from research import earnings_experiment as base
from research import earnings_passage_pipeline as pipe
from research import earnings_report_flow as flow


class FlowTests(PassageFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.writing=self.root/'writing.txt';self.writing.write_text('Fictional standard')
        self.output=self.root/'run'
        pipe.freeze(self.casepath,self.output,self.writing,deterministic_corrections=True)

    def test_finite_base_resume_one_call_per_turn_and_no_duplicate_jobs(self):
        jobs={};calls=[]
        def worker(path,text,model,effort,bindings,timeout):
            if str(path) in jobs:return jobs[str(path)]
            calls.append(bindings['role'])
            role=bindings['role']
            value={'financial':self.financial,'retrieval':self.retrieval,'analysis':self.report,
                   'review':{'verdict':'pass','criteria':{c:{'status':'pass','evidence':'Fictional check'} for c in pipe.legacy.CRITERIA},'findings':[]}}[role]
            base.save(path/'request.json',{'bindings':bindings,'model':model,'effort':effort});(path/'prompt.txt').write_text(text)
            receipt={'started_at':'2040-01-01T00:00:00+00:00','finished_at':'2040-01-01T00:00:01+00:00','session':{'id':path.name}}
            jobs[str(path)]={'content':copy.deepcopy(value),'receipt':receipt};return jobs[str(path)]
        with patch.object(pipe,'run_role',side_effect=worker),patch.object(pipe,'verify_job',side_effect=lambda p:jobs[str(p)]):
            for number in range(4):
                result=flow.advance(self.output)
                self.assertEqual(len(calls),number+1)
                self.assertEqual(result['status'],'pending')
            self.assertEqual(calls,['financial','retrieval','analysis','review'])
            self.assertEqual(flow.advance(self.output,False)['stage'],'signals')
            self.assertEqual(len(calls),4)

    def test_signals_not_skipped_and_blocked_annotations_do_not_publish(self):
        base.save(self.output/'result.json',{'status':'accepted'})
        edition=self.output.with_name('run-signals');edition.mkdir();base.save(edition/'protocol.json',{})
        with patch.object(pipe,'verify',return_value={'status':'accepted'}),patch.object(flow.signals,'advance',return_value={'status':'blocked'}) as signal:
            result=flow.advance(self.output)
            self.assertEqual(result['status'],'blocked');self.assertNotIn('report',result)
            signal.assert_called_once_with(edition.resolve(),True)

    def test_incomplete_preparation_does_not_launch_corrections(self):
        base.save(self.output/'result.json',{'status':'blocked'});base.save(self.output/'artifacts.json',{});base.save(self.output/'review.json',None)
        with patch.object(pipe,'verify',return_value={'status':'blocked'}),patch.object(flow.corrections,'initialize') as init:
            self.assertEqual(flow.advance(self.output)['status'],'blocked');init.assert_not_called()

    def test_missing_required_stage_flags_refuses_execution(self):
        protocol, bundle, catalog=pipe.load(self.output);protocol['report_signals']=False
        with patch.object(pipe,'load',return_value=(protocol,bundle,catalog)),patch.object(pipe,'run') as run:
            with self.assertRaises(ValueError):flow.advance(self.output)
            run.assert_not_called()

    def test_accepted_correction_defers_signals_to_next_turn(self):
        base.save(self.output/'result.json',{'status':'blocked'})
        continuation=self.output.with_name('run-corrections');continuation.mkdir();base.save(continuation/'protocol.json',{})
        with patch.object(pipe,'verify',return_value={'status':'blocked'}),patch.object(flow.corrections,'verify',return_value={'status':'pending'}),patch.object(flow.corrections,'advance',return_value={'status':'accepted'}),patch.object(flow.signals,'advance') as signal:
            self.assertEqual(flow.advance(self.output)['stage'],'signals');signal.assert_not_called()
