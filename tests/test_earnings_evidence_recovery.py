"""Bounded original-evidence delivery; fictional requests, no provider calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_passage_pipeline as p, earnings_mixed_runner as r

class RecoveryTests(unittest.TestCase):
 def exercise(self, extension=True, third_request=False, tamper=False):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'inputs').mkdir();r.save(root/'inputs/retrieval-r0.json',{})
   saved={'needs_evidence':[{'scope_id':'D002','reason':'Original text'}]}
   recovery={'imports':{'retrieval-r0-evidence-1':{'fake':True}},'extra_evidence':{'job':'retrieval-r0-evidence-1','request_sha256':r.digest(saved),'max_additional_expansions':1}}
   if tamper:recovery['extra_evidence']['request_sha256']='bad'
   r.save(root/'protocol.json',{'response_recovery':recovery if extension else {}})
   calls=[]
   def obtain(job,text,bindings):
    calls.append(bindings);out=({'needs_evidence':[{'scope_id':'D001','reason':'Original text'}]} if len(calls)==1 else saved if len(calls)==2 or third_request else {'complete':True})
    job.mkdir(parents=True);r.save(job/'output.json',out)
    return {'content':out,'receipt':{'session':{'id':job.name}}}
   def scopes(out,*args):return tuple(x['scope_id'] for x in out['needs_evidence']) if 'needs_evidence' in out else None
   with patch('research.earnings_role_import.authenticate',return_value={'content':saved}),patch.object(p,'prompt',return_value='same'),patch('research.earnings_efficient_evidence.requested_scopes',side_effect=scopes):
    value=p.efficient_exchange(root,'retrieval',0,{'dependencies':{},'feedback':[],'prior':None,'issues':None},{},{},'',obtain)
   return value,calls
 def test_bound_request_gets_exactly_one_extra_lookup(self):
  value,calls=self.exercise();self.assertEqual(value[0],{'complete':True});self.assertEqual(value[2],('D001','D002'));self.assertEqual([c['evidence_expansion'] for c in calls],[0,1,2]);self.assertTrue(all(c['round']==0 for c in calls))
 def test_original_limit_unchanged(self):
  with self.assertRaisesRegex(ValueError,'expansion exhausted'):self.exercise(extension=False)
 def test_third_request_stops(self):
  with self.assertRaisesRegex(ValueError,'expansion exhausted'):self.exercise(third_request=True)
 def test_changed_saved_request_stops(self):
  with self.assertRaisesRegex(ValueError,'binding differs'):self.exercise(tamper=True)
 def test_imported_unknown_timing_is_not_fabricated(self):
  self.assertIsNone(p.measured_wall_seconds([{'receipt':{'usage_is_inherited':True}}]))
