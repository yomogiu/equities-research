import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_single_retrieval_answer_quote as h,earnings_prepared_retrieval as prep
class Runtime(unittest.TestCase):
 def fixture(self):
  cat={'passages':[{'passage_id':p,'scope_id':s}for p,s in [('Q','q'),('A1','a'),('A2','a'),('X','other')]]};idx={'exchanges':[{'id':'e','question_turn_ids':['q'],'answer_turn_ids':['a']}]};raw={'exchange_coverage':[{'exchange_id':'e','question':'Original question','answer':'Original answer','question_passage_ids':['Q'],'answer_passage_ids':['A1','bad']}],'quotes':[{'passage_id':'bad'}]};t=h.linked.targets(raw,cat,idx);proposal={'repairs':[{'exchange_id':'e','field':'answer_passage_ids','before_ids':['A1','bad'],'after_ids':['A1','A2']}]};return raw,cat,idx,t,proposal
 def test_exact_two_position_round_trip(self):
  raw,cat,idx,t,proposal=self.fixture();before=copy.deepcopy(raw);v=h.apply(raw,t,proposal,cat,idx);self.assertEqual(raw,before);self.assertEqual(v['quotes'],[{'passage_id':'A2'}]);v['quotes'][0]['passage_id']='bad';v['exchange_coverage'][0]['answer_passage_ids']=['A1','bad'];self.assertEqual(v,before)
 def test_no_unbound_target_or_question_replacement(self):
  raw,cat,idx,t,proposal=self.fixture()
  for ids in [['A1','Q'],['A1','X'],['A2','A1'],['A1','A2','X']]:
   v=copy.deepcopy(proposal);v['repairs'][0]['after_ids']=ids
   with self.assertRaises(ValueError):h.apply(raw,t,v,cat,idx)
  with self.assertRaises(ValueError):h.apply(raw,[],proposal,cat,idx)
 def test_explicit_preparation_dispatch(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'manifest';p.write_text(json.dumps({'version':h.PREPARATION_VERSION}))
   with patch.object(h,'verify',return_value={'checked':True})as verify:
    self.assertEqual(prep.verify(p,'case',{}),{'checked':True});verify.assert_called_once_with(p,'case',{})
 def test_preparation_failed_usage_cannot_change(self):
  with tempfile.TemporaryDirectory()as tmp:
   r=Path(tmp);(r/'reservation.json').write_text('{}');case=r/'case';case.write_text('{}');actual={'tokens':321000,'max_tokens':1200000,'spent_correction_rounds':1,'session_ids':['original','fresh'],'models':{'retrieval':['original','max']},'case_sha256':h.b.sha(case),'catalog_sha256':h.b.digest({})};v={'version':h.PREPARATION_VERSION,'repair_root':str(r),'reservation_sha256':h.b.sha(r/'reservation.json'),**actual};out=r/'prepared'
   with patch.object(h,'completed',return_value=actual):
    out.write_text(json.dumps(v));self.assertEqual(h.verify(out,case,{})['tokens'],321000)
    for key,value in [('tokens',0),('spent_correction_rounds',0),('session_ids',['fresh']),('models',{})]:
     out.write_text(json.dumps({**v,key:value}))
     with self.subTest(key=key),self.assertRaises(ValueError):h.verify(out,case,{})
