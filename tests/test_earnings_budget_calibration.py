"""Fictional authenticated review calibration; no models or real source data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from research import earnings_budget as budget
from research import earnings_experiment as base
from research import earnings_remediation as remediation
import test_earnings_remediation as fixtures
import test_earnings_repair_review as reviews
from test_earnings_passages import PassageFixture


def reference(root):
    job = root.resolve()/'prior-review'; job.mkdir()
    (job/'prompt.txt').write_text('F'*1000)
    base.save(job/'request.json', {'model':remediation.MODEL[0], 'effort':remediation.MODEL[1], 'bindings':{'role':'review'}})
    base.save(job/'output.json', {'fictional':True}); base.save(job/'execution.json', {'fictional':True})
    result={'receipt':{'session':{'id':'fictional-source-review','model':remediation.MODEL[0],
        'effort':remediation.MODEL[1],'provider':'openai-codex',
        'usage':{'input':100,'cacheRead':200,'cacheWrite':50,'output':40,'totalTokens':390}}}}
    return job,result,{str(p):base.sha(p) for p in job.iterdir()}


class CalibrationTests(unittest.TestCase):
    def test_bound_authenticated_cached_input_and_floor(self):
        with tempfile.TemporaryDirectory() as directory:
            job,result,bindings=reference(Path(directory)); verifier=Mock(return_value=result)
            rows=budget.review_calibration([str(job)],bindings,remediation.MODEL,verifier)
            self.assertEqual(rows[0]['input_including_cache_tokens'],350)
            reserve=budget.calibrated_admission('F'*300000,200000,rows)
            self.assertEqual(reserve['reserved_tokens'],186864); self.assertTrue(reserve['admitted'])
            self.assertFalse(budget.calibrated_admission('F'*300000,27196,rows)['admitted'])
            self.assertFalse(budget.calibrated_admission('F'*350000,200000,rows)['admitted'])
            self.assertEqual(reserve['input_tokens_per_byte'],{'numerator':1,'denominator':2})
            verifier.assert_called_once_with(job)

    def test_wrong_source_model_role_provider_and_changed_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            job,result,bindings=reference(Path(directory))
            with self.assertRaises(ValueError): budget.review_calibration([str(job)],{},remediation.MODEL,lambda j:result)
            for key,value in [('provider','foreign'),('model','foreign'),('effort','high')]:
                wrong=copy.deepcopy(result); wrong['receipt']['session'][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):
                    budget.review_calibration([str(job)],bindings,remediation.MODEL,lambda j:wrong)
            request=base.read(job/'request.json');request['bindings']['role']='analysis';(job/'request.json').write_text(json.dumps(request))
            bindings[str(job/'request.json')]=base.sha(job/'request.json')
            with self.assertRaisesRegex(ValueError,'same-model/effort review'):
                budget.review_calibration([str(job)],bindings,remediation.MODEL,lambda j:result)
            (job/'prompt.txt').write_text('changed')
            with self.assertRaises(ValueError):budget.review_calibration([str(job)],bindings,remediation.MODEL,lambda j:result)


class CalibrationReplayTests(PassageFixture,unittest.TestCase):
    replay=reviews.RepairReviewTests.replay
    complete=reviews.RepairReviewTests.complete
    def setUp(self):
        super().setUp()
        self.job=self.root/'attempts/0/review'; self.results={}
        self.candidate,self.plan=base.digest({'fake':'candidate'}),base.digest({'fake':'plan'})
        self.requests=[{'scope_id':'D002','reason':'Read complete fictional context'}]

    def test_expansion_recalculates_and_completed_overrun_still_blocks(self):
        calls=[]
        def admission(text,remaining):
            calls.append(remaining)
            return budget.admission(text,remaining)
        pending=self.replay(admission_fn=admission)
        self.complete(pending,'needs_evidence',tokens=100,requests=self.requests)
        self.replay(admission_fn=admission)
        self.assertEqual(calls,[100000,99900])
        extra=self.replay(admission_fn=admission)
        self.complete(extra,sid='fictional-extra',tokens=100000)
        final=self.replay(admission_fn=admission)
        self.assertEqual(final['status'],'budget_exhausted');self.assertTrue(final['requires_adjudication'])
        self.assertEqual(final['tokens'],100100)


class CalibrationEditionTests(PassageFixture,unittest.TestCase):
    state=fixtures.RemediationTests.state
    operation=fixtures.RemediationTests.operation
    plan=fixtures.RemediationTests.plan
    edition=fixtures.RemediationTests.edition

    def test_reference_authority_and_replay_are_bound_without_ceiling_change(self):
        original=self.edition(); oldauth=base.read(original/'authorization.json')
        job,result,_=reference(self.seed)
        out=self.root/'calibrated'
        auth={**oldauth,'output_path':str(out),'budget_reference_jobs':[str(job)]}
        with patch.object(remediation,'verify_job',return_value=result) as verifier:
            remediation.initialize(self.seed,out,self.plan(),auth)
            p,*_=remediation.load(out)
            self.assertEqual(p['max_tokens'],oldauth['max_tokens'])
            self.assertEqual(p['budget_calibration'][0]['input_including_cache_tokens'],350)
            self.assertEqual(verifier.call_count,2)
            p['budget_calibration'][0]['input_including_cache_tokens']=1
            (out/'protocol.json').write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError,'calibration changed'):remediation.load(out)


if __name__=='__main__':unittest.main()
