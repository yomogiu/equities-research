import unittest,copy
from research.earnings_structural_addresses import repair
class StructuralTests(unittest.TestCase):
 def setUp(self):
  self.v={'exchange_coverage':[{'exchange_id':'E','question_passage_ids':['bad']}],'quotes':[{'passage_id':'bad'}]};self.c={'passages':[{'passage_id':'Pexact','scope_id':'T'}]};self.i={'exchanges':[{'id':'E','question_turn_ids':['T'],'answer_turn_ids':[]}]}
 def test_exact_structural_relation_and_immutable_source(self):
  old=copy.deepcopy(self.v);v,a=repair(self.v,self.c,self.i);self.assertEqual(self.v,old);self.assertEqual(v['quotes'][0]['passage_id'],'Pexact');self.assertEqual(a[0]['original_turn_ids'],['T'])
 def test_multiple_paragraphs_rejected(self):
  self.c['passages'].append({'passage_id':'Pother','scope_id':'T'})
  with self.assertRaises(ValueError):repair(self.v,self.c,self.i)
 def test_prefix_not_used(self):
  self.c['passages'][0]['scope_id']='different'
  with self.assertRaises(ValueError):repair(self.v,self.c,self.i)
 def test_quote_prose_rejected(self):
  self.v['quotes'][0]['text']='claim'
  with self.assertRaises(ValueError):repair(self.v,self.c,self.i)
