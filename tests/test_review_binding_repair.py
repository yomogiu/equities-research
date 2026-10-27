import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_review_binding_repair as h,earnings_prepared_review as review
class Repair(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.run='a'*24;self.previous=self.root/'reporting/runs'/self.run/'pipeline';j=self.previous/'jobs/review-0';j.mkdir(parents=True);(j/'request.json').write_text(json.dumps({'code_root':str(self.root/'.report-workflow'/('b'*40))}));self.output=self.root/'reporting/repairs/review-bindings'/self.run
 def test_exact_path(self):h.reservation_path(self.previous,self.output)
 def test_alternate_path_rejects(self):
  with self.assertRaises(ValueError):h.reservation_path(self.previous,self.root/'another-version'/self.run)
 def test_legacy_usage_rejects(self):
  p=self.root/'reporting/repairs/old-version/slot/reservation.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'previous_root':str(self.previous)}))
  with self.assertRaises(ValueError):h.reservation_path(self.previous,self.output)
 def test_canonical_existing_not_treated_as_alternate(self):
  self.output.mkdir(parents=True);(self.output/'reservation.json').write_text(json.dumps({'previous_root':str(self.previous)}));h.reservation_path(self.previous,self.output)
 def test_typed_proposal_requires_complete_inspection_and_unresolved_review(self):
  import copy
  from test_review_binding_recovery import BindingTests
  raw,items,catalog,proposal=BindingTests().fixture();before=copy.deepcopy(raw);artifacts={'state':{},'signals':{},'units':items,'unreviewed_original_review_json':json.dumps(raw),'original_review_job':'original/review-0'}
  with patch('research.earnings_file_pipeline.coverage')as coverage,patch('research.earnings_file_pipeline.review_result',return_value=({},{'analysis:0':{'reason':'unchanged'}},False))as adjudicate:
   out,findings=h.validate_proposal(Path('index'),Path('fresh-job'),proposal,artifacts,catalog,{})
   coverage.assert_called_once();self.assertEqual(adjudicate.call_args.args[-1],Path('original/review-0'));self.assertTrue(findings);out['decisions'][0]['passage_ids']=[];self.assertEqual(out,before)
  with patch('research.earnings_file_pipeline.coverage',side_effect=ValueError('Uninspected')):
   with self.assertRaisesRegex(ValueError,'Uninspected'):h.validate_proposal(Path('index'),Path('job'),proposal,artifacts,catalog,{})
  with patch('research.earnings_file_pipeline.coverage'),patch('research.earnings_file_pipeline.review_result',return_value=({}, {},True)):
   with self.assertRaisesRegex(ValueError,'no acceptance'):h.validate_proposal(Path('index'),Path('job'),proposal,artifacts,catalog,{})
 def test_opt_in_preparation_dispatch(self):
  file=self.root/'prepared';file.write_text(json.dumps({'version':h.PREPARATION_VERSION}))
  with patch.object(h,'verify',return_value={'verified':True}):self.assertEqual(review.verify(file,'case',{}),{'verified':True})
 def test_binding_spends_round_one_then_requires_final_correction_two(self):
  from research import earnings_file_pipeline as p
  prepared={'version':h.PREPARATION_VERSION,'state':{'format':{}},'signals':{'signals':[]},'tokens':600000,'session_ids':['r','a','s','review','binding'],'start_round':2,'spent_correction_rounds':1,'findings':{'analysis:0':{'reason':'original'}}};file=self.root/'continued';file.write_text(json.dumps(prepared));protocol={'review_preparation_path':str(file),'inherited_tokens':600000};seen=[]
  def pending(root,protocol,bundle,catalog,role,name,deps,metadata,report,execute,sessions,tokens):
   seen.append((role,name,deps['findings'],len(sessions),tokens));return {'status':'pending'},tokens
  with patch.object(p,'load',return_value=(protocol,{},{})),patch.object(p.batch,'units',return_value={}),patch.object(p.batch,'validate',return_value=(prepared['state'],prepared['signals'])),patch.object(p.markdown,'report',return_value='report'),patch.object(p,'_job',side_effect=pending):self.assertEqual(p._advance(self.root,False),{'status':'pending'})
  self.assertEqual(seen,[('correction','correction-2',prepared['findings'],5,600000)])
 def test_legacy_nested_normalized_usage_rejects(self):
  file=self.root/'reporting/repairs/legacy/slot/reservation.json';file.parent.mkdir(parents=True);file.write_text(json.dumps({'nested':[str(self.previous.parent/'x/../pipeline')]}))
  with self.assertRaisesRegex(ValueError,'legacy'):h.reservation_path(self.previous,self.output)

class CompletedAccounting(unittest.TestCase):
 def run_case(self,model='review-model',sid='binding',tokens=100000):
  from research import earnings_file_runner as runner,earnings_compact_evidence as evidence
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/binding-repair';job.mkdir(parents=True);(job/'prompt.md').write_text('exact');(job/'output.json').write_text('{}');previous=root/'original';previous.mkdir();(previous/'protocol.json').write_text(json.dumps({'evidence_manifest':'manifest','writing_sha256':'writing','report_template':'source-led-six-sections-v1'}));(previous/'passages.json').write_text('{}')
   prior={'tokens':400000,'session_ids':['r','a','s','review'],'max_tokens':1200000,'state':{},'signals':{},'items':{},'review':{},'targets':['analysis:0'],'original_review_job':'original/review-0','review_output_sha256':'review-hash','case_sha256':'case','catalog_sha256':'catalog'}
   v={'job':str(job),'index':'index','previous_root':str(previous),'prior':prior,'bindings':{'role':'analysis'},'max_tokens':800000,'models':{'review':['review-model','medium']},'prompt':'exact'};q={'bindings':v['bindings'],'max_tokens':800000,'max_tool_calls':48,'model':model,'effort':'medium'};done={'content':{'bindings':[]},'receipt':{'session':{'id':sid,'usage':{'totalTokens':tokens}}}};read=h.b.read
   with patch.object(h,'frozen',return_value=None),patch.object(h,'verify_reservation',return_value=v),patch.object(h.b,'read',side_effect=lambda p:q if Path(p)==job/'request.json' else read(p)),patch.object(runner,'verify_job',return_value=done),patch.object(evidence,'load_bundle',return_value={}),patch.object(h,'validate_proposal',return_value=({'complete':'review'},{'analysis:0':{'required':'unchanged'}})):
    return h.completed(root)
 def test_five_real_sessions_and_final_correction_only(self):
  v=self.run_case();self.assertEqual(v['tokens'],500000);self.assertEqual(len(v['session_ids']),5);self.assertEqual((v['spent_correction_rounds'],v['start_round']),(1,2));self.assertTrue(v['findings']);self.assertEqual(v['bound_review'],{'complete':'review'})
 def test_changed_role_duplicate_session_and_reset_reject(self):
  for args in [{'model':'other'},{'sid':'review'},{'tokens':900000}]:
   with self.assertRaises(ValueError):self.run_case(**args)

class ReviewHandoffTests(unittest.TestCase):
 def test_typed_handoff_delivers_entire_ledger_and_targets_default_unchanged(self):
  from types import SimpleNamespace
  from research.earnings_file_context import Evidence
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);artifacts={'units':{'analysis:0':{'value':'candidate'}},'signals':{'signals':[]},'unreviewed_original_review_json':json.dumps({'decisions':[{'unit_id':'analysis:0','passage_ids':[],'reason':'x'*60000}]}),'missing_review_targets':['analysis:0'],'original_review_job':'immutable-review-job'};reader=SimpleNamespace(root=root,artifacts=artifacts,index={'files':{}})
   (root/'metadata.json').write_text(json.dumps({'repair_version':h.VERSION}));body=json.loads(Evidence._handoff_body(reader));self.assertEqual(body['artifacts'],{k:v for k,v in artifacts.items() if k!='signals'});self.assertGreater(len(body['artifacts']['unreviewed_original_review_json']),59000)
   (root/'metadata.json').write_text(json.dumps({'role':'analysis'}));ordinary=json.loads(Evidence._handoff_body(reader));self.assertEqual(ordinary['artifacts'],{'units':artifacts['units']})
