import unittest,copy
from research.earnings_prepared_signals import canonicalize
class SignalsTests(unittest.TestCase):
 def test_exact_existing_cited_scope_only_and_no_prose_change(self):
  raw={'signals':[{'id':'signal-1','summary':'Original wording','citations':['D001'],'passage_ids':[]},{'id':'signal-2','citations':['D002'],'passage_ids':['Pexisting']} ]};old=copy.deepcopy(raw);cat={'passages':[{'scope_id':'D001','passage_id':'P1'},{'scope_id':'D002','passage_id':'P2'}]};out,note=canonicalize(raw,cat,['D001']);self.assertEqual(out['signals'][0]['passage_ids'],['P1']);self.assertEqual(out['signals'][0]['summary'],raw['signals'][0]['summary']);self.assertEqual(out['signals'][1],raw['signals'][1]);self.assertEqual(raw,old);self.assertEqual(len(note),1)
 def test_incomplete_scope_and_no_expansion_fail(self):
  with self.assertRaises(ValueError):canonicalize({'signals':[{'id':'signal-1','citations':['D001'],'passage_ids':[]}]},{'passages':[]},[])
  with self.assertRaises(ValueError):canonicalize({'signals':[{'id':'signal-1','citations':['D001'],'passage_ids':['Pbad']}]},{'passages':[]},['D001'])
