"""Fictitious linked answer-list and quotation address cases."""
import copy,unittest
from research import earnings_retrieval_answer_quote as m
class LinkedQuoteTests(unittest.TestCase):
 def fixture(self):
  cat={'passages':[{'passage_id':p,'scope_id':s}for p,s in [('Q','q'),('A1','a'),('A2','a'),('A3','other')]]};idx={'exchanges':[{'id':'e','question_turn_ids':['q'],'answer_turn_ids':['a']}]};raw={'exchange_coverage':[{'exchange_id':'e','question':'Unchanged question','answer':'Unchanged answer','question_passage_ids':['Q'],'answer_passage_ids':['A1','unknown']}],'quotes':[{'passage_id':'A1'},{'passage_id':'unknown'}]};proposal={'repairs':[{'exchange_id':'e','field':'answer_passage_ids','before_ids':['A1','unknown'],'after_ids':['A1','A2']}]};return raw,cat,idx,proposal
 def test_two_positions_only_no_mutation(self):
  r,c,i,p=self.fixture();before=copy.deepcopy(r);out=m.apply(r,c,i,p);self.assertEqual(r,before);self.assertEqual(out['quotes'][1],{'passage_id':'A2'});out['quotes'][1]={'passage_id':'unknown'};out['exchange_coverage'][0]['answer_passage_ids']=['A1','unknown'];self.assertEqual(out,r)
 def test_no_prefix_other_turn_question_or_multiple_selection(self):
  r,c,i,p=self.fixture()
  for ids in [['A1','unknow'],['A1','A3'],['A1','Q'],['A2','A1'],['A1','A2','A3'],['A2']]:
   bad=copy.deepcopy(p);bad['repairs'][0]['after_ids']=ids
   with self.subTest(ids=ids),self.assertRaises(ValueError):m.apply(r,c,i,bad)
 def test_quote_must_be_exact_same_single_unknown(self):
  r,c,i,p=self.fixture()
  for quotes in [[{'passage_id':'different'}],[{'passage_id':'unknown'},{'passage_id':'unknown'}],[{'passage_id':'unknown','text':'altered'}],[{'passage_id':'A1'}]]:
   bad=copy.deepcopy(r);bad['quotes']=quotes
   with self.assertRaises(ValueError):m.targets(bad,c,i)
 def test_unrelated_question_address_not_waived(self):
  r,c,i,p=self.fixture();r['exchange_coverage'][0]['question_passage_ids']=['bad']
  with self.assertRaises(ValueError):m.targets(r,c,i)
 def test_valid_position_order_preserved(self):
  r,c,i,p=self.fixture();p['repairs'][0]['after_ids']=['A2','A1']
  with self.assertRaises(ValueError):m.apply(r,c,i,p)
 def test_extra_fields_and_reopened_targets_rejected(self):
  r,c,i,p=self.fixture()
  for mutate in [lambda x:x.update(prose='new'),lambda x:x['repairs'][0].update(quote='new'),lambda x:x['repairs'].append(copy.deepcopy(x['repairs'][0]))]:
   bad=copy.deepcopy(p);mutate(bad)
   with self.assertRaises(ValueError):m.apply(r,c,i,bad)
if __name__=='__main__':unittest.main()
