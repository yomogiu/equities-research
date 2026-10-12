"""Fictional final-review bridge: immutable candidate and historical budget."""
import contextlib,copy,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_remediation as m
class AuthenticatedSeedTests(unittest.TestCase):
 def export(self,status='blocked',rounds=2,used=2):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p={'version':'authenticated-final-review-handoff-v1','max_correction_rounds':2,'review_attempt_recovery':{'used_correction_rounds':used,'inherited_tokens':12345}}
   (root/'protocol.json').write_text(json.dumps(p))
   state={'artifacts':{'financial':{'fixture':1},'retrieval':{},'analysis':{}},'format':{}};original=copy.deepcopy(state)
   c=types.SimpleNamespace(load=lambda r:(p,{},[],''))
   b=types.SimpleNamespace(replay=lambda r:{'status':status,'round':rounds,'items':{},'findings':{'financial':'Original fictional finding'},'tokens':321},materialize=lambda items:(copy.deepcopy(state),{}),load=lambda r:({'source_protocol':{'fictional':True}},),remediation=types.SimpleNamespace(repair=types.SimpleNamespace(finding_id=lambda f:'fictional-finding')))
   import research
   with patch.dict(sys.modules,{'research.earnings_review_attempt_recovery':c,'research.earnings_batch_review':b}),patch.object(research,'earnings_review_attempt_recovery',c,create=True),patch.object(research,'earnings_batch_review',b,create=True),patch.object(sys,'argv',['bridge',str(root)]),contextlib.redirect_stdout(io.StringIO()) as out:
    with self.assertRaises(SystemExit):exec(m.EXPORT,{})
   self.assertEqual(state,original);return json.loads(out.getvalue())
 def test_preserves_complete_candidate_and_usage(self):
  v=self.export();self.assertEqual(v['prior_rounds'],2);self.assertEqual(v['prior_tokens'],12666);self.assertEqual(v['snapshot']['artifacts']['financial'],{'fixture':1});self.assertEqual(v['source_protocol'],{'fictional':True});self.assertEqual(len(v['snapshot']['findings']),1)
 def test_rejects_nonfinal_or_budget_changed(self):
  for args in [('pending',2,2),('accepted',2,2),('blocked',1,2),('blocked',2,1)]:
   with self.subTest(args=args),self.assertRaisesRegex(ValueError,'conclusively stopped'):self.export(*args)

 def test_row_metadata_allowlist_keeps_fact_ids_and_membership_inert(self):
  state={'artifacts':{'financial':{'rows':[{'label':'Fictional revenue','fact_ids':['F001']}],'context':[],'gaps':[]},'retrieval':{'exchange_coverage':[],'document_findings':[]},'analysis':{'title':'Fictional','opening':'Fictional','opening_citations':[],'scope':'Fictional','findings':[],'next_tests':[]}},'format':{'basis':{'text':'','citations':[]}}}
  with patch.object(m.repair,'row_catalog',return_value={}):targets=m.targets(state,{})
  self.assertIn(('artifacts','financial','rows',0,'label'),targets)
  self.assertNotIn(('artifacts','financial','rows',0,'fact_ids'),targets)
  self.assertNotIn(('artifacts','financial','rows'),targets)
