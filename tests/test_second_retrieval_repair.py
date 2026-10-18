import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_second_retrieval_repair as second
from research import earnings_file_pipeline as pipeline
from test_earnings_passages import PassageFixture
import test_earnings_report_template as tf
import test_earnings_signals as sf

class SecondRepairLineageTests(unittest.TestCase):
 def test_all_three_sessions_usage_and_spent_round_are_bound(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={'passages':[]}
   actual={'tokens':550000,'spent_correction_rounds':2,'session_ids':['original','first','second'],'models':{'retrieval':['original','max']},'case_sha256':second.b.sha(case),'catalog_sha256':second.b.digest(catalog)}
   v={'version':second.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':second.b.sha(root/'reservation.json'),**actual};record=root/'prepared';record.write_text(json.dumps(v))
   with patch.object(second,'completed',return_value=actual):
    self.assertEqual(second.verify(record,case,catalog)['tokens'],550000)
    for key,value in [('tokens',0),('spent_correction_rounds',1),('session_ids',['second']),('models',{})]:
     record.write_text(json.dumps({**v,key:value}))
     with self.assertRaises(ValueError,msg=key):second.verify(record,case,catalog)

class FinalReviewRoutingTests(PassageFixture,unittest.TestCase):
 def test_two_charged_retrieval_repairs_allow_only_fresh_review2(self):
  state=tf.TemplateTests.state(self);pack=sf.SignalTests.pack(self,state)
  root=Path(self.tmp.name)/'final-review';root.mkdir();(root/'qa-grounding.json').write_text('{}');record=root/'continued';record.write_text(json.dumps({'state':state,'signals':pack,'session_ids':['r0','r1','r2','author','signals']}))
  protocol={'review_preparation_path':str(record),'inherited_tokens':700000,'retrieval_repair_rounds':2}
  def pending(root,p,bundle,catalog,role,name,artifacts,metadata,report,execute,sessions,tokens):
   self.assertEqual((role,name),('review','review-2'));self.assertEqual(tokens,700000);self.assertEqual(len(sessions),5)
   return {'status':'pending','stage':name},tokens
  with patch.object(pipeline,'load',return_value=(protocol,self.bundle,self.catalog)),patch.object(pipeline,'_job',side_effect=pending) as job:
   self.assertEqual(pipeline._advance(root,False)['stage'],'review-2');self.assertEqual(job.call_count,1)

class LaunchBindingTests(unittest.TestCase):
 def test_historical_clock_requires_exact_launch_request_binding(self):
  with tempfile.TemporaryDirectory() as d:
   job=Path(d);self.assertIsNone(second.launched_at(job));request={'bindings':{'original_tokens':340011}}
   (job/'request.json').write_text(json.dumps(request));launch={'request_sha256':second.b.digest(request),'started_at':'2026-01-01T01:00:00+00:00'}
   (job/'launch.json').write_text(json.dumps(launch));self.assertEqual(second.launched_at(job),launch['started_at'])
   request['bindings']['original_tokens']=0;(job/'request.json').write_text(json.dumps(request))
   with self.assertRaises(ValueError):second.launched_at(job)
