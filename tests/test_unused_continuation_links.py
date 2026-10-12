import copy,unittest
from research.earnings_qa_grounding import prune_unused_continuations

class UnusedLinkTests(unittest.TestCase):
 def fixture(self):
  row={'exchange_id':'parent','answer_passage_ids':['Pparent'],'continuation_exchange_ids':['child'],'text':'Unchanged'}
  child={'exchange_id':'child','answer_passage_ids':['Pchild'],'continuation_exchange_ids':[],'grounding_status':'bound','text':'Actual continued answer'}
  g={'exchanges':[{'exchange_id':'parent','allowed_continuation_exchange_ids':['child']},{'exchange_id':'child','allowed_continuation_exchange_ids':[],'followup_of':'parent','flags':[],'answer_turn_ids':['answer'],'turns':[{'id':'answer','passage_ids':['Pchild']}]}]}
  return {'exchange_coverage':[row,child]},g
 def test_only_unused_link_removed_and_all_evidence_preserved(self):
  out,g=self.fixture();prior=copy.deepcopy(out);derived,audit=prune_unused_continuations(out,g)
  self.assertEqual(out,prior);self.assertEqual(derived['exchange_coverage'][0]['continuation_exchange_ids'],[])
  self.assertEqual(derived['exchange_coverage'][1],prior['exchange_coverage'][1])
  self.assertEqual(derived['exchange_coverage'][0]['answer_passage_ids'],['Pparent']);self.assertEqual(len(audit),1)
 def test_used_unresolved_or_wrong_parent_link_not_removed(self):
  for case in ('used','unresolved','wrong_parent','unsupported'):
   out,g=self.fixture()
   if case=='used':out['exchange_coverage'][0]['answer_passage_ids'].append('Pchild')
   if case=='unresolved':g['exchanges'][1]['flags']=['unknown_speaker_role']
   if case=='wrong_parent':g['exchanges'][1]['followup_of']='other'
   if case=='unsupported':out['exchange_coverage'][1]['answer_passage_ids']=['invented']
   derived,audit=prune_unused_continuations(out,g);self.assertEqual(derived,out);self.assertEqual(audit,[])
