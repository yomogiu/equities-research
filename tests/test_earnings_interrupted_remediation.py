"""Fictional approved blocked state and unknown-usage lineage; no model calls."""
import contextlib
import copy
import io
import json
import sys
import unittest
from unittest.mock import patch
from test_earnings_passages import PassageFixture
import test_earnings_remediation as fixtures
from research import earnings_remediation as m, earnings_interrupted_review as interrupted
from research import earnings_experiment as b, earnings_signals as signals, earnings_review_policy as policy

class InterruptedRemediationTests(PassageFixture,unittest.TestCase):
    state=fixtures.RemediationTests.state
    operation=fixtures.RemediationTests.operation
    plan=fixtures.RemediationTests.plan
    review=fixtures.RemediationTests.review
    edition=fixtures.RemediationTests.edition
    complete=fixtures.RemediationTests.complete

    def context_edition(self):
        old=self.edition();original=b.read(self.seed/'protocol.json');original['source_usage_uncertainty']={'session_id':'stopped','total_tokens':None,'status':'unknown_interrupted_request'}
        original['excluded_session_ids']=['stopped']
        exported={'status':'blocked','snapshot':self.state(),'source_protocol':original['source_protocol'],'prior_rounds':2,'prior_tokens':456,
                  'source_usage_uncertainty':original['source_usage_uncertainty']}
        exporter=patch.object(m,'export_seed',return_value=(original,exported));exporter.start();self.addCleanup(exporter.stop)
        out=self.root/'unknown-edition';a=b.read(old/'authorization.json');a.update(output_path=str(out.resolve()),max_tokens=None,max_review_attempts=1,
          review_context_policy={'version':policy.VERSION,**policy.LIMITS,'authorization':'Fictional explicit targeted formatting review','token_authorization':'Known uncapped policy; unknown historical usage remains unknown'})
        m.initialize(self.seed,out,self.plan(),a)
        return out,exported,a

    def test_targeted_edition_keeps_unknown_usage_and_stopped_session(self):
        out,exported,_=self.context_edition();p,_,_,_=m.load(out)
        self.assertEqual(p['source_usage_uncertainty'],exported['source_usage_uncertainty']);self.assertIn('stopped',p['excluded_session_ids'])
        self.assertEqual(p['history']['prior_rounds'],2);self.assertEqual(p['history']['prior_tokens'],456)
        result=self.complete(out)
        with patch.object(m,'verify_job',return_value=result):
            value=m.verify(out);self.assertEqual(value['status'],'accepted');self.assertIsNone(value['total_tokens'])
            self.assertEqual(value['source_usage_uncertainty'],exported['source_usage_uncertainty'])
            job=out/'attempts/0/review';m.repair.write(job/'execution.json',result['receipt'])
            with patch.object(sys,'argv',['export',str(out)]),contextlib.redirect_stdout(io.StringIO()) as capture:exec(signals.EXPORT,{})
        value=json.loads(capture.getvalue());self.assertIn('stopped',value['excluded_session_ids']);self.assertIn('fresh-review',value['excluded_session_ids'])
        self.assertEqual(value['source_usage_uncertainty'],exported['source_usage_uncertainty'])

    def test_unknown_usage_cannot_drop_or_allow_two_reviews(self):
        out,exported,a=self.context_edition();other=self.root/'two-reviews';a.update(output_path=str(other.resolve()),max_review_attempts=2)
        with self.assertRaisesRegex(ValueError,'one targeted review'):m.initialize(self.seed,other,self.plan(),a)
        p=b.read(out/'protocol.json');p.pop('source_usage_uncertainty');(out/'protocol.json').write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError,'unknown usage changed'):m.load(out)

    def test_export_derives_approved_after_state_from_original_review(self):
        root=self.root/'interrupted';root.mkdir();(root/'protocol.json').write_text(json.dumps({'version':interrupted.VERSION}))
        before=self.state();plan=self.plan();candidate=m.apply(before,plan,self.bundle,self.catalog);review=self.review(before,plan,candidate,verdict='revise')
        p={'source_protocol':{'exact':'source'},'correction_round':2,'known_prior_tokens':600,'unknown_prior_usage':{'session_id':'old','total_tokens':None,'status':'unknown_interrupted_request'}}
        e={'before':before,'plan':plan,'candidate':candidate}
        with patch.object(interrupted,'verify',return_value={'status':'blocked','measured_new_tokens':40}),patch.object(interrupted,'load',return_value=(p,e,self.bundle,self.catalog)),patch.object(interrupted.runner,'verify_job',return_value={'content':review}),patch.object(sys,'argv',['export',str(root)]),contextlib.redirect_stdout(io.StringIO()) as capture:
            with self.assertRaises(SystemExit):exec(m.EXPORT,{})
        value=json.loads(capture.getvalue());self.assertEqual(value['snapshot']['artifacts'],candidate['artifacts']);self.assertEqual(value['prior_tokens'],640)
        self.assertEqual(value['prior_rounds'],2);self.assertIsNone(value['source_usage_uncertainty']['total_tokens'])
        self.assertFalse((root/'result.json').exists())
        with patch.object(interrupted,'verify',return_value={'status':'execution_uncertain'}),patch.object(sys,'argv',['export',str(root)]):
            with self.assertRaisesRegex(ValueError,'completed blocked'):exec(m.EXPORT,{})
