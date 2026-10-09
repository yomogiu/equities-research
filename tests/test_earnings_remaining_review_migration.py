"""Fictitious authenticated-export review counters; no models or private data."""
import copy
import unittest
from research import earnings_remediation as m

class RemainingReviewMigrationTests(unittest.TestCase):
    def setUp(self):
        self.old={'version':'targeted-remediation-v3','history':{'prior_rounds':4},
                  'max_review_attempts':2,'max_tokens':None,
                  'review_context_policy':{'version':'fake-policy','authority':'same'}}
        self.export={'status':'awaiting_plan','prior_rounds':5,'prior_tokens':456789}
        self.auth={'remaining_review_authorization':'Explicitly finish using remaining attempt',
                   'max_review_attempts':1,'max_tokens':None,'review_context_policy':copy.deepcopy(self.old['review_context_policy'])}
    def test_one_remaining_with_inherited_history_is_allowed_without_mutation(self):
        before=copy.deepcopy((self.old,self.export,self.auth))
        m.validate_remaining_reviews(self.old,self.export,self.auth)
        self.assertEqual(before,(self.old,self.export,self.auth))
    def test_reset_exhaustion_wrong_state_and_policy_change_rejected(self):
        cases=[('auth','max_review_attempts',2),('export','prior_rounds',6),
               ('export','prior_rounds',4),('export','prior_rounds',3),
               ('export','status','pending'),('old','version','deterministic-corrections-v1'),
               ('auth','remaining_review_authorization',''),('auth','max_tokens',1000),
               ('auth','review_context_policy',{'version':'different'})]
        for which,key,value in cases:
            old,export,auth=copy.deepcopy((self.old,self.export,self.auth))
            {'old':old,'export':export,'auth':auth}[which][key]=value
            with self.subTest(which=which,key=key,value=value),self.assertRaises(ValueError):
                m.validate_remaining_reviews(old,export,auth)
    def test_finite_original_allowance_cannot_be_reset(self):
        self.old['max_tokens']=900000
        self.auth['max_tokens']=900000
        with self.assertRaisesRegex(ValueError,'already uncapped'):
            m.validate_remaining_reviews(self.old,self.export,self.auth)

    def test_missing_marker_rejected_and_ordinary_stopped_edition_unchanged(self):
        del self.auth['remaining_review_authorization']
        with self.assertRaises(ValueError):m.validate_remaining_reviews(self.old,self.export,self.auth)
        self.export['status']='invalid_review'
        m.validate_remaining_reviews(self.old,self.export,self.auth)

if __name__=='__main__':unittest.main()
