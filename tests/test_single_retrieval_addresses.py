import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_single_retrieval_addresses as s
from research import earnings_compact_evidence as evidence,earnings_file_pipeline as pipeline
class SingleAddressTests(unittest.TestCase):
 def fixture(self):
  raw={'exchange_coverage':[{'exchange_id':'e','question':'original question','answer':'original answer','question_passage_ids':['Q'],'answer_passage_ids':['unrelated-missing','A']}],'quotes':['unchanged']};catalog={'passages':[{'passage_id':'Q','scope_id':'q'},{'passage_id':'A','scope_id':'a'},{'passage_id':'B','scope_id':'a'}]};bundle={'transcript_index':{'exchanges':[{'id':'e','question_turn_ids':['q'],'answer_turn_ids':['a']}]}};return raw,catalog,bundle
 def test_single_original_targets_do_not_guess_or_change_prose(self):
  raw,cat,bundle=self.fixture();before=copy.deepcopy(raw)
  with patch.object(s.original,'original',return_value={'raw':raw}),patch.object(s.b,'read',side_effect=[{'evidence_manifest':'manifest'},cat,{'context_index':'index'}]),patch.object(evidence,'load_bundle',return_value=bundle),patch.object(pipeline,'coverage') as coverage:
   prior,candidate,targets=s.derive(Path('/original'))
  self.assertEqual(raw,before);self.assertEqual(candidate,raw);self.assertEqual(targets[0]['allowed_passage_ids'],['A','B']);self.assertEqual(targets[0]['before_ids'],['unrelated-missing','A']);self.assertEqual(coverage.call_args.args[3]['exchange_coverage'],[])
  fixed=s.ref.apply(candidate,targets,{'repairs':[{'exchange_id':'e','field':'answer_passage_ids','before_ids':['unrelated-missing','A'],'after_ids':['B','A']}]},cat);self.assertEqual(fixed['quotes'],raw['quotes']);self.assertEqual(fixed['exchange_coverage'][0]['answer'],'original answer')
  with self.assertRaises(ValueError):s.ref.apply(candidate,targets,{'repairs':[{'exchange_id':'e','field':'answer_passage_ids','before_ids':['unrelated-missing','A'],'after_ids':['B']}]},cat)
 def test_other_missing_coverage_never_waived(self):
  raw,cat,bundle=self.fixture()
  with patch.object(s.original,'original',return_value={'raw':raw}),patch.object(s.b,'read',side_effect=[{'evidence_manifest':'manifest'},cat,{'context_index':'index'}]),patch.object(evidence,'load_bundle',return_value=bundle),patch.object(pipeline,'coverage',side_effect=ValueError('uninspected original quote')):
   with self.assertRaisesRegex(ValueError,'uninspected'):s.derive(Path('/original'))
 def test_preparation_preserves_both_sessions_round_one_and_usage(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'reservation.json').write_text('{}');case=root/'case';case.write_text('{}');actual={'tokens':300000,'spent_correction_rounds':1,'session_ids':['original','reference'],'models':{'retrieval':['original','max']},'case_sha256':s.b.sha(case),'catalog_sha256':s.b.digest({})};v={'version':s.PREPARATION_VERSION,'repair_root':str(root),'reservation_sha256':s.b.sha(root/'reservation.json'),**actual};out=root/'proof'
   with patch.object(s,'completed',return_value=actual):
    out.write_text(json.dumps(v));self.assertEqual(s.verify(out,case,{})['tokens'],300000)
    for k,value in [('tokens',0),('spent_correction_rounds',0),('session_ids',['reference']),('models',{})]:
     out.write_text(json.dumps({**v,k:value}))
     with self.assertRaises(ValueError):s.verify(out,case,{})
class DuplicateMembershipTests(unittest.TestCase):
 def fixture(self):
  rows=[{'exchange_id':'e1','question':'unaltered1','answer':'unaltered1','question_passage_ids':['Q2'],'answer_passage_ids':['A2']},{'exchange_id':'e1','question':'unaltered2','answer':'unaltered2','question_passage_ids':['Q1'],'answer_passage_ids':['A1']}];cat={'passages':[{'passage_id':p,'scope_id':p.lower()} for p in ['Q1','A1','Q2','A2']]};idx={'exchanges':[{'id':'e'+str(i),'question_turn_ids':['q'+str(i)],'answer_turn_ids':['a'+str(i)]} for i in [1,2]]};return {'exchange_coverage':rows,'quotes':['preserved']},cat,idx
 def test_exact_question_and_answer_membership_only(self):
  raw,cat,idx=self.fixture();old=copy.deepcopy(raw);out,changes=s.exact_duplicate_membership(raw,cat,idx);self.assertEqual(raw,old);self.assertEqual([x['exchange_id'] for x in out['exchange_coverage']],['e2','e1']);self.assertEqual(out['quotes'],raw['quotes']);self.assertEqual(len(changes),1)
  out['exchange_coverage'][0]['exchange_id']='e1';self.assertEqual(out,raw)
 def test_missing_unknown_or_conflicting_turns_rejected(self):
  for change in ['unknown','conflict','ambiguous','cardinality']:
   raw,cat,idx=self.fixture()
   if change=='unknown':raw['exchange_coverage'][0]['answer_passage_ids']=['missing']
   if change=='conflict':raw['exchange_coverage'][0]['answer_passage_ids']=['A1']
   if change=='ambiguous':idx['exchanges'][0]['question_turn_ids']+=['q2'];idx['exchanges'][0]['answer_turn_ids']+=['a2']
   if change=='cardinality':raw['exchange_coverage'].append(copy.deepcopy(raw['exchange_coverage'][0]))
   with self.subTest(change=change),self.assertRaises(ValueError):s.exact_duplicate_membership(raw,cat,idx)
