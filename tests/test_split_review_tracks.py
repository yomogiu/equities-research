import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_batch_review as b,earnings_editorial_stage as e

class DependencyTests(unittest.TestCase):
 def items(self):
  result={}
  for key,deps in [('retrieval',[]),('analysis:0',['retrieval']),('analysis:1',['retrieval']),('analysis:next_tests',['analysis:0','analysis:1']),('signal-1',['analysis:0']),('signal-2',['analysis:1'])]:
   result[key]={'value':{'text':'Fictional evidence','citations':['P1']},'depends_on':deps}
  return result
 def test_upstream_factual_finding_does_not_discard_independent_passes(self):
  items=self.items();review={'batch_sha256':b.runner.digest(items),'decisions':[{'unit_id':k,'verdict':'revise' if k=='retrieval' else 'pass','reason':'Fictional source assessment','passage_ids':['P1']} for k in items],'reopen':[]}
  accepted,findings=b.adjudicate(items,set(items),{},review,{'passages':[{'passage_id':'P1'}]},'receipt',b.FACTUAL_VERSION)
  self.assertEqual(set(findings),{'retrieval'});self.assertEqual(set(accepted),set(items)-{'retrieval'})
  old,_=b.adjudicate(items,set(items),{},review,{'passages':[{'passage_id':'P1'}]},'receipt',b.VERSION)
  self.assertEqual(old,{})
 def test_changed_finding_reopens_only_its_signals(self):
  items=self.items();self.assertEqual(b.factual_affected(items,{'analysis:0'}),{'analysis:0','signal-1'})
 def test_explicit_source_backed_contradiction_reopens_other_unit(self):
  items=self.items();accepted={k:{'unit_sha256':b.runner.digest(v)} for k,v in items.items() if k!='retrieval'}
  review={'batch_sha256':b.runner.digest(items),'decisions':[{'unit_id':'retrieval','verdict':'pass','reason':'Supported','passage_ids':[]}],'reopen':[{'unit_id':'analysis:1','reason':'Specific fictional contradiction','passage_ids':['P1']}]}
  out,findings=b.adjudicate(items,{'retrieval'},accepted,review,{'passages':[{'passage_id':'P1'}]},'receipt',b.FACTUAL_VERSION)
  self.assertEqual(set(findings),{'analysis:1','signal-2'});self.assertIn('analysis:0',out);self.assertIn('analysis:next_tests',out)

