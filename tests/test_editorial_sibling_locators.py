import copy,unittest
from research.earnings_batch_review import resolve_editorial_locators

class LocatorTests(unittest.TestCase):
 def fixture(self):
  items={'retrieval':{'value':{'rows':[{'text':'Exact unique sentence.'},{'text':'Other sentence.'}]}}}
  review={'batch_sha256':'fixed','decisions':[{'unit_id':'retrieval','verdict':'revise','reason':'Unchanged','passage_ids':['P1'],'editorial_repairs':[{'field_path':['rows',1,'text'],'before':'Exact unique sentence.','after':'Approved rewrite.','reason':'Unchanged'}]}],'reopen':[]}
  return review,items
 def test_only_index_changes_original_review_untouched(self):
  r,i=self.fixture();prior=copy.deepcopy(r);out,note=resolve_editorial_locators(r,i)
  self.assertEqual(r,prior);edit=out['decisions'][0]['editorial_repairs'][0]
  self.assertEqual(edit['field_path'],['rows',0,'text']);self.assertEqual(edit['after'],'Approved rewrite.')
  self.assertEqual(out['decisions'][0]['verdict'],'revise');self.assertEqual(len(note['changes']),1)
 def test_ambiguous_missing_and_wrong_field_rejected(self):
  for case in ('duplicate','missing','wrongfield'):
   r,i=self.fixture()
   if case=='duplicate':i['retrieval']['value']['rows'].append({'text':'Exact unique sentence.'})
   if case=='missing':r['decisions'][0]['editorial_repairs'][0]['before']='Missing'
   if case=='wrongfield':r['decisions'][0]['editorial_repairs'][0]['field_path'][-1]='other'
   with self.assertRaises(ValueError):resolve_editorial_locators(r,i)
