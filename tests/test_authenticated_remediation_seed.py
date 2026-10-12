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

 def test_zero_call_admission_recovery_keeps_exact_allowance_plan(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'attempts/0').mkdir(parents=True)
   plan={'fictional':'exact'};auth={'max_review_attempts':1,'max_tokens':200000,'admission_recovery_authorization':'Explicit fixture authority','budget_reference_jobs':['/fictional/review']}
   (root/'authorization.json').write_text(json.dumps({'max_review_attempts':1,'max_tokens':200000}))
   (root/'attempts/0/plan.json').write_text(json.dumps(plan))
   old={'version':m.VERSION,'history':{'prior_rounds':2,'prior_tokens':12345},'max_review_attempts':1,'max_tokens':200000}
   exported={'status':'budget_exhausted','prior_rounds':2,'prior_tokens':12345}
   m.validate_admission_recovery(root,old,exported,plan,auth)
   for altered in [dict(auth,max_tokens=200001),dict(auth,max_review_attempts=2)]:
    with self.assertRaises(ValueError):m.validate_admission_recovery(root,old,exported,plan,altered)
   for altered in [dict(exported,prior_tokens=12346),dict(exported,prior_rounds=3),dict(exported,status='blocked')]:
    with self.assertRaises(ValueError):m.validate_admission_recovery(root,old,altered,plan,auth)
   with self.assertRaises(ValueError):m.validate_admission_recovery(root,old,exported,{'changed':True},auth)
   (root/'attempts/0/review').mkdir()
   with self.assertRaisesRegex(ValueError,'launched'):m.validate_admission_recovery(root,old,exported,plan,auth)
 def test_original_batch_reference_requires_exact_bound_review_shape(self):
  from research import earnings_budget as budget,earnings_experiment as base
  with tempfile.TemporaryDirectory() as d:
   job=Path(d).resolve()/'batch-review/batches/2/review';job.mkdir(parents=True)
   request={'model':'gpt-6.1-sol','effort':'medium','bindings':{'protocol_sha256':'a'*64,'batch_sha256':'b'*64,'round':2}}
   (job/'request.json').write_text(json.dumps(request));(job/'prompt.txt').write_text('Fictional source review ' * 100)
   for name in ['output.json','execution.json']:(job/name).write_text('{}')
   def refs():return {str(p):base.sha(p) for p in job.rglob('*') if p.is_file()}
   value={'receipt':{'session':{'id':'fictional-session','model':'gpt-6.1-sol','effort':'medium','provider':'openai-codex','usage':{'input':100,'cacheRead':0,'cacheWrite':0,'output':10,'totalTokens':110}}}}
   self.assertEqual(len(budget.review_calibration([str(job)],refs(),('gpt-6.1-sol','medium'),lambda p:value)),1)
   request['bindings']['role']='analysis';(job/'request.json').write_text(json.dumps(request))
   with self.assertRaisesRegex(ValueError,'same-model'):budget.review_calibration([str(job)],refs(),('gpt-6.1-sol','medium'),lambda p:value)
