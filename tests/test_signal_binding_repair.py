import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_signal_binding_repair as h,earnings_prepared_review as review
class Repair(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.run='a'*24;self.previous=self.root/'reporting/runs'/self.run/'pipeline';j=self.previous/'jobs/signal_author';j.mkdir(parents=True);(j/'request.json').write_text(json.dumps({'code_root':str(self.root/'.report-workflow'/('b'*40))}));self.output=self.root/'reporting/repairs/signal-bindings'/self.run
 def test_exact_path(self):h.reservation_path(self.previous,self.output)
 def test_alternate_path_rejects(self):
  with self.assertRaises(ValueError):h.reservation_path(self.previous,self.root/'another-version'/self.run)
 def test_legacy_usage_rejects(self):
  p=self.root/'reporting/repairs/old-version/slot/reservation.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'previous_root':str(self.previous)}))
  with self.assertRaises(ValueError):h.reservation_path(self.previous,self.output)
 def test_canonical_existing_not_treated_as_alternate(self):
  self.output.mkdir(parents=True);(self.output/'reservation.json').write_text(json.dumps({'previous_root':str(self.previous)}));h.reservation_path(self.previous,self.output)
 def test_runtime_requires_both_schema_and_complete_inspection(self):
  artifacts={'state':{},'unreviewed_prior_signals_json':json.dumps({'report_sha256':'x','signals':[{'id':'signal-1','passage_ids':[]}]})};catalog={'passages':[{'passage_id':'P-one'}]};proposal={'bindings':[{'signal_id':'signal-1','passage_ids':['P-one']}]}
  with patch('research.earnings_file_pipeline.signals.validate')as schema,patch('research.earnings_file_pipeline.coverage')as inspection:
   out=h.validate_proposal(Path('index'),Path('job'),proposal,artifacts,catalog,{});schema.assert_called_once();inspection.assert_called_once();self.assertEqual(out['signals'][0]['passage_ids'],['P-one'])
  with patch('research.earnings_file_pipeline.signals.validate'),patch('research.earnings_file_pipeline.coverage',side_effect=ValueError('Uninspected')):
   with self.assertRaises(ValueError):h.validate_proposal(Path('index'),Path('job'),proposal,artifacts,catalog,{})
 def test_opt_in_preparation_dispatch(self):
  p=self.root/'prepared.json';p.write_text(json.dumps({'version':h.PREPARATION_VERSION}))
  with patch.object(h,'verify',return_value={'verified':True})as verify:
   self.assertEqual(review.verify(p,'case',{}),{'verified':True});verify.assert_called_once_with(p,'case',{})
 def test_next_stage_is_new_review_one_with_four_real_sessions(self):
  from research import earnings_file_pipeline as p
  prepared={'version':h.PREPARATION_VERSION,'state':{'format':{}},'signals':{'signals':[]},'tokens':123456,'session_ids':['one','two','three','fresh'],'start_round':1,'spent_correction_rounds':1,'findings':{}};file=self.root/'continued.json';file.write_text(json.dumps(prepared));(self.root/'qa-grounding.json').write_text('{}');protocol={'review_preparation_path':str(file),'inherited_tokens':123456};seen=[]
  def next_job(root,protocol,bundle,catalog,role,name,deps,metadata,report,execute,sessions,tokens):
   seen.append((role,name,set(sessions),tokens));return {'status':'pending'},tokens
  with patch.object(p,'load',return_value=(protocol,{},{})),patch.object(p.batch,'units',return_value={}),patch.object(p.batch,'validate',return_value=(prepared['state'],prepared['signals'])),patch.object(p.mechanical,'check'),patch.object(p.markdown,'report',return_value='report'),patch.object(p.signals,'report_digest',return_value='hash'),patch.object(p,'_job',side_effect=next_job):
   self.assertEqual(p._advance(self.root,False),{'status':'pending'})
  self.assertEqual(seen,[('review','review-1',set(prepared['session_ids']),123456)])
