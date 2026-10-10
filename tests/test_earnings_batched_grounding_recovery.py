"""Fictitious recovery contract tests, without provider calls."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from research import earnings_batched_grounding_recovery as g


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        old={'case_sha256':'fake-source','max_correction_rounds':2,'qa_grounding':'source-bound-qa-membership-v2'}
        p={**old,'qa_grounding':'source-bound-qa-membership-v3','grounding_recovery':{
            'seed':'/fictional/seed','protocol_sha256':'fake-digest','authorization':'Fictional repair',
            'prior_correction_rounds':0,'responses':{x:{'job':'/fictional/seed/batch-jobs/'+x,'code':'/fictional/code'} for x in ('financial','retrieval')}}}
        return old,p

    def call(self,old,p,session=None):
        from research import earnings_passage_pipeline as pipe
        with patch.object(g,'original',return_value=(old,Path('/fictional/code'))), patch.object(g.r,'sha',return_value='fake-digest'), patch.object(g.imp,'authenticate',side_effect=lambda ref:{'content':{'fake':True},'session':{'id':session or ref['job'],'usage':{'totalTokens':7}}}), patch.object(pipe,'validate'), patch.object(pipe.grounding,'normalize_courtesy',side_effect=lambda out,*args:(out,[])):
            return g.validate(p,{}, {})

    def test_reuses_preparers_with_inherited_usage(self):
        old,p=self.fixture();result=self.call(old,p)
        self.assertEqual(set(result),{'financial','retrieval'})
        self.assertTrue(all(v['receipt']['usage_is_inherited'] for v in result.values()))

    def test_changed_evidence_budget_role_or_version_rejected(self):
        old,p=self.fixture()
        for change in [lambda x:x.update(case_sha256='changed'),lambda x:x.update(max_correction_rounds=3),lambda x:x.update(qa_grounding='unknown'),lambda x:x['grounding_recovery'].update(prior_correction_rounds=1),lambda x:x['grounding_recovery']['responses']['financial'].update(job='/different')]:
            altered=copy.deepcopy(p);change(altered)
            with self.assertRaises(ValueError):self.call(old,altered)

    def test_shared_session_rejected(self):
        old,p=self.fixture()
        with self.assertRaisesRegex(ValueError,'Distinct'):self.call(old,p,'same-session')
