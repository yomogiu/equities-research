import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_retrieval_reference_repair as r,earnings_file_runner as runner
class ReferenceProposalTests(unittest.TestCase):
 def setUp(self):
  self.row={'exchange_id':'e1','question':'unchanged question','answer':'unchanged answer','question_passage_ids':['missing'],'answer_passage_ids':['P3']}
  self.old={'exchange_coverage':[self.row],'other':'original'};self.new={'exchange_coverage':[],'other':'repaired'}
  self.catalog={'passages':[{'passage_id':'P1','scope_id':'q'},{'passage_id':'P2','scope_id':'q'},{'passage_id':'P3','scope_id':'a'}]};self.index={'exchanges':[{'id':'e1','question_turn_ids':['q'],'answer_turn_ids':['a']}]}
 def test_omitted_field_preserves_provenance_without_choosing_ambiguous_paragraph(self):
  before=copy.deepcopy((self.old,self.new));candidate,targets,preserved=r.candidate_and_targets(self.old,self.new,self.catalog,self.index)
  self.assertTrue(preserved);self.assertEqual(candidate['other'],'repaired');self.assertEqual(candidate['exchange_coverage'],[self.row]);self.assertEqual(targets[0]['allowed_passage_ids'],['P1','P2']);self.assertEqual((self.old,self.new),before)
  proposal={'repairs':[{'exchange_id':'e1','field':'question_passage_ids','before_ids':['missing'],'after_ids':['P2']}]};fixed=r.apply(candidate,targets,proposal,self.catalog)
  self.assertEqual(fixed['exchange_coverage'][0]['question_passage_ids'],['P2']);self.assertEqual(fixed['exchange_coverage'][0]['question'],self.row['question']);self.assertEqual(candidate['exchange_coverage'][0]['question_passage_ids'],['missing'])
 def test_wrong_scope_prose_changes_partial_or_duplicate_proposals_rejected(self):
  candidate,targets,_=r.candidate_and_targets(self.old,self.new,self.catalog,self.index);good={'exchange_id':'e1','field':'question_passage_ids','before_ids':['missing'],'after_ids':['P1']}
  for values in ([],[good,good],[{**good,'after_ids':['P3']}],[{**good,'question':'rewritten'}],[{**good,'before_ids':['other']}]):
   with self.assertRaises(ValueError):r.apply(candidate,targets,{'repairs':values},self.catalog)
 def test_existing_valid_references_cannot_be_dropped(self):
  self.row['question_passage_ids']=['P1','missing'];candidate,targets,_=r.candidate_and_targets(self.old,self.new,self.catalog,self.index)
  with self.assertRaises(ValueError):r.apply(candidate,targets,{'repairs':[{'exchange_id':'e1','field':'question_passage_ids','before_ids':['P1','missing'],'after_ids':['P2']}]},self.catalog)
 def test_missing_or_conflicting_exchange_membership_never_synthesized(self):
  for old,new in [({'exchange_coverage':[]},self.new),(self.old,{'exchange_coverage':[{**self.row,'exchange_id':'wrong'}]})]:
   with self.assertRaises(ValueError):r.candidate_and_targets(old,new,self.catalog,self.index)
class ReferenceWorkPlanTests(unittest.TestCase):
 def test_target_evidence_and_validation_have_explicit_slots(self):
  with patch.object(runner.context,'Evidence') as reader,patch.object(runner.old,'read',return_value={'source_scope_ids':['q','a']}):
   reader.return_value._handoff_body.return_value='x'*100;reader.return_value._support_body.return_value=('x'*100,[],[])
   self.assertEqual(runner.work_plan('retrieval_reference',Path('/tmp/index.json'))['work_tool_limit'],3)
   reader.return_value._support_body.return_value=('x'*500000,[],[])
   with self.assertRaises(ValueError):runner.work_plan('retrieval_reference',Path('/tmp/index.json'))
class ReferencePreparationTests(unittest.TestCase):
 def test_three_sessions_usage_and_final_round_are_bound(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');catalog={};actual={'tokens':390000,'spent_correction_rounds':2,'session_ids':['old','first','reference'],'models':{'retrieval':['original','max']},'case_sha256':r.b.sha(case),'catalog_sha256':r.b.digest(catalog)};value={'version':r.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':r.b.sha(root/'reservation.json'),**actual};out=root/'prepared'
   with patch.object(r,'completed',return_value=actual):
    out.write_text(json.dumps(value));self.assertEqual(r.verify(out,case,catalog)['tokens'],390000)
    for k,v in [('tokens',0),('spent_correction_rounds',1),('session_ids',['reference']),('models',{})]:
     out.write_text(json.dumps({**value,k:v}))
     with self.assertRaises(ValueError):r.verify(out,case,catalog)
