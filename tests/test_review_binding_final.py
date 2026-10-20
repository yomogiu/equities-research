import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_review_binding_final as h,earnings_file_pipeline as p,earnings_batch_review as batch
import test_review_binding_recovery as fixtures

class CombinedTests(unittest.TestCase):
 def fixture(self):
  raw,items,catalog,proposal=fixtures.BindingTests().fixture();a={'units':items,'state':{},'signals':{},'unreviewed_original_review_json':json.dumps(raw),'original_review_job':'immutable-review'};plan={'before_sha256':h.b.digest(items),'changes':[{'unit_id':'analysis:0','before_sha256':h.b.digest(items['analysis:0']['value']),'value':{'text':'Actual authored correction'},'reason':'Source-grounded correction'}]};return a,catalog,{'bindings':proposal['bindings'],'correction':plan}
 def run_value(self,a,catalog,value,coverage_error=False):
  with patch.object(p,'coverage',side_effect=ValueError('missing source')if coverage_error else None)as coverage,patch.object(p,'review_result',return_value=({}, {'analysis:0':{'reason':'original'}},False)),patch.object(batch,'resolve_basis_citations',side_effect=lambda items,plan,bundle:(plan,{})),patch.object(batch,'validate',side_effect=lambda items,bundle,catalog:({'corrected_units':items},{'signals':[]})):
   out=h.validate_proposal(Path('index'),Path('fresh-job'),value,a,catalog,{});self.assertEqual([x.args[0]for x in coverage.call_args_list],['review','correction']);return out
 def test_source_binding_and_actual_atomic_authored_correction_together(self):
  a,catalog,value=self.fixture();before=copy.deepcopy(a);out=self.run_value(a,catalog,value);self.assertEqual(a,before);self.assertEqual(out['bound_review']['decisions'][0]['passage_ids'],['Pabc']);self.assertEqual(out['state']['corrected_units']['analysis:0']['value'],{'text':'Actual authored correction'});self.assertTrue(out['findings'])
 def test_no_bindings_only_noop_or_stale_authored_output(self):
  a,catalog,value=self.fixture()
  for change in [lambda v:v.pop('correction'),lambda v:v['correction'].update(changes=[]),lambda v:v['correction'].update(before_sha256='stale'),lambda v:v['correction']['changes'][0].update(value=copy.deepcopy(a['units']['analysis:0']['value'])),lambda v:v.update(extra='edit')]:
   bad=copy.deepcopy(value);change(bad)
   with self.assertRaises(ValueError):self.run_value(a,catalog,bad)
 def test_no_unknown_binding_or_source_inspection_waiver(self):
  a,catalog,value=self.fixture();bad=copy.deepcopy(value);bad['bindings'][0]['passage_ids']=['Pprefix']
  with self.assertRaises(ValueError):self.run_value(a,catalog,bad)
  with self.assertRaisesRegex(ValueError,'missing source'):self.run_value(a,catalog,value,coverage_error=True)
 def test_preparation_goes_directly_to_new_independent_review_two(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);record=root/'prepared';state={'format':{}};signals={'signals':[]};ids=['r','a','s','review','empty-binding','combined-final'];v={'version':h.PREPARATION_VERSION,'state':state,'signals':signals,'tokens':900000,'session_ids':ids,'start_round':2,'spent_correction_rounds':2,'findings':{'analysis:0':{'reason':'pending independent verification'}}};record.write_text(json.dumps(v));(root/'qa-grounding.json').write_text('{}');protocol={'review_preparation_path':str(record),'inherited_tokens':900000};seen=[]
   def next_role(root,protocol,bundle,catalog,role,name,deps,metadata,report,execute,sessions,tokens):seen.append((role,name,set(sessions),tokens));return {'status':'pending'},tokens
   with patch.object(p,'load',return_value=(protocol,{},{})),patch.object(batch,'units',return_value={}),patch.object(batch,'validate',return_value=(state,signals)),patch.object(p.mechanical,'check'),patch.object(p.markdown,'report',return_value='report'),patch.object(p.signals,'report_digest',return_value='digest'),patch.object(p,'_job',side_effect=next_role):self.assertEqual(p._advance(root,False),{'status':'pending'})
   self.assertEqual(seen,[('review','review-2',set(ids),900000)])
 def test_explicit_preparation_dispatch(self):
  from research import earnings_prepared_review as prepared
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'prepared';path.write_text(json.dumps({'version':h.PREPARATION_VERSION}))
   with patch.object(h,'verify',return_value={'authenticated':True}):self.assertEqual(prepared.verify(path,'case',{}),{'authenticated':True})