class EditorialTests(unittest.TestCase):
 def items(self):return {'analysis:0':{'value':{'text':'Track FFF installation.','citations':['P1']},'depends_on':[]},'signal-1':{'value':{'summary':'Fictional outlook'},'depends_on':['analysis:0']}}
 def response(self,kind='term_expansion',before='FFF',after='Fictional Fabrication Facility'):
  return {'verdict':'apply','reason':'Expand first use','edits':[{'unit_id':'analysis:0','field_path':['text'],'before':before,'after':after,'kind':kind,'reason':'Guide conformance'}]}
 def test_bound_term_edit_keeps_factual_sources_and_no_reopen(self):
  items=self.items();prior=copy.deepcopy(items);terms=[{'short':'FFF','expanded':'Fictional Fabrication Facility'}]
  candidate,pending,audit=e.apply_edits(items,self.response(),terms)
  self.assertEqual(items,prior);self.assertEqual(pending,set());self.assertEqual(candidate['analysis:0']['value']['citations'],['P1'])
  self.assertEqual(candidate['signal-1'],prior['signal-1']);self.assertFalse(audit[0]['meaning_review_required'])
 def test_other_wording_reopens_only_changed_finding_and_signal(self):
  _,pending,_=e.apply_edits(self.items(),self.response('wording','Track FFF installation.','FFF is installed.'),[])
  self.assertEqual(pending,{'analysis:0','signal-1'})
 def test_unbound_terms_protected_fields_and_number_changes_cannot_bypass_facts(self):
  with self.assertRaises(ValueError):e.apply_edits(self.items(),self.response(),[])
  response=self.response();response['edits'][0].update(field_path=['citations',0],before='P1',after='P2')
  with self.assertRaises(ValueError):e.apply_edits(self.items(),response,[])
  with self.assertRaises(ValueError):e.apply_edits(self.items(),self.response('whitespace','FFF','FFF 2'),[])
 def test_terminology_comes_from_literal_source_association(self):
  cat={'passages':[{'scope_id':'turn','start':0,'text':'Fictional Fabrication Facility, or FFF, is planned.'}]}
  self.assertEqual(e.terminology(cat,['Track FFF installation.'])[0]['expanded'],'Fictional Fabrication Facility')
 def test_exhausted_factual_budget_does_not_authorize_third_author_round(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);fact=root/'facts';fact.mkdir();(fact/'protocol.json').write_text('{}')
   items=self.items();frozen={'version':b.FACTUAL_VERSION,'source_protocol':{'excluded_session_ids':[],'writing_sha256':'writing'}}
   result={'status':'accepted','round':2,'items':items,'accepted':{k:{'unit_sha256':b.runner.digest(v)} for k,v in items.items()}}
   response={'content':self.response('wording','Track FFF installation.','FFF is installed.'),'receipt':{'session':{'id':'editor','usage':{'totalTokens':42}}}}
   with patch.object(b,'load',return_value=(frozen,items,{}, {'passages':[]},'Guide')),patch.object(b,'replay',return_value=result),patch.object(b,'validate'),patch.object(e,'meaning_prompt',return_value='Verify identical factual meaning only'),patch.object(e.flow,'job',side_effect=[response,{'pending_status':'pending'}]) as calls:
    output=e.advance(fact,root/'editorial',True)
   self.assertEqual(output['status'],'pending');self.assertEqual(output['stage'],'editorial_factual_review');self.assertEqual(calls.call_count,2)
   self.assertEqual(calls.call_args.args[4]['factual_rounds_used'],2);self.assertEqual(result['round'],2)
   self.assertEqual(result['accepted']['analysis:0']['unit_sha256'],b.runner.digest(items['analysis:0']))

class ProjectionTests(unittest.TestCase):
 def test_only_explicit_editorial_kind_projects_factual_pass(self):
  review={'batch_sha256':'same','decisions':[{'unit_id':'a','verdict':'revise','reason':'Acronym','passage_ids':['P1'],'review_kind':'editorial','editorial_repairs':[{}]},{'unit_id':'b','verdict':'revise','reason':'Wrong fact','passage_ids':['P2'],'review_kind':'factual','editorial_repairs':[]}],'reopen':[]}
  original=copy.deepcopy(review);out=b.project_factual_review(review)
  self.assertEqual(review,original);self.assertEqual(out['decisions'][0]['verdict'],'pass');self.assertEqual(out['decisions'][1]['verdict'],'revise')

