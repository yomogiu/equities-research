import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_coverage as c,earnings_report_template as t

class BindingTests(unittest.TestCase):
 def setUp(self):
  self.index={'turns':[{'id':x} for x in ['unrelated-q','unrelated-a','q','a','follow-q','follow-a']], 'exchanges':[{'id':'provisional','turn_ids':['unrelated-q','unrelated-a','q','a'],'followup_of':None},{'id':'follow','turn_ids':['follow-q','follow-a'],'followup_of':'provisional'}]}
 def test_exact_turns_never_copy_neighbors_or_inferred_followup(self):
  f={'citations':['q','a'],'quotes':[]};before=copy.deepcopy(f);bindings=t.original_bindings(f,self.index)
  self.assertEqual([v for _,v in bindings],[['q','a']]);self.assertEqual(f,before)
 def test_explicit_exchange_retains_its_original_extent(self):
  f={'citations':['follow'],'quotes':[]};self.assertEqual(t.original_bindings(f,self.index),[('follow',['follow-q','follow-a'])])
 def test_quote_scope_is_bound_without_topic_matching(self):
  f={'citations':['D001'],'quotes':[{'scope_id':'a'}]};self.assertEqual(t.original_bindings(f,self.index)[0][1],['a'])
 def test_distinct_subsets_have_distinct_render_keys(self):
  a=t.original_bindings({'citations':['q'],'quotes':[]},self.index);b=t.original_bindings({'citations':['a'],'quotes':[]},self.index);self.assertNotEqual(a[0][0],b[0][0])

class CoverageLineageTests(unittest.TestCase):
 def test_manifest_cannot_reset_tokens_models_round_or_completed_work(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'protocol.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={'passages':[]}
   actual={'tokens':463568,'max_tokens':1200000,'start_round':1,'state':{'artifacts':{'analysis':{'completed':True}}},'signals':{'completed':True},'models':{'analysis':['original','max']},'case_sha256':c.b.sha(case),'catalog_sha256':c.b.digest(catalog),'session_ids':['r','a','s']}
   v={'version':c.VERSION,'previous_root':str(root),'protocol_sha256':c.b.sha(root/'protocol.json'),**actual};p=root/'prepared';p.write_text(json.dumps(v))
   with patch.object(c,'replay',return_value=actual):
    self.assertEqual(c.verify(p,case,catalog)['tokens'],463568)
    for key,value in [('tokens',0),('start_round',0),('models',{}),('state',{}),('signals',{}),('session_ids',[])]:
     p.write_text(json.dumps({**v,key:value}))
     with self.assertRaises(ValueError,msg=key):c.verify(p,case,catalog)
 def test_program_rejects_later_or_uncertain_jobs_and_retains_original_sessions(self):
  self.assertIn("==['analysis','retrieval','signal_author']",c.PROGRAM)
  self.assertIn('r.verify_job(job)',c.PROGRAM)
  self.assertIn('p.coverage(role,index,job',c.PROGRAM)
  self.assertIn("role=='retrieval'",c.PROGRAM)
  self.assertIn('sid not in sessions',c.PROGRAM)

from test_earnings_passages import PassageFixture
import test_earnings_report_template as template_fixture
import test_earnings_signals as signal_fixture
from research import earnings_file_pipeline as pipeline

class CoverageAdvanceTests(PassageFixture,unittest.TestCase):
 def test_first_step_preserves_author_and_signal_and_only_requests_correction(self):
  state=template_fixture.TemplateTests.state(self);pack=signal_fixture.SignalTests.pack(self,state)
  pack['signals'][0]['passage_ids']=['Punknown-ancestor']
  inherited={'version':c.VERSION,'state':state,'signals':pack,'session_ids':['retrieval','analysis','signals'],'tokens':463568,'start_round':1,'findings':{'signal-1':'Invalid original passage ID'}}
  root=Path(self.tmp.name)/'continuation';root.mkdir();record=root/'prepared.json';record.write_text(json.dumps(inherited))
  p={'review_preparation_path':str(record),'inherited_tokens':463568}
  def pending(root,p,bundle,catalog,role,name,deps,metadata,report,execute,sessions,tokens):
   self.assertEqual((role,name),('correction','correction-1'));self.assertEqual(tokens,463568)
   self.assertEqual(sessions,{'retrieval','analysis','signals'});self.assertIn('Punknown-ancestor',report)
   self.assertEqual(deps['units']['signal-1']['value']['passage_ids'],['Punknown-ancestor'])
   return {'status':'pending','stage':name},tokens
  with patch.object(pipeline,'load',return_value=(p,self.bundle,self.catalog)),patch.object(pipeline,'_job',side_effect=pending) as job:
   self.assertEqual(pipeline._advance(root,False)['stage'],'correction-1');self.assertEqual(job.call_count,1)
