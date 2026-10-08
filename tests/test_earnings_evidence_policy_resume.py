"""Fictional saved review continuation retains requests, usage and round lineage."""
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import unittest
from test_earnings_review_evidence_resume import BindingTests
from research import earnings_corrections as c, earnings_experiment as b

class EvidencePolicyTests(BindingTests):
 def setUp(self):
  super().setUp();(self.root/'protocol.json').write_text(json.dumps({'prior_rounds':1,'max_tokens':600000,'code':[]}))
 def bind(self):
  with patch.object(c,'verify_saved_proposal',side_effect=lambda imported,records:self.outputs[imported['job']]),patch.object(c,'verify_job',side_effect=AssertionError('Current runner forbidden')),patch.object(c.evidence,'load_bundle',return_value={'manifest':{}}),patch.object(c.passages,'catalog',return_value={}),patch.object(c.context,'evidence_response',side_effect=lambda b,k,req:{'scope_ids':sorted({r['scope_id'] for r in req})}):
   return c.review_evidence_binding(self.root,{'used_rounds':1},{'original':'snapshot'},{'evidence_manifest':'fake'},'saved-review-evidence-v2')
 def test_one_authenticated_request_is_preserved_without_second_lookup(self):
  shutil.rmtree(self.folder/'review-evidence-1');result=self.bind()
  self.assertEqual(result['version'],'saved-review-evidence-v2');self.assertEqual(result['scope_ids'],['F001']);self.assertEqual(len(result['jobs']),1);self.assertEqual(result['additional_lookup_rounds'],0)
 def test_uncertain_second_lookup_is_not_dropped(self):
  job=self.folder/'review-evidence-1';(job/'output.json').unlink();(job/'request.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'uncertain'):self.bind()
 def test_missing_first_request_is_rejected(self):
  shutil.rmtree(self.folder/'review');shutil.rmtree(self.folder/'review-evidence-1')
  with self.assertRaisesRegex(ValueError,'No authenticated'):self.bind()
 def test_policy_changes_only_ceiling_with_exact_old_lineage(self):
  path=self.root/'policy.json';exported={'used_rounds':1,'spent_tokens':345678}
  value={'version':'evidence-token-policy-v1','enabled':True,'scope':'token_ceiling_only','source_protocol_sha256':b.sha(self.root/'protocol.json'),'prior_max_tokens':600000,'max_tokens':None,'prior_rounds':1,'inherited_tokens':345678,'authorized_by':'fictional-user','reason':'Explicit previously authorized ceiling removal; keep two rounds'}
  b.save(path,value);self.assertEqual(c.evidence_token_policy(path,self.root,exported),{'path':str(path.resolve()),'sha256':b.sha(path)})
  for key,new in [('prior_rounds',0),('inherited_tokens',0),('source_protocol_sha256','f'*64),('max_tokens',900000),('scope','reset'),('enabled',False),('reason','')]:
   with self.subTest(key=key):
    changed=copy.deepcopy(value);changed[key]=new;path.write_text(json.dumps(changed))
    with self.assertRaises(ValueError):c.evidence_token_policy(path,self.root,exported)
 def test_override_requires_evidence_resume_and_unlimited(self):
  for kw in ({'evidence_token_authorization':'fake'},{'resume_evidence':True,'reuse_proposal':True,'evidence_token_authorization':'fake','max_tokens':700000}):
   with self.assertRaisesRegex(ValueError,'Token-only override'):c.initialize(self.root,self.root.parent/'new',**kw)

if __name__=='__main__':unittest.main()