class EditorialGateLifecycleTests(unittest.TestCase):
 def test_factual_acceptance_alone_never_publishes(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);fact=root/'facts';fact.mkdir();(fact/'protocol.json').write_text('{}')
   items=EditorialTests().items();frozen={'version':b.FACTUAL_VERSION,'source_protocol':{'excluded_session_ids':['author'],'writing_sha256':'guide'}}
   state={'status':'accepted','round':0,'items':items,'accepted':{k:{'unit_sha256':b.runner.digest(v)} for k,v in items.items()}}
   with patch.object(b,'load',return_value=(frozen,items,{}, {'passages':[]},'Guide')),patch.object(b,'replay',return_value=state),patch.object(e.flow,'job') as job:
    result=e.advance(fact,root/'editorial',False)
   self.assertEqual(result['stage'],'editorial_review');job.assert_not_called()
   self.assertFalse((root/'editorial/report.html').exists())
 def test_editorial_pass_binds_guide_and_replays_without_new_call(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);fact=root/'facts';fact.mkdir();(fact/'protocol.json').write_text('{}')
   items=EditorialTests().items();frozen={'version':b.FACTUAL_VERSION,'source_protocol':{'excluded_session_ids':['author'],'writing_sha256':'guide'}}
   state={'status':'accepted','round':0,'items':items,'accepted':{k:{'unit_sha256':b.runner.digest(v)} for k,v in items.items()}}
   result={'content':{'verdict':'pass','edits':[],'reason':'Guide fulfilled'},'receipt':{'session':{'id':'editor','usage':{'totalTokens':10}}}}
   def job(folder,name,prompt,model,bindings,execute,excluded):
    self.assertIn('author',excluded)
    self.assertIn('Guide',prompt)
    target=folder/'batch-jobs'/name/'output.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text('{}')
    return result
   def render(target,*args,**kw):target.write_text('Fictional accepted report')
   with patch.object(b,'load',return_value=(frozen,items,{}, {'passages':[]},'Guide')),patch.object(b,'replay',return_value=state),patch.object(b,'validate'),patch.object(b,'materialize',return_value=({},{})),patch.object(b.signals,'_render_content',side_effect=render),patch.object(e.flow,'job',side_effect=job):
    first=e.advance(fact,root/'editorial',True);second=e.advance(fact,root/'editorial',False)
    self.assertEqual(first,second);self.assertEqual(first['status'],'accepted')
    self.assertEqual(first['detail']['unchanged_factual_acceptance'],state['accepted'])
    frozen['source_protocol']['writing_sha256']='changed'
    with self.assertRaisesRegex(ValueError,'snapshot changed'):e.advance(fact,root/'editorial',True)
 def test_ambiguous_alias_and_acronym_substrings_cannot_bypass_fact_gate(self):
  items=EditorialTests().items();terms=[{'short':'FFF','expanded':'Fictional Fabrication Facility'},{'short':'FFF','expanded':'Other Facility'}]
  with self.assertRaises(ValueError):e.apply_edits(items,EditorialTests().response(),terms)
  items['analysis:0']['value']['text']='Track AlphaFFF installation.'
  with self.assertRaises(ValueError):e.apply_edits(items,EditorialTests().response(),terms[:1])
 def test_quoted_source_selections_are_not_editable_fields(self):
  items=EditorialTests().items();items['analysis:0']['value']['quotes']=[{'passage_id':'P1'}]
  response=EditorialTests().response();response['edits'][0].update(field_path=['quotes',0,'passage_id'],before='P1',after='P2',kind='wording')
  with self.assertRaises(ValueError):e.apply_edits(items,response,[])

from test_earnings_passages import PassageFixture
class EditorialEvidenceScopeTests(PassageFixture,unittest.TestCase):
 def test_meaning_review_resolves_passage_to_complete_source_and_both_exchange_sides(self):
  exchange=self.bundle['transcript_index']['exchanges'][0]
  passage=next(p for p in self.catalog['passages'] if p['scope_id'] in exchange['turn_ids'] and p['text'].strip())
  items={'analysis:0':{'value':{'text':'Fictional original wording','citations':[passage['passage_id']]},'depends_on':[]}}
  candidate=copy.deepcopy(items);candidate['analysis:0']['value']['text']='Fictional revised wording'
  prompt=e.meaning_prompt(items,candidate,{'analysis:0'},self.bundle,self.catalog)
  context=json.loads(prompt.split('\nCONTEXT\n',1)[1]);serialized=json.dumps(context)
  self.assertIn(passage['scope_id'],serialized);self.assertIn(json.dumps(passage['text']),serialized)
  exchange=next(x for x in self.bundle['transcript_index']['exchanges'] if passage['scope_id'] in x['turn_ids'])
  for tid in exchange['turn_ids']:
   for p in self.catalog['passages']:
    if p['scope_id']==tid and p['text'].strip():self.assertIn(json.dumps(p['text']),serialized)
