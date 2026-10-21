import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import earnings_prepared_turn_dedup as p,earnings_mixed_runner as b

def fixture():
 raw={'opening':'Fictional unchanged opening','findings':[{'section':'qa','text':'Fictional retained claim','quotes':[{'passage_id':'P-original'}],'citations':['turn-absent','turn-valid','D-retained']}]}
 candidate=copy.deepcopy(raw);candidate['findings'][0]['citations'][0]='turn-valid'
 targets=[{'field_path':['findings',0,'citations'],'position':0,'before_ids':raw['findings'][0]['citations'],'unknown_id':'turn-absent','allowed_turn_ids':['turn-valid','turn-other']}]
 return raw,candidate,targets
class TurnDedupTests(unittest.TestCase):
 def test_remove_only_inserted_duplicate_preserving_original_order_and_all_prose(self):
  args=fixture();before=copy.deepcopy(args);out=p.normalize(*args);self.assertEqual(args,before);self.assertEqual(out['findings'][0]['citations'],['turn-valid','D-retained']);expected=copy.deepcopy(args[0]);expected['findings'][0]['citations'].pop(0);self.assertEqual(out,expected)
 def test_no_prefix_inference_or_other_replacement(self):
  raw,v,t=fixture()
  for selected in ('turn-absent','turn-valid-prefix','turn-other','D-retained'):
   x=copy.deepcopy(v);x['findings'][0]['citations'][0]=selected
   with self.assertRaises(ValueError):p.normalize(raw,x,t)
 def test_prose_quotes_valid_reference_order_and_extra_changes_rejected(self):
  for change in ('prose','quote','order','extra','remove'):
   raw,v,t=fixture()
   if change=='prose':v['opening']='Changed'
   elif change=='quote':v['findings'][0]['quotes']=[]
   elif change=='order':v['findings'][0]['citations']=['turn-valid','D-retained','turn-valid']
   elif change=='extra':v['extra']='Forbidden'
   else:v['findings'][0]['citations'].pop(0)
   with self.assertRaises(ValueError):p.normalize(raw,v,t)
 def test_wrong_target_or_multiple_targets_rejected(self):
  raw,v,t=fixture()
  for bad in ([],t+t,[{**t[0],'position':1}],[{**t[0],'field_path':['opening_citations']}],[{**t[0],'allowed_turn_ids':[]}]):
   with self.assertRaises(ValueError):p.normalize(raw,v,bad)
 def test_manifest_round_trip_rejects_accounting_candidate_or_session_changes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);case=root/'case.json';case.write_text('{}');catalog={'passages':[]};path=root/'preparation.json';actual={'case_sha256':b.sha(case),'catalog_sha256':b.digest(catalog),'tokens':650001,'session_ids':['a','b','c'],'spent_correction_rounds':1,'content':p.normalize(*fixture()),'source_proposal_sha256':'a'*64}
   with patch.object(p,'replay',return_value=actual):
    v=p.prepare(root,case,path);self.assertEqual(p.verify(path,case,catalog)['tokens'],650001)
    for key,value in [('tokens',0),('session_ids',[]),('spent_correction_rounds',0),('content',{}),('source_proposal_sha256','b'*64)]:
     x=copy.deepcopy(v);x[key]=value;path.write_text(json.dumps(x))
     with self.assertRaises(ValueError):p.verify(path,case,catalog)
