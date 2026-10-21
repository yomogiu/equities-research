"""Fictitious turn-only closed-author recovery; never a guessed mapping."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_analysis_turn_address_repair as a,earnings_analysis_address_repair as exchange

class TurnAddressTests(unittest.TestCase):
 def fixture(self):
  index={'turns':[{'id':x}for x in ['turn-question','turn-answer-one','turn-answer-two','turn-prepared']], 'exchanges':[{'id':'exchange-one','answer_turn_ids':['turn-answer-one','turn-answer-two']}]}
  raw={'title':'Fictional company','opening':'Original opening','opening_citations':['D001'],'findings':[{'section':'qa','heading':'Original heading','text':'Original prose','citations':['turn-unknown','turn-answer-two'],'quotes':[{'passage_id':'Pexact'}]}],'scope':'Original scope','next_tests':[]}
  candidate=copy.deepcopy(raw);candidate['findings'][0]['citations'][0]='turn-answer-one';return raw,index,candidate
 def test_one_typed_qa_position_with_only_original_answer_turns(self):
  raw,index,candidate=self.fixture();before=copy.deepcopy(raw);target=a.targets(raw,index)[0];self.assertEqual(target['field_path'],['findings',0,'citations']);self.assertEqual(target['allowed_turn_ids'],['turn-answer-one','turn-answer-two']);self.assertEqual(a.checked_candidate(raw,candidate,index),candidate);self.assertEqual(raw,before);self.assertEqual(a.inspection_candidate(raw,index)['findings'][0]['citations'],['turn-answer-two'])
  with self.assertRaises(ValueError):exchange.targets(raw,index)
 def test_no_prefix_similarity_question_prepared_or_exchange_replacement(self):
  raw,index,candidate=self.fixture()
  for identifier in ['turn-answer','turn-answer-onex','turn-question','turn-prepared','exchange-one','Pexact','turn-unknown']:
   bad=copy.deepcopy(candidate);bad['findings'][0]['citations'][0]=identifier
   with self.subTest(identifier=identifier),self.assertRaises(ValueError):a.checked_candidate(raw,bad,index)
 def test_only_qa_single_field_single_unknown_with_retained_support(self):
  raw,index,_=self.fixture()
  mutations=[lambda x:x['findings'][0].update(section='demand'),lambda x:x['findings'][0].update(citations=['turn-unknown']),lambda x:x.update(opening_citations=['turn-other-unknown','D001']),lambda x:x['findings'].append(copy.deepcopy(x['findings'][0])),lambda x:x['findings'][0].update(citations=['turn-unknown','turn-second-unknown','D001']),lambda x:x['findings'][0].update(citations=['turn-answer-one','turn-answer-two'])]
  for mutate in mutations:
   bad=copy.deepcopy(raw);mutate(bad)
   with self.assertRaises(ValueError):a.targets(bad,index)
  for bad in [{**index,'turns':index['turns']*2},{**index,'exchanges':[{'id':'exchange-one','answer_turn_ids':['turn-absent']}]},{**index,'exchanges':[]}]:
   with self.assertRaises(ValueError):a.targets(raw,bad)
 def test_no_prose_quote_scope_valid_reference_or_position_changes(self):
  raw,index,candidate=self.fixture()
  mutations=[lambda x:x.update(opening='Changed'),lambda x:x.update(scope='Changed'),lambda x:x['findings'][0].update(text='Changed'),lambda x:x['findings'][0].update(quotes=[]),lambda x:x['findings'][0].update(citations=['turn-answer-one']),lambda x:x['findings'][0].update(citations=['turn-answer-two','turn-answer-one']),lambda x:x['findings'][0].update(citations=['turn-answer-one','turn-answer-one']),lambda x:x['findings'][0].update(citations=['turn-answer-one']*4+['turn-answer-two'])]
  for mutate in mutations:
   bad=copy.deepcopy(candidate);mutate(bad)
   with self.assertRaises(ValueError):a.checked_candidate(raw,bad,index)
 def test_original_prose_is_explicit_unreviewed_handoff_not_evidence(self):
  raw,index,_=self.fixture();v=a.contents({'raw':raw,'targets':a.targets(raw,index),'dependencies':{'retrieval':{'citations':['D001']}}});self.assertEqual(json.loads(v['unreviewed_prior_analysis_json']),raw);self.assertNotIn('turn-unknown',v['original_valid_source_inventory']['citations']);self.assertIn('turn-answer-two',v['original_valid_source_inventory']['citations'])
 def test_same_canonical_slot_prevents_cross_variant_usage_erasure(self):
  with tempfile.TemporaryDirectory()as tmp:
   private=Path(tmp).resolve();run='a'*24;previous=private/'reporting/runs'/run/'pipeline';job=previous/'jobs/analysis';job.mkdir(parents=True);(job/'request.json').write_text(json.dumps({'code_root':str(private/'.report-workflow'/('b'*40))}));slot=private/'reporting/repairs/analysis-addresses'/run
   a.reservation_path(previous,slot);exchange.reservation_path(previous,slot)
   with self.assertRaises(ValueError):a.reservation_path(previous,slot.with_name(run+'-fresh'))

from test_earnings_passages import PassageFixture
import test_analysis_address_repair as original_tests
from research import earnings_file_context as context,earnings_file_pipeline as pipeline
class TurnPipelineTests(PassageFixture,unittest.TestCase):
 def test_inherited_three_sessions_original_models_budget_and_spent_round(self):
  with patch.object(original_tests,'a',a):original_tests.AnalysisRepairPipelineTests.test_three_sessions_one_spent_round_and_original_budget_survive_pipeline(self)
 def test_validation_checks_immutable_candidate_before_full_source_coverage(self):
  raw=copy.deepcopy(self.report);raw['findings'][0].update(section='qa',citations=['turn-unknown','D001']);answer=self.bundle['transcript_index']['exchanges'][0]['answer_turn_ids'][0];candidate=copy.deepcopy(raw);candidate['findings'][0]['citations'][0]=answer;prior={'raw':raw,'targets':a.targets(raw,self.bundle['transcript_index']),'dependencies':{'retrieval':self.retrieval}}
  index=context.assemble(self.root/'evidence/manifest.json',self.catalog,self.root/'turn-repair-context',artifacts=a.contents(prior),metadata={'role':'analysis','repair_version':a.VERSION});job=self.root/'turn-repair-job';job.mkdir();(job/'request.json').write_text(json.dumps({'version':'file-prime-role-v1','context_index':str(index),'bindings':{'role':'analysis'}}));reader=context.Evidence(index,job/'retrieval.jsonl')
  with patch.object(pipeline,'coverage',side_effect=ValueError('uninspected original source'))as coverage:
   bad=copy.deepcopy(candidate);bad['opening']='Rewritten';v=reader.validate_result(bad);self.assertFalse(v['valid']);self.assertIn('must remain exact',v['error']);coverage.assert_not_called();v=reader.validate_result(candidate);self.assertFalse(v['valid']);self.assertIn('uninspected original source',v['error']);self.assertFalse(v['acceptance'])
