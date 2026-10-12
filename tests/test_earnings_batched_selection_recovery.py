import copy,unittest
from research import earnings_batched_selection_recovery as s

class SelectionRecoveryTests(unittest.TestCase):
 def fixture(self):
  ids=['D'+str(n) for n in range(24)];items={'retrieval':{'value':{'selected_document_ids':ids}}}
  plan={'changes':[{'unit_id':'retrieval','value':{'selected_document_ids':ids+['Dextra'],'document_findings':[{'text':'Fictional fact','citations':['Dextra']}],'quotes':['unchanged'],'exchange_coverage':['unchanged']}}]}
  return plan,items
 def test_restores_preparation_selection_and_preserves_every_citation(self):
  plan,items=self.fixture();before=copy.deepcopy(plan);resolved=s.derive(plan,items)
  self.assertEqual(plan,before)
  self.assertEqual(resolved['changes'][0]['value']['selected_document_ids'],items['retrieval']['value']['selected_document_ids'])
  for key in ('document_findings','quotes','exchange_coverage'):self.assertEqual(resolved['changes'][0]['value'][key],plan['changes'][0]['value'][key])
 def test_uncited_added_selection_reorder_or_multiple_additions_rejected(self):
  for change in ('uncited','reordered','multiple','original_short'):
   p,i=self.fixture();v=p['changes'][0]['value']
   if change=='uncited':v['document_findings'][0]['citations']=[]
   if change=='reordered':v['selected_document_ids'][0],v['selected_document_ids'][1]=v['selected_document_ids'][1],v['selected_document_ids'][0]
   if change=='multiple':v['selected_document_ids'].append('another')
   if change=='original_short':i['retrieval']['value']['selected_document_ids'].pop()
   with self.assertRaises(ValueError):s.derive(p,i)
