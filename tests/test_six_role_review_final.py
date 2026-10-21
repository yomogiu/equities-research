import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_six_role_review_final as h,earnings_prepared_review as prepared,earnings_file_pipeline as p
class CanonicalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.private=Path(self.tmp.name).resolve();self.run='a'*24;self.previous=self.private/'reporting/runs'/self.run/'pipeline';job=self.previous/'jobs/review-1';job.mkdir(parents=True);(job/'request.json').write_text(json.dumps({'code_root':str(self.private/'.report-workflow'/('b'*40))}));self.root=self.private/'reporting/repairs/review-final'/self.run
 def test_only_canonical_six_role_slot(self):
  h.reservation_path(self.previous,self.root)
  with self.assertRaises(ValueError):h.reservation_path(self.previous,self.root.parent/'other')
 def test_normalized_legacy_usage_rejects(self):
  file=self.private/'reporting/repairs/other/reservation.json';file.parent.mkdir(parents=True);file.write_text(json.dumps({'nested':[str(self.previous.parent/'x/../pipeline')]}))
  with self.assertRaisesRegex(ValueError,'legacy'):h.reservation_path(self.previous,self.root)
 def test_new_preparation_dispatch_only(self):
  file=self.private/'prepared';file.write_text(json.dumps({'version':h.PREPARATION_VERSION}))
  with patch.object(h,'verify',return_value={'verified':True}):self.assertEqual(prepared.verify(file,'case',{}),{'verified':True})
 def test_final_preparation_goes_only_to_new_review_two(self):
  self.root.mkdir(parents=True);file=self.root/'prepared';state={'format':{}};signals={'signals':[]};ids=['r','a','s','review0','correction1','review1','combined2'];v={'version':h.PREPARATION_VERSION,'state':state,'signals':signals,'tokens':1100000,'session_ids':ids,'start_round':2,'spent_correction_rounds':2,'findings':{}};file.write_text(json.dumps(v));(self.root/'qa-grounding.json').write_text('{}');protocol={'review_preparation_path':str(file),'inherited_tokens':1100000};seen=[]
  def next_role(root,protocol,bundle,catalog,role,name,deps,metadata,report,execute,sessions,tokens):seen.append((role,name,len(sessions),tokens));return {'status':'pending'},tokens
  with patch.object(p,'load',return_value=(protocol,{},{})),patch.object(p.batch,'units',return_value={}),patch.object(p.batch,'validate',return_value=(state,signals)),patch.object(p.mechanical,'check'),patch.object(p.markdown,'report',return_value='report'),patch.object(p.signals,'report_digest',return_value='hash'),patch.object(p,'_job',side_effect=next_role):self.assertEqual(p._advance(self.root,False),{'status':'pending'})
  self.assertEqual(seen,[('review','review-2',7,1100000)])

class AccountingTests(unittest.TestCase):
 def run_case(self,sid='final',used=50000,model='original'):
  from research import earnings_file_runner as runner,earnings_compact_evidence as evidence
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/final-correction-2';job.mkdir(parents=True);(job/'prompt.md').write_text('exact');source=root/'source';source.mkdir();(source/'protocol.json').write_text(json.dumps({'evidence_manifest':'manifest'}));prior={'tokens':1000000,'session_ids':['r','a','s','review0','correction1','review1'],'max_tokens':1200000,'catalog':{},'case_sha256':'case','catalog_sha256':'catalog','writing_sha256':'writing','report_template':'source-led-six-sections-v1'};v={'job':str(job),'index':'index','previous_root':str(source),'prior':prior,'bindings':{'role':'correction'},'max_tokens':200000,'models':{'correction':['original','max']},'prompt':'exact'};q={'bindings':v['bindings'],'max_tokens':200000,'max_tool_calls':48,'model':model,'effort':'max'};done={'content':{},'receipt':{'session':{'id':sid,'usage':{'totalTokens':used}}}};read=h.b.read
   with patch.object(h,'frozen',return_value=None),patch.object(h,'verify_reservation',return_value=v),patch.object(h.b,'read',side_effect=lambda path:q if Path(path)==job/'request.json'else read(path)),patch.object(runner,'verify_job',return_value=done),patch.object(evidence,'load_bundle',return_value={}),patch.object(h,'artifacts',return_value={}),patch.object(h,'validate_proposal',return_value={'state':{},'signals':{}}):return h.completed(root)
 def test_all_seven_sessions_and_only_original_final_round(self):
  v=self.run_case();self.assertEqual(v['tokens'],1050000);self.assertEqual(len(v['session_ids']),7);self.assertEqual((v['spent_correction_rounds'],v['start_round']),(2,2))
 def test_changed_route_duplicate_session_and_cap_overrun_reject(self):
  for args in [{'model':'other'},{'sid':'review1'},{'used':250000}]:
   with self.assertRaises(ValueError):self.run_case(**args)
