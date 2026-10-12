"""Fictional source handoffs and actual presentation dependencies."""
import copy,json,unittest
from unittest.mock import patch
import test_earnings_signals as fixtures
from test_earnings_passages import PassageFixture
from research import earnings_batch_review as b,earnings_batched_flow as f

class HandoffTests(PassageFixture,unittest.TestCase):
 state=fixtures.SignalTests.state
 pack=fixtures.SignalTests.pack
 def items(self):
  state=self.state();return b.units(state,self.pack(state))
 def test_original_financial_evidence_only_under_explicit_factual_contract(self):
  items=self.items();review={'batch_sha256':b.runner.digest(items),'decisions':[{'unit_id':'financial','verdict':'revise','reason':'Original financial source issue','passage_ids':['F002']}],'reopen':[]}
  with self.assertRaises(ValueError):b.adjudicate(items,{'financial'},{},review,self.catalog,'receipt',b.FACTUAL_VERSION)
  _,findings=b.adjudicate(items,{'financial'},{},review,self.catalog,'receipt',b.FACTUAL_VERSION,financial_evidence=self.bundle['financial']['observations'])
  self.assertIn('F002',findings['financial'])
  review['decisions'][0]['passage_ids']=['F999999']
  with self.assertRaises(ValueError):b.adjudicate(items,{'financial'},{},review,self.catalog,'receipt',b.FACTUAL_VERSION,financial_evidence=self.bundle['financial']['observations'])
  with self.assertRaises(ValueError):b.adjudicate(items,{'financial'},{},review,self.catalog,'receipt',b.VERSION,financial_evidence=self.bundle['financial']['observations'])
 def test_requested_existing_scope_reaches_correction_context(self):
  items=self.items();scope=self.bundle['documents']['chunks'][-1]['id']
  # The pending draft deliberately has no reference to this requested scope.
  with patch.object(b.evidence,'source_slices',wraps=b.evidence.source_slices) as slices:
   prompt=b.prompt(items,items,{'signal-1'},{},{'signal-1':'Inspect '+scope+' before deciding. D999999 is unavailable.'},self.catalog,'Guide',1,self.bundle,b.FACTUAL_VERSION)
  self.assertIn(scope,slices.call_args_list[0].args[1]);self.assertNotIn('D999999',slices.call_args_list[0].args[1]);self.assertIn(scope,prompt)
 def test_row_selection_changes_reopen_formatter_without_broad_cascade(self):
  items=self.items();value=copy.deepcopy(items['financial']['value']);value['rows'][0]['label']+=' — accounting basis unverified'
  plan={'before_sha256':b.runner.digest(items),'changes':[{'unit_id':'financial','before_sha256':b.runner.digest(items['financial']['value']),'value':value,'reason':'Original reviewer requires revised table basis'}]}
  _,pending=b.apply(items,plan,b.FACTUAL_VERSION)
  self.assertEqual(pending,{'financial','format'})
  value=copy.deepcopy(items['financial']['value']);value['gaps'].append('Fictional source limitation')
  plan['changes'][0]['value']=value
  _,pending=b.apply(items,plan,b.FACTUAL_VERSION);self.assertEqual(pending,{'financial'})
 def test_corrector_receives_real_display_interface(self):
  items=self.items();result={'round':1,'items':items,'findings':{'financial':'Rendered accounting basis label is unsupported'},'accepted':{}}
  prompt=f.proposal_prompt(result,self.bundle,self.catalog,'Guide',b.FACTUAL_VERSION)
  self.assertIn('edit format.rows or format.basis',prompt)

from research import earnings_review_attempt_recovery as recovery
class SavedAuthorFormatTests(unittest.TestCase):
 def test_exact_author_qualification_compiles_only_existing_labels(self):
  items={'financial':{'value':{'rows':[{'label':'Revenue — as filed; accounting basis unverified','fact_ids':['F1','F2']}]}},'format':{'value':{'rows':{'row':{'label':'Revenue (GAAP)','dimensions':'USD','citations':['F1','F2']}},'basis':{'text':'','citations':[]}}},'analysis:0':{'value':{'text':'Unchanged accepted claim'}}}
  rows={'row':{'row':{'cells':[{'fact_ids':['F1']},{'fact_ids':['F2']}]}}}
  with patch.object(b.remediation.repair,'row_catalog',return_value=rows):out,audit=recovery.compile_format(items,{})
  self.assertEqual(out['financial'],items['financial']);self.assertEqual(out['analysis:0'],items['analysis:0']);self.assertEqual(out['format']['value']['rows']['row']['citations'],['F1','F2']);self.assertEqual(len(audit),1)
  self.assertEqual(items['format']['value']['rows']['row']['label'],'Revenue (GAAP)')
 def test_ambiguous_foreign_or_non_gaap_rows_are_not_reclassified(self):
  items={'financial':{'value':{'rows':[{'label':'Revenue; accounting basis unverified','fact_ids':['F1']}]}},'format':{'value':{'rows':{'row':{'label':'Non-GAAP revenue','dimensions':'','citations':['F1']}},'basis':{'text':'','citations':[]}}}}
  rows={'row':{'row':{'cells':[{'fact_ids':['other']}]}}}
  with patch.object(b.remediation.repair,'row_catalog',return_value=rows),self.assertRaises(ValueError):recovery.compile_format(items,{})

class InheritedReviewCheckpointTests(unittest.TestCase):
 def test_failed_verification_cannot_request_another_author_round(self):
  import tempfile
  with tempfile.TemporaryDirectory() as tmp:
   root=__import__('pathlib').Path(tmp);b.runner.save(root/'protocol.json',{})
   items={'financial':{'value':{'text':'Fictional saved correction'},'depends_on':[]},'analysis:0':{'value':{'text':'Accepted fictional claim'},'depends_on':[]}}
   accepted={'analysis:0':{'unit_sha256':b.runner.digest(items['analysis:0'])}}
   p={'version':b.FACTUAL_VERSION,'source_protocol':{'excluded_session_ids':['author']},'seeded_factual_acceptance':accepted,'inherited_factual_rounds':2,'pending_inherited_review':{'pending':['financial'],'findings':{'financial':'Original source issue'},'derivation':{'no_new_author':True}}}
   bundle={'financial':{'observations':[{'id':'F1'}]}};catalog={'passages':[]}
   with patch.object(b,'load',return_value=(p,items,bundle,catalog,'Guide')),patch.object(b,'prompt',return_value='Original bound context'):
    pending=b.replay(root);job=__import__('pathlib').Path(pending['job']);job.mkdir(parents=True)
    (job/'prompt.txt').write_text(pending['prompt']);b.runner.save(job/'request.json',{'bindings':pending['bindings'],'model':b.MODEL[0],'effort':b.MODEL[1]});(job/'output.json').write_text('{}')
    response={'content':{'batch_sha256':'echo','decisions':[{'unit_id':'financial','verdict':'revise','reason':'Unresolved source defect','passage_ids':['F1']}],'reopen':[]},'receipt':{'session':{'id':'reviewer','usage':{'totalTokens':10}}}}
    with patch.object(b.runner,'verify_job',return_value=response):result=b.replay(root)
   self.assertEqual(result['status'],'blocked');self.assertEqual(result['round'],2);self.assertIn('analysis:0',result['accepted'])
