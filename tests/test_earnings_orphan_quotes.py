import copy,unittest
from research.earnings_orphan_quotes import prune
class OrphanQuoteTests(unittest.TestCase):
 def setUp(self):
  self.catalog={'passages':[{'passage_id':'P'+str(i)} for i in range(5)]}
  self.value={'quotes':[{'passage_id':'P'+str(i)} for i in range(5)]+[{'passage_id':'wrong'}],'claim':'unchanged'}
 def test_lossless_kept_rows_and_original_immutable(self):
  before=copy.deepcopy(self.value);v,d=prune(self.value,self.catalog)
  self.assertEqual(self.value,before);self.assertEqual(v['quotes'],before['quotes'][:-1]);self.assertEqual(v['claim'],'unchanged');self.assertEqual(d,[{'index':5,'original_row':{'passage_id':'wrong'}}])
 def test_unknown_claim_reference_forbidden(self):
  self.value['claim']='wrong'
  with self.assertRaises(ValueError):prune(self.value,self.catalog)
 def test_prose_removal_forbidden(self):
  self.value['quotes'][-1]['text']='claim'
  with self.assertRaises(ValueError):prune(self.value,self.catalog)
 def test_minimum_and_duplicates_enforced(self):
  self.value['quotes']=self.value['quotes'][:3]+self.value['quotes'][-1:]
  with self.assertRaises(ValueError):prune(self.value,self.catalog)
 def test_valid_input_not_reinterpreted(self):
  self.value['quotes'].pop()
  with self.assertRaises(ValueError):prune(self.value,self.catalog)
