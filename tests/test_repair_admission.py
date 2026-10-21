import unittest
from research.repair_admission import check,fingerprint
class AdmissionTests(unittest.TestCase):
 def test_missing_and_changed_hold_block(self):
  row={'status':'held','reason':'old','run_id':'r'}; q={'version':'repair-priority-v1','companies':{}}
  self.assertFalse(check({'a':row},q)[0])
  q['companies']['a']={'failure_fingerprint':fingerprint(row),'disposition':'execution_uncertain','next_action':'reconcile execution','retry_trigger':'conclusive provider receipt'}
  self.assertTrue(check({'a':row},q)[0]);row['reason']='changed';self.assertFalse(check({'a':row},q)[0])
 def test_actionable_repair_blocks(self):
  row={'status':'held'}
  for disposition in ('repairable','repair_in_progress'):
   q={'version':'repair-priority-v1','companies':{'a':{'failure_fingerprint':fingerprint(row),'disposition':disposition,'next_action':'repair','retry_trigger':'now'}}}
   self.assertFalse(check({'a':row},q)[0])
 def test_missing_blocker_cannot_bypass(self):
  row={'status':'held'};q={'version':'repair-priority-v1','companies':{'a':{'failure_fingerprint':fingerprint(row),'disposition':'exhausted'}}}
  self.assertFalse(check({'a':row},q)[0])
 def test_active_worker_is_not_held(self):
  self.assertTrue(check({'a':{'status':'advancing'}},{'version':'repair-priority-v1','companies':{}})[0])
