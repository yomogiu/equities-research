"""Fictitious exact reviewer proposal tests; no research data."""
import copy,unittest
from research.earnings_prepared_heading import derive_heading
class HeadingTests(unittest.TestCase):
 def fixture(self):
  items={'analysis:0':{'value':{'heading':'Two unrelated fictional findings','text':'Original body.','citations':['section-fake'],'quotes':[{'passage_id':'Pfake'}]}},'analysis:next_tests':{'value':['Original follow-up']}}
  review={'reopen':[],'decisions':[{'unit_id':'analysis:0','verdict':'revise','review_kind':'editorial','reason':'One heading only','passage_ids':[],'editorial_repairs':[{'field_path':['heading'],'before':'Two unrelated fictional findings','after':'Fictional launch targets next year','reason':'Name one finding'}]},{'unit_id':'analysis:next_tests','verdict':'pass','review_kind':'none','reason':'Pass','passage_ids':[],'editorial_repairs':[]}]};return items,review
 def test_only_exact_heading_changes_and_original_is_immutable(self):
  items,review=self.fixture();before=copy.deepcopy(items);result,key=derive_heading(items,review);self.assertEqual(key,'analysis:0');self.assertEqual(items,before);expected=copy.deepcopy(before);expected[key]['value']['heading']=review['decisions'][0]['editorial_repairs'][0]['after'];self.assertEqual(result,expected)
 def test_factual_mixed_quotes_body_and_unknown_unit_are_rejected(self):
  for field,value in [('review_kind','factual'),('review_kind','mixed'),('unit_id','analysis:opening'),('verdict','blocked'),('passage_ids',['Punknown'])]:
   items,review=self.fixture();review['decisions'][0][field]=value
   with self.subTest(field=field,value=value),self.assertRaises(ValueError):derive_heading(items,review)
  for path in [['text'],['quotes'],['citations']]:
   items,review=self.fixture();review['decisions'][0]['editorial_repairs'][0]['field_path']=path
   with self.assertRaises(ValueError):derive_heading(items,review)
 def test_stale_unbounded_empty_markup_and_multiline_heading_rejected(self):
  for value in ['', 'x'*201, 'Changed\nclaim','<b>Claim</b>', 'Two unrelated fictional findings',None]:
   items,review=self.fixture();review['decisions'][0]['editorial_repairs'][0]['after']=value
   with self.assertRaises(ValueError):derive_heading(items,review)
  items,review=self.fixture();review['decisions'][0]['editorial_repairs'][0]['before']='Stale'
  with self.assertRaises(ValueError):derive_heading(items,review)
 def test_no_missing_duplicate_reopened_or_second_revision(self):
  for change in ['missing','duplicate','reopen','second','passed_edits']:
   items,review=self.fixture()
   if change=='missing':review['decisions'].pop()
   if change=='duplicate':review['decisions'][1]=copy.deepcopy(review['decisions'][0])
   if change=='reopen':review['reopen']=['analysis:0']
   if change=='second':review['decisions'][1]['verdict']='revise'
   if change=='passed_edits':review['decisions'][1]['editorial_repairs']=[{'field_path':['text']}]
   with self.subTest(change=change),self.assertRaises(ValueError):derive_heading(items,review)

class HeadingProfileTests(unittest.TestCase):
 def test_exact_inherited_routes_and_spent_accounting_only(self):
  from research import earnings_inherited_profile_guard as g,earnings_file_pipeline as p
  v={'model_profile':None,'models':p.profile_models('original-file-review-routes-v1'),'preparation_version':g.HEADING_HANDLER,'spent_correction_rounds':2,'session_count':6};self.assertTrue(g.matches_heading(v,'original-file-review-routes-v1'))
  for key,value in [('model_profile','other'),('preparation_version',g.HANDLER),('spent_correction_rounds',1),('session_count',5),('models',{})]:
   bad=copy.deepcopy(v);bad[key]=value
   with self.assertRaises(ValueError):g.matches_heading(bad,'original-file-review-routes-v1')