class StoppedBindingAuthentication(unittest.TestCase):
 def replay(self,*,content=None,exposed=False,reused=False):
  import contextlib,io,sys
  from types import SimpleNamespace
  from research import earnings_review_binding_repair as old,earnings_file_runner as runner,earnings_file_context as context
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/binding-repair';job.mkdir(parents=True);(job/'prompt.md').write_text('exact');(job/'output.json').write_text('{}');(root/'reservation.json').write_text('{}');index=root/'context/index.json';index.parent.mkdir();prior={'tokens':400000,'session_ids':['r','a','s','review'],'max_tokens':1200000};v={'job':str(job),'index':str(index),'bindings':{'role':'analysis'},'max_tokens':800000,'models':{'review':['original','medium']},'prompt':'exact','prior':prior,'previous_root':'source','source_currentness':{'path':'proof','sha256':'hash'}};q={'bindings':v['bindings'],'max_tokens':800000,'max_tool_calls':48,'model':'original','effort':'medium'};value={'content':{'bindings':[]}if content is None else content,'receipt':{'session':{'id':'review'if reused else 'empty','usage':{'totalTokens':100000}}}};a={'unreviewed_original_review_json':'complete ledger','missing_review_targets':['analysis:0']};reader=SimpleNamespace(_handoff_body=lambda:json.dumps({'artifacts':a if exposed else {'units':{}}}));stream=io.StringIO();read=h.b.read
   def read_bound(path):
    if Path(path)==job/'request.json':return q
    if Path(path)==index.parent/'artifacts.json':return a
    return read(path)
   with patch.object(sys,'argv',['program','unused',str(root)]),patch.object(old,'verify_reservation',return_value=v),patch.object(old,'completed',side_effect=ValueError('Every missing field exactly once')),patch.object(runner,'verify_job',return_value=value),patch.object(h.b,'read',side_effect=read_bound),patch.object(context,'Evidence',return_value=reader),patch.object(context,'audit',return_value=[]),patch.object(context,'complete_ranges',return_value={'handoff'}),contextlib.redirect_stdout(stream):exec(h.PROGRAM,{})
   return json.loads(stream.getvalue())
 def test_exact_closed_empty_role_and_omitted_handoff_retain_fifth_charge(self):
  v=self.replay();self.assertEqual(v['tokens'],500000);self.assertEqual(len(v['session_ids']),5)
 def test_real_proposal_already_exposed_ledger_or_reused_session_reject(self):
  for args in [{'content':{'bindings':[{}]}},{'exposed':True},{'reused':True}]:
   with self.assertRaises(AssertionError):self.replay(**args)

class FinalAccounting(unittest.TestCase):
 def run_case(self,sid='final',used=100000,model='original-correction'):
  from research import earnings_file_runner as runner,earnings_compact_evidence as evidence
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);job=root/'jobs/final-correction-2';job.mkdir(parents=True);(job/'prompt.md').write_text('exact');source=root/'source';source.mkdir();(source/'protocol.json').write_text(json.dumps({'evidence_manifest':'manifest','case_sha256':'case','writing_sha256':'writing','report_template':'source-led-six-sections-v1'}));(source/'passages.json').write_text('{}')
   prior={'tokens':500000,'session_ids':['r','a','s','review','empty'],'source_root':str(source),'prior':{'max_tokens':1200000}};v={'prior':prior,'job':str(job),'index':'index','bindings':{'role':'correction'},'max_tokens':700000,'models':{'correction':['original-correction','max']},'prompt':'exact'};q={'bindings':v['bindings'],'max_tokens':700000,'max_tool_calls':48,'model':model,'effort':'max'};done={'content':{},'receipt':{'session':{'id':sid,'usage':{'totalTokens':used}}}};read=h.b.read
   with patch.object(h,'frozen',return_value=None),patch.object(h,'verify_reservation',return_value=v),patch.object(h.b,'read',side_effect=lambda path:q if Path(path)==job/'request.json' else read(path)),patch.object(runner,'verify_job',return_value=done),patch.object(evidence,'load_bundle',return_value={}),patch.object(h,'artifacts',return_value={}),patch.object(h,'validate_proposal',return_value={'state':{},'signals':{},'bound_review':{},'findings':{}}):return h.completed(root)
 def test_six_real_sessions_full_usage_and_both_spent_rounds(self):
  out=self.run_case();self.assertEqual(out['tokens'],600000);self.assertEqual(len(out['session_ids']),6);self.assertEqual((out['spent_correction_rounds'],out['start_round']),(2,2))
 def test_changed_route_reused_session_and_cap_overrun_reject(self):
  for args in [{'sid':'empty'},{'used':800000},{'model':'different'}]:
   with self.assertRaises(ValueError):self.run_case(**args)
