"""Fictitious missing-review bindings; no private issuer data."""
import copy,unittest
from research import earnings_review_binding_recovery as m,earnings_mixed_runner as b
class BindingTests(unittest.TestCase):
 def fixture(self):
  items={'analysis:0':{'value':{'text':'Unchanged fictional operating statement'},'depends_on':[]},'analysis:1':{'value':{'text':'Other unchanged statement'},'depends_on':[]}}
  raw={'batch_sha256':b.digest(items),'decisions':[{'unit_id':'analysis:0','verdict':'revise','reason':'Fictional missing original evidence','passage_ids':[],'review_kind':'factual','editorial_repairs':[]},{'unit_id':'analysis:1','verdict':'pass','reason':'Supported','passage_ids':[],'review_kind':'none','editorial_repairs':[]}],'reopen':[]}
  cat={'passages':[{'passage_id':'Pabc','scope_id':'D001'},{'passage_id':'Pdef','scope_id':'D002'}]};proposal={'bindings':[{'unit_id':'analysis:0','passage_ids':['Pabc']}]};return raw,items,cat,proposal
 def test_only_missing_field_changes_original_immutable(self):
  r,i,c,p=self.fixture();before=copy.deepcopy(r);o=m.apply(r,i,c,p);self.assertEqual(r,before);o['decisions'][0]['passage_ids']=[];self.assertEqual(o,r)
 def test_unknown_prefix_financial_label_and_duplicate_rejected(self):
  r,i,c,p=self.fixture()
  for ids in [['Pab'],['F001'],['Pabc','Pabc'],[],['Pabc']*9]:
   x=copy.deepcopy(p);x['bindings'][0]['passage_ids']=ids
   with self.subTest(ids=ids),self.assertRaises(ValueError):m.apply(r,i,c,x)
 def test_no_prose_or_criteria_edit_and_wrong_unit(self):
  r,i,c,p=self.fixture()
  for mutate in [lambda x:x.update(review={}),lambda x:x['bindings'][0].update(reason='changed'),lambda x:x['bindings'][0].update(unit_id='analysis:1'),lambda x:x['bindings'].append(copy.deepcopy(x['bindings'][0]))]:
   x=copy.deepcopy(p);mutate(x)
   with self.assertRaises(ValueError):m.apply(r,i,c,x)
 def test_whole_decision_ledger_required(self):
  r,i,c,p=self.fixture()
  for mutate in [lambda x:x['decisions'].pop(),lambda x:x['decisions'].append(copy.deepcopy(x['decisions'][0])),lambda x:x.update(reopen=[{}]),lambda x:x.update(batch_sha256='changed')]:
   x=copy.deepcopy(r);mutate(x)
   with self.assertRaises(ValueError):m.targets(x,i,c)
 def test_unrelated_invalid_retained_decision_not_waived(self):
  r,i,c,p=self.fixture();r['decisions'][1].update(verdict='revise',review_kind='mixed',passage_ids=['Pabc'],editorial_repairs=[])
  with self.assertRaisesRegex(ValueError,'Unrelated'):m.targets(r,i,c)
 def test_nonfactual_empty_binding_not_eligible(self):
  r,i,c,p=self.fixture();r['decisions'][0]['review_kind']='mixed'
  with self.assertRaises(ValueError):m.targets(r,i,c)
 def test_two_missing_fields_both_required(self):
  r,i,c,p=self.fixture();r['decisions'][1].update(verdict='revise',review_kind='factual');p['bindings'].append({'unit_id':'analysis:1','passage_ids':['Pdef']});self.assertEqual(m.targets(r,i,c),['analysis:0','analysis:1']);self.assertEqual(m.apply(r,i,c,p)['decisions'][1]['passage_ids'],['Pdef'])
 def test_valid_existing_reference_cannot_be_rebound(self):
  r,i,c,p=self.fixture();r['decisions'][1].update(verdict='revise',review_kind='factual',passage_ids=['Pdef']);p['bindings'].append({'unit_id':'analysis:1','passage_ids':['Pabc']})
  with self.assertRaises(ValueError):m.apply(r,i,c,p)
if __name__=='__main__':unittest.main()
