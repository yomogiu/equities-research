"""Source-bound saved-review recovery using fictitious candidate and requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_corrections as c, earnings_experiment as b

class BindingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  b.save(self.root/'protocol.json',{'prior_rounds':1});self.folder=self.root/'rounds/0';self.folder.mkdir(parents=True)
  self.candidate={'fake':'candidate'};self.plan={'fake':'plan'}
  b.save(self.folder/'candidate.json',self.candidate);b.save(self.folder/'plan.json',self.plan)
  self.outputs={}
  for name,sid in [('review','F001'),('review-evidence-1','D002')]:
   job=self.folder/name;job.mkdir()
   out={'verdict':'needs_evidence','candidate_sha256':b.digest(self.candidate),'plan_sha256':b.digest(self.plan),'requests':[{'scope_id':sid,'reason':'Read original terms'}]}
   b.save(job/'output.json',out);self.outputs[str(job)]={'content':out,'receipt':{'session':{'id':name}}}
 def bind(self):
  with patch.object(c,'verify_job',side_effect=lambda p:self.outputs[str(p)]),patch.object(c.evidence,'load_bundle',return_value={'manifest':{}}),patch.object(c.passages,'catalog',return_value={}),patch.object(c.context,'evidence_response',side_effect=lambda b,k,req:{'scope_ids':sorted({r['scope_id'] for r in req})}):
   return c.review_evidence_binding(self.root,{'used_rounds':1},{'original':'snapshot'},{'evidence_manifest':'fake'})
 def test_requests_candidate_and_session_identities_bound(self):
  v=self.bind();self.assertEqual(v['scope_ids'],['D002','F001']);self.assertEqual(v['additional_lookup_rounds'],0);self.assertEqual(len(v['jobs']),2);self.assertEqual(v['candidate_sha256'],b.digest(self.candidate))
 def test_wrong_candidate_rejected(self):
  self.outputs[str(self.folder/'review-evidence-1')]['content']['candidate_sha256']='f'*64
  with self.assertRaisesRegex(ValueError,'exact-candidate'):self.bind()
 def test_final_verdict_cannot_be_retried_as_evidence_request(self):
  self.outputs[str(self.folder/'review')]['content']['verdict']='blocked'
  with self.assertRaisesRegex(ValueError,'exact-candidate'):self.bind()
 def test_resume_cannot_reset_budget_or_skip_saved_proposal(self):
  for kwargs in [{'resume_evidence':True},{'resume_evidence':True,'reuse_proposal':True,'new_experiment':True}]:
   with self.assertRaisesRegex(ValueError,'original budget'):
    c.initialize(self.root,self.root.parent/'new-edition',**kwargs)
