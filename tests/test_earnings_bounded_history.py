"""Synthetic bounded history admission preserves unknown usage and fresh-review cap."""
import copy
import unittest
from research import earnings_remediation as m,earnings_experiment as b


class BoundedHistoryTests(unittest.TestCase):
    def setUp(self):
        binding={'seed':'fake-failed-signal','job':'fake-job','session_id':'fake','usage_is_unknown':True}
        self.exported={'prior_tokens':272017,'source_protocol':{'signal_provider_recovery':binding}}
        self.uncertainty={'version':'audited-terminal-signal-overload-reserve-v1','usage_is_unknown':True,'correction_rounds':2,'failed_job':'fake-job','failed_session':'fake','source_flow_replay_sha256':'0'*64,'known_measured_tokens':17,'failed_request_reserved_tokens':272000,'total_tokens_upper_bound':272017,'signal_failure_binding_sha256':b.digest(binding)}
        self.auth={'max_tokens':200000,'max_review_attempts':1}
    def test_audited_unknown_usage_keeps_fresh_cap(self):
        self.assertTrue(m.bounded_history_authorization(self.uncertainty,self.exported,self.auth))
    def test_other_unknown_history_not_silently_capped(self):
        changed=copy.deepcopy(self.uncertainty);changed['version']='unknown-other'
        self.assertFalse(m.bounded_history_authorization(changed,self.exported,self.auth))
    def test_no_reserve_budget_or_round_changes(self):
        for field,value in [('known_measured_tokens',-1),('failed_job','wrong'),('failed_session','wrong'),('source_flow_replay_sha256','wrong'),('failed_request_reserved_tokens',0),('total_tokens_upper_bound',17),('correction_rounds',0),('signal_failure_binding_sha256','changed')]:
            changed=copy.deepcopy(self.uncertainty);changed[field]=value
            self.assertFalse(m.bounded_history_authorization(changed,self.exported,self.auth))
        self.assertFalse(m.bounded_history_authorization(self.uncertainty,self.exported,{**self.auth,'max_tokens':400000}))
        self.assertFalse(m.bounded_history_authorization(self.uncertainty,self.exported,{**self.auth,'max_review_attempts':2}))
