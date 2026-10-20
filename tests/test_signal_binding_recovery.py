import copy,unittest
from research import earnings_signal_binding_recovery as h
class Contract(unittest.TestCase):
 def setUp(self):
  self.catalog={'passages':[{'passage_id':'P-a'},{'passage_id':'P-b'}]};self.pack={'report_sha256':'report','signals':[{'id':'signal-1','passage_ids':[],'direction':'conditional','citations':['section-a'],'summary':'Unchanged prose'},{'id':'signal-2','passage_ids':['P-b'],'direction':'unresolved'}]};self.proposal={'bindings':[{'signal_id':'signal-1','passage_ids':['P-a']}]}
 def test_exact_round_trip(self):
  before=copy.deepcopy(self.pack);out=h.apply(self.pack,self.catalog,self.proposal);self.assertEqual(self.pack,before);out['signals'][0]['passage_ids']=[];self.assertEqual(out,before)
 def test_rejections(self):
  bad=[{}, {'bindings':[]},{'bindings':self.proposal['bindings']*2},{'bindings':[{'signal_id':'signal-2','passage_ids':['P-a']}]},{'bindings':[{'signal_id':'signal-1','passage_ids':[]}]},{'bindings':[{'signal_id':'signal-1','passage_ids':['P-unknown']}]},{'bindings':[{'signal_id':'signal-1','passage_ids':['P-a','P-a']}]},{'bindings':[{'signal_id':'signal-1','passage_ids':['P-a'],'summary':'rewrite'}]},{**self.proposal,'direction':'improving'}]
  for proposal in bad:
   with self.subTest(proposal=proposal),self.assertRaises(ValueError):h.apply(self.pack,self.catalog,proposal)
 def test_unrelated_invalid_list_rejects(self):
  self.pack['signals'][1]['passage_ids']=['unknown']
  with self.assertRaises(ValueError):h.targets(self.pack,self.catalog)
 def test_duplicate_identity_rejects(self):
  self.pack['signals'][1]['id']='signal-1'
  with self.assertRaises(ValueError):h.targets(self.pack,self.catalog)
 def test_no_empty_field_rejects(self):
  self.pack['signals'][0]['passage_ids']=['P-a']
  with self.assertRaises(ValueError):h.targets(self.pack,self.catalog)

 def test_bad_proposal_identity_types_reject(self):
  for name in [None,[],{}]:
   with self.subTest(name=name),self.assertRaises(ValueError):h.apply(self.pack,self.catalog,{'bindings':[{'signal_id':name,'passage_ids':['P-a']}]})
 def test_no_hidden_source_or_direction_edits(self):
  for key in ['citations','direction','evidence_basis','finding_id','report_sha256','reason']:
   proposal=copy.deepcopy(self.proposal);proposal['bindings'][0][key]='rewrite'
   with self.subTest(key=key),self.assertRaises(ValueError):h.apply(self.pack,self.catalog,proposal)
 def test_selection_is_bounded(self):
  self.catalog={'passages':[{'passage_id':'P-'+str(i)}for i in range(9)]}
  with self.assertRaises(ValueError):h.apply(self.pack|{'signals':[self.pack['signals'][0]]},self.catalog,{'bindings':[{'signal_id':'signal-1','passage_ids':['P-'+str(i)for i in range(9)]}]})
