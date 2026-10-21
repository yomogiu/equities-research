import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_review_inspection as recovery,earnings_file_pipeline as pipeline
from test_earnings_passages import PassageFixture
import test_earnings_report_template as tf
import test_earnings_signals as sf
class ReviewInspectionLineageTests(unittest.TestCase):
 def test_only_inspection_failures_are_eligible(self):
  self.assertTrue(recovery.inspection_failure('Complete original call must be inspected, including unassigned spans'))
  self.assertTrue(recovery.inspection_failure('Required original evidence was not completely inspected: P123, turn-abc'))
  for message in ('fetch failed','Lifecycle token budget exceeded','Required original evidence was not completely inspected: ../bad',''):
   self.assertFalse(recovery.inspection_failure(message))
 def test_usage_sessions_models_and_spent_round_cannot_change(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'protocol.json').write_text('{}');case=r/'case';case.write_text('{}');catalog={}
   actual={'case_sha256':recovery.b.sha(case),'catalog_sha256':recovery.b.digest(catalog),'tokens':966273,'max_tokens':1200000,'start_round':1,'spent_correction_rounds':1,'session_ids':['a','b','c','d','e','f'],'models':{'review':['original','medium']}}
   value={'version':recovery.VERSION,'previous_root':str(r),'protocol_sha256':recovery.b.sha(r/'protocol.json'),**actual};out=r/'prepared'
   with patch.object(recovery,'replay',return_value=actual):
    out.write_text(json.dumps(value));self.assertEqual(recovery.verify(out,case,catalog)['tokens'],966273)
    for key,new in [('tokens',0),('spent_correction_rounds',0),('start_round',0),('session_ids',['f']),('models',{})]:
     out.write_text(json.dumps({**value,key:new}))
     with self.assertRaises(ValueError,msg=key):recovery.verify(out,case,catalog)
class ReviewInspectionRoutingTests(PassageFixture,unittest.TestCase):
 def test_fresh_review1_precedes_any_remaining_correction(self):
  state=tf.TemplateTests.state(self);pack=sf.SignalTests.pack(self,state);root=Path(self.tmp.name)/'resume-review';root.mkdir();(root/'qa-grounding.json').write_text('{}');record=root/'prepared'
  record.write_text(json.dumps({'version':recovery.VERSION,'state':state,'signals':pack,'session_ids':['r','a','s','v0','c1','v1'],'start_round':1,'spent_correction_rounds':1,'findings':[]}))
  protocol={'review_preparation_path':str(record),'inherited_tokens':966273}
  def pending(root,p,bundle,catalog,role,name,artifacts,metadata,report,execute,sessions,tokens):
   self.assertEqual((role,name),('review','review-1'));self.assertEqual(tokens,966273);self.assertEqual(len(sessions),6)
   return {'status':'pending','stage':name},tokens
  with patch.object(pipeline,'load',return_value=(protocol,self.bundle,self.catalog)),patch.object(pipeline,'_job',side_effect=pending) as job:
   self.assertEqual(pipeline._advance(root,False)['stage'],'review-1');self.assertEqual(job.call_count,1)
